"""Pricing-floor maths for the retailer.

PRD-week7 §4.4 specifies:

    retail_price >= wholesale_price × (1 + markup_pct/100)

with a hard floor of `MINIMUM_MARKUP_PCT` (15 %). These are pure
functions — the wholesale price is looked up by the caller (today via
`ManufacturerClient.list_wholesale_prices`) and passed in.

Keeping the maths separate from the I/O makes this trivial to unit-test
without booting an HTTP server or seeding a database.
"""

from __future__ import annotations

from decimal import Decimal

from app.services.starter_profile import MINIMUM_MARKUP_PCT


def compute_floor(wholesale_price: Decimal, markup_pct: int) -> Decimal:
    """Return the minimum legal retail price for a given wholesale + markup.

    The effective markup is `max(markup_pct, MINIMUM_MARKUP_PCT)` — the
    configured markup may exceed the floor but never undershoot it.
    """

    effective_markup = max(markup_pct, MINIMUM_MARKUP_PCT)
    multiplier = Decimal(100 + effective_markup) / Decimal(100)
    return (wholesale_price * multiplier).quantize(Decimal("0.01"))


def validate_retail_price(
    retail_price: Decimal, wholesale_price: Decimal, markup_pct: int
) -> None:
    """Raise `ValueError` if `retail_price` is below the markup floor.

    The caller catches the `ValueError` and converts it into the
    surface-appropriate error (HTTP 400 from the API layer, non-zero
    exit from the CLI).
    """

    if retail_price <= 0:
        raise ValueError("retail_price must be positive")
    if wholesale_price <= 0:
        raise ValueError("wholesale_price must be positive")

    floor = compute_floor(wholesale_price, markup_pct)
    if retail_price < floor:
        raise ValueError(
            f"retail_price {retail_price} is below the markup floor {floor} "
            f"(wholesale {wholesale_price}, markup {max(markup_pct, MINIMUM_MARKUP_PCT)}%)"
        )
