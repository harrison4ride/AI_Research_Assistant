"""Getting a paper's full text: storing uploaded PDFs and downloading open-access ones."""

import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from ..config import get_settings
from ..models import Paper
from . import pdf
from .http import get_client

log = logging.getLogger(__name__)

# One download per paper at a time (e.g. page load + summarize clicked together).
# Entries are reference-counted and removed when unused.
_locks: dict[int, tuple[asyncio.Lock, int]] = {}


@asynccontextmanager
async def _paper_lock(paper_id: int) -> AsyncIterator[None]:
    lock, users = _locks.get(paper_id, (asyncio.Lock(), 0))
    _locks[paper_id] = (lock, users + 1)
    try:
        async with lock:
            yield
    finally:
        lock, users = _locks[paper_id]
        if users <= 1:
            del _locks[paper_id]
        else:
            _locks[paper_id] = (lock, users - 1)


class TooLarge(Exception):
    pass


def looks_like_pdf(data: bytes) -> bool:
    # The header may be preceded by a little junk; PDF readers tolerate up to 1 KB.
    return b"%PDF-" in data[:1024]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_pdf(data: bytes) -> str:
    """Save PDF bytes under a content hash and return the file name. Blocking."""
    name = f"{sha256(data)}.pdf"
    pdf_dir = get_settings().pdf_dir
    pdf_dir.mkdir(parents=True, exist_ok=True)
    path = pdf_dir / name
    if not path.exists():
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    return name


def remove_pdf_if_unused(name: str | None, db: Session) -> None:
    """Delete a stored PDF unless another library entry still points at it."""
    if name and not db.scalar(select(Paper.id).where(Paper.pdf_path == name).limit(1)):
        (get_settings().pdf_dir / name).unlink(missing_ok=True)


async def attach_pdf(paper: Paper, data: bytes, extracted: pdf.ExtractedPdf, db: Session) -> None:
    """Store a PDF and its text on an existing library entry.

    Raises StaleDataError if the paper was deleted concurrently (the stored file
    is cleaned up first).
    """
    old_path = paper.pdf_path
    new_path = await run_in_threadpool(store_pdf, data)
    paper.pdf_path = new_path
    paper.full_text = extracted.text
    paper.page_count = extracted.page_count
    paper.full_text_status = "ok"
    paper.full_text_error = None
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        remove_pdf_if_unused(new_path, db)
        raise
    if old_path != new_path:
        remove_pdf_if_unused(old_path, db)


async def _download(url: str) -> bytes:
    limit = get_settings().max_pdf_mb * 1024 * 1024
    async with get_client().stream("GET", url, timeout=60.0) as resp:
        resp.raise_for_status()
        chunks, size = [], 0
        async for chunk in resp.aiter_bytes():
            size += len(chunk)
            if size > limit:
                raise TooLarge
            chunks.append(chunk)
    return b"".join(chunks)


def _still_exists(paper_id: int, db: Session) -> bool:
    # The user may delete the paper while its PDF is downloading.
    return db.scalar(select(Paper.id).where(Paper.id == paper_id)) is not None


async def ensure_full_text(paper: Paper, db: Session, retry: bool = False) -> bool:
    """Download and extract the paper's PDF if that hasn't been done yet.

    Expected failures are recorded in full_text_status/error (so the UI can
    explain why only the abstract is available) rather than raised. Returns
    False if the paper was deleted in the meantime.
    """
    paper_id = paper.id
    async with _paper_lock(paper_id):
        if not _still_exists(paper_id, db):
            return False
        db.refresh(paper)
        if paper.full_text_status == "ok":
            return True
        if paper.full_text_status is not None and not retry:
            return True

        status, error, data, extracted = "error", None, None, None
        if not paper.pdf_url:
            status, error = "unavailable", "No open-access PDF link is known for this paper."
        else:
            try:
                data = await _download(paper.pdf_url)
                if not looks_like_pdf(data):
                    error = "The PDF link led to a web page instead of a PDF file."
                else:
                    extracted = await run_in_threadpool(pdf.extract, data)
            except TooLarge:
                error = f"The PDF is larger than {get_settings().max_pdf_mb} MB."
            except httpx.HTTPStatusError as exc:
                error = f"The PDF link returned HTTP {exc.response.status_code}."
            except httpx.HTTPError as exc:
                log.warning("PDF download failed for paper %s: %r", paper_id, exc)
                error = "The PDF could not be downloaded."
            except pdf.PdfError as exc:
                error = str(exc)

        if not _still_exists(paper_id, db):
            return False
        try:
            if extracted is not None and data is not None:
                await attach_pdf(paper, data, extracted, db)
            else:
                paper.full_text_status = status
                paper.full_text_error = error
                db.commit()
        except StaleDataError:  # deleted between the check and the commit
            db.rollback()
            return False
        return True
