# Provider App

This folder contains the Week 6 **provider** application. The provider sells
raw materials to the manufacturer over a REST API.

The provider is its **own** independent process with its **own** SQLite
database and its **own** simulated-day counter. It exposes:

- a CLI (`python -m provider.cli`) for humans and, later, agents
- a REST API (FastAPI + Swagger) consumed by the manufacturer

The full design (data model, endpoints, lifecycle, scenario) lives in
[`docs/PRD-week6.md`](../docs/PRD-week6.md). The conventions every app in
this repo must follow live in [`CLAUDE.md`](../CLAUDE.md).

## Start The Provider

From the repository root:

```bash
cd provider
../.venv/bin/python scripts/seed_data.py
cd ..
.venv/bin/python -m provider.cli serve --port 8001
```

Open the provider API docs at:

```text
http://localhost:8001/docs
```

The SQLite database is `provider/provider.db`. The seed script is idempotent,
so it is safe to rerun when the database already exists.

## CLI Commands

Run these from the repository root:

```bash
.venv/bin/python -m provider.cli catalog
.venv/bin/python -m provider.cli stock
.venv/bin/python -m provider.cli orders list
.venv/bin/python -m provider.cli orders show <order_id>
.venv/bin/python -m provider.cli price set <product_or_id> <min_quantity> <unit_price>
.venv/bin/python -m provider.cli restock <product_or_id> <quantity>
.venv/bin/python -m provider.cli day current
.venv/bin/python -m provider.cli day advance
.venv/bin/python -m provider.cli export
.venv/bin/python -m provider.cli import <state.json>
```

## Running With The Manufacturer

`../scripts/dev-start.sh` starts the full Week 6 stack:

- provider API on `http://localhost:8001`
- manufacturer API on `http://localhost:8002`
- React frontend on `http://localhost:3000`

```bash
bash scripts/dev-start.sh
```

Then advance simulated days in this order:

```bash
.venv/bin/python -m provider.cli day advance
.venv/bin/python -m manufacturer.cli day advance
```

The manufacturer is configured in `manufacturer/config.json` to send
`ChipSupply Co` orders to `http://localhost:8001`.

## Tests

```bash
.venv/bin/pytest provider/tests
```
