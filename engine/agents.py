"""Decision agents for the turn engine — stub and LLM variants."""

from __future__ import annotations

import logging
import shlex
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Commands the LLM agent must never call.
_FORBIDDEN_COMMANDS = {"day advance", "day"}
_FORBIDDEN_PREFIXES = ("retailer-cli", "provider-cli")


class AgentProtocolError(Exception):
    """Raised when the LLM agent tries to call a forbidden command."""


class ProviderAgent:
    """Provider makes no autonomous decisions in stub mode."""

    def __init__(self, base_url: str) -> None:
        self._url = base_url.rstrip("/")

    def run(self, day: int, signal: dict[str, Any]) -> None:
        pass


class ManufacturerAgent:
    """Reorder raw materials when stock + inbound falls below threshold."""

    REORDER_THRESHOLD = 50
    REORDER_QTY = 100

    def __init__(self, base_url: str) -> None:
        self._url = base_url.rstrip("/")

    def run(self, day: int, signal: dict[str, Any]) -> None:
        with httpx.Client(timeout=10.0) as client:
            inventory = self._get_inventory(client)
            suppliers = self._get_suppliers(client)
            pending_pos = self._get_pending_pos(client)

        pending_by_product: dict[str, float] = {}
        for po in pending_pos:
            pid = po.get("product_id", "")
            pending_by_product[pid] = (
                pending_by_product.get(pid, 0.0) + float(po.get("quantity", 0))
            )

        supplier_by_product: dict[str, dict[str, Any]] = {}
        for s in suppliers:
            pid = s.get("product_id", "")
            if pid not in supplier_by_product:
                supplier_by_product[pid] = s

        with httpx.Client(timeout=10.0) as client:
            for item in inventory:
                pid = str(item.get("product_id", ""))
                qty = float(item.get("quantity", 0))
                inbound = float(item.get("pending_inbound_quantity", 0))
                total = qty + inbound + pending_by_product.get(pid, 0.0)

                if total < self.REORDER_THRESHOLD and pid in supplier_by_product:
                    supplier = supplier_by_product[pid]
                    self._place_po(client, supplier["id"], pid, self.REORDER_QTY)

    def _get_inventory(self, client: httpx.Client) -> list[dict[str, Any]]:
        try:
            resp = client.get(f"{self._url}/api/inventory/", follow_redirects=True)
            resp.raise_for_status()
            data: list[dict[str, Any]] = resp.json()
            return data
        except httpx.HTTPError as exc:
            logger.warning("ManufacturerAgent: inventory fetch failed: %s", exc)
            return []

    def _get_suppliers(self, client: httpx.Client) -> list[dict[str, Any]]:
        try:
            resp = client.get(f"{self._url}/api/suppliers/", follow_redirects=True)
            resp.raise_for_status()
            data: list[dict[str, Any]] = resp.json()
            return data
        except httpx.HTTPError as exc:
            logger.warning("ManufacturerAgent: suppliers fetch failed: %s", exc)
            return []

    def _get_pending_pos(self, client: httpx.Client) -> list[dict[str, Any]]:
        try:
            resp = client.get(f"{self._url}/api/orders/purchase/")
            resp.raise_for_status()
            all_pos: list[dict[str, Any]] = resp.json()
            return [po for po in all_pos if po.get("status") == "PENDING"]
        except httpx.HTTPError as exc:
            logger.warning("ManufacturerAgent: purchase orders fetch failed: %s", exc)
            return []

    def _place_po(
        self, client: httpx.Client, supplier_id: str, product_id: str, qty: int
    ) -> None:
        try:
            resp = client.post(
                f"{self._url}/api/orders/purchase/",
                json={"supplier_id": supplier_id, "product_id": product_id, "quantity": qty},
            )
            resp.raise_for_status()
            logger.info(
                "ManufacturerAgent: placed PO — product=%s qty=%d", product_id, qty
            )
        except httpx.HTTPError as exc:
            logger.warning("ManufacturerAgent: PO placement failed: %s", exc)


class LLMManufacturerAgent:
    """Calls `claude --print` with the skill file + state snapshot each day."""

    def __init__(
        self,
        base_url: str,
        skill_file: Path,
        log_dir: Path,
    ) -> None:
        self._url = base_url.rstrip("/")
        self._skill_file = skill_file
        self._log_dir = log_dir

    def run(self, day: int, signal: dict[str, Any]) -> None:
        state = self._build_state_snapshot()
        prompt = self._build_prompt(state, signal, day)

        logger.info("LLMManufacturerAgent: calling claude --print for day %d", day)
        llm_output = self._call_llm(prompt)

        commands = _parse_commands(llm_output)
        _validate_commands(commands)

        cmd_outputs: list[tuple[str, str, str]] = []
        for cmd in commands:
            stdout, stderr = _execute_manufacturer_cli(cmd)
            cmd_outputs.append((cmd, stdout, stderr))
            logger.info("LLMManufacturerAgent: ran %r → %s", cmd, stdout[:120])

        self._write_transcript(day, prompt, llm_output, cmd_outputs)

    # ── state snapshot ─────────────────────────────────────────────────────────

    def _build_state_snapshot(self) -> str:
        lines: list[str] = ["## Current State\n"]

        inventory = _http_get(f"{self._url}/api/inventory/", follow_redirects=True)
        lines.append("### Inventory (raw materials)")
        if inventory:
            for item in inventory:
                lines.append(
                    f"- {item.get('product_name', item.get('product_id'))}: "
                    f"on_hand={item.get('quantity', 0)}, "
                    f"inbound={item.get('pending_inbound_quantity', 0)}"
                )
        else:
            lines.append("- (no inventory data)")

        sales_orders = _http_get(f"{self._url}/api/sales/orders")
        pending_sales = [o for o in sales_orders if o.get("status") == "PENDING"]
        lines.append(f"\n### Sales Orders (from retailer): {len(sales_orders)} total, {len(pending_sales)} pending")
        for o in sales_orders[:10]:
            lines.append(
                f"- id={o.get('id')} model={o.get('model_name')} "
                f"qty={o.get('quantity')} status={o.get('status')} "
                f"delivery_day={o.get('expected_delivery_day')}"
            )

        purchase_orders = _http_get(f"{self._url}/api/orders/purchase/")
        pending_pos = [p for p in purchase_orders if p.get("status") == "PENDING"]
        lines.append(f"\n### Purchase Orders (to provider): {len(purchase_orders)} total, {len(pending_pos)} pending")
        for p in pending_pos[:5]:
            lines.append(
                f"- {p.get('product_name')} qty={p.get('quantity')} "
                f"expected={p.get('expected_delivery')}"
            )

        prices = _http_get(f"{self._url}/api/sales/prices")
        lines.append("\n### Wholesale Prices")
        for p in prices:
            lines.append(
                f"- {p.get('model_name')}: {p.get('price')} (lead_time={p.get('lead_time_days')}d)"
            )

        suppliers = _http_get(f"{self._url}/api/suppliers/", follow_redirects=True)
        lines.append("\n### Suppliers")
        for s in suppliers:
            lines.append(
                f"- supplier={s.get('name')!r} product={s.get('product_name')!r} "
                f"cost={s.get('unit_cost')} lead={s.get('lead_time_days')}d"
            )

        return "\n".join(lines)

    def _build_prompt(
        self, state: str, signal: dict[str, Any], day: int
    ) -> str:
        skill = self._skill_file.read_text()
        modifier_lines: list[str] = []
        dm = signal.get("demand_modifier")
        sm = signal.get("supply_modifier")
        if dm is not None:
            modifier_lines.append(f"- demand_modifier: {dm}")
        if sm is not None:
            modifier_lines.append(f"- supply_modifier: {sm}")
        signals_block = "\n".join(modifier_lines) if modifier_lines else "- (no modifiers — business as usual)"

        return textwrap.dedent(f"""\
            {skill}

            ---

            ## Today's Context

            Simulated day: {day}

            ### Market Signals
            {signals_block}

            {state}

            ---

            Now follow your Decision Framework for day {day}. Output your reasoning
            and any `manufacturer-cli` commands you want to run, one per line.
        """)

    def _call_llm(self, prompt: str) -> str:
        try:
            result = subprocess.run(
                ["claude", "--print"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode != 0:
                logger.warning(
                    "LLMManufacturerAgent: claude exited %d: %s",
                    result.returncode,
                    result.stderr[:200],
                )
            return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("LLMManufacturerAgent: claude call failed: %s — falling back to stub", exc)
            return ""

    def _write_transcript(
        self,
        day: int,
        prompt: str,
        llm_output: str,
        cmd_outputs: list[tuple[str, str, str]],
    ) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        path = self._log_dir / f"manufacturer-agent-day-{day:02d}.txt"
        parts = [
            f"=== Manufacturer Agent — Day {day} ===\n",
            "--- PROMPT ---\n",
            prompt,
            "\n--- LLM OUTPUT ---\n",
            llm_output,
        ]
        if cmd_outputs:
            parts.append("\n--- COMMANDS EXECUTED ---\n")
            for cmd, stdout, stderr in cmd_outputs:
                parts.append(f"$ {cmd}\n{stdout}")
                if stderr:
                    parts.append(f"[stderr] {stderr}")
        path.write_text("".join(parts))
        logger.info("LLMManufacturerAgent: transcript written to %s", path)


class RetailerAgent:
    """Order finished printers when stock is 0 and no in-flight purchase order exists."""

    def __init__(self, base_url: str, buyer_name: str = "TurnEngine") -> None:
        self._url = base_url.rstrip("/")
        self._buyer = buyer_name

    def run(self, day: int, signal: dict[str, Any]) -> None:
        with httpx.Client(timeout=10.0) as client:
            stock = self._get_stock(client)
            pending_pos = self._get_pending_pos(client)

        in_flight: set[str] = {
            po["model_name"]
            for po in pending_pos
            if po.get("status") in ("PENDING", "pending")
        }

        with httpx.Client(timeout=10.0) as client:
            for item in stock:
                model = str(item.get("model_name", ""))
                qty = float(item.get("quantity", 0))
                if qty == 0 and model not in in_flight:
                    self._place_order(client, model, 5)

    def _get_stock(self, client: httpx.Client) -> list[dict[str, Any]]:
        try:
            resp = client.get(f"{self._url}/api/stock")
            resp.raise_for_status()
            data: list[dict[str, Any]] = resp.json()
            return data
        except httpx.HTTPError as exc:
            logger.warning("RetailerAgent: stock fetch failed: %s", exc)
            return []

    def _get_pending_pos(self, client: httpx.Client) -> list[dict[str, Any]]:
        try:
            resp = client.get(f"{self._url}/api/purchases")
            resp.raise_for_status()
            all_pos: list[dict[str, Any]] = resp.json()
            return [po for po in all_pos if po.get("status") in ("PENDING", "pending")]
        except httpx.HTTPError as exc:
            logger.warning("RetailerAgent: purchases fetch failed: %s", exc)
            return []

    def _place_order(self, client: httpx.Client, model: str, qty: int) -> None:
        try:
            resp = client.post(
                f"{self._url}/api/purchases",
                json={"model": model, "quantity": qty},
            )
            resp.raise_for_status()
            logger.info("RetailerAgent: placed PO — model=%s qty=%d", model, qty)
        except httpx.HTTPError as exc:
            logger.warning("RetailerAgent: order placement failed: %s", exc)


# ── helpers ────────────────────────────────────────────────────────────────────

def _http_get(
    url: str, follow_redirects: bool = False
) -> list[dict[str, Any]]:
    try:
        resp = httpx.get(url, timeout=5.0, follow_redirects=follow_redirects)
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()
        return data
    except httpx.HTTPError as exc:
        logger.warning("HTTP GET %s failed: %s", url, exc)
        return []


def _parse_commands(llm_output: str) -> list[str]:
    """Extract lines that start with 'manufacturer-cli' from LLM output."""
    commands: list[str] = []
    for line in llm_output.splitlines():
        stripped = line.strip().lstrip("`").rstrip("`").strip()
        if stripped.startswith("manufacturer-cli "):
            commands.append(stripped)
    return commands


def _validate_commands(commands: list[str]) -> None:
    for cmd in commands:
        for forbidden_prefix in _FORBIDDEN_PREFIXES:
            if cmd.startswith(forbidden_prefix):
                raise AgentProtocolError(f"Forbidden command prefix: {cmd!r}")
        rest = cmd.removeprefix("manufacturer-cli").strip()
        if rest.startswith("day"):
            raise AgentProtocolError(f"Forbidden day command: {cmd!r}")


def _execute_manufacturer_cli(cmd: str) -> tuple[str, str]:
    """Translate 'manufacturer-cli <args>' → subprocess call and return stdout, stderr."""
    args_str = cmd.removeprefix("manufacturer-cli").strip()
    args = shlex.split(args_str)
    result = subprocess.run(
        [sys.executable, "-m", "manufacturer.cli"] + args,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout, result.stderr


def build_agents(
    scenario: dict[str, Any],
    agent_overrides: dict[str, str],
    log_dir: Path | None = None,
) -> tuple[RetailerAgent, ManufacturerAgent | LLMManufacturerAgent, ProviderAgent]:
    apps = scenario.get("apps", {})
    retailer_url: str = apps.get("retailer", {}).get("url", "http://localhost:8003")
    manufacturer_url: str = apps.get("manufacturer", {}).get("url", "http://localhost:8002")
    provider_url: str = apps.get("provider", {}).get("url", "http://localhost:8001")

    retailer_agent = RetailerAgent(retailer_url)
    provider_agent = ProviderAgent(provider_url)

    mfg_mode = agent_overrides.get("manufacturer", "stub")
    if mfg_mode == "llm":
        if not shutil.which("claude"):
            logger.warning("claude not found on PATH — falling back to stub manufacturer agent")
            manufacturer_agent: ManufacturerAgent | LLMManufacturerAgent = ManufacturerAgent(manufacturer_url)
        else:
            skill_file = Path("skills/manufacturer-manager.md")
            if not skill_file.exists():
                logger.warning("Skill file %s not found — falling back to stub", skill_file)
                manufacturer_agent = ManufacturerAgent(manufacturer_url)
            else:
                manufacturer_agent = LLMManufacturerAgent(
                    base_url=manufacturer_url,
                    skill_file=skill_file,
                    log_dir=log_dir or Path("logs"),
                )
                logger.info("LLM manufacturer agent enabled")
    else:
        manufacturer_agent = ManufacturerAgent(manufacturer_url)

    return retailer_agent, manufacturer_agent, provider_agent
