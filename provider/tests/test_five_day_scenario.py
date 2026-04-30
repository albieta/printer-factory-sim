"""Provider-side rehearsal of the Week 6 five-day scenario.

The full scenario in `docs/PRD-week6.md` §8 spans both apps and is gated
on the manufacturer's outbound integration that will land in a later
milestone. This test drives only the provider half — the order
placement, the lifecycle, and the day-by-day advance — exactly as a
buyer would see it through the REST API. It is the regression gate for
the provider's behaviour by itself.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.models import OrderStatus, Stock
from app.services.catalog_service import CatalogService
from app.services.day_service import DayService
from app.services.order_service import OrderService
from app.services.sim_state_service import SimStateService


def test_provider_half_of_five_day_scenario(seeded_session: Session) -> None:
    sim = SimStateService(seeded_session)
    catalog = CatalogService(seeded_session)
    day = DayService(seeded_session)
    orders = OrderService(seeded_session)

    # Setup: day 0, the seed stocks 500 Control Boards.
    assert sim.get_current_day() == 0
    control_board = catalog.get_product_by_name("Control Board")
    assert control_board is not None
    assert seeded_session.query(Stock).filter_by(product_id=control_board.id).one().quantity == 500

    # Day 1: advance, then place a 50-unit order. Tier-20 price applies.
    day.advance()
    assert sim.get_current_day() == 1

    order = orders.create_order(
        buyer="manufacturer", product_id=control_board.id, quantity=50
    )
    assert order.status is OrderStatus.PENDING
    assert order.placed_day == 1
    assert order.expected_delivery_day == 4
    assert order.unit_price == Decimal("32.00")
    assert order.total_price == Decimal("1600.00")

    # Day 2: advance — order ships.
    day.advance()
    seeded_session.refresh(order)
    assert order.status is OrderStatus.SHIPPED
    assert order.shipped_day == 2

    # Day 3: advance — still in flight.
    day.advance()
    seeded_session.refresh(order)
    assert order.status is OrderStatus.SHIPPED
    assert order.delivered_day is None

    # Day 4: advance — order delivers.
    day.advance()
    seeded_session.refresh(order)
    assert order.status is OrderStatus.DELIVERED
    assert order.delivered_day == 4
    assert sim.get_current_day() == 4

    # Stock decremented once at placement, never twice.
    remaining = seeded_session.query(Stock).filter_by(product_id=control_board.id).one().quantity
    assert remaining == 500 - 50
