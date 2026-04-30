"""Quantity-break pricing for the provider's catalogue.

A `Product` carries an ordered list of `PricingTier` rows of the form
`(min_quantity, unit_price)`. For an order of size `q`, the applicable
tier is the one with the largest `min_quantity` that is still `<= q` —
i.e., the deepest discount the buyer qualifies for. The seed validator
guarantees a tier with `min_quantity == 1`, so any positive quantity has
a defined price.
"""

from __future__ import annotations

from decimal import Decimal

from app.models.models import Product


def calculate_unit_price(product: Product, quantity: int) -> Decimal:
    """Return the unit price `product` charges for `quantity` units.

    Raises `ValueError` for non-positive quantities or for a product
    whose tiers do not cover the requested size (which would be a seed
    error).
    """

    if quantity <= 0:
        raise ValueError(f"quantity must be positive, got {quantity}")

    applicable = [tier for tier in product.pricing_tiers if tier.min_quantity <= quantity]
    if not applicable:
        raise ValueError(
            f"No pricing tier matches quantity {quantity} for product "
            f"{product.name!r}; tiers must start at min_quantity=1."
        )

    best = max(applicable, key=lambda tier: tier.min_quantity)
    # `unit_price` is a SQL DECIMAL — already a Decimal in Python.
    return Decimal(best.unit_price)
