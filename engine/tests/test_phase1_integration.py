"""Phase 1 integration test — deterministic 2-day run, all stubs.

Mocks all three apps' HTTP surfaces via httpx.MockTransport routed through
per-app ASGI TestClients.  No real network or real databases are used.

This is the acceptance gate for PRD-week7 §10.1 (Phase 1 plumbing).
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from engine.turn_engine import run_day, main


# ── shared fixtures ───────────────────────────────────────────────────────────

STUB_SCENARIO: dict[str, Any] = {
    "scenario_name": "phase1-smoke",
    "base_demand": {"mean": 2, "variance": 0},
    "events": [
        {"name": "normal", "start_day": 1, "end_day": 10, "demand_modifier": 1.0},
    ],
}

STUB_CONFIG: dict[str, Any] = {
    "retailers": [
        {"name": "PrinterWorld", "url": "http://retailer", "path": ".", "skill": None}
    ],
    "manufacturer": {
        "name": "Factory",
        "url": "http://manufacturer",
        "path": ".",
        "skill": None,
    },
    "providers": [
        {"name": "ChipSupply Co", "url": "http://provider", "path": ".", "skill": None}
    ],
}


def _mock_transport() -> httpx.MockTransport:
    """Minimal transport: catalog + orders + day/advance for all three apps."""

    _day_counter: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        path = request.url.path
        method = request.method

        if path == "/api/catalog":
            return httpx.Response(
                200,
                json={
                    "entries": [
                        {"product_name": "Basic300", "retail_price": "650.00"},
                        {"product_name": "Elite700", "retail_price": "2000.00"},
                    ]
                },
            )

        if path == "/api/orders" and method == "POST":
            payload = json.loads(request.content.decode())
            if set(payload) != {"customer", "product_name", "quantity"}:
                return httpx.Response(422, json={"detail": "invalid order payload"})
            return httpx.Response(
                201,
                json={"id": f"co-{host}-001", "status": "PENDING"},
            )

        if path == "/api/day/advance" and method == "POST":
            _day_counter[host] = _day_counter.get(host, 0) + 1
            return httpx.Response(
                200,
                json={"current_day": _day_counter[host], "purchase_orders_delivered": 0},
            )

        return httpx.Response(404, json={"detail": "not found"})

    return httpx.MockTransport(handler)


def _patch_httpx(monkeypatch: Any, transport: httpx.MockTransport) -> None:
    """Route all httpx.Client calls through the mock transport."""

    real_init = httpx.Client.__init__

    def patched_init(self: httpx.Client, **kwargs: Any) -> None:
        real_init(self, transport=transport, **{k: v for k, v in kwargs.items() if k != "transport"})

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)


# ── tests ─────────────────────────────────────────────────────────────────────

def test_two_day_run_advances_all_apps(tmp_path: Any, monkeypatch: Any) -> None:
    """Each day's advance_results must include all three roles."""

    monkeypatch.chdir(tmp_path)
    _patch_httpx(monkeypatch, _mock_transport())

    day1 = run_day(STUB_CONFIG, STUB_SCENARIO, day=1)
    day2 = run_day(STUB_CONFIG, STUB_SCENARIO, day=2)

    for day_result in (day1, day2):
        assert "PrinterWorld" in day_result["advance_results"]
        assert "Factory" in day_result["advance_results"]
        assert "ChipSupply Co" in day_result["advance_results"]

    assert day1["day"] == 1
    assert day2["day"] == 2


def test_two_day_run_creates_stub_log_files(tmp_path: Any, monkeypatch: Any) -> None:
    """Stub agents must write a log file for every role on every day."""

    monkeypatch.chdir(tmp_path)
    _patch_httpx(monkeypatch, _mock_transport())

    for day in (1, 2):
        run_day(STUB_CONFIG, STUB_SCENARIO, day=day)

    logs_dir = tmp_path / "logs"
    assert logs_dir.is_dir()

    expected_logs = [
        "day-001-PrinterWorld.log",
        "day-001-Factory.log",
        "day-001-ChipSupply Co.log",
        "day-002-PrinterWorld.log",
        "day-002-Factory.log",
        "day-002-ChipSupply Co.log",
    ]
    for name in expected_logs:
        log_file = logs_dir / name
        assert log_file.exists(), f"Missing log file: {name}"
        assert "[stub]" in log_file.read_text()


def test_demand_injected_for_each_day(tmp_path: Any, monkeypatch: Any) -> None:
    """demand_injected should be non-empty when catalog returns models."""

    monkeypatch.chdir(tmp_path)
    _patch_httpx(monkeypatch, _mock_transport())

    result = run_day(STUB_CONFIG, STUB_SCENARIO, day=1)
    injected = result["demand_injected"]

    assert len(injected) == 1  # one retailer
    retailer_orders = injected[0]
    # mean=2, variance=0 → 2 orders per model (Basic300 + Elite700) = 4 total
    assert len(retailer_orders) == 4
    assert all("result" in order for order in retailer_orders)


def test_agent_outputs_truncated_in_summary(tmp_path: Any, monkeypatch: Any) -> None:
    """Agent output stored in summary is ≤ 200 characters (truncated for log size)."""

    monkeypatch.chdir(tmp_path)
    _patch_httpx(monkeypatch, _mock_transport())

    result = run_day(STUB_CONFIG, STUB_SCENARIO, day=1)

    for role, output in result["agent_outputs"].items():
        assert len(output) <= 200, f"Output for {role!r} exceeds 200 chars in summary"


def test_main_entry_point_bad_args() -> None:
    """main() returns non-zero exit code when argument count is wrong."""

    code = main([])
    assert code != 0

    code = main(["only_one_arg"])
    assert code != 0


def test_main_entry_point_missing_files(tmp_path: Any) -> None:
    """main() returns non-zero when config/scenario files don't exist."""

    code = main([str(tmp_path / "missing.json"), str(tmp_path / "also-missing.json"), "3"])
    assert code != 0


def test_main_entry_point_runs_stub_days(tmp_path: Any, monkeypatch: Any) -> None:
    """main() with valid files and stub config completes successfully."""

    import json

    monkeypatch.chdir(tmp_path)
    _patch_httpx(monkeypatch, _mock_transport())

    config_path = tmp_path / "sim.json"
    scenario_path = tmp_path / "scenario.json"

    config_path.write_text(json.dumps(STUB_CONFIG), encoding="utf-8")
    scenario_path.write_text(json.dumps(STUB_SCENARIO), encoding="utf-8")

    code = main([str(config_path), str(scenario_path), "2"])
    assert code == 0

    logs_dir = tmp_path / "logs"
    assert (logs_dir / "day-001-Factory.log").exists()
    assert (logs_dir / "day-002-Factory.log").exists()
