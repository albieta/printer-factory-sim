"""Unit tests for the quantity-break pricing helper."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.models import PricingTier, Product
from app.services.pricing import calculate_unit_price


def _product_with_tiers(session: Session, tiers: list[tuple[int, str]]) -> Product:
    product = Product(name="Test Part", lead_time_days=3)
    session.add(product)
    session.flush()
    for min_qty, price in tiers:
        session.add(
            PricingTier(
                product_id=product.id,
                min_quantity=min_qty,
                unit_price=Decimal(price),
            )
        )
    session.flush()
    session.refresh(product)
    return product


def test_picks_lowest_tier_when_quantity_just_meets_first_break(session: Session) -> None:
    product = _product_with_tiers(session, [(1, "40.00"), (20, "32.00"), (200, "25.00")])

    assert calculate_unit_price(product, 1) == Decimal("40.00")
    assert calculate_unit_price(product, 19) == Decimal("40.00")


def test_picks_middle_tier_at_threshold_and_above(session: Session) -> None:
    product = _product_with_tiers(session, [(1, "40.00"), (20, "32.00"), (200, "25.00")])

    assert calculate_unit_price(product, 20) == Decimal("32.00")
    assert calculate_unit_price(product, 50) == Decimal("32.00")
    assert calculate_unit_price(product, 199) == Decimal("32.00")


def test_picks_top_tier_at_and_above_largest_break(session: Session) -> None:
    product = _product_with_tiers(session, [(1, "40.00"), (20, "32.00"), (200, "25.00")])

    assert calculate_unit_price(product, 200) == Decimal("25.00")
    assert calculate_unit_price(product, 9999) == Decimal("25.00")


def test_rejects_non_positive_quantity(session: Session) -> None:
    product = _product_with_tiers(session, [(1, "10.00")])

    with pytest.raises(ValueError, match="quantity must be positive"):
        calculate_unit_price(product, 0)
    with pytest.raises(ValueError, match="quantity must be positive"):
        calculate_unit_price(product, -5)


def test_rejects_product_whose_tiers_do_not_start_at_one(session: Session) -> None:
    product = _product_with_tiers(session, [(50, "10.00")])

    with pytest.raises(ValueError, match="No pricing tier matches"):
        calculate_unit_price(product, 10)
