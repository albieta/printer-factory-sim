"""Unit tests for `CustomerOrderService`.

Exercises the three branches of `place_order` (immediate fulfilment,
backorder, validation) and the FIFO `auto_fulfil_backorders` flow.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.models import CustomerOrderStatus, EventType
from app.services.customer_order_service import CustomerOrderService
from app.services.event_service import EventService
from app.services.stock_service import StockService


def test_place_order_fulfils_from_stock(seeded_session: Session) -> None:
    service = CustomerOrderService(seeded_session)

    order = service.place_order("alice", "Basic300", 2, sim_day=1)
    seeded_session.commit()

    assert order.status == CustomerOrderStatus.FULFILLED
    assert order.fulfilled_day == 1
    assert order.unit_price == Decimal("650")
    assert order.total_price == Decimal("1300.00")
    assert StockService(seeded_session).get_quantity("Basic300") == 3

    placed_events = EventService(seeded_session).list(
        event_type=EventType.CUSTOMER_ORDER_PLACED
    )
    fulfilled_events = EventService(seeded_session).list(
        event_type=EventType.CUSTOMER_ORDER_FULFILLED
    )
    assert len(placed_events) == 1
    assert len(fulfilled_events) == 1


def test_place_order_backorders_when_stock_insufficient(seeded_session: Session) -> None:
    service = CustomerOrderService(seeded_session)

    # Elite700 has initial stock 1; ordering 5 must backorder.
    order = service.place_order("bob", "Elite700", 5, sim_day=2)
    seeded_session.commit()

    assert order.status == CustomerOrderStatus.BACKORDERED
    assert order.fulfilled_day is None
    assert order.status_reason is not None and "available 1" in order.status_reason
    assert StockService(seeded_session).get_quantity("Elite700") == 1  # untouched

    backorder_events = EventService(seeded_session).list(
        event_type=EventType.CUSTOMER_ORDER_BACKORDERED
    )
    assert len(backorder_events) == 1


def test_place_order_rejects_unknown_product(seeded_session: Session) -> None:
    service = CustomerOrderService(seeded_session)
    with pytest.raises(ValueError, match="Catalog has no entry"):
        service.place_order("carol", "Mystery9000", 1, sim_day=0)


def test_place_order_rejects_non_positive_quantity(seeded_session: Session) -> None:
    service = CustomerOrderService(seeded_session)
    with pytest.raises(ValueError, match="positive"):
        service.place_order("dave", "Basic300", 0, sim_day=0)


def test_cancel_order_moves_to_cancelled(seeded_session: Session) -> None:
    service = CustomerOrderService(seeded_session)

    # Backorder first; cancel afterwards.
    order = service.place_order("eve", "Elite700", 10, sim_day=1)
    seeded_session.commit()
    assert order.status == CustomerOrderStatus.BACKORDERED

    cancelled = service.cancel_order(order.id, sim_day=2)
    seeded_session.commit()
    assert cancelled.status == CustomerOrderStatus.CANCELLED

    cancel_events = EventService(seeded_session).list(
        event_type=EventType.CUSTOMER_ORDER_CANCELLED
    )
    assert len(cancel_events) == 1


def test_cancel_order_refuses_terminal_states(seeded_session: Session) -> None:
    service = CustomerOrderService(seeded_session)

    order = service.place_order("frank", "Basic300", 1, sim_day=1)
    seeded_session.commit()
    assert order.status == CustomerOrderStatus.FULFILLED

    with pytest.raises(ValueError, match="cannot be cancelled"):
        service.cancel_order(order.id, sim_day=2)


def test_auto_fulfil_backorders_satisfies_what_it_can(seeded_session: Session) -> None:
    co_service = CustomerOrderService(seeded_session)
    stock_service = StockService(seeded_session)

    # Elite700 stock = 1; create two backorders of qty 2 each.
    first_id = co_service.place_order("gina", "Elite700", 2, sim_day=1).id
    second_id = co_service.place_order("hank", "Elite700", 2, sim_day=1).id
    seeded_session.commit()

    # Restock by 2 — exactly one backorder can be satisfied (FIFO).
    # Total stock 1 + 2 = 3; first backorder needs 2; remainder 1 < 2.
    stock_service.add_stock("Elite700", 2, sim_day=2)
    seeded_session.commit()

    fulfilled = co_service.auto_fulfil_backorders(sim_day=2)
    seeded_session.commit()

    assert [o.id for o in fulfilled] == [first_id]

    refreshed_first = co_service.get_order(first_id)
    refreshed_second = co_service.get_order(second_id)
    assert refreshed_first is not None and refreshed_second is not None
    assert refreshed_first.status == CustomerOrderStatus.FULFILLED
    assert refreshed_first.fulfilled_day == 2
    assert refreshed_second.status == CustomerOrderStatus.BACKORDERED
    # 1 initial + 2 restock - 2 fulfilled = 1 remaining
    assert stock_service.get_quantity("Elite700") == 1

    backorder_fulfilled_events = EventService(seeded_session).list(
        event_type=EventType.BACKORDER_FULFILLED
    )
    assert len(backorder_fulfilled_events) == 1


def test_auto_fulfil_backorders_noop_when_stock_still_short(seeded_session: Session) -> None:
    co_service = CustomerOrderService(seeded_session)

    order = co_service.place_order("ian", "Elite700", 10, sim_day=1)
    seeded_session.commit()
    assert order.status == CustomerOrderStatus.BACKORDERED

    fulfilled = co_service.auto_fulfil_backorders(sim_day=2)
    assert fulfilled == []
    assert order.status == CustomerOrderStatus.BACKORDERED
