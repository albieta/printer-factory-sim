# 3D Printer Supply Chain Simulator

A multi-process simulation of a 3D printer supply chain, built across three course weeks. Three cooperating processes — a **manufacturer**, a **provider**, and a **retailer** — communicate over REST APIs. A **turn engine** orchestrates daily simulation ticks and can drive roles autonomously via Claude Code (LLM agent) skill files.

## Architecture

```
                 ┌──────────────────────┐
                 │  React + Vite UI      │  http://localhost:3000
                 └──────────┬───────────┘
                            │
         ┌──────────────────┴──────────────────┐
         │                                     │
         ▼                                     ▼
┌─────────────────────┐              ┌──────────────────────┐
│  Manufacturer API   │  ← HTTP →    │  Retailer API         │
│  port 8002          │              │  port 8003            │
│  FastAPI + SQLite   │              │  FastAPI + SQLite     │
└──────────┬──────────┘              └──────────────────────┘
           │ httpx (purchase orders)
           ▼
┌──────────────────────┐
│  Provider API         │
│  port 8001            │
│  FastAPI + SQLite     │
└──────────────────────┘

┌──────────────────────────────────────────────────────────┐
│  Turn Engine  (engine/turn_engine.py)                    │
│  Injects demand → runs role agents → advances all apps   │
└──────────────────────────────────────────────────────────┘
```

Each app owns its own SQLite database and its own simulated-day counter. Cross-app communication is HTTP/JSON only — no app ever reads another's database.

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite + TypeScript + Bootstrap + Plotly |
| Backend | FastAPI + SQLAlchemy 2.0 + Pydantic v2 |
| Database | SQLite (one file per app) |
| CLI | Typer (`manufacturer-cli`, `provider-cli`, `retailer-cli`) |
| HTTP client | httpx |
| Tooling | pytest, Ruff, mypy --strict |

## Dev Container Quick Start

Open the repository in the provided Docker dev container. On first creation the devcontainer automatically:

1. Installs Python 3.10, Node.js 20, and required OS packages.
2. Creates `.venv` and installs all Python dependencies.
3. Installs frontend dependencies with `npm ci`.
4. Seeds all three SQLite databases with starter data.

On every container start the devcontainer launches the full stack:

| Service | URL |
|---|---|
| Manufacturer UI (React) | http://localhost:3000 |
| Provider API + Swagger | http://localhost:8001/docs |
| Manufacturer API + Swagger | http://localhost:8002/docs |
| Retailer API + Swagger | http://localhost:8003/docs |

VS Code forwards all four ports automatically (Ports panel).

## Manual Start

If you want to start (or restart) all services yourself:

```bash
bash scripts/dev-start.sh
```

This starts all four services, waits for health checks, and prints the URLs. Press `Ctrl+C` to stop.

Stack log (useful if a service fails at container startup):

```bash
cat /tmp/printer-factory-sim/full-stack.log
```

## Manual Setup Without the Dev Container

```bash
# 1. Create the Python virtualenv and install dependencies
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# 2. Install frontend dependencies
cd manufacturer/frontend && npm ci && cd ../..

# 3. Seed all three databases
cd manufacturer/backend && ../../.venv/bin/python scripts/seed_data.py && cd ../..
cd provider           && ../.venv/bin/python scripts/seed_data.py && cd ..
cd retailer && \
  RETAILER_DB_URL="sqlite:///./retailer.db" \
  RETAILER_MANUFACTURER_URL="http://localhost:8002" \
  RETAILER_NAME="PrinterWorld" \
  RETAILER_MANUFACTURER_NAME="Factory" \
  ../.venv/bin/python scripts/seed_data.py && cd ..

# 4. Start everything
bash scripts/dev-start.sh
```

## Running the Simulation

### Option A — Automated turn engine (recommended)

The turn engine runs a full supply-chain day: injects customer demand at the retailer, gives each role a decision turn, then advances all three apps' clocks.

**Step 1 — start all three apps** (skip if the devcontainer already started them):

```bash
bash scripts/dev-start.sh
```

**Step 2 — run the engine:**

Phase 1 — deterministic stubs (no LLM required):

```bash
.venv/bin/python -m engine.turn_engine config/sim-stub.json scenarios/smoke-test.json 3
```

This runs 3 simulated days. Each role prints a `[stub] … would decide here` marker and a log file is written to `logs/day-001-*.log` etc.

Phase 2 — manufacturer driven by Claude Code:

```bash
# Requires 'claude' CLI to be installed and authenticated
.venv/bin/python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 1
```

`config/sim.json` sets `"skill": "skills/manufacturer-manager.md"` for the manufacturer. The agent reads state via the CLI, releases production orders, places purchase orders, and adjusts prices. Output is written to `logs/day-001-Factory.log`.

### Option B — Manual day-by-day (CLI)

Advance apps in **downstream-first** order: retailer → manufacturer → provider.

```bash
# Inspect state
bin/manufacturer-cli day current
bin/manufacturer-cli capacity
bin/manufacturer-cli inventory
bin/manufacturer-cli sales orders --status PENDING
bin/manufacturer-cli production status
bin/manufacturer-cli purchase list
bin/manufacturer-cli price list

# Release a sales order to production
bin/manufacturer-cli production release <ORDER_ID>

# Place a purchase order with the provider
bin/manufacturer-cli purchase create \
  --supplier "ChipSupply Co" \
  --product "Control Board" \
  --qty 50

# Advance the clock (retailer first, then manufacturer, then provider)
bin/retailer-cli day advance
bin/manufacturer-cli day advance
bin/provider-cli day advance
```

Useful retailer commands:

```bash
bin/retailer-cli catalog
bin/retailer-cli stock
bin/retailer-cli customers orders
bin/retailer-cli purchase list
bin/retailer-cli day current
```

Useful provider commands:

```bash
bin/provider-cli catalog
bin/provider-cli stock
bin/provider-cli orders list
bin/provider-cli day current
```

## Project Layout

```text
printer-factory-sim/
├── .devcontainer/             # Dev container bootstrap and auto-start scripts
│   ├── devcontainer.json      # Port forwarding: 3000, 8001, 8002, 8003
│   ├── post-create.sh         # Install deps + seed all three databases
│   └── post-start.sh          # Auto-start all four services on container wake
├── CLAUDE.md                  # Project conventions / Claude Code contract
├── bin/                       # Shell shims for the three CLIs
│   ├── manufacturer-cli       # → .venv/bin/python -m manufacturer.cli
│   ├── provider-cli           # → .venv/bin/python -m provider.cli
│   └── retailer-cli           # → .venv/bin/python -m retailer.cli
├── config/
│   ├── sim.json               # Full config: manufacturer skill enabled
│   └── sim-stub.json          # Phase 1 config: all roles stubbed (no LLM)
├── docs/
│   ├── PRD.md                 # Week 5 original PRD
│   ├── PRD2.md                # Week 5 retrospective PRD
│   ├── PRD-week6.md           # Week 6 PRD (provider integration)
│   └── PRD-week7.md           # Week 7 PRD (retailer + engine + skills)
├── engine/                    # Turn engine
│   ├── demand.py              # Price-elastic, deterministic customer demand
│   ├── agent_runner.py        # Stub / claude --print subprocess runner
│   ├── turn_engine.py         # Orchestrates one full simulation turn
│   └── tests/                 # 24 unit + integration tests
├── manufacturer/
│   ├── backend/               # FastAPI app, services, models, routes, tests
│   └── frontend/              # React + Vite + TS manufacturing dashboard
├── provider/                  # Headless supplier FastAPI app + CLI
├── retailer/                  # Headless retailer FastAPI app + CLI
├── scenarios/
│   └── smoke-test.json        # 10-day steady-state scenario
├── scripts/
│   └── dev-start.sh           # Starts all four services
├── skills/
│   └── manufacturer-manager.md  # Claude Code skill: factory manager role
├── logs/                      # Per-day agent logs (gitignored)
└── requirements.txt           # Shared Python dependencies
```

## Manufacturer Web UI

| Path | Purpose |
|---|---|
| `/` | Factory overview dashboard |
| `/orders` | Manufacturing orders |
| `/inventory` | Material stock and warehouse capacity |
| `/suppliers` | Procurement sources |
| `/production` | Production flow and inbound sales orders |
| `/reports` | Charts and event history |
| `/settings` | Simulation configuration |

## API Reference

All three apps serve interactive Swagger docs at `/docs`.

**Provider** (`http://localhost:8001/api`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/catalog` | List raw materials and pricing tiers |
| GET | `/stock` | Provider stock levels |
| POST | `/orders` | Create a purchase order |
| GET | `/orders/{id}` | Poll order lifecycle state |
| POST | `/day/advance` | Advance provider simulation by one day |

**Manufacturer** (`http://localhost:8002/api`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/inventory/` | Material stock levels |
| POST | `/sales/orders` | Accept inbound sales order from retailer |
| GET | `/sales/orders` | List sales orders (`?status=PENDING` etc.) |
| GET | `/sales/orders/{id}` | Get one sales order |
| POST | `/production/release` | Release a sales order to production |
| GET | `/prices` | Wholesale prices per model |
| POST | `/prices` | Update a wholesale price |
| POST | `/simulation/advance-day/` | Advance manufacturer simulation |

**Retailer** (`http://localhost:8003/api`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/catalog` | Retailer catalog with retail prices |
| GET | `/stock` | Finished-printer stock |
| POST | `/orders` | Place a customer order |
| POST | `/purchases` | Place a purchase order with the manufacturer |
| GET | `/purchases/{id}` | Poll purchase order status |
| POST | `/day/advance` | Advance retailer simulation by one day |

## Testing

```bash
# Run all test suites
.venv/bin/pytest manufacturer/backend/tests provider/tests engine/tests -v

# Retailer tests (run separately — same 'app.*' namespace as provider)
.venv/bin/pytest retailer/tests -v

# Lint
.venv/bin/ruff check .

# Type checking
(cd manufacturer/backend && ../../.venv/bin/mypy --config-file ../../setup.cfg app)
(cd provider  && ../.venv/bin/mypy --config-file ../setup.cfg --explicit-package-bases app cli)
(cd retailer  && ../.venv/bin/mypy --config-file ../setup.cfg --explicit-package-bases app cli)
.venv/bin/mypy --config-file setup.cfg --explicit-package-bases engine
```

## Skill Files

`skills/manufacturer-manager.md` teaches a Claude Code agent to play the manufacturer's role. It specifies the available commands, a five-step decision framework (Assess → Fulfil → Order → Adjust → Log), and explicit DO NOTs (never call `day advance`, never exceed assembly capacity).

To run one day with the manufacturer driven by Claude Code:

```bash
.venv/bin/python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 1
# Agent reasoning → logs/day-001-Factory.log
```

If the agent behaves poorly, rewrite `skills/manufacturer-manager.md` — not the code.
