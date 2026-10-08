"""Local paper library: save, browse, view, delete (F2)."""

import logging
import re
import unicodedata
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from ..config import get_settings
from ..db import get_db
from ..models import Paper
from ..schemas import OutlineOut, PaperDetail, PaperMeta, PaperOut, PaperUpdate, SavedKey
from ..services import arxiv, llm, pdf
from ..services.fulltext import (
    attach_pdf,
    ensure_full_text,
    paper_lock,
    looks_like_pdf,
    remove_pdf_if_unused,
    sha256,
    store_pdf,
)
from ..services.http import UpstreamError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/papers", tags=["library"])

# DataCite DOIs that arXiv assigns to every preprint, e.g. 10.48550/arXiv.1706.03762.
ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.(.+)$", re.IGNORECASE)


def _fold(text: str) -> str:
    """Unicode-aware case folding (SQLite's lower() only handles ASCII)."""
    return unicodedata.normalize("NFKC", text).casefold()


def _matches(paper: Paper, needle: str) -> bool:
    return (
        needle in _fold(paper.title)
        or needle in _fold(paper.abstract or "")
        or any(needle in _fold(author) for author in paper.authors or [])
    )


def get_paper_or_404(paper_id: int, db: Session) -> Paper:
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paper not found.")
    return paper


def find_duplicate(meta: PaperMeta, db: Session) -> Paper | None:
    """Find the same paper already saved, possibly from a different source.

    Matches on (source, external_id), on DOI, and on arXiv id vs. arXiv DOI so
    that saving a paper from arXiv and then from OpenAlex doesn't create two rows.
    """
    conditions = [(Paper.source == meta.source) & (Paper.external_id == meta.external_id)]
    dois = set()
    if meta.doi:
        dois.add(meta.doi.lower())
        if m := ARXIV_DOI_RE.match(meta.doi):
            conditions.append((Paper.source == "arxiv") & (Paper.external_id == m.group(1)))
    if meta.source == "arxiv" and meta.external_id:
        dois.add(f"10.48550/arxiv.{meta.external_id}".lower())
    if dois:
        conditions.append(func.lower(Paper.doi).in_(dois))
    return db.scalar(select(Paper).where(or_(*conditions)).order_by(Paper.id).limit(1))


@router.get("", response_model=list[PaperOut])
def list_papers(
    q: str | None = Query(None, max_length=200, description="Filter by title, author, or abstract"),
    db: Session = Depends(get_db),
) -> list[Paper]:
    papers = list(db.scalars(
        select(Paper)
        .where(Paper.in_library.is_(True))
        .order_by(func.coalesce(Paper.saved_at, Paper.created_at).desc(), Paper.id.desc())
    ))
    # A personal library is small, so filtering in Python is fast and gets
    # Unicode case-insensitivity right.
    if q and q.strip():
        needle = _fold(q.strip())
        papers = [p for p in papers if _matches(p, needle)]
    return papers


@router.get("/keys", response_model=list[SavedKey])
def saved_keys(db: Session = Depends(get_db)) -> list[SavedKey]:
    """Identities of saved search results, so the search page can mark them as saved."""
    rows = db.execute(
        select(Paper.source, Paper.external_id, Paper.id).where(
            Paper.external_id.is_not(None), Paper.in_library.is_(True)
        )
    )
    return [SavedKey(source=s, external_id=e, id=i) for s, e, i in rows]


def _get_or_create(meta: PaperMeta, db: Session, *, save: bool) -> tuple[Paper, bool]:
    """The library entry for a search result, created if needed. Returns (paper, created).

    `save=True` puts it in the library (and promotes an unsaved copy that was
    only opened before, keeping its chat and outline); `save=False` only opens
    it for reading, leaving it out of the library.
    """
    if meta.source == "upload":
        raise HTTPException(422, "Use the upload endpoint to add PDF files.")
    if not meta.external_id:
        raise HTTPException(422, "external_id is required for a search result.")
    now = datetime.now(timezone.utc)

    def reuse(existing: Paper) -> tuple[Paper, bool]:
        if save:
            if not existing.in_library:
                existing.in_library, existing.saved_at = True, now
        else:
            existing.last_opened_at = now
        db.commit()
        db.refresh(existing)
        return existing, False

    if existing := find_duplicate(meta, db):
        return reuse(existing)
    paper = Paper(**meta.model_dump(), in_library=save, saved_at=now if save else None, last_opened_at=now)
    db.add(paper)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request created the same paper first.
        db.rollback()
        existing = find_duplicate(meta, db)
        if existing is None:
            raise
        return reuse(existing)
    db.refresh(paper)
    return paper, True


@router.post("", response_model=PaperOut, status_code=status.HTTP_201_CREATED)
def save_paper(meta: PaperMeta, response: Response, db: Session = Depends(get_db)) -> Paper:
    """Save a search result to the library (200 with the existing entry if already there)."""
    paper, created = _get_or_create(meta, db, save=True)
    if not created:
        response.status_code = status.HTTP_200_OK
    return paper


@router.post("/open", response_model=PaperOut, status_code=status.HTTP_201_CREATED)
def open_paper(meta: PaperMeta, response: Response, db: Session = Depends(get_db)) -> Paper:
    """Open a search result in the reader without saving it to the library."""
    paper, created = _get_or_create(meta, db, save=False)
    if not created:
        response.status_code = status.HTTP_200_OK
    return paper


async def _arxiv_metadata(extracted: pdf.ExtractedPdf) -> PaperMeta | None:
    """Authoritative metadata for an arXiv PDF, if its id is stamped on page 1."""
    if not extracted.arxiv_id:
        return None
    try:
        meta = await arxiv.fetch_by_id(extracted.arxiv_id)
    except UpstreamError as exc:
        log.info("arXiv lookup for %s failed: %s", extracted.arxiv_id, exc)
        return None
    # Guard against an id that came from a citation rather than this paper.
    if meta and pdf.title_on_page(meta.title, extracted.first_page):
        return meta
    return None


async def _read_pdf_upload(file: UploadFile) -> tuple[bytes, pdf.ExtractedPdf]:
    """Read an uploaded file, check it is a PDF within the size limit, and extract it."""
    limit = get_settings().max_pdf_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"The file is larger than {get_settings().max_pdf_mb} MB.")
    if not looks_like_pdf(data):
        raise HTTPException(415, "The file is not a PDF.")
    try:
        extracted = await run_in_threadpool(pdf.extract, data)
    except pdf.PdfError as exc:
        raise HTTPException(422, str(exc)) from exc
    return data, extracted


def _merge_llm_metadata(paper: Paper, found: llm.ExtractedMetadata, extracted: pdf.ExtractedPdf) -> None:
    """Prefer the LLM's reading over the heuristics, if its title really is on the first pages.

    A title that isn't in the text means the answer can't be trusted, so then
    none of its fields are used.
    """
    if not (found.title.strip() and pdf.title_on_page(found.title, extracted.text[:15000])):
        return
    paper.title = found.title.strip()
    authors = [a.strip() for a in found.authors if a.strip()]
    if authors:
        paper.authors = authors
    if found.year is not None:
        paper.year = found.year
    if found.abstract and len(found.abstract.strip()) >= 100:
        paper.abstract = found.abstract.strip()


@router.post("/upload", response_model=PaperOut, status_code=status.HTTP_201_CREATED)
async def upload_pdf(
    response: Response,
    file: UploadFile = File(..., description="A research paper in PDF format"),
    db: Session = Depends(get_db),
) -> Paper:
    """Add an uploaded PDF to the library, extracting its text and metadata (F3)."""
    data, extracted = await _read_pdf_upload(file)

    # Identical files map to the same entry.
    digest = await run_in_threadpool(sha256, data)
    if existing := db.scalar(select(Paper).where(Paper.source == "upload", Paper.external_id == digest)):
        response.status_code = status.HTTP_200_OK
        return existing

    fallback_title = (file.filename or "Untitled PDF").removesuffix(".pdf").removesuffix(".PDF")
    paper = Paper(
        source="upload",
        in_library=True,
        saved_at=datetime.now(timezone.utc),
        external_id=digest,
        title=extracted.title or fallback_title,
        authors=extracted.authors,
        year=extracted.year,
        abstract=extracted.abstract,
        page_count=extracted.page_count,
        full_text=extracted.text,
        full_text_status="ok",
    )
    if meta := await _arxiv_metadata(extracted):
        paper.title = meta.title
        paper.authors = meta.authors
        paper.year = meta.year
        paper.abstract = meta.abstract
        paper.url = meta.url
        paper.venue = meta.venue
        paper.doi = meta.doi
    elif found := await llm.extract_metadata(extracted.text[:15000]):
        _merge_llm_metadata(paper, found, extracted)

    # Store the file last, once nothing that could fail is left before the commit.
    paper.pdf_path = await run_in_threadpool(store_pdf, data)

    db.add(paper)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # the same file was uploaded concurrently
        existing = db.scalar(select(Paper).where(Paper.source == "upload", Paper.external_id == digest))
        if existing is None:
            raise
        response.status_code = status.HTTP_200_OK
        return existing
    db.refresh(paper)
    return paper


@router.get("/{paper_id}", response_model=PaperDetail)
def get_paper(paper_id: int, db: Session = Depends(get_db)) -> Paper:
    paper = get_paper_or_404(paper_id, db)
    if not paper.in_library:
        # Keeps it from being pruned. A single UPDATE (not an ORM flush) so a
        # concurrent delete simply matches no row.
        db.execute(
            update(Paper)
            .where(Paper.id == paper_id, Paper.in_library.is_(False))
            .values(last_opened_at=datetime.now(timezone.utc))
        )
        db.commit()
    return paper


@router.post("/{paper_id}/save", response_model=PaperDetail)
def save_existing(paper_id: int, db: Session = Depends(get_db)) -> Paper:
    """Add a paper that was only opened for reading to the library."""
    paper = get_paper_or_404(paper_id, db)
    if not paper.in_library:
        paper.in_library, paper.saved_at = True, datetime.now(timezone.utc)
    db.commit()
    db.refresh(paper)
    return paper


@router.get("/{paper_id}/outline", response_model=OutlineOut)
async def get_outline(paper_id: int, db: Session = Depends(get_db)) -> OutlineOut:
    """The paper's sections (from its PDF), with one-sentence summaries once generated."""
    paper = get_paper_or_404(paper_id, db)
    if not await ensure_full_text(paper, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paper not found.")
    return await ensure_outline(paper, db)


async def ensure_outline(paper: Paper, db: Session) -> OutlineOut:
    """Read the section structure from the stored PDF the first time it is needed.

    One extraction per paper at a time; if the PDF is replaced meanwhile, the
    result is dropped instead of being stored for the wrong file.
    """
    async with paper_lock(paper.id):
        db.refresh(paper)
        if paper.outline is None:
            pdf_path = paper.pdf_path
            path = get_settings().pdf_dir / pdf_path if pdf_path else None
            if path is None or not path.is_file():
                return OutlineOut(available=False, reason="The outline needs the paper's PDF.")
            try:
                entries = await run_in_threadpool(lambda: pdf.extract_outline(path.read_bytes()))
            except pdf.PdfError as exc:
                return OutlineOut(available=False, reason=str(exc))
            db.refresh(paper)
            if paper.pdf_path != pdf_path:
                raise HTTPException(409, "The paper's PDF changed while it was being read. Try again.")
            paper.outline = [
                {"level": e.level, "title": e.title, "page": e.page, "top": round(e.top, 4), "summary": None}
                for e in entries
            ]
            db.commit()
    return outline_out(paper)


def outline_out(paper: Paper) -> OutlineOut:
    return OutlineOut(
        available=True,
        sections=paper.outline or [],
        summarized=paper.outline_summarized_at is not None,
        model=paper.outline_model,
        summarized_at=paper.outline_summarized_at,
    )


@router.patch("/{paper_id}", response_model=PaperDetail)
def update_paper(paper_id: int, update: PaperUpdate, db: Session = Depends(get_db)) -> Paper:
    """Correct a paper's metadata (title, authors, year, abstract)."""
    paper = get_paper_or_404(paper_id, db)
    for field, value in update.model_dump(exclude_unset=True).items():
        if field == "title" and value is None:
            raise HTTPException(422, "title must not be null")
        if field == "authors" and value is None:
            value = []  # the column is a non-null list
        setattr(paper, field, value)
    db.commit()
    db.refresh(paper)
    return paper


@router.post("/{paper_id}/fulltext", response_model=PaperOut)
async def fetch_full_text(
    paper_id: int, retry: bool = False, db: Session = Depends(get_db)
) -> Paper:
    """Download and extract the paper's open-access PDF so the LLM can read it."""
    paper = get_paper_or_404(paper_id, db)
    if not await ensure_full_text(paper, db, retry=retry):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paper not found.")
    return paper


@router.post("/{paper_id}/pdf", response_model=PaperOut)
async def attach_pdf_file(
    paper_id: int,
    file: UploadFile = File(..., description="The paper's PDF"),
    db: Session = Depends(get_db),
) -> Paper:
    """Attach a PDF to an existing entry (e.g. a search result without an open-access PDF)."""
    paper = get_paper_or_404(paper_id, db)
    data, extracted = await _read_pdf_upload(file)
    try:
        await attach_pdf(paper, data, extracted, db)
    except StaleDataError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paper not found.") from None
    db.refresh(paper)
    return paper


@router.get("/{paper_id}/pdf")
def get_pdf(paper_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """Serve the locally stored PDF (uploaded or downloaded)."""
    paper = get_paper_or_404(paper_id, db)
    path = get_settings().pdf_dir / paper.pdf_path if paper.pdf_path else None
    if path is None or not path.is_file():
        raise HTTPException(404, "No local PDF for this paper.")
    return FileResponse(path, media_type="application/pdf", content_disposition_type="inline")


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_paper(paper_id: int, db: Session = Depends(get_db)) -> Response:
    paper = get_paper_or_404(paper_id, db)
    pdf_path = paper.pdf_path
    db.delete(paper)
    db.commit()
    # PDFs are stored by content hash, so another entry may share the file.
    remove_pdf_if_unused(pdf_path, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
