"""Shared pytest fixtures for the provider test suite.

The provider tests run against an in-memory SQLite database so they
never touch the developer's `provider/provider.db`. The `session`
fixture creates the schema on every test, and the `seeded_session`
fixture additionally loads the canonical seed file so we can exercise
the same catalogue the Week 6 five-day scenario uses.
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
    PricingTier,
    Product,
    SimState,
    Stock,
)
from app.services.starter_profile import (  # noqa: E402
    INITIAL_DAY,
    load_seed_data,
)
from app.services.sim_state_service import CURRENT_DAY_KEY  # noqa: E402
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
    """Insert products, pricing tiers, stock, and SimState from a seed dict."""

    for entry in seed["products"]:
        product = Product(
            name=entry["name"],
            description=entry.get("description"),
            lead_time_days=entry["lead_time_days"],
        )
        session.add(product)
        session.flush()

        for tier in entry["pricing"]:
            session.add(
                PricingTier(
                    product_id=product.id,
                    min_quantity=tier["min_qty"],
                    unit_price=tier["unit_price"],
                )
            )
        session.add(Stock(product_id=product.id, quantity=entry["initial_stock"]))

    initial_day = seed.get("initial_day", INITIAL_DAY)
    session.add(SimState(key=CURRENT_DAY_KEY, value=str(initial_day)))
    session.commit()


@pytest.fixture()
def seeded_session(session: Session) -> Session:
    """Session pre-populated from `provider/seed/seed-provider.json`."""

    _load_seed_into(session, load_seed_data())
    return session
