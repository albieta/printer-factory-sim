# 3D Printer Production Simulator

A full-stack manufacturing simulation for a 3D printer factory. The app includes a React frontend for operations workflows and a FastAPI backend for simulation logic, inventory, suppliers, orders, and reporting data.

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

On every container start, the devcontainer also starts:

- FastAPI on `http://localhost:8000`
- Vite frontend on `http://localhost:3000`

VS Code now waits for that startup step to finish before marking the container ready, so the first open can take a little longer but should no longer expose a half-started app.

The devcontainer forwards ports `3000` and `8000`, so from your host machine you can open:

- Frontend: `http://localhost:3000`
- FastAPI docs: `http://localhost:8000/docs`
- FastAPI ReDoc: `http://localhost:8000/redoc`

### Host Communication

The app runs inside the dev container, but VS Code Dev Containers forwards container ports to matching ports on the host machine. That means the frontend listens on `0.0.0.0:3000` inside the container, VS Code exposes that port on the host, and your browser reaches it through `http://localhost:3000`. The backend works the same way on port `8000`, and the frontend talks to it through Vite's `/api` proxy inside the container.

If you use VS Code Dev Containers, the Ports panel should show both forwarded ports automatically.

## Manual Run

If you want to run the app manually, or restart both services yourself, use:

```bash
bash scripts/dev-start.sh
```

That command starts both the backend and frontend together and stops both when you press `Ctrl+C`.
Inside the devcontainer, if those services are already running on ports `8000` and `3000`, the script reuses them instead of trying to start duplicates.

## Manual Setup Without The Dev Container

If you are not using the devcontainer, set the project up with:

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
cd frontend && npm ci
cd ../backend && ../.venv/bin/python scripts/seed_data.py
cd ..
bash scripts/dev-start.sh
```

## Auto-Start Logs

When the devcontainer auto-starts the app, logs are written to:

- `/tmp/printer-factory-sim/backend.log`
- `/tmp/printer-factory-sim/frontend.log`

Those files are useful if a service fails during container startup.

## Project Layout

```text
printer-factory-sim/
├── .devcontainer/            # Devcontainer bootstrap and auto-start scripts
├── backend/                  # FastAPI app, services, models, routes, seed script
├── frontend/                 # React + Vite frontend
├── scripts/dev-start.sh      # Manual one-command local runner
├── requirements.txt          # Python dependencies
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

- `GET /api/config/` returns the current simulation configuration
- `GET /api/materials/` lists materials
- `GET /api/inventory/` returns stock levels
- `GET /api/orders/mfg/` lists manufacturing orders
- `POST /api/simulation/advance-day/` advances the simulation by one day
- `GET /api/events/` returns event history

## Seed Data

The seeded database includes:

- 3 printer models
- 6 raw materials
- 6 suppliers
- starter inventory
- a default simulation configuration

The seed script is idempotent. If the database is already initialized, it exits without duplicating records.

## Development Commands

Run tests:

```bash
cd backend
../.venv/bin/pytest
```

Run linting:

```bash
.venv/bin/ruff check .
```

Run type checking:

```bash
.venv/bin/mypy --strict backend
```
