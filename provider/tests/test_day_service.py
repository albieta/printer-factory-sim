"""Unit tests for the provider's day-advance service."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import Event, EventType, OrderStatus
from app.services.catalog_service import CatalogService
from app.services.day_service import DayService
from app.services.order_service import OrderService
from app.services.sim_state_service import SimStateService


def _control_board_id(session: Session) -> int:
    product = CatalogService(session).get_product_by_name("Control Board")
    assert product is not None
    return product.id


def test_advance_increments_current_day_and_writes_summary_event(seeded_session: Session) -> None:
    summary = DayService(seeded_session).advance()

    assert summary["previous_day"] == 0
    assert summary["current_day"] == 1
    assert SimStateService(seeded_session).get_current_day() == 1

    last = (
        seeded_session.query(Event)
        .filter(Event.event_type == EventType.DAY_ADVANCED)
        .order_by(Event.id.desc())
        .first()
    )
    assert last is not None
    assert last.sim_day == 1


def test_advance_ships_pending_orders_with_full_lifecycle_audit(seeded_session: Session) -> None:
    product_id = _control_board_id(seeded_session)
    sim = SimStateService(seeded_session)
    sim.set_current_day(1)
    seeded_session.commit()

    order = OrderService(seeded_session).create_order(
        buyer="manufacturer", product_id=product_id, quantity=50
    )
    assert order.status is OrderStatus.PENDING

    DayService(seeded_session).advance()
    seeded_session.refresh(order)

    assert order.status is OrderStatus.SHIPPED
    assert order.shipped_day == 2

    types_for_order = [
        event.event_type
        for event in seeded_session.query(Event)
        .filter(Event.entity_id == order.id, Event.entity_type == "order")
        .order_by(Event.id)
        .all()
    ]
    # ORDER_PLACED was written at creation; advance writes the lifecycle.
    assert EventType.ORDER_CONFIRMED in types_for_order
    assert EventType.ORDER_IN_PROGRESS in types_for_order
    assert EventType.ORDER_SHIPPED in types_for_order


def test_shipped_orders_deliver_on_expected_day(seeded_session: Session) -> None:
    product_id = _control_board_id(seeded_session)
    sim = SimStateService(seeded_session)
    sim.set_current_day(1)
    seeded_session.commit()

    order = OrderService(seeded_session).create_order(
        buyer="manufacturer", product_id=product_id, quantity=50
    )
    # Control Board lead_time = 2 -> expected_delivery_day = 1 + 2 = 3.
    assert order.expected_delivery_day == 3

    day = DayService(seeded_session)
    day.advance()  # day 2: ships
    seeded_session.refresh(order)
    assert order.status is OrderStatus.SHIPPED

    day.advance()  # day 3: due -> delivered
    seeded_session.refresh(order)
    assert order.status is OrderStatus.DELIVERED
    assert order.delivered_day == 3


def test_advance_does_not_touch_rejected_orders(seeded_session: Session) -> None:
    product_id = _control_board_id(seeded_session)
    rejected = OrderService(seeded_session).create_order(
        buyer="manufacturer", product_id=product_id, quantity=10_000_000
    )
    assert rejected.status is OrderStatus.REJECTED

    DayService(seeded_session).advance()
    seeded_session.refresh(rejected)

    assert rejected.status is OrderStatus.REJECTED
    assert rejected.shipped_day is None
    assert rejected.delivered_day is None


def test_summary_counts_ships_and_deliveries(seeded_session: Session) -> None:
    product_id = _control_board_id(seeded_session)
    OrderService(seeded_session).create_order(
        buyer="manufacturer", product_id=product_id, quantity=10
    )
    OrderService(seeded_session).create_order(
        buyer="manufacturer", product_id=product_id, quantity=20
    )

    summary = DayService(seeded_session).advance()
    assert summary["orders_shipped"] == 2
    assert summary["orders_delivered"] == 0

    # Both orders deliver on day = 0 + lead_time(2) = 2. Advance to day 2.
    summary = DayService(seeded_session).advance()  # day 2
    assert summary["orders_shipped"] == 0
    assert summary["orders_delivered"] == 2
