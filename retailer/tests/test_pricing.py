"""Unit tests for the pricing-floor maths.

The pricing module is pure — no DB, no HTTP — so we exercise it
directly with Decimal arithmetic.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.pricing import compute_floor, validate_retail_price


class TestComputeFloor:
    def test_default_markup_30_pct(self) -> None:
        assert compute_floor(Decimal("100.00"), 30) == Decimal("130.00")

    def test_floor_clamps_to_minimum_15_pct(self) -> None:
        # markup_pct = 5 is below the 15 % floor; effective markup is 15
        assert compute_floor(Decimal("100.00"), 5) == Decimal("115.00")

    def test_floor_quantizes_to_two_decimals(self) -> None:
        # 33.33 * 1.30 = 43.329 → 43.33
        assert compute_floor(Decimal("33.33"), 30) == Decimal("43.33")

    def test_floor_above_minimum_uses_configured_markup(self) -> None:
        assert compute_floor(Decimal("100.00"), 50) == Decimal("150.00")


class TestValidateRetailPrice:
    def test_passes_when_at_floor(self) -> None:
        validate_retail_price(Decimal("130.00"), Decimal("100.00"), 30)

    def test_passes_when_above_floor(self) -> None:
        validate_retail_price(Decimal("999.99"), Decimal("100.00"), 30)

    def test_raises_when_below_floor(self) -> None:
        with pytest.raises(ValueError, match="below the markup floor"):
            validate_retail_price(Decimal("129.99"), Decimal("100.00"), 30)

    def test_raises_on_non_positive_retail_price(self) -> None:
        with pytest.raises(ValueError, match="retail_price must be positive"):
            validate_retail_price(Decimal("0"), Decimal("100.00"), 30)

    def test_raises_on_non_positive_wholesale_price(self) -> None:
        with pytest.raises(ValueError, match="wholesale_price must be positive"):
            validate_retail_price(Decimal("130.00"), Decimal("0"), 30)

    def test_minimum_markup_15_pct_is_enforced(self) -> None:
        # The configured markup is 5 % but the floor effective markup is 15 %,
        # so a 1.10x price (10 % markup) is still rejected.
        with pytest.raises(ValueError, match="below the markup floor"):
            validate_retail_price(Decimal("110.00"), Decimal("100.00"), 5)

        # 1.15x clears the floor.
        validate_retail_price(Decimal("115.00"), Decimal("100.00"), 5)
