"""ORM models for the local paper library."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text, TypeDecorator, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Stores UTC and returns timezone-aware datetimes.

    SQLite has no timezone support and hands back naive datetimes, which the API
    would then serialize without an offset (and browsers would read as local time).
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


class Paper(Base):
    __tablename__ = "papers"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_paper_source_external_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20))  # arxiv | openalex | upload
    external_id: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[list[str]] = mapped_column(JSON, default=list)
    year: Mapped[int | None] = mapped_column(Integer)
    abstract: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    pdf_url: Mapped[str | None] = mapped_column(Text)
    venue: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
