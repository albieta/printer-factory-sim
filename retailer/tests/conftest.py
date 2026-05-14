"""Shared pytest fixtures for the retailer test suite.

The retailer tests run against an in-memory SQLite database so they
never touch the developer's `retailer/retailer.db`. The `session`
fixture creates the schema on every test, and the `seeded_session`
fixture additionally loads the canonical seed file so we can exercise
the same catalog the Week 7 smoke scenario uses.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

for module_name in list(sys.modules):
    if module_name == "app" or module_name.startswith("app."):
        del sys.modules[module_name]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.models import (  # noqa: E402
    CatalogEntry,
    SimState,
    Stock,
)
from app.services.sim_state_service import CURRENT_DAY_KEY  # noqa: E402
from app.services.starter_profile import INITIAL_DAY, load_seed_data  # noqa: E402
from app.utils.database import Base  # noqa: E402


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _load_seed_into(session: Session, seed: dict[str, Any]) -> None:
    """Insert catalog entries, stock, and SimState from a seed dict."""

    for entry in seed["catalog"]:
        session.add(
            CatalogEntry(
                product_name=entry["product_name"],
                description=entry.get("description"),
                retail_price=entry["retail_price"],
            )
        )
        session.add(
            Stock(
                product_name=entry["product_name"],
                quantity=entry["initial_stock"],
            )
        )

    initial_day = seed.get("initial_day", INITIAL_DAY)
    session.add(SimState(key=CURRENT_DAY_KEY, value=str(initial_day)))
    session.commit()


@pytest.fixture()
def seeded_session(session: Session) -> Session:
    """Session pre-populated from `retailer/seed/seed-retailer.json`."""

    _load_seed_into(session, load_seed_data())
    return session
