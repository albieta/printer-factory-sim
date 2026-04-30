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
├── scripts/dev-start.sh           # starts manufacturer (backend + frontend)
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
  .venv/bin/ruff check .
  .venv/bin/mypy --strict manufacturer provider
  ```

## How to run things

Manufacturer (Week 5 surface, unchanged from the user's perspective):

```bash
bash scripts/dev-start.sh
# → React UI at http://localhost:3000
# → FastAPI at  http://localhost:8000  (will move to 8002 once Week 6 ports land)
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
    --supplier "ChipSupply Co" --product pcb --qty 50
.venv/bin/python -m manufacturer.cli day advance
```

Tests:

```bash
.venv/bin/pytest manufacturer/backend/tests provider/tests
```

## Current state

- **Week 5 — done.** All R0–R8 functional requirements are covered by the
  manufacturer app. The Streamlit prototype in
  `manufacturer/backend/app/ui/dashboard.py` is legacy; the React app is
  the active UI. Report (`docs/report.md`) is in progress.
- **Week 6 — milestone #3 done.** Provider data model, seed loader, and
  service layer are in place:
  - SQLAlchemy models in `provider/app/models/models.py` for `Product`,
    `PricingTier`, `Stock`, `Order`, `Event`, `SimState`, with the full
    `OrderStatus` lifecycle enum and an `EventType` enum.
  - `provider/app/utils/database.py` mirrors the manufacturer's
    bootstrap and writes to `provider/provider.db`.
  - `provider/seed/seed-provider.json` ships a starter catalogue covering
    all six manufacturer-BOM materials (Control Board, Stepper Motor,
    Aluminum Frame, PLA Filament, ABS Filament, LCD Screen) with
    1 / 20+ / 200+ pricing tiers, 3–7 day lead times, initial stock.
  - `provider/scripts/seed_data.py` is idempotent and validated; runs
    via `cd provider && ../.venv/bin/python scripts/seed_data.py`.
  - Service layer in `provider/app/services/`:
    - `event_service.py` — append-only audit log (caller commits).
    - `sim_state_service.py` — `current_day` get/set with self-healing
      bootstrap if the row is missing.
    - `catalog_service.py` — read-only product / stock lookups.
    - `pricing.py` — quantity-break tier picker; rejects non-positive
      quantities and tier sets that don't start at 1.
    - `order_service.py` — `create_order` enforces the stock check and
      the ironclad rule (`expected_delivery_day = placed_day +
      lead_time_days`, ≥ 1). Stock is decremented atomically with
      placement; insufficient stock yields a `REJECTED` order without
      reservation.
    - `day_service.py` — `advance()` walks `PENDING → CONFIRMED →
      IN_PROGRESS → SHIPPED`, delivers `SHIPPED` orders whose
      `expected_delivery_day` is due, increments the day, writes a
      `DAY_ADVANCED` summary event.
  - Provider tests grew from 7 to 26: pricing tiers, order placement
    (8 cases including ironclad rule and reject path), day-advance
    state transitions (5 cases), and a provider-side rehearsal of the
    Week 6 five-day scenario. Manufacturer's 14 tests still pass;
    `ruff` is clean.
  - `typer==0.9.0` added to `requirements.txt`.
- **Still missing for Week 6** (see `docs/PRD-week6.md` §10):
  1. ~~Provider data model + seed loader.~~ ✅
  2. ~~Provider service layer (catalog, orders, day-advance, pricing-tier
     calculation, stock check, ironclad-rule enforcement).~~ ✅
  3. Provider FastAPI routes + Swagger (`provider/main.py` + `app/api/`).
  4. `provider-cli` (Typer).
  5. `manufacturer-cli` (Typer).
  6. Manufacturer outbound integration (`Supplier.external_provider_url`
     column, httpx call on PO create, `SimulationService.advance_day`
     polling, port move 8000 → 8002, `manufacturer/config.json`).
  7. End-to-end five-day scenario as the acceptance gate.

## Working with Claude Code in this repo

- Start every session by reading this file and `docs/PRD-week6.md`. Then
  glance at the current code state before proposing changes.
- Be specific in requests. Prefer "Implement `provider/app/services/orders.py:create_order()` per §5.3 of `docs/PRD-week6.md`" over "build the provider".
- When something doesn't fit the PRD, push back and update the PRD —
  don't silently invent.
- Do not commit unless the user asks. Do not introduce new top-level
  dependencies (Streamlit, SimPy, matplotlib, etc.) without flagging it
  first.
