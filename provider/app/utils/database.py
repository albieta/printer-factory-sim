"""SQLAlchemy bootstrap for the provider app.

Mirrors `manufacturer/backend/app/utils/database.py` so a reader who knows
one knows the other. The provider stores its data in `provider.db`,
written next to the working directory of whichever process started the
app (CLI or FastAPI server). Both are gitignored via `*.db`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DATABASE_URL = "sqlite:///./provider.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db_path() -> Path:
    """Absolute path to the provider's SQLite database file.

    Useful for tests that want to assert the file exists or to remove it
    between runs. The file lives at `provider/provider.db` when the app
    is started from the `provider/` directory, which is the convention.
    """

    return Path(__file__).resolve().parents[2] / "provider.db"


def ensure_schema() -> None:
    """Create all tables declared on `Base` if they do not yet exist.

    No ALTER-style migrations are needed yet; the provider has no shipped
    schema in production. If/when a migration is needed, follow the
    manufacturer's pattern in its `database.py`.
    """

    # Import models for their side effect of registering with `Base`.
    from app.models import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def bootstrap_database() -> None:
    """Idempotent startup hook: ensure the schema is in place."""

    ensure_schema()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped SQLAlchemy session."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
