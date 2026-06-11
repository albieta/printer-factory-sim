"""Tests for the provider data model and seed loader.

Covers Week 6 milestone #2:

- the SQLAlchemy schema can be created end-to-end on an in-memory SQLite
  database and populated with one of every entity,
- the shipped seed file validates,
- the seed file covers every raw material referenced by the
  manufacturer's BOM, so the Week 6 scenario can run without manual
  fixup,
- the seed validator catches malformed input before any DB writes
  happen.
"""

from __future__ import annotations

import copy
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.models import (  # noqa: E402
    Event,
    EventType,
    Order,
    OrderStatus,
    PricingTier,
    Product,
    SimState,
    Stock,
)
from app.services.starter_profile import (  # noqa: E402
    SCHEMA_VERSION,
    load_seed_data,
)
from app.utils.database import Base  # noqa: E402
from scripts.seed_data import validate_seed  # noqa: E402


# Materials the manufacturer's BOM uses; the provider must sell every one
# of these so the Week 6 five-day scenario can run end-to-end without
# manual stitching of catalogues.
MANUFACTURER_BOM_MATERIALS = {
    "PLA Filament",
    "ABS Filament",
    "Aluminum Frame",
    "Stepper Motor",
    "Control Board",
    "LCD Screen",
}


@pytest.fixture()
def session():
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


def test_schema_supports_full_provider_round_trip(session):
    product = Product(
        name="Control Board",
        description="Main printer controller PCB",
        lead_time_days=3,
    )
    session.add(product)
    session.flush()

    session.add_all(
        [
            PricingTier(product_id=product.id, min_quantity=1, unit_price=Decimal("40.00")),
            PricingTier(product_id=product.id, min_quantity=20, unit_price=Decimal("32.00")),
            PricingTier(product_id=product.id, min_quantity=200, unit_price=Decimal("25.00")),
            Stock(product_id=product.id, quantity=500),
            Order(
                buyer="manufacturer",
                product_id=product.id,
                quantity=50,
                unit_price=Decimal("32.00"),
                total_price=Decimal("1600.00"),
                placed_day=1,
                expected_delivery_day=4,
                status=OrderStatus.PENDING,
            ),
            Event(
                event_type=EventType.ORDER_PLACED,
                sim_day=1,
                entity_type="order",
                entity_id=1,
                details={"buyer": "manufacturer", "quantity": 50},
            ),
            SimState(key="current_day", value="0"),
        ]
    )
    session.commit()

    persisted = session.query(Product).filter_by(name="Control Board").one()
    assert persisted.lead_time_days == 3
    assert len(persisted.pricing_tiers) == 3
    assert persisted.stock.quantity == 500
    assert [tier.min_quantity for tier in persisted.pricing_tiers] == [1, 20, 200]

    order = session.query(Order).one()
    assert order.product is persisted
    assert order.status is OrderStatus.PENDING
    assert order.expected_delivery_day - order.placed_day >= 1  # ironclad rule

    sim_state = session.query(SimState).filter_by(key="current_day").one()
    assert sim_state.value == "0"


def test_shipped_seed_file_validates():
    seed = load_seed_data()

    assert seed["schema_version"] == SCHEMA_VERSION
    validate_seed(seed)  # must not raise


def test_seed_covers_every_manufacturer_bom_material():
    seed = load_seed_data()
    seed_names = {entry["name"] for entry in seed["products"]}

    missing = MANUFACTURER_BOM_MATERIALS - seed_names
    assert not missing, (
        f"Provider seed is missing materials referenced by the manufacturer BOM: {missing}. "
        "The Week 6 scenario expects the provider to sell every BOM material."
    )


def test_validator_rejects_lead_time_below_one():
    seed = copy.deepcopy(load_seed_data())
    seed["products"][0]["lead_time_days"] = 0

    with pytest.raises(ValueError, match="lead_time_days"):
        validate_seed(seed)


def test_validator_rejects_pricing_not_starting_at_one():
    seed = copy.deepcopy(load_seed_data())
    seed["products"][0]["pricing"] = [
        {"min_qty": 10, "unit_price": 32.00},
        {"min_qty": 200, "unit_price": 25.00},
    ]

    with pytest.raises(ValueError, match="min_qty=1"):
        validate_seed(seed)


def test_validator_rejects_wrong_schema_version():
    seed = copy.deepcopy(load_seed_data())
    seed["schema_version"] = SCHEMA_VERSION + 99

    with pytest.raises(ValueError, match="schema_version"):
        validate_seed(seed)


def test_validator_rejects_missing_required_field():
    seed = copy.deepcopy(load_seed_data())
    del seed["products"][0]["pricing"]

    with pytest.raises(ValueError, match="pricing"):
        validate_seed(seed)
