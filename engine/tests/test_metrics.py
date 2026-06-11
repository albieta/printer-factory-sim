from __future__ import annotations

import httpx

from engine.metrics import _retailer_snapshot


def test_retailer_snapshot_counts_customer_outcomes_from_events(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/stock":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/api/catalog":
            return httpx.Response(200, json={"entries": []})
        if request.url.path == "/api/purchases":
            return httpx.Response(200, json=[])
        if request.url.path == "/api/orders":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 1,
                        "placed_day": 4,
                        "fulfilled_day": 5,
                        "status": "FULFILLED",
                    }
                ],
            )
        if request.url.path == "/api/events":
            assert request.url.params["from_day"] == "4"
            assert request.url.params["to_day"] == "4"
            return httpx.Response(
                200,
                json=[
                    {"event_type": "CUSTOMER_ORDER_PLACED", "sim_day": 4},
                    {"event_type": "CUSTOMER_ORDER_BACKORDERED", "sim_day": 4},
                    {"event_type": "BACKORDER_FULFILLED", "sim_day": 4},
                ],
            )
        return httpx.Response(404, json={"detail": "not found"})

    real_init = httpx.Client.__init__

    def patched_init(self: httpx.Client, **kwargs) -> None:
        real_init(self, transport=httpx.MockTransport(handler), **{k: v for k, v in kwargs.items() if k != "transport"})

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)

    snapshot = _retailer_snapshot({"name": "PrinterWorld", "url": "http://retailer"}, day=5, logger=None)

    assert snapshot["customer_orders"]["placed_today"] == 1
    assert snapshot["customer_orders"]["backordered_today"] == 1
    assert snapshot["customer_orders"]["fulfilled_today"] == 1
