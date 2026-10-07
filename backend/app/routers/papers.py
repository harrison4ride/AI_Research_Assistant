"""Local paper library: save, browse, view, delete (F2)."""

import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Paper
from ..schemas import PaperMeta, PaperOut, SavedKey

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
    papers = list(db.scalars(select(Paper).order_by(Paper.created_at.desc(), Paper.id.desc())))
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
        select(Paper.source, Paper.external_id, Paper.id).where(Paper.external_id.is_not(None))
    )
    return [SavedKey(source=s, external_id=e, id=i) for s, e, i in rows]


@router.post("", response_model=PaperOut, status_code=status.HTTP_201_CREATED)
def save_paper(meta: PaperMeta, response: Response, db: Session = Depends(get_db)) -> Paper:
    """Save a search result. Saving a paper that is already saved returns that entry (200)."""
    if meta.source == "upload":
        raise HTTPException(422, "Use the upload endpoint to add PDF files.")
    if not meta.external_id:
        raise HTTPException(422, "external_id is required to save a search result.")

    if existing := find_duplicate(meta, db):
        response.status_code = status.HTTP_200_OK
        return existing

    paper = Paper(**meta.model_dump())
    db.add(paper)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request saved the same paper first.
        db.rollback()
        existing = find_duplicate(meta, db)
        if existing is None:
            raise
        response.status_code = status.HTTP_200_OK
        return existing
    db.refresh(paper)
    return paper


@router.get("/{paper_id}", response_model=PaperOut)
def get_paper(paper_id: int, db: Session = Depends(get_db)) -> Paper:
    return get_paper_or_404(paper_id, db)


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_paper(paper_id: int, db: Session = Depends(get_db)) -> Response:
    paper = get_paper_or_404(paper_id, db)
    db.delete(paper)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
