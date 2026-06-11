"""Unit tests for `StockService`."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.models import EventType
from app.services.event_service import EventService
from app.services.stock_service import StockService


def test_list_stock_returns_seeded_rows(seeded_session: Session) -> None:
    rows = StockService(seeded_session).list_stock()
    quantities = {row.product_name: row.quantity for row in rows}
    assert quantities == {"Basic300": 5, "Pro450": 3, "Elite700": 1}


def test_get_quantity_returns_zero_for_unknown_product(session: Session) -> None:
    assert StockService(session).get_quantity("DoesNotExist") == 0


def test_add_stock_increments_and_records_event(seeded_session: Session) -> None:
    service = StockService(seeded_session)

    service.add_stock("Basic300", 10, sim_day=3)
    seeded_session.commit()

    assert service.get_quantity("Basic300") == 15

    events = EventService(seeded_session).list(event_type=EventType.STOCK_ADDED)
    assert len(events) == 1
    assert events[0].sim_day == 3
    assert events[0].details == {
        "product_name": "Basic300",
        "delta": 10,
        "new_quantity": 15,
    }


def test_add_stock_creates_row_for_new_product(session: Session) -> None:
    service = StockService(session)

    service.add_stock("Newcomer", 7, sim_day=0)
    session.commit()

    assert service.get_quantity("Newcomer") == 7


def test_add_stock_rejects_non_positive(seeded_session: Session) -> None:
    service = StockService(seeded_session)
    with pytest.raises(ValueError, match="positive"):
        service.add_stock("Basic300", 0, sim_day=1)
    with pytest.raises(ValueError, match="positive"):
        service.add_stock("Basic300", -1, sim_day=1)


def test_consume_stock_decrements_and_records_event(seeded_session: Session) -> None:
    service = StockService(seeded_session)

    service.consume_stock("Basic300", 3, sim_day=2)
    seeded_session.commit()

    assert service.get_quantity("Basic300") == 2

    events = EventService(seeded_session).list(event_type=EventType.STOCK_CONSUMED)
    assert len(events) == 1
    assert events[0].details == {
        "product_name": "Basic300",
        "delta": -3,
        "new_quantity": 2,
    }


def test_consume_stock_refuses_to_go_negative(seeded_session: Session) -> None:
    service = StockService(seeded_session)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.consume_stock("Basic300", 999, sim_day=0)
