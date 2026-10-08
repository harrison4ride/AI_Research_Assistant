"""SQLite database setup (SQLAlchemy 2.x)."""

import json
import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


settings = get_settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
DB_PATH = settings.data_dir / "app.db"

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    # FastAPI runs sync endpoints in a thread pool.
    connect_args={"check_same_thread": False},
    # Keep non-ASCII text (author names, titles) readable in JSON columns.
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_connection, _record) -> None:
    # SQLite ignores FOREIGN KEY / ON DELETE CASCADE unless this is set per connection.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db() -> None:
    """Create tables, and add any nullable columns a newer model defines.

    This stands in for a migration tool: later milestones add columns, and an
    existing library database should keep working without being deleted.
    """
    from . import models  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                if not column.nullable:
                    # SQLite can't add a NOT NULL column without a default; fail at
                    # startup instead of on the first insert.
                    raise RuntimeError(
                        f"Database schema is out of date: cannot add required column "
                        f"{table.name}.{column.name}. Delete {DB_PATH} to recreate it."
                    )
                col_type = column.type.compile(engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))
                log.info("Added column %s.%s", table.name, column.name)
        # Papers saved before the reader existed are all library papers, saved when created.
        conn.execute(text("UPDATE papers SET in_library = 1 WHERE in_library IS NULL"))
        conn.execute(text("UPDATE papers SET saved_at = created_at WHERE in_library = 1 AND saved_at IS NULL"))


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
