"""Integration tests for the turn engine — stubs only (no claude --print).

Uses httpx.MockTransport so no real network is needed; all three apps are
mocked as minimal HTTP responders.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from engine.demand import generate_customer_demand, get_day_signal
from engine.agent_runner import run_agent


SMOKE_SCENARIO: dict[str, Any] = {
    "scenario_name": "smoke-test",
    "base_demand": {"mean": 2, "variance": 0},
    "events": [
        {"name": "normal", "start_day": 1, "end_day": 10, "demand_modifier": 1.0},
    ],
}

SMOKE_CONFIG: dict[str, Any] = {
    "retailers": [{"name": "PrinterWorld", "url": "http://retailer", "path": ".", "skill": None}],
    "manufacturer": {"name": "Factory", "url": "http://manufacturer", "path": ".", "skill": None},
    "providers": [{"name": "ChipSupply Co", "url": "http://provider", "path": ".", "skill": None}],
}


# ── agent_runner unit tests ───────────────────────────────────────────────────

def test_stub_agent_returns_marker(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    output = run_agent("retailer", 1, "unused prompt", skill_file=None)
    assert "[stub]" in output
    assert "retailer" in output


def test_stub_agent_writes_log_file(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    run_agent("manufacturer", 3, "prompt", skill_file=None)
    log = tmp_path / "logs" / "day-003-manufacturer.log"
    assert log.exists()
    assert "[stub]" in log.read_text()


# ── demand + signal integration ───────────────────────────────────────────────

def test_smoke_scenario_day1_produces_orders() -> None:
    signal = get_day_signal(SMOKE_SCENARIO, 1)
    prices = {"Basic300": 650.0, "Pro450": 1200.0, "Elite700": 2000.0}
    orders = generate_customer_demand(1, signal, prices, prices)
    # mean=2, variance=0 → exactly 2 orders per model → 6 total
    assert len(orders) == 6
    models = {m for m, _ in orders}
    assert models == {"Basic300", "Pro450", "Elite700"}


def test_smoke_scenario_all_days_deterministic() -> None:
    prices = {"Basic300": 650.0}
    for day in range(1, 4):
        signal = get_day_signal(SMOKE_SCENARIO, day)
        a = generate_customer_demand(day, signal, prices, prices)
        b = generate_customer_demand(day, signal, prices, prices)
        assert a == b, f"Day {day} not deterministic"


# ── run_day with mock HTTP ────────────────────────────────────────────────────

def _make_mock_app() -> httpx.MockTransport:
    """A minimal mock that handles catalog, orders POST, and day/advance."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/catalog":
            return httpx.Response(
                200,
                json={
                    "entries": [
                        {"product_name": "Basic300", "retail_price": "650.00"},
                    ]
                },
            )
        if path == "/api/orders" and request.method == "POST":
            payload = json.loads(request.content.decode())
            if set(payload) != {"customer", "product_name", "quantity"}:
                return httpx.Response(422, json={"detail": "invalid order payload"})
            return httpx.Response(201, json={"id": "co-001", "status": "PENDING"})
        if path == "/api/day/advance" and request.method == "POST":
            return httpx.Response(200, json={"current_day": 1, "purchase_orders_delivered": 0})
        return httpx.Response(404, json={"detail": "not found"})

    return httpx.MockTransport(handler)


def test_run_day_returns_summary_with_expected_keys(tmp_path: Any, monkeypatch: Any) -> None:
    """run_day returns a dict with day, signal, demand_injected, agent_outputs,
    and advance_results even with stub agents."""

    monkeypatch.chdir(tmp_path)

    real_client_init = httpx.Client.__init__

    def patched_init(self: httpx.Client, **kwargs: Any) -> None:
        real_client_init(self, transport=_make_mock_app(), **{
            k: v for k, v in kwargs.items() if k != "transport"
        })

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)

    from engine.turn_engine import run_day

    result = run_day(SMOKE_CONFIG, SMOKE_SCENARIO, day=1)

    assert result["day"] == 1
    assert "signal" in result
    assert "demand_injected" in result
    assert "agent_outputs" in result
    assert "advance_results" in result
    assert "PrinterWorld" in result["advance_results"]
    assert "Factory" in result["advance_results"]
    assert "ChipSupply Co" in result["advance_results"]
    retailer_orders = result["demand_injected"][0]
    assert retailer_orders
    assert all("result" in order for order in retailer_orders)


# ── scenario configuration tests ──────────────────────────────────────

def test_apply_scenario_config_with_assembly_and_costs() -> None:
    """Verify that apply_scenario_config correctly extracts and prepares payload."""
    from engine.turn_engine import apply_scenario_config
    
    scenario = {
        "scenario_name": "test-scenario",
        "recommended_assembly": {
            "assembly_lines": 3,
            "workers_per_line": 2,
            "shift_hours": 10.0,
        },
        "recommended_costs": {
            "cost_per_assembly_line": 75000,
            "cost_per_worker_per_hour": 60,
            "max_workers_per_line": 15,
        }
    }
    
    # Mock transport to capture the PUT request
    captured_request = {}
    
    def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/config/" and request.method == "PUT":
            captured_request["payload"] = json.loads(request.content.decode())
            return httpx.Response(200, json={
                "assembly_lines": 3,
                "workers_per_line": 2,
                "shift_hours": 10.0,
                "cost_per_assembly_line": 75000,
                "cost_per_worker_per_hour": 60,
                "max_workers_per_line": 15,
            })
        return httpx.Response(404, json={"detail": "not found"})
    
    transport = httpx.MockTransport(mock_handler)
    
    with httpx.Client(transport=transport) as client:
        # Temporarily patch the client for this test
        import engine.turn_engine as engine_module
        original_client = engine_module.httpx.Client
        
        try:
            def mock_client_context(*args, **kwargs):
                return client
            
            # Monkey-patch the _put function's client creation
            real_put = engine_module._put
            
            def mock_put(url: str, payload: dict[str, Any], logger = None) -> dict[str, Any]:
                if "/api/config/" in url:
                    response = client.put(url, json=payload)
                    return dict(response.json())
                return {}
            
            engine_module._put = mock_put
            
            result = apply_scenario_config("http://manufacturer", scenario)
            
            # Verify the result
            assert result.get("assembly_lines") == 3
            assert result.get("workers_per_line") == 2
            assert result.get("shift_hours") == 10.0
            assert result.get("cost_per_assembly_line") == 75000
            assert result.get("cost_per_worker_per_hour") == 60
            assert result.get("max_workers_per_line") == 15
        finally:
            engine_module._put = real_put


def test_scenario_config_with_defaults() -> None:
    """Verify that apply_scenario_config handles scenarios with only assembly."""
    from engine.turn_engine import apply_scenario_config
    
    scenario = {
        "scenario_name": "test-assembly-only",
        "recommended_assembly": {
            "assembly_lines": 2,
        }
    }
    
    def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/config/" and request.method == "PUT":
            return httpx.Response(200, json={"assembly_lines": 2})
        return httpx.Response(404, json={"detail": "not found"})
    
    transport = httpx.MockTransport(mock_handler)
    
    with httpx.Client(transport=transport) as client:
        import engine.turn_engine as engine_module
        real_put = engine_module._put
        
        def mock_put(url: str, payload: dict[str, Any], logger = None) -> dict[str, Any]:
            if "/api/config/" in url:
                response = client.put(url, json=payload)
                return dict(response.json())
            return {}
        
        engine_module._put = mock_put
        
        try:
            result = apply_scenario_config("http://manufacturer", scenario)
            assert result.get("assembly_lines") == 2
        finally:
            engine_module._put = real_put
