# Project: 3D Printer Production Simulator — Multi-app Supply Chain

## What this is

A multi-process simulation of a 3D printer supply chain, built across two
course weeks:

- **Week 5 (done):** a single-app factory simulator. Web UI for a
  production planner. Runs the daily cycle of demand generation, BOM
  checks, production, internal procurement, JSON export/import.
- **Week 6 (done):** the factory is no longer alone. A separate
  **provider** application sells raw materials over a REST API. The
  Week 5 app keeps working unchanged from the user's point of view, but it
  now also acts as an HTTP client to the provider for procurement. Each
  app owns its own database and its own simulated-day counter.
- **Week 7 (current):** a **retailer** app (port 8003) buys finished
  printers from the manufacturer and sells them to end customers. A
  **turn engine** (`engine/` package) orchestrates all three apps in
  lockstep each simulated day: reads a scenario file, generates customer
  demand, runs each role's decision stub (or LLM agent), then advances
  all day counters. A **skill file** (`skills/manufacturer-manager.md`)
  defines the manufacturer-manager agent's persona and decision framework;
  in Milestone 5 it drives a live `claude --print` call.
- **Week 8 (future):** multi-retailer market experiments, retailer/provider
  LLM agents, market-signal injection, and the final report.

This file is the living contract for Claude Code in **this** repository.
The Week 7 plan in detail lives in [`docs/PRD-week7.md`](docs/PRD-week7.md).
Week 6 plan: [`docs/PRD-week6.md`](docs/PRD-week6.md).
Older plans are preserved in `docs/PRD.md` (original) and `docs/PRD2.md`
(retrospective).

## Tech stack

We have **deliberately diverged** from the brief's suggestions of Streamlit,
matplotlib, and SimPy. Carry these choices into all new code in this repo
unless we explicitly decide to change them in the PRD:

- **Python 3.11+** (single shared `.venv` at the repository root).
- **FastAPI + Pydantic + SQLAlchemy** for all three backends (manufacturer,
  provider, retailer). One SQLite database per app.
- **Typer** for all three CLIs (`manufacturer-cli`, `provider-cli`,
  `retailer-cli`). Added in Week 6; retailer added in Week 7.
- **httpx** for cross-app HTTP calls (manufacturer → provider,
  retailer → manufacturer).
- **React 18 + Vite + TypeScript + Bootstrap + Plotly** for the
  manufacturer's web UI (Week 5). The provider and retailer are headless —
  no browser UI.
- **pytest, ruff, mypy** for tests, lint, and type checking.
- **SQLite per app**: `manufacturer/backend/printer_factory_sim.db`,
  `provider/provider.db`, and `retailer/retailer.db`. All gitignored via
  `*.db`.
- **Turn engine** (`engine/` Python package): headless orchestrator that
  speaks only HTTP. No SQLAlchemy dependency. Run via `python -m engine`.

If a future task tempts you to introduce Streamlit, SimPy, or matplotlib, do
not — discuss with the user first.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Turn Engine  (engine/ — HTTP only, no shared DB)               │
│  python -m engine --scenario ... --days N                       │
│  • reads scenario file  • generates customer demand             │
│  • runs agent stubs / claude --print  • advances all days       │
└──┬──────────────┬──────────────────────┬────────────────────────┘
   │ HTTP         │ HTTP                 │ HTTP
   ▼              ▼                      ▼
┌──────────────┐ ┌────────────────────────────────────────────────┐
│ retailer-cli │ │ React + Vite UI   manufacturer-cli  provider-cli│
│ (Typer)      │ │ (port 3000)       (Typer)           (Typer)    │
└──────┬───────┘ └──────────┬──────────────┬────────────────────┘
       │                    │              │
       ▼                    ▼              ▼
┌─────────────────┐  ┌──────────────────────────┐  ┌────────────────────────┐
│ FastAPI         │  │ FastAPI                  │  │ FastAPI                │
│ retailer        │  │ manufacturer (port 8002) │  │ provider   (port 8001) │
│ (port 8003)     │  │ routes→services→SQLite   │  │ routes→services→SQLite │
│ routes→services │  └──────────┬───────────────┘  └────────────────────────┘
│ →SQLite         │             │ httpx                        ▲
└──────┬──────────┘             │ POST /api/sales/orders       │
       │ httpx                  │ GET  /api/sales/orders/{id}  │
       │ POST /api/sales/orders └──────────────────────────────┘
       │ GET  /api/sales/orders/{id}
       └──────────────────────▶ manufacturer (port 8002)
```

Hard rules:

- No app reads another app's database. All cross-app communication is
  HTTP/JSON over the documented REST contracts:
  - provider endpoints: [`docs/PRD-week6.md`](docs/PRD-week6.md) §5.2
  - manufacturer sales endpoints: [`docs/PRD-week7.md`](docs/PRD-week7.md) §5.2
  - retailer endpoints: [`docs/PRD-week7.md`](docs/PRD-week7.md) §4.3
- The turn engine is also HTTP-only — it imports nothing from `app.*` in
  any of the three services.
- Each app's CLI and REST routes are **thin wrappers** over a single
  service layer per app (`{manufacturer,provider,retailer}/app/services/`).
  Business logic does not live in `api/routes/` or `cli/` modules.
- Each app appends to its own `events` table on every meaningful state
  change (order placed, order shipped, order delivered, day advanced,
  price changed, stock updated, …). The event log is the audit trail.
- Each app owns its own simulated-day counter. Under the turn engine, days
  advance in the order **retailer → manufacturer → provider** (downstream
  first). Manual operation without the engine should follow the same order.

## Data model (high level)

Manufacturer (already implemented in Week 5; see `docs/PRD2.md` §5):
`Product`, `BillOfMaterials`, `Supplier`, `Inventory`, `ManufacturingOrder`,
`PurchaseOrder`, `Event`, `SimulationConfig`. Status enums on orders.

In Week 6 the `Supplier` row gains optional `external_provider_url` and
`external_product_id` columns so a Week 5 supplier can be wired to a Week 6
provider. Existing data and existing UI keep working.

Provider (new in Week 6): `Product`, `PricingTier`, `Stock`, `Order`,
`Event`, `SimState`. Order lifecycle:
`pending → confirmed → in_progress → shipped → delivered`, with terminal
short-circuits to `rejected` and `cancelled`. The "ironclad rule": parts
ordered on day N cannot arrive before day `N + lead_time_days`; minimum
lead time is 1 day.

Retailer (new in Week 7): `CatalogItem`, `Stock`, `CustomerOrder`,
`PurchaseOrder`, `Event`, `SimState`. Customer order lifecycle:
`pending → fulfilled` or `pending → backordered → fulfilled`. Purchase
order lifecycle mirrors the manufacturer's sales-order states. The retailer
polls the manufacturer for delivery the same way the manufacturer polls the
provider. Multi-instance: all paths resolved from a `retailer.json` config
file; no hardcoded ports or singletons.

Manufacturer additions (Week 7): `SalesOrder` (inbound orders from
retailers), `WholesalePrice` (per-model wholesale price). Sales order
lifecycle: `pending → released → in_progress → shipped → delivered`.
New REST endpoints: `POST /api/sales/orders`, `GET /api/sales/orders/{id}`,
`GET /api/sales/prices`, `PUT /api/sales/prices/{model}`.

## Repository layout

```
printer-factory-sim/
├── CLAUDE.md                      # this file
├── README.md
├── requirements.txt               # shared deps for all apps
├── setup.cfg                      # mypy + ruff config
├── .gitignore
├── .devcontainer/                 # dev container bootstrap (manufacturer)
├── scripts/
│   ├── dev-start.sh               # starts provider + manufacturer + frontend
│   └── dev-start-all.sh           # NEW (Week 7): all three apps
├── skills/                        # NEW (Week 7): LLM agent skill files
│   └── manufacturer-manager.md    # persona, commands, decision framework
├── engine/                        # NEW (Week 7): turn engine package
│   ├── __main__.py                # entry: python -m engine
│   ├── runner.py                  # main turn loop
│   ├── demand.py                  # customer demand generation
│   ├── agents.py                  # decision stubs + LLM integration
│   ├── kpi.py                     # KPI collection → logs/kpi.csv
│   └── scenarios/
│       └── week7-default.json     # 5-day default scenario
├── docs/
│   ├── PRD.md                     # Week 5 original PRD
│   ├── PRD2.md                    # Week 5 retrospective PRD
│   ├── PRD-week6.md               # Week 6 PRD (historical)
│   ├── PRD-week7.md               # Week 7 PRD (current source of truth)
│   └── report.md                  # Week 5 report (in progress)
├── manufacturer/                  # Week 5 app, extended in Week 6 + Week 7
│   ├── backend/                   # FastAPI + SQLAlchemy
│   │   ├── main.py
│   │   ├── app/
│   │   │   ├── api/routes/        # includes sales.py (NEW Week 7)
│   │   │   ├── services/          # includes sales_service.py (NEW Week 7)
│   │   │   ├── models/            # SalesOrder, WholesalePrice (NEW Week 7)
│   │   │   ├── schemas/
│   │   │   ├── utils/
│   │   │   └── ui/
│   │   ├── cli/                   # Typer manufacturer-cli
│   │   ├── scripts/seed_data.py
│   │   └── tests/
│   └── frontend/                  # React + Vite + TS dashboard
├── provider/                      # Week 6 app (unchanged in Week 7)
│   ├── main.py
│   ├── app/{api,services,models,schemas,utils}/
│   ├── cli/                       # Typer provider-cli
│   ├── seed/seed-provider.json
│   ├── scripts/seed_data.py
│   └── tests/
└── retailer/                      # NEW in Week 7
    ├── main.py
    ├── app/{api,services,models,schemas,utils}/
    ├── cli/                       # Typer retailer-cli
    ├── seed/seed-retailer.json
    ├── scripts/seed_data.py
    └── tests/
```

## Coding conventions

- Use type hints everywhere. `mypy --strict` should keep passing.
- Pydantic models for every API request/response schema. Reuse them inside
  Typer commands so the CLI surface and REST surface stay aligned.
- Keep API routes thin. Thicker logic belongs in `app/services/`. The CLI
  imports the same services — no logic duplication between CLI and API.
- Status fields are SQL enums (or `VARCHAR` with an enum-backed Python
  type), never scattered booleans.
- Every state transition writes an `Event` row in the same transaction
  that performs the transition. If you skip the event row, the audit log
  lies.
- Configuration via files (`manufacturer/config.json`) or environment
  variables. **Never hard-code provider URLs, ports, or API keys** in
  `.py` files. Never commit `.env`.
- Docstrings for public service functions. Comments only for non-obvious
  *why* — not what.
- Lint and type-check before committing:

  ```bash
  # Ruff (whole repo)
  .venv/bin/ruff check .

  # mypy — run each app from its own root so 'app.*' imports resolve correctly
  (cd provider             && ../.venv/bin/mypy --config-file ../setup.cfg --explicit-package-bases app cli)
  (cd manufacturer/backend && ../../.venv/bin/mypy --config-file ../../setup.cfg app)
  (cd retailer             && ../.venv/bin/mypy --config-file ../setup.cfg --explicit-package-bases app cli)
  (cd engine               && ../.venv/bin/mypy --config-file ../setup.cfg .)
  ```

  All apps and the engine are configured in `setup.cfg` at the repo root.
  The SQLAlchemy mypy plugin is enabled. `app/ui/dashboard.py` (legacy
  Streamlit) and Week 5 API route handlers are excluded from strict checking
  — annotating those is a follow-up pass. The retailer and engine packages
  must be mypy-strict clean from day one.

## How to run things

Manufacturer (Week 5 surface, unchanged from the user's perspective):

```bash
bash scripts/dev-start.sh
# → React UI at http://localhost:3000
# → FastAPI at  http://localhost:8002
```

Provider (once implemented in Week 6):

```bash
# Terminal A
.venv/bin/python -m provider.cli serve --port 8001

# Terminal B (CLI)
.venv/bin/python -m provider.cli catalog
.venv/bin/python -m provider.cli day advance
```

Manufacturer CLI (Week 6+):

```bash
.venv/bin/python -m manufacturer.cli suppliers list
.venv/bin/python -m manufacturer.cli purchase create \
    --supplier "ChipSupply Co" --product "Control Board" --qty 50
.venv/bin/python -m manufacturer.cli day advance
# Week 7 additions:
.venv/bin/python -m manufacturer.cli sales orders
.venv/bin/python -m manufacturer.cli price list
.venv/bin/python -m manufacturer.cli price set "P3D Classic" 750
```

Retailer (new in Week 7):

```bash
# Terminal — serve (config selects port and DB path)
.venv/bin/python -m retailer.cli serve --config retailer.json --port 8003

# CLI
.venv/bin/python -m retailer.cli --config retailer.json catalog
.venv/bin/python -m retailer.cli --config retailer.json stock
.venv/bin/python -m retailer.cli --config retailer.json purchase create "P3D Classic" 5
.venv/bin/python -m retailer.cli --config retailer.json day advance
```

Turn engine (new in Week 7):

```bash
# Stub mode (deterministic)
.venv/bin/python -m engine \
    --scenario engine/scenarios/week7-default.json \
    --days 5 --seed 42 --log-dir logs/

# LLM mode (manufacturer manager uses claude --print)
.venv/bin/python -m engine \
    --scenario engine/scenarios/week7-default.json \
    --days 5 --seed 42 --agent manufacturer=llm --log-dir logs/
```

Tests:

```bash
.venv/bin/pytest manufacturer/backend/tests
.venv/bin/pytest provider/tests
.venv/bin/pytest retailer/tests
.venv/bin/pytest engine/tests
```

## Current state

- **Week 5 — done.** All R0–R8 functional requirements are covered by the
  manufacturer app. The Streamlit prototype in
  `manufacturer/backend/app/ui/dashboard.py` is legacy; the React app is
  the active UI. Report (`docs/report.md`) is in progress.
- **Week 6 — complete.** All milestones done (see `docs/PRD-week6.md` §10).
  42 tests passing; ruff zero warnings; mypy --strict clean on provider
  and manufacturer service layers. Both apps on SQLAlchemy 2.0 `Mapped[]`.
  Report (`docs/report.md`) in progress.

- **Week 7 — in progress.** Five milestones (see `docs/PRD-week7.md` §12):
  1. Retailer data model (schema, config loading, seed). Gate: `retailer-cli catalog` returns valid empty response.
  2. Retailer service + CLI + REST. Gate: fulfillment and backorder logic unit-tested.
  3. Manufacturer sales API (`SalesOrder`, `WholesalePrice`, new routes/CLI). Gate: retailer can place and poll a printer order over multiple day advances.
  4. Turn engine — stub mode. Gate: 3-day run completes; KPI CSV has 3 rows; all three event logs coherent.
  5. Skill file + LLM upgrade. Gate: 5-day acceptance scenario passes with `--agent manufacturer=llm`; agent logs written to `logs/`.

## Working with Claude Code in this repo

- Start every session by reading this file and `docs/PRD-week7.md`. Then
  glance at the current code state before proposing changes.
- Be specific in requests. Prefer "Implement `retailer/app/services/order_service.py:fulfill_order()` per §4.4 of `docs/PRD-week7.md`" over "build the retailer".
- When something doesn't fit the PRD, push back and update the PRD —
  don't silently invent.
- Do not commit unless the user asks. Do not introduce new top-level
  dependencies (Streamlit, SimPy, matplotlib, etc.) without flagging it
  first.
- The turn engine must never import from `app.*` in any service package.
  All state access goes through HTTP.
