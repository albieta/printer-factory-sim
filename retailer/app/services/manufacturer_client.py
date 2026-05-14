"""HTTP wrapper around the manufacturer's REST API.

The retailer talks to the manufacturer for three things in Week 7:

- placing a sales order (`POST /api/sales/orders`),
- polling a sales order's status (`GET /api/sales/orders/{id}`),
- looking up the current wholesale price for a model
  (`GET /api/prices`).

Failures are normalised to `ManufacturerError` so callers do not need
to know about `httpx`-shaped exceptions. The one-shot 10 s timeout
mirrors the Week 6 manufacturer → provider contract (PRD-week6 §7).

Tests pass an `httpx.MockTransport` via the `transport` argument; the
default `None` makes the real `httpx.Client` open a network socket.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

import httpx


DEFAULT_TIMEOUT_SECONDS = 10.0


class ManufacturerError(RuntimeError):
    """Raised when the manufacturer returns an error or the network fails."""


class ManufacturerClient:
    """Synchronous HTTP client for the manufacturer's REST API."""

    def __init__(
        self,
        base_url: str,
        *,
        transport: Optional[httpx.BaseTransport] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def _client(self) -> httpx.Client:
        kwargs: dict[str, Any] = {"timeout": self._timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

    def create_sales_order(
        self, retailer_name: str, product_name: str, quantity: int
    ) -> dict[str, Any]:
        """POST /api/sales/orders; return the order dict from the response."""

        try:
            with self._client() as client:
                response = client.post(
                    f"{self.base_url}/api/sales/orders",
                    json={
                        "retailer": retailer_name,
                        "model": product_name,
                        "quantity": quantity,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ManufacturerError(
                f"Manufacturer rejected sales order: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ManufacturerError(f"Manufacturer request failed: {exc}") from exc

        payload = response.json()
        order = payload.get("order")
        if not isinstance(order, dict):
            raise ManufacturerError("Manufacturer response did not include an order object")
        return order

    def get_sales_order(self, order_id: int) -> dict[str, Any]:
        """GET /api/sales/orders/{id}; return the order dict from the response."""

        try:
            with self._client() as client:
                response = client.get(f"{self.base_url}/api/sales/orders/{order_id}")
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ManufacturerError(
                f"Manufacturer sales-order poll failed: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ManufacturerError(f"Manufacturer sales-order poll failed: {exc}") from exc

        payload = response.json()
        order = payload.get("order")
        if not isinstance(order, dict):
            raise ManufacturerError("Manufacturer response did not include an order object")
        return order

    def list_wholesale_prices(self) -> dict[str, Decimal]:
        """GET /api/prices; return `{model_name: wholesale_price}`."""

        try:
            with self._client() as client:
                response = client.get(f"{self.base_url}/api/prices")
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ManufacturerError(
                f"Manufacturer price lookup failed: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ManufacturerError(f"Manufacturer price lookup failed: {exc}") from exc

        payload = response.json()
        prices = payload.get("prices")
        if not isinstance(prices, dict):
            raise ManufacturerError("Manufacturer response did not include a prices dict")
        return {str(name): Decimal(str(price)) for name, price in prices.items()}

    def get_wholesale_price(self, product_name: str) -> Decimal:
        """Convenience: fetch one model's wholesale price."""

        prices = self.list_wholesale_prices()
        if product_name not in prices:
            raise ManufacturerError(
                f"Manufacturer has no wholesale price for {product_name!r}"
            )
        return prices[product_name]
