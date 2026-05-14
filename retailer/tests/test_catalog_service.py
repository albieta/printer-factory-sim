"""Unit tests for `CatalogService`.

Wholesale-price lookup is mocked out because it lives in
`ManufacturerClient`; the catalog service only consumes the resulting
Decimal.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.models import EventType
from app.services.catalog_service import CatalogService
from app.services.event_service import EventService


def test_list_catalog_returns_seeded_entries(seeded_session: Session) -> None:
    entries = CatalogService(seeded_session).list_catalog()
    names = [e.product_name for e in entries]
    assert names == ["Basic300", "Elite700", "Pro450"]


def test_get_retail_price_returns_seeded_value(seeded_session: Session) -> None:
    assert CatalogService(seeded_session).get_retail_price("Basic300") == Decimal("650")


def test_get_retail_price_raises_on_unknown_product(session: Session) -> None:
    with pytest.raises(ValueError, match="Catalog has no entry"):
        CatalogService(session).get_retail_price("Nonexistent")


def test_set_retail_price_above_floor_succeeds(seeded_session: Session) -> None:
    service = CatalogService(seeded_session)

    # Wholesale = 450, markup_pct = 30 → floor = 585. 700 is above.
    service.set_retail_price(
        "Basic300",
        Decimal("700.00"),
        wholesale_price=Decimal("450.00"),
        markup_pct=30,
        sim_day=2,
    )
    seeded_session.commit()

    assert service.get_retail_price("Basic300") == Decimal("700.00")

    events = EventService(seeded_session).list(event_type=EventType.PRICE_CHANGED)
    assert len(events) == 1
    details = events[0].details
    assert details is not None
    assert details["product_name"] == "Basic300"
    assert details["new_price"] == "700.00"
    assert details["wholesale_reference"] == "450.00"
    assert details["markup_pct"] == 30


def test_set_retail_price_rejects_below_floor(seeded_session: Session) -> None:
    service = CatalogService(seeded_session)

    with pytest.raises(ValueError, match="below the markup floor"):
        service.set_retail_price(
            "Basic300",
            Decimal("500.00"),  # below floor of 585
            wholesale_price=Decimal("450.00"),
            markup_pct=30,
            sim_day=1,
        )

    # Price unchanged.
    assert service.get_retail_price("Basic300") == Decimal("650")


def test_set_retail_price_rejects_unknown_product(session: Session) -> None:
    with pytest.raises(ValueError, match="Catalog has no entry"):
        CatalogService(session).set_retail_price(
            "Nonexistent",
            Decimal("999.00"),
            wholesale_price=Decimal("100.00"),
            markup_pct=30,
            sim_day=0,
        )
