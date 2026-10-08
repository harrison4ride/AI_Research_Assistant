"""Clean-up of papers that were opened from search but never saved."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from ..config import get_settings
from ..db import SessionLocal
from ..models import Paper
from .fulltext import remove_pdf_if_unused

log = logging.getLogger(__name__)


def prune_cached_papers() -> int:
    """Delete unsaved papers (with their chats and PDFs) not opened for CACHED_PAPER_DAYS."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=get_settings().cached_paper_days)
    removed = 0
    still_stale = (
        Paper.in_library.is_(False),
        func.coalesce(Paper.last_opened_at, Paper.created_at) < cutoff.replace(tzinfo=None),
    )
    with SessionLocal() as db:
        candidates = db.execute(select(Paper.id, Paper.pdf_path).where(*still_stale)).all()
        for paper_id, pdf_path in candidates:
            # Re-check in the DELETE itself: the paper may have been saved or
            # reopened since it was selected. Chat messages go with it (FK cascade).
            deleted = db.execute(delete(Paper).where(Paper.id == paper_id, *still_stale)).rowcount
            db.commit()
            if deleted:
                remove_pdf_if_unused(pdf_path, db)
                removed += deleted
    if removed:
        log.info("Removed %d unsaved paper(s) not opened for %d days", removed, get_settings().cached_paper_days)
    return removed
