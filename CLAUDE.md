# Project: 3D Printer Production Simulator — Multi-app Supply Chain

## What this is

A multi-process simulation of a 3D printer supply chain, built across two
course weeks:

- **Week 5 (done):** a single-app factory simulator. Web UI for a
  production planner. Runs the daily cycle of demand generation, BOM
  checks, production, internal procurement, JSON export/import.
- **Week 6 (current):** the factory is no longer alone. A separate
  **provider** application sells raw materials over a REST API. The
  Week 5 app keeps working unchanged from the user's point of view, but it
  now also acts as an HTTP client to the provider for procurement. Each
  app owns its own database and its own simulated-day counter.
- **Week 7 / Week 8 (future):** a retailer app, a turn engine, LLM agents
  driving the three roles, and market-signal injection.

This file is the living contract for Claude Code in **this** repository.
The Week 6 plan in detail lives in [`docs/PRD-week6.md`](docs/PRD-week6.md).
Older plans are preserved in `docs/PRD.md` (original) and `docs/PRD2.md`
(retrospective).

## Tech stack

We have **deliberately diverged** from the brief's suggestions of Streamlit,
matplotlib, and SimPy. Carry these choices into all new code in this repo
unless we explicitly decide to change them in the PRD:

- **Python 3.11+** (single shared `.venv` at the repository root).
- **FastAPI + Pydantic + SQLAlchemy** for both backends (manufacturer and
  provider). One SQLite database per app.
- **Typer** for both CLIs (`manufacturer-cli`, `provider-cli`). Added in
  Week 6.
- **httpx** for cross-app HTTP calls (manufacturer → provider).
- **React 18 + Vite + TypeScript + Bootstrap + Plotly** for the
  manufacturer's web UI (Week 5). The provider is headless — no browser UI.
- **pytest, ruff, mypy** for tests, lint, and type checking.
- **SQLite per app**: `manufacturer/backend/printer_factory_sim.db` and
  `provider/provider.db`. Both are gitignored via `*.db`.

If a future task tempts you to introduce Streamlit, SimPy, or matplotlib, do
not — discuss with the user first.

## Architecture

```
                 ┌────────────────────────┐
                 │  Planner / human / CLI │
                 └─────────┬──────────────┘
                           │
        ┌──────────────────┴──────────────────┐
        │                                     │
        ▼                                     ▼
┌───────────────────┐              ┌──────────────────────┐
│ React + Vite UI   │  HTTP/JSON   │  manufacturer-cli    │
│ (port 3000)       │◀────────────▶│  (Typer)             │
└─────────┬─────────┘              └──────────┬───────────┘
          │                                   │
          │   shared service layer            │
          ▼                                   ▼
┌──────────────────────────────────────────────────┐
│  FastAPI backend — manufacturer (port 8002)      │
│  routes → services → SQLAlchemy → SQLite         │
└──────────────────────┬───────────────────────────┘
                       │ httpx (POST /api/orders, GET /api/orders/{id})
                       ▼
┌──────────────────────────────────────────────────┐
│  FastAPI backend — provider    (port 8001)       │
│  routes → services → SQLAlchemy → SQLite         │
└──────────────────────┬───────────────────────────┘
                       ▲
                       │
              ┌────────┴────────┐
              │  provider-cli   │
              │  (Typer)        │
              └─────────────────┘
```

Hard rules:

- The manufacturer never reads the provider's database, and vice versa.
  All cross-app communication goes through HTTP/JSON over the documented
  endpoints in [`docs/PRD-week6.md`](docs/PRD-week6.md) §5.2.
- Each app's CLI and REST routes are **thin wrappers** over a single
  service layer per app (`{manufacturer,provider}/app/services/`). Business
  logic does not live in `api/routes/` or `cli/` modules.
- Each app appends to its own `events` table on every meaningful state
  change (order placed, order shipped, order delivered, day advanced,
  price changed, stock updated, …). The event log is the audit trail.
- Each app owns its own simulated-day counter persisted in a `sim_state`
  (provider) or `simulation_config.sim_date` (manufacturer) row. Days are
  advanced by the human operator: provider first, manufacturer second,
  every day. A turn engine arrives in Week 7.

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

## Repository layout

```
printer-factory-sim/
├── CLAUDE.md                      # this file
├── README.md
├── requirements.txt               # shared deps for both apps
├── .gitignore
├── .devcontainer/                 # dev container bootstrap (manufacturer)
├── scripts/dev-start.sh           # starts provider + manufacturer + frontend
├── docs/
│   ├── PRD.md                     # Week 5 original PRD
│   ├── PRD2.md                    # Week 5 retrospective PRD
│   ├── PRD-week6.md               # Week 6 PRD (current source of truth)
│   └── report.md                  # Week 5 report (in progress)
├── manufacturer/                  # Week 5 app, extended in Week 6
│   ├── backend/                   # FastAPI + SQLAlchemy
│   │   ├── main.py
│   │   ├── app/{api,services,models,schemas,utils,ui}/
│   │   ├── cli/                   # NEW: Typer manufacturer-cli (Week 6)
│   │   ├── scripts/seed_data.py
│   │   └── tests/
│   └── frontend/                  # React + Vite + TS dashboard
└── provider/                      # NEW in Week 6
    ├── main.py
    ├── app/{api,services,models,schemas,utils}/
    ├── cli/                       # Typer provider-cli
    ├── seed/seed-provider.json
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
  (cd provider          && ../.venv/bin/mypy --config-file ../setup.cfg --explicit-package-bases app cli)
  (cd manufacturer/backend && ../../.venv/bin/mypy --config-file ../../setup.cfg app)
  ```

  Both apps are configured in `setup.cfg` at the repo root. The SQLAlchemy
  mypy plugin is enabled; `app/ui/dashboard.py` (legacy Streamlit) and
  `app/api/routes/` (Week 5 untyped handlers) are excluded from strict
  checking — annotating the route handlers is a follow-up pass.

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

Manufacturer CLI (once implemented in Week 6):

```bash
.venv/bin/python -m manufacturer.cli suppliers list
.venv/bin/python -m manufacturer.cli purchase create \
    --supplier "ChipSupply Co" --product "Control Board" --qty 50
.venv/bin/python -m manufacturer.cli day advance
```

Tests:

```bash
.venv/bin/pytest manufacturer/backend/tests
.venv/bin/pytest provider/tests
```

## Current state

- **Week 5 — done.** All R0–R8 functional requirements are covered by the
  manufacturer app. The Streamlit prototype in
  `manufacturer/backend/app/ui/dashboard.py` is legacy; the React app is
  the active UI. Report (`docs/report.md`) is in progress.
- **Week 6 — milestones #7, #8, and #9 done.** Provider data model, seed loader,
  service layer, FastAPI routes, CLI, manufacturer CLI, outbound provider
  integration, and the five-day acceptance smoke are complete:
  - Data model: SQLAlchemy in `provider/app/models/models.py` with full
    `OrderStatus` lifecycle and `EventType` enum. ✅
  - Database: `provider/app/utils/database.py` → `provider.db`. ✅
  - Seed data: `provider/seed/seed-provider.json` covers all six
    manufacturer-BOM materials with quantity-break pricing. ✅
  - Service layer in `provider/app/services/` (event, state, catalog,
    pricing, orders, day-advance): all complete. ✅
    - New: `admin_service.py` (JSON export/import), `state_service.py`
      (unified state queries). ✅
  - Provider tests: 26+ passing, covering pricing, orders, day-advance. ✅
  - **Provider FastAPI** (`provider/main.py` + `provider/app/api/routes/`):
    - Routes: `/api/catalog`, `/api/stock`, `/api/orders`, `/api/orders/{id}`,
      `/api/day/advance`, `/api/day/current`, `/health`, `/docs`. ✅
  - **Provider CLI** (`provider/cli/__main__.py`, run via
    `python -m provider.cli`):
    - Commands: `catalog`, `stock`, `orders list/show`, `price set`,
      `restock`, `day advance/current`, `export`, `import`, `serve`. ✅
  - **Manufacturer CLI** (`manufacturer/cli/__main__.py`, run via
    `python -m manufacturer.cli`):
    - Commands: `suppliers list/catalog`, `purchase create/list`,
      `inventory`, `day advance/current`, `export`, `import`. ✅
  - **Manufacturer outbound integration**:
    - `Supplier.external_provider_url`, `Supplier.external_product_id`, and
      `PurchaseOrder.external_order_id` are migrated onto existing SQLite DBs. ✅
    - `manufacturer/config.json` wires `ChipSupply Co` to the provider
      on `http://localhost:8001`; the manufacturer now runs on port 8002. ✅
    - Creating a PO for an external supplier posts to provider
      `POST /api/orders`; day advance polls `GET /api/orders/{id}` and
      receives inventory only after the provider reports `DELIVERED`. ✅
  - **Five-day smoke**:
    - `manufacturer/backend/tests/test_operations_flow.py` covers the
      provider handoff with `httpx.MockTransport`: 5 → 55 Control Boards
      after provider delivery. ✅
    - Provider's own five-day scenario test remains green. ✅
- **Still missing for Week 6** (see `docs/PRD-week6.md` §10):
  1. ~~Provider data model + seed loader.~~ ✅
  2. ~~Provider service layer.~~ ✅
  3. ~~Provider FastAPI routes + Swagger.~~ ✅
  4. ~~Provider CLI.~~ ✅
  5. ~~Manufacturer CLI.~~ ✅
  6. ~~Manufacturer outbound integration (`Supplier.external_provider_url`,
     httpx calls on PO create, polling on day advance, port 8000 → 8002).~~ ✅
  7. ~~End-to-end five-day scenario as the acceptance gate.~~ ✅
  8. ~~Tests and lint clean; mypy --strict passing for both apps.~~ ✅
    - 42 tests passing (15 manufacturer + 27 provider).
    - ruff: zero warnings.
    - mypy --strict: zero errors on provider and manufacturer service layers.
    - Both apps migrated to SQLAlchemy 2.0 `Mapped[]` ORM style.
    - `setup.cfg` with `sqlalchemy.ext.mypy.plugin`; legacy `dashboard.py`
      and Week 5 API route handlers excluded (follow-up annotation pass).
  9. Two-page report + screenshots. (next)

## Working with Claude Code in this repo

- Start every session by reading this file and `docs/PRD-week6.md`. Then
  glance at the current code state before proposing changes.
- Be specific in requests. Prefer "Implement `provider/app/services/orders.py:create_order()` per §5.3 of `docs/PRD-week6.md`" over "build the provider".
- When something doesn't fit the PRD, push back and update the PRD —
  don't silently invent.
- Do not commit unless the user asks. Do not introduce new top-level
  dependencies (Streamlit, SimPy, matplotlib, etc.) without flagging it
  first.
