# 3D Printer Production Simulator

A multi-process simulation of a 3D printer supply chain, built across three course weeks.

- The **provider** (port 8001) sells raw materials over a REST API.
- The **manufacturer** (port 8002) buys raw materials, assembles printers, and sells them wholesale to the retailer. It has a full React planner dashboard.
- The **retailer** (port 8003) buys finished printers from the manufacturer and sells them to end customers.
- The **turn engine** (`engine/`) orchestrates all three apps in lockstep each simulated day: generates customer demand, runs agent decision logic, advances all day counters, and writes a KPI log.
- A **skill file** (`skills/manufacturer-manager.md`) defines the manufacturer-manager agent's persona and decision framework. With `--agent manufacturer=llm`, the engine calls `claude --print` each day and parses the agent's `manufacturer-cli` commands for execution.

Each app owns its own SQLite database and its own simulated-day counter. All cross-app communication is HTTP/JSON — no shared databases or shared Python imports.

## Stack

| Layer | Technology |
|---|---|
| Frontend (manufacturer only) | React 18 + Vite + TypeScript + Bootstrap + Plotly |
| Backend (all three apps) | FastAPI + SQLAlchemy + Pydantic |
| Database | SQLite (one per app) |
| CLIs | Typer (`manufacturer-cli`, `provider-cli`, `retailer-cli`) |
| Turn engine | Python package (`engine/`), HTTP only |
| Tooling | pytest, Ruff, mypy |

## Quick Start (dev container)

The dev container installs all dependencies and seeds the manufacturer database on first creation. On every container start it launches:

- Provider API on `http://localhost:8001`
- Manufacturer API on `http://localhost:8002`
- React frontend on `http://localhost:3000`

The retailer must be started manually (see below).

Forwarded ports: `3000`, `8001`, `8002`, `8003`.

## Starting all three backends

```bash
# Provider
PYTHONPATH=provider .venv/bin/uvicorn provider.main:app --host 0.0.0.0 --port 8001 &

# Manufacturer (must run from its own directory for correct DB path)
(cd manufacturer/backend && PYTHONPATH=. ../../.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8002) &

# Retailer
.venv/bin/python -m retailer.cli serve --port 8003 &
```

Or use the all-in-one script:

```bash
bash scripts/dev-start-all.sh
```

## Seeding databases

Each app needs its seed script run once after a fresh database:

```bash
(cd manufacturer/backend && PYTHONPATH=. ../../.venv/bin/python scripts/seed_data.py)
(cd provider            && PYTHONPATH=. ../.venv/bin/python scripts/seed_data.py)
(cd retailer            && PYTHONPATH=. ../.venv/bin/python scripts/seed_data.py --config ../retailer.json)
```

> **Important:** always run seed scripts from the app's own directory so that the relative SQLite path matches where the server writes.

## Running the turn engine

**Stub mode** (deterministic, ~10 seconds for 5 days):

```bash
.venv/bin/python -m engine \
    --scenario engine/scenarios/week7-default.json \
    --days 5 --seed 42 --log-dir logs/
```

**LLM mode** (manufacturer agent calls `claude --print` each day):

```bash
.venv/bin/python -m engine \
    --scenario engine/scenarios/week7-acceptance.json \
    --days 5 --seed 42 \
    --agent manufacturer=llm \
    --log-dir logs/acceptance/
```

After the run:

```bash
cat logs/kpi.csv                                    # daily KPI table
cat logs/acceptance/manufacturer-agent-day-01.txt   # LLM reasoning + commands
```

## CLI reference

**Manufacturer:**
```bash
.venv/bin/python -m manufacturer.cli inventory
.venv/bin/python -m manufacturer.cli sales orders
.venv/bin/python -m manufacturer.cli price list
.venv/bin/python -m manufacturer.cli price set "Basic300" 800
.venv/bin/python -m manufacturer.cli purchase list
.venv/bin/python -m manufacturer.cli purchase create --supplier "ChipSupply Co" --product "Control Board" --qty 100
.venv/bin/python -m manufacturer.cli suppliers list
.venv/bin/python -m manufacturer.cli day advance
```

**Retailer:**
```bash
.venv/bin/python -m retailer.cli catalog
.venv/bin/python -m retailer.cli stock
.venv/bin/python -m retailer.cli purchase list
.venv/bin/python -m retailer.cli purchase create "Basic300" 5
.venv/bin/python -m retailer.cli day advance
```

**Provider:**
```bash
.venv/bin/python -m provider.cli catalog
.venv/bin/python -m provider.cli stock
.venv/bin/python -m provider.cli orders list
.venv/bin/python -m provider.cli day advance
```

## Day-advance order

When operating manually (without the turn engine), advance apps in this order:

```
retailer → manufacturer → provider
```

The app being polled must be in its final state before the poller advances. The turn engine enforces this automatically.

## Project layout

```text
printer-factory-sim/
├── CLAUDE.md                    # Project conventions and Claude Code contract
├── README.md
├── requirements.txt
├── setup.cfg                    # mypy + ruff config
├── retailer.json                # Retailer instance config (port, DB path, manufacturer URL)
├── skills/
│   └── manufacturer-manager.md  # LLM agent skill file (persona, commands, decision framework)
├── engine/                      # Turn engine package
│   ├── __main__.py              # CLI entry: python -m engine
│   ├── runner.py                # Main turn loop
│   ├── demand.py                # Customer demand generation
│   ├── agents.py                # Stub and LLM manufacturer agents
│   ├── kpi.py                   # KPI collection and CSV writing
│   └── scenarios/
│       ├── week7-default.json   # 5-day scenario with demand modifiers
│       └── week7-acceptance.json# 5-day flat scenario for M5 gate
├── manufacturer/
│   ├── backend/                 # FastAPI + SQLAlchemy + Pydantic
│   │   ├── main.py
│   │   ├── app/
│   │   │   ├── api/routes/      # includes sales.py (wholesale orders)
│   │   │   ├── services/        # includes sales_service.py
│   │   │   ├── models/
│   │   │   └── schemas/
│   │   ├── cli/
│   │   ├── scripts/seed_data.py
│   │   └── tests/
│   └── frontend/                # React + Vite + TypeScript
├── provider/                    # Raw material supplier app (port 8001)
│   ├── main.py
│   ├── app/
│   ├── cli/
│   ├── scripts/seed_data.py
│   └── tests/
├── retailer/                    # Finished printer retailer app (port 8003)
│   ├── main.py
│   ├── app/
│   ├── cli/
│   ├── scripts/seed_data.py
│   └── tests/
├── docs/
│   ├── PRD.md                   # Week 5 original PRD
│   ├── PRD2.md                  # Week 5 retrospective
│   ├── PRD-week6.md             # Week 6 PRD
│   ├── PRD-week7.md             # Week 7 PRD (current)
│   └── report-week7.md          # Week 7 report
└── scripts/
    ├── dev-start.sh             # Starts provider + manufacturer + frontend
    └── dev-start-all.sh         # Starts all three backends + frontend
```

## React UI pages (manufacturer, port 3000)

| Path | Purpose |
|---|---|
| `/` | Overview dashboard — bottleneck analysis, advance day |
| `/orders` | Manufacturing orders — release into assembly queue |
| `/inventory` | Raw material stock levels and warehouse capacity |
| `/suppliers` | Procurement sources and purchase orders |
| `/production` | Production flow and capacity tracking |
| `/reports` | Charts and event history |
| `/settings` | Simulation configuration |

## Key API endpoints

**Manufacturer (port 8002):**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/simulation/status` | Current date, order counts, capacity |
| POST | `/api/simulation/advance-day` | Advance one simulated day |
| GET | `/api/inventory/` | Raw material stock |
| GET | `/api/sales/orders` | Inbound orders from the retailer |
| GET | `/api/sales/prices` | Wholesale prices per printer model |
| PUT | `/api/sales/prices/{model}` | Update wholesale price |

**Retailer (port 8003):**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/catalog` | Printer models with retail prices |
| GET | `/api/stock` | Finished-printer inventory |
| POST | `/api/orders` | Place a customer order |
| POST | `/api/purchases` | Place a purchase order with the manufacturer |
| POST | `/api/day/advance` | Advance one simulated day |

**Provider (port 8001):**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/catalog` | Raw materials with pricing tiers |
| GET | `/api/stock` | Provider stock levels |
| POST | `/api/orders` | Place a purchase order |
| POST | `/api/day/advance` | Advance one simulated day |

Full interactive docs at `/docs` on each backend.

## Development commands

```bash
# Tests (run each suite in isolation — shared pytest invocation causes path conflicts)
.venv/bin/pytest manufacturer/backend/tests
.venv/bin/pytest provider/tests
.venv/bin/pytest retailer/tests

# Lint
.venv/bin/ruff check .

# Type checking
(cd provider             && ../.venv/bin/mypy --config-file ../setup.cfg --explicit-package-bases app cli)
(cd manufacturer/backend && ../../.venv/bin/mypy --config-file ../../setup.cfg app)
(cd retailer             && ../.venv/bin/mypy --config-file ../setup.cfg --explicit-package-bases app cli)
(cd engine               && ../.venv/bin/mypy --config-file ../setup.cfg .)
```
