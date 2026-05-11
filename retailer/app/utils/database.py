"""SQLAlchemy bootstrap for the retailer app.

Unlike the provider's module-level singleton, the retailer's engine is
initialized at runtime from a config file. This lets multiple retailer
instances run in the same Python process (or at least in separate
processes pointing at separate databases) without any code change.

Call `init_db(db_path)` once at startup — from the CLI callback or the
FastAPI lifespan — before touching any session.
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker[Session]] = None


def init_db(db_path: str | Path) -> None:
    """Create the SQLAlchemy engine for the given SQLite file path.

    Creates parent directories if they do not yet exist so a fresh install
    only needs the config file, not a pre-existing directory tree.
    """
    global _engine, _SessionLocal
    resolved = Path(db_path).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{resolved}"
    _engine = create_engine(url, connect_args={"check_same_thread": False}, echo=False)
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def ensure_schema() -> None:
    """Create all tables declared on `Base` if they do not yet exist."""
    from app.models import models  # noqa: F401

    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    Base.metadata.create_all(bind=_engine)


def bootstrap_database(db_path: str | Path) -> None:
    """Idempotent startup hook: initialize engine and create schema."""
    init_db(db_path)
    ensure_schema()


def get_session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped SQLAlchemy session."""
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()
