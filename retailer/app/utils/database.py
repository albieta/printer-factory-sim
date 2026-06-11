"""SQLAlchemy bootstrap for the retailer app.

Mirrors `provider/app/utils/database.py` so a reader who knows one knows
the other. The retailer's data lives at `./retailer.db` next to the
working directory of whichever process started the app, unless overridden
via the `RETAILER_DB_URL` environment variable.

The env-var seam exists because Week 7's PRD (§4.5) requires the retailer
to be runnable as multiple instances on different ports and different
DB files. The CLI will set this variable per instance before importing
the app modules. Week 7 only exercises one instance, but the seam must
be there.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DEFAULT_DATABASE_URL = "sqlite:///./retailer.db"
DATABASE_URL = os.environ.get("RETAILER_DB_URL", DEFAULT_DATABASE_URL)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db_path() -> Path:
    """Absolute path to the retailer's SQLite database file.

    Only meaningful for the default `sqlite:///./retailer.db` URL.
    Returns the resolved path inside the `retailer/` package when the
    app is started from the `retailer/` directory, which is the
    convention used by `scripts/seed_data.py`.
    """

    return Path(__file__).resolve().parents[2] / "retailer.db"


def ensure_schema() -> None:
    """Create all tables declared on `Base` if they do not yet exist."""

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
