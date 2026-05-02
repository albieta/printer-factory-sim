# 3D Printer Production Simulator

A multi-process simulation of a 3D printer supply chain.

- The **manufacturer** app (Week 5, completed) is a full-stack manufacturing
  simulation for a 3D printer factory: a React frontend for the planner's
  workflows and a FastAPI backend for simulation logic, inventory,
  suppliers, orders, and reporting.
- The **provider** app (Week 6, completed) is a separate process that
  sells raw materials to the manufacturer over a REST API. The
  manufacturer talks to it via HTTP. The provider has a CLI but no UI.

Each app owns its own SQLite database and its own simulated-day counter.
See [`CLAUDE.md`](CLAUDE.md) for the project conventions and
[`docs/PRD-week6.md`](docs/PRD-week6.md) for the current plan.

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 18 + Vite + TypeScript + Bootstrap |
| Backend | FastAPI + SQLAlchemy + Pydantic |
| Database | SQLite |
| Charts | Plotly |
| Tooling | npm, Python venv, pytest, Ruff, mypy |

## Dev Container Quick Start

Open the repository in the provided Docker dev container. On the first container creation, the devcontainer now does this automatically:

- installs Python, Node.js 20, and required OS packages
- creates `.venv`
- installs Python dependencies from `requirements.txt`
- installs frontend dependencies with `npm ci`
- seeds the SQLite database with starter data

On every container start, the devcontainer starts the full Week 6 stack:

- Provider API on `http://localhost:8001`
- Manufacturer FastAPI on `http://localhost:8002`
- Vite frontend on `http://localhost:3000`

VS Code now waits for that startup step to finish before marking the container ready, so the first open can take a little longer but should no longer expose a half-started app.

The devcontainer forwards ports `3000`, `8001`, and `8002`, so from your host
machine you can open:

- Frontend: `http://localhost:3000`
- Provider docs: `http://localhost:8001/docs`
- Manufacturer API docs: `http://localhost:8002/docs`
- Manufacturer ReDoc: `http://localhost:8002/redoc`

### Host Communication

The app runs inside the dev container, but VS Code Dev Containers forwards container ports to matching ports on the host machine. That means the frontend listens on `0.0.0.0:3000` inside the container, VS Code exposes that port on the host, and your browser reaches it through `http://localhost:3000`. In the Week 6 manual flow, the manufacturer backend runs on port `8002`, the provider runs on port `8001`, and the frontend talks to the manufacturer through Vite's `/api` proxy inside the container.

If you use VS Code Dev Containers, the Ports panel should show both forwarded ports automatically.

## Manual Run

If you want to run the full stack manually, or restart all services yourself,
use:

```bash
bash scripts/dev-start.sh
```

That command starts all Week 6 services together:

- provider API on `http://localhost:8001`
- manufacturer API on `http://localhost:8002`
- React frontend on `http://localhost:3000`

It also seeds the provider database before starting the provider. If services
are already running on those ports, the script reuses them instead of trying
to start duplicates.

Useful provider CLI commands:

```bash
.venv/bin/python -m provider.cli catalog
.venv/bin/python -m provider.cli stock
.venv/bin/python -m provider.cli orders list
.venv/bin/python -m provider.cli day current
.venv/bin/python -m provider.cli day advance
```

For the manual supply-chain turn order, advance the provider first, then the
manufacturer:

```bash
.venv/bin/python -m provider.cli day advance
.venv/bin/python -m manufacturer.cli day advance
```

## Manual Setup Without The Dev Container

If you are not using the devcontainer, set the project up with:

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
cd manufacturer/frontend && npm ci
cd ../backend && ../../.venv/bin/python scripts/seed_data.py
cd ../..
bash scripts/dev-start.sh
```

## Auto-Start Logs

When the devcontainer auto-starts the app, the stack log is written to:

- `/tmp/printer-factory-sim/full-stack.log`

That file is useful if a service fails during container startup.

## Project Layout

```text
printer-factory-sim/
├── .devcontainer/            # Devcontainer bootstrap and auto-start scripts
├── CLAUDE.md                 # Project conventions / Claude Code contract
├── docs/
│   ├── PRD.md                # Week 5 original PRD
│   ├── PRD2.md               # Week 5 retrospective PRD
│   ├── PRD-week6.md          # Week 6 PRD (multi-app supply chain)
│   └── report.md             # Week 5 report (in progress)
├── manufacturer/             # Week 5 app, extended in Week 6
│   ├── backend/              # FastAPI app, services, models, routes, seed script
│   └── frontend/             # React + Vite + TS frontend
├── provider/                 # Week 6 provider app: FastAPI, CLI, services, seed data
├── scripts/dev-start.sh      # Starts provider + manufacturer backend + frontend
├── requirements.txt          # Shared Python dependencies for both apps
└── README.md
```

## Main Application URLs

- `/` shows the factory overview dashboard
- `/orders` manages manufacturing orders
- `/inventory` shows stock levels and capacity
- `/suppliers` manages procurement sources
- `/production` tracks production flow
- `/reports` shows charts and historical metrics
- `/settings` manages simulation configuration

## API Highlights

Manufacturer API:

- `GET /api/config/` returns the current simulation configuration
- `GET /api/materials/` lists materials
- `GET /api/inventory/` returns stock levels
- `GET /api/orders/mfg/` lists manufacturing orders
- `POST /api/simulation/advance-day/` advances the simulation by one day
- `GET /api/events/` returns event history

Provider API:

- `GET /api/catalog` lists sellable raw materials and pricing tiers
- `GET /api/stock` returns provider stock levels
- `POST /api/orders` creates a provider-side purchase order
- `GET /api/orders/{id}` returns provider order lifecycle state
- `POST /api/day/advance` advances the provider simulation by one day

## Seed Data

The seeded database includes:

- 3 printer models
- 6 raw materials
- 6 suppliers
- starter inventory
- a default simulation configuration

The seed script is idempotent. If the database is already initialized, it exits without duplicating records.

Provider seed data lives in `provider/seed/seed-provider.json` and covers the
same six raw materials used by the manufacturer's BOMs.

## Development Commands

Run tests:

```bash
.venv/bin/pytest manufacturer/backend/tests
.venv/bin/pytest provider/tests
```

Run linting:

```bash
.venv/bin/ruff check .
```

Run type checking:

```bash
.venv/bin/mypy --strict manufacturer
```
