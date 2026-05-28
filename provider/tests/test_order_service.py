"""Unit tests for the provider's order-placement service."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.models import Event, EventType, OrderStatus, Stock
from app.services.catalog_service import CatalogService
from app.services.order_service import (
    OrderError,
    OrderService,
    ProductNotFoundError,
)
from app.services.sim_state_service import SimStateService


def _control_board_id(session: Session) -> int:
    product = CatalogService(session).get_product_by_name("Control Board")
    assert product is not None
    return product.id


def test_create_order_picks_tier_price_and_computes_total(seeded_session: Session) -> None:
    product_id = _control_board_id(seeded_session)
    SimStateService(seeded_session).set_current_day(1)
    seeded_session.commit()

    order = OrderService(seeded_session).create_order(
        buyer="manufacturer", product_id=product_id, quantity=50
    )

    assert order.status is OrderStatus.PENDING
    assert order.unit_price == Decimal("32.00")  # tier-20 break
    assert order.total_price == Decimal("1600.00")
    assert order.placed_day == 1
    assert order.expected_delivery_day == 3  # ironclad rule: 1 + lead_time(2)


def test_create_order_decrements_stock_and_writes_audit_events(seeded_session: Session) -> None:
    product_id = _control_board_id(seeded_session)
    initial_stock = seeded_session.query(Stock).filter_by(product_id=product_id).one().quantity

    OrderService(seeded_session).create_order(
        buyer="manufacturer", product_id=product_id, quantity=50
    )

    remaining = seeded_session.query(Stock).filter_by(product_id=product_id).one().quantity
    assert remaining == initial_stock - 50

    event_types = {event.event_type for event in seeded_session.query(Event).all()}
    assert EventType.ORDER_PLACED in event_types
    assert EventType.STOCK_CONSUMED in event_types
    assert EventType.ORDER_REJECTED not in event_types


def test_insufficient_stock_yields_rejected_order_without_decrementing(
    seeded_session: Session,
) -> None:
    product_id = _control_board_id(seeded_session)
    initial_stock = seeded_session.query(Stock).filter_by(product_id=product_id).one().quantity

    order = OrderService(seeded_session).create_order(
        buyer="manufacturer", product_id=product_id, quantity=initial_stock + 1
    )

    assert order.status is OrderStatus.REJECTED
    assert order.status_reason is not None
    assert "insufficient stock" in order.status_reason

    stock_after = seeded_session.query(Stock).filter_by(product_id=product_id).one().quantity
    assert stock_after == initial_stock  # no reservation on a rejected order

    event_types = {event.event_type for event in seeded_session.query(Event).all()}
    assert EventType.ORDER_PLACED in event_types
    assert EventType.ORDER_REJECTED in event_types
    assert EventType.STOCK_CONSUMED not in event_types


def test_unknown_product_id_raises(seeded_session: Session) -> None:
    with pytest.raises(ProductNotFoundError):
        OrderService(seeded_session).create_order(
            buyer="manufacturer", product_id=999_999, quantity=1
        )


def test_non_positive_quantity_raises(seeded_session: Session) -> None:
    product_id = _control_board_id(seeded_session)

    with pytest.raises(OrderError, match="quantity must be positive"):
        OrderService(seeded_session).create_order(
            buyer="manufacturer", product_id=product_id, quantity=0
        )
    with pytest.raises(OrderError, match="quantity must be positive"):
        OrderService(seeded_session).create_order(
            buyer="manufacturer", product_id=product_id, quantity=-1
        )


def test_blank_buyer_raises(seeded_session: Session) -> None:
    product_id = _control_board_id(seeded_session)

    with pytest.raises(OrderError, match="buyer must"):
        OrderService(seeded_session).create_order(
            buyer="   ", product_id=product_id, quantity=1
        )


def test_expected_delivery_day_honours_ironclad_rule(seeded_session: Session) -> None:
    product_id = _control_board_id(seeded_session)
    SimStateService(seeded_session).set_current_day(7)
    seeded_session.commit()

    order = OrderService(seeded_session).create_order(
        buyer="manufacturer", product_id=product_id, quantity=5
    )

    # Control Board has lead_time_days=2 -> 7 + 2 = 9. Never sooner than placed + 1.
    assert order.expected_delivery_day == 9
    assert order.expected_delivery_day - order.placed_day >= 1


def test_list_orders_filters_by_status(seeded_session: Session) -> None:
    product_id = _control_board_id(seeded_session)
    service = OrderService(seeded_session)
    service.create_order(buyer="manufacturer", product_id=product_id, quantity=10)
    service.create_order(
        buyer="manufacturer", product_id=product_id, quantity=10_000_000
    )  # rejected

    pending = service.list_orders(status=OrderStatus.PENDING)
    rejected = service.list_orders(status=OrderStatus.REJECTED)

    assert len(pending) == 1
    assert len(rejected) == 1
    assert pending[0].status is OrderStatus.PENDING
    assert rejected[0].status is OrderStatus.REJECTED
