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

Phase 2 — all three roles driven by Claude Code:

```bash
# Requires 'claude' CLI to be installed and authenticated
.venv/bin/python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 1
```

`config/sim.json` enables `skills/retail-manager.md`, `skills/manufacturer-manager.md`, and `skills/provider-manager.md`. Each agent reads state through its CLI, takes role-specific actions, prints short `LOG:` lines, and writes a per-day file under `logs/`.

Week 8 scenario runs:

```bash
# Skill isolation checks
.venv/bin/python -m engine.turn_engine config/sim-retailer-only.json scenarios/smoke-test.json 1
.venv/bin/python -m engine.turn_engine config/sim-manufacturer-only.json scenarios/smoke-test.json 1
.venv/bin/python -m engine.turn_engine config/sim-provider-only.json scenarios/smoke-test.json 1

# Control group
.venv/bin/python -m engine.turn_engine config/sim.json scenarios/calm-market.json 20

# Volatile market with overlapping events
.venv/bin/python -m engine.turn_engine config/sim.json scenarios/holiday-rush.json 25
```

Each run appends daily snapshots to `logs/metrics.jsonl`. Generate charts and an interpretation with:

```bash
.venv/bin/python -m engine.analyze_run logs/metrics.jsonl \
  --scenario scenarios/holiday-rush.json \
  --out analysis/holiday-rush
```

### Option A.bis — Launch from the web UI (recommended for demos)

The manufacturer web UI exposes a **Scenarios** tab (`http://localhost:3000/scenarios`) that wraps the same engine. From there you can:

- Pick any file in `config/` and any file in `scenarios/`, set the number of days (1–60), and press **Start scenario**.
- Watch the engine's stdout stream into the browser, with a status badge, current day, and a progress bar.
- Open any file the engine writes under `logs/` (per-agent decision logs, `day-NNN-api-calls.jsonl`, `day-NNN-bash-calls.jsonl`, the `metrics.jsonl` snapshot file, and the consolidated `run-<id>.log`) without leaving the browser.
- See an inventory chart (provider / manufacturer / retailer stock by day) and a customer-demand chart (placed / fulfilled / backordered) that refresh automatically while a run is in progress.
- Press **Stop** to send `SIGTERM` to the running engine, or **Clear logs/** to wipe the log directory between runs.

Only one run is active at a time (the engine drives the live apps). The runner records the run in-memory; restarting the manufacturer backend forgets the handle but the files on disk remain.

The REST API is the same one the CLI hits, so you can drive it from `curl` if you want:

```bash
curl -X POST http://localhost:8002/api/scenarios/start \
  -H 'Content-Type: application/json' \
  -d '{"config":"sim-stub.json","scenario":"holiday-rush.json","days":15}'

curl http://localhost:8002/api/scenarios/status
curl http://localhost:8002/api/scenarios/logs                       # list files
curl "http://localhost:8002/api/scenarios/logs/day-001-Factory.log" # tail one file
curl "http://localhost:8002/api/scenarios/metrics?limit=25"         # metrics.jsonl as JSON
```

### Option B — Manual day-by-day (CLI)

Advance apps in **downstream-first** order: retailer → manufacturer → provider.

**Manufacturer example (batch operations):**

```bash
# Inspect state
bin/manufacturer-cli day current
bin/manufacturer-cli capacity
bin/manufacturer-cli inventory
bin/manufacturer-cli sales orders --status PENDING
bin/manufacturer-cli production status
bin/manufacturer-cli purchase list
bin/manufacturer-cli price list

# Release multiple sales orders to production in one call
bin/manufacturer-cli production release --order SO-001 --order SO-002 --order SO-003

# Place multiple purchase orders in one call
bin/manufacturer-cli purchase create \
  --item "ChipSupply Co:Control Board:100" \
  --item "Fastparts:Stepper Motor:50"

# Adjust multiple wholesale prices in one call
bin/manufacturer-cli price set \
  --item "Basic300:450" \
  --item "Pro450:950"

# Advance the clock
bin/manufacturer-cli day advance
```

**Retailer example (batch operations):**

```bash
bin/retailer-cli catalog
bin/retailer-cli stock
bin/retailer-cli customers orders

# Fulfill multiple customer orders
bin/retailer-cli fulfill --order 1001 --order 1002

# Backorder multiple orders
bin/retailer-cli backorder --order 2001 --order 2002

# Place multiple purchase orders
bin/retailer-cli purchase create --item "Basic300:50" --item "Elite700:20"

# Adjust multiple retail prices
bin/retailer-cli price set --item "Basic300:445" --item "Elite700:1490"

bin/retailer-cli day advance
```

**Provider example (batch operations):**

```bash
bin/provider-cli catalog
bin/provider-cli stock
bin/provider-cli orders list

# Restock multiple products
bin/provider-cli restock \
  --item "Control Board:200" \
  --item "LCD Screen:100" \
  --item "Stepper Motor:150"

# Adjust multiple pricing tiers
bin/provider-cli price set \
  --item "Control Board:500:50" \
  --item "LCD Screen:200:35"

bin/provider-cli day advance
```

**Command execution order:**
```bash
# Advance in downstream-first order
bin/retailer-cli day advance
bin/manufacturer-cli day advance
bin/provider-cli day advance
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
│   ├── sim.json                       # All three roles driven by Claude skills
│   ├── sim-stub.json                  # Stub agents (no LLM, no API key needed)
│   ├── sim-manufacturer-only.json     # Skill only on the manufacturer
│   ├── sim-provider-only.json         # Skill only on the provider
│   └── sim-retailer-only.json         # Skill only on the retailer
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
│   ├── smoke-test.json        # 10-day steady-state scenario
│   ├── calm-market.json       # Control group — stable demand for 20 days
│   └── holiday-rush.json      # Black Friday + chip shortage + Christmas (25 days)
├── scripts/
│   └── dev-start.sh           # Starts all four services
├── skills/
│   ├── manufacturer-manager.md  # Claude Code skill: factory manager role
│   ├── provider-manager.md      # Claude Code skill: parts supplier role
│   └── retail-manager.md        # Claude Code skill: retail store role
├── logs/                      # Engine output (gitignored; surfaced via /scenarios)
│   ├── day-NNN-{Factory,PrinterWorld,ChipSupply Co}.log  # per-agent decisions
│   ├── day-NNN-api-calls.jsonl                            # every HTTP call made by the engine
│   ├── day-NNN-bash-calls.jsonl                           # every bash command an agent ran
│   ├── metrics.jsonl                                      # daily metric snapshot (one JSON per line)
│   └── run-YYYYMMDD-HHMMSS.log                            # consolidated stdout of one engine run
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
| `/scenarios` | Launch scenarios, watch live agent logs, browse `logs/` |
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
| GET | `/scenarios/` | List scenarios + configs (used by the UI launcher) |
| GET | `/scenarios/status` | Current run record (status, current day, stdout tail) |
| POST | `/scenarios/start` | Launch a run: `{config, scenario, days}` |
| POST | `/scenarios/stop` | SIGTERM the active engine subprocess |
| GET | `/scenarios/logs` | List files in `logs/` with size + mtime |
| GET | `/scenarios/logs/{name}` | Tail one log file (path-safe, `?max_bytes=` cap) |
| GET | `/scenarios/metrics` | `logs/metrics.jsonl` parsed (`?limit=`) |
| POST | `/scenarios/logs/clear` | Delete every file under `logs/` |

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

Three Markdown skills teach Claude Code how to play each role. Each one specifies the CLI commands the role may use, a short decision framework, and explicit *DO NOT* rules (most importantly: never call `day advance` — the engine owns the clock). **All action commands support batch operations** — agents supply multiple items to a single CLI call.

| Skill | Role | Key commands |
|---|---|---|
| `skills/manufacturer-manager.md` | Factory manager (the manufacturer app) | `production release --order ID ...` / `purchase create --item SUPPLIER:PRODUCT:QTY ...` / `price set --item MODEL:PRICE ...` |
| `skills/provider-manager.md`     | Parts supplier (the provider app)       | `restock --item PRODUCT:QTY ...` / `price set --item PRODUCT:TIER:PRICE ...` |
| `skills/retail-manager.md`       | Retail store (the retailer app)         | `fulfill --order ID ...` / `backorder --order ID ...` / `purchase create --item MODEL:QTY ...` / `price set --item MODEL:PRICE ...` |

### Where the agent's output ends up

Each `claude --print` invocation writes its complete reasoning trace to a per-day file under `logs/`:

```
logs/day-001-Factory.log       # prompt sent, every tool call + stdout, final response
logs/day-001-PrinterWorld.log
logs/day-001-ChipSupply Co.log
logs/day-001-api-calls.jsonl   # every HTTP call the engine itself made
logs/day-001-bash-calls.jsonl  # every bash command issued by an agent
logs/metrics.jsonl             # one JSON snapshot per simulated day
```

### Running the three skills

```bash
# Whole supply chain, real LLM (requires authenticated `claude` CLI)
.venv/bin/python -m engine.turn_engine config/sim.json scenarios/holiday-rush.json 20

# Isolate one role at a time to test a skill (others fall back to stubs)
.venv/bin/python -m engine.turn_engine config/sim-manufacturer-only.json scenarios/smoke-test.json 3
.venv/bin/python -m engine.turn_engine config/sim-provider-only.json    scenarios/smoke-test.json 3
.venv/bin/python -m engine.turn_engine config/sim-retailer-only.json    scenarios/smoke-test.json 3
```

…or do all of this from the **Scenarios** tab in the web UI. The page launches the same engine, streams stdout into the browser, and lets you open any of the per-day files above without leaving the page.

If an agent behaves poorly, rewrite the skill file — not the engine. The engine is deliberately ignorant of business policy.
