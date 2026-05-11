# PRD — Week 7: The Full Supply Chain

## Purpose

Week 6 delivered two cooperating processes: a provider that sells raw
materials over REST and a manufacturer that buys them. Week 7 completes the
supply chain by adding a **retailer** that buys finished printers from the
manufacturer and sells them to end customers, a **turn engine** that
orchestrates all three apps in lockstep, and a **skill file** that describes
how a manufacturer-manager agent should reason — starting with a deterministic
stub and ending with a live Claude API call.

This PRD is scoped strictly to the Week 7 deliverable. Multi-retailer market
experiments, retailer/provider LLM agents, and the Week 8 report are out of
scope.

## Document status

- Date: 2026-05-11
- Supersedes: none. Extends `docs/PRD-week6.md` (preserved as historical artefact).
- Tech stack continues unchanged from Week 6 (see §3 for the one addition:
  the `engine` package).

---

## 1. Project summary (Week 7)

By the end of Week 7 the repository contains three cooperating processes:

- **provider** (Week 6, unchanged): FastAPI on port 8001, headless, sells
  raw materials. No changes to its REST contract this week.
- **manufacturer** (Week 5–6, extended): FastAPI on port 8002, React UI on
  port 3000. New in Week 7: a **sales API** that lets retailers buy finished
  printers, wholesale prices per model, and new CLI commands.
- **retailer** (new): FastAPI on port 8003, headless. Buys finished printers
  from the manufacturer, maintains its own inventory, and sells to end
  customers. Multi-instance capable via config file.

A new **turn engine** (`engine/` package) advances all three apps in lockstep
each simulated day: it reads a scenario file, generates customer demand,
runs each role's decision stub (or LLM agent), then advances all apps' day
counters. A **skill file** (`skills/manufacturer-manager.md`) defines the
manufacturer-manager agent's persona and decision framework for Claude. In
milestone 5, the turn engine upgrades from a Python stub to a real Claude API
call for the manufacturer role.

---

## 2. Goals and non-goals

### 2.1 Goals

- Three separate processes communicate over REST/JSON with no shared database
  or Python module. The provider-to-manufacturer contract from Week 6 is
  preserved unchanged.
- The retailer is **multi-instance capable**: two instances can run on
  different ports with different config files without code changes.
- The turn engine runs a deterministic `N`-day scenario from a JSON file,
  advancing all three apps in the correct order each day, generating
  customer demand, and writing a combined KPI log.
- A skill file for the manufacturer-manager role is checked into the
  repository and documented in this PRD.
- The manufacturer-manager role is upgraded from a Python stub to a Claude
  API call (`claude --print`) in milestone 5. The agent's output is captured
  to a log file, not stdout.
- The five-day end-to-end scenario (all three apps) passes in an automated
  acceptance test.

### 2.2 Non-goals

- No LLM agents for the retailer or provider this week.
- No multi-retailer market experiments (deferred to Week 8).
- No replacement of the Week 5/6 procurement model. The manufacturer's
  internal `PurchaseOrder` tables and provider-polling logic are preserved
  unchanged.
- No authentication between apps. Single-tenant local dev only.
- No changes to the provider app.

---

## 3. Repository layout (delta from Week 6)

```text
printer-factory-sim/
├── CLAUDE.md
├── README.md
├── requirements.txt           # add: nothing new for Week 7 (httpx, fastapi,
│                              #   typer, sqlalchemy already present)
├── setup.cfg
├── scripts/
│   ├── dev-start.sh           # unchanged
│   └── dev-start-all.sh       # NEW: starts all three apps + engine watch mode
├── docs/
│   ├── PRD.md                 # Week 5 (unchanged)
│   ├── PRD2.md                # Week 5 retrospective (unchanged)
│   ├── PRD-week6.md           # Week 6 (unchanged)
│   └── PRD-week7.md           # this file
├── skills/                    # NEW: skill files for LLM agents
│   └── manufacturer-manager.md
├── engine/                    # NEW: turn engine package
│   ├── __main__.py            # entry point: python -m engine
│   ├── runner.py              # main turn loop
│   ├── demand.py              # customer demand generation
│   ├── agents.py              # decision stubs + LLM integration
│   ├── kpi.py                 # KPI collection and CSV log
│   └── scenarios/
│       └── week7-default.json # default 5-day scenario
├── manufacturer/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── api/routes/
│   │   │   │   └── sales.py   # NEW: POST /api/orders, GET /api/prices
│   │   │   ├── models/models.py  # NEW: SalesOrder table, wholesale_price col
│   │   │   ├── schemas/schemas.py
│   │   │   └── services/
│   │   │       └── sales_service.py  # NEW
│   │   └── cli/__main__.py    # extended: sales, price subcommands
│   └── frontend/              # unchanged
├── retailer/                  # NEW in Week 7
│   ├── main.py
│   ├── app/
│   │   ├── api/routes/
│   │   ├── services/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── utils/
│   ├── cli/
│   │   └── __main__.py
│   ├── seed/
│   │   └── seed-retailer.json
│   ├── scripts/
│   │   └── seed_data.py
│   └── tests/
└── provider/                  # unchanged from Week 6
```

---

## 4. Retailer app

### 4.1 Data model

| Entity          | Notes                                                                  |
|-----------------|------------------------------------------------------------------------|
| `CatalogItem`   | Printer model the retailer sells, plus its retail price.               |
| `Stock`         | Current on-hand inventory of finished printers, per model.             |
| `CustomerOrder` | Order received from an end customer. One row per unit or per batch.    |
| `PurchaseOrder` | Order placed by the retailer with the manufacturer.                    |
| `Event`         | Append-only audit log (`EventType` enum).                              |
| `SimState`      | Single-row key/value holding `current_day`.                            |

**`CustomerOrder` status lifecycle:**

```
pending → fulfilled
   ↓
backordered → fulfilled (when stock arrives on day advance)
   ↓
cancelled
```

**`PurchaseOrder` status lifecycle** (mirrors manufacturer's view):

```
pending → confirmed → in_progress → shipped → delivered
   ↓
cancelled | rejected
```

The retailer polls the manufacturer's `GET /api/orders/{id}` on each day
advance, identical to the pattern the manufacturer uses against the provider.
When the manufacturer reports `delivered`, the retailer adds printers to stock
and auto-fulfils any backordered customer orders in FIFO order.

**Price constraint (enforced at order placement):** the retailer's retail
price for a model must be at least `wholesale_price × (1 + markup_pct / 100)`.
`markup_pct` comes from config (default 30). The retailer fetches the current
wholesale price from `GET /api/prices` on the manufacturer at startup and on
each day advance.

**Multi-instance design:** every path — database file, log file, config file —
is resolved from the config provided at startup. No hardcoded paths or
singleton globals. Two retailer processes can run concurrently without
conflict.

### 4.2 Configuration

`retailer.json` (path passed via `--config` flag or `RETAILER_CONFIG` env var):

```json
{
  "retailer": {
    "name": "PrinterWorld",
    "port": 8003,
    "db_path": "retailer/retailer.db",
    "manufacturer": {
      "name": "Factory",
      "url": "http://localhost:8002"
    },
    "markup_pct": 30
  }
}
```

A second instance would use a different config file pointing to a different
`db_path` and `port`.

### 4.3 REST endpoints (retailer, port 8003)

| Method | Path                      | Purpose                                                  |
|--------|---------------------------|----------------------------------------------------------|
| GET    | `/api/catalog`            | Printer models with retail prices.                       |
| GET    | `/api/stock`              | Current finished-printer inventory.                      |
| POST   | `/api/orders`             | End customer places an order.                            |
| GET    | `/api/orders`             | List customer orders. Optional `?status=` filter.        |
| GET    | `/api/orders/{id}`        | Single customer order with lifecycle timestamps.         |
| POST   | `/api/purchases`          | Retailer places a purchase order with the manufacturer.  |
| GET    | `/api/purchases`          | List purchase orders placed with the manufacturer.       |
| GET    | `/api/purchases/{id}`     | Single purchase order with status.                       |
| POST   | `/api/day/advance`        | Advance simulated day by 1.                              |
| GET    | `/api/day/current`        | Current simulated day.                                   |
| GET    | `/health`                 | Liveness probe.                                          |
| GET    | `/docs`, `/openapi.json`  | Auto-generated by FastAPI.                               |

`POST /api/orders` request body:

```json
{ "model": "P3D Classic", "quantity": 2 }
```

Response: the persisted customer order including `placed_day`, `status`
(`pending` or `backordered` if no stock).

`POST /api/purchases` request body:

```json
{ "model": "P3D Classic", "quantity": 10 }
```

The retailer's service layer immediately POSTs to the manufacturer's
`POST /api/orders`, stores the manufacturer's returned order id, and
tracks the purchase order through the same polling-on-day-advance
mechanism used between manufacturer and provider.

### 4.4 Day-advance behaviour

On `POST /api/day/advance`:

1. Poll the manufacturer for each pending purchase order (`GET
   /api/orders/{id}`). For orders reported `delivered`, add printers to
   stock.
2. Auto-fulfil backordered customer orders in FIFO order, consuming newly
   arrived stock.
3. Fetch updated wholesale prices from `GET /api/prices` so the price
   constraint check remains current.
4. Increment `current_day`.
5. Write one `Event` row per stock update, per fulfilment, per backorder
   resolution, plus a `DAY_ADVANCED` summary row.

### 4.5 CLI (`retailer-cli`, run via `python -m retailer.cli`)

```text
retailer-cli catalog                         # list models with retail prices
retailer-cli stock                           # current finished-printer inventory
retailer-cli customers orders [--status S]   # list customer orders
retailer-cli customers order <order_id>      # detail for one customer order
retailer-cli fulfill <order_id>              # manually ship from stock
retailer-cli backorder <order_id>            # manually mark as backordered
retailer-cli purchase list                   # orders placed with manufacturer
retailer-cli purchase create <model> <qty>   # order printers from manufacturer
retailer-cli price set <model> <price>       # set retail price
retailer-cli day advance                     # process one day
retailer-cli day current                     # current simulated day
retailer-cli export                          # dump full state to JSON
retailer-cli import <file>                   # load state from JSON
retailer-cli serve [--config C] [--port P]   # start the FastAPI server
```

All commands accept `--config <path>` (or `RETAILER_CONFIG` env var) to
select the config file. This is the multi-instance hook.

### 4.6 Seed data

`retailer/seed/seed-retailer.json` ships with the starting catalogue. It
maps each printer model (from the manufacturer's starter profile) to an
initial retail price and zero starting stock:

| Model         | Retail price | Initial stock |
|---------------|-------------|---------------|
| P3D Classic   | 899 EUR     | 0             |
| P3D Pro       | 1249 EUR    | 0             |
| P3D Mini      | 649 EUR     | 0             |

Retail prices must exceed `wholesale_price × 1.15` (minimum 15% margin).
The seed loader validates this against the manufacturer's `/api/prices`
endpoint at seed time, or uses the config's `markup_pct` if the
manufacturer is not yet running.

---

## 5. Manufacturer changes (Week 7)

### 5.1 New data: sales orders and wholesale prices

Two additions to `manufacturer/backend/app/models/models.py`:

- **`SalesOrder`** table: inbound orders from retailers.

  | Column               | Type    | Notes                                  |
  |----------------------|---------|----------------------------------------|
  | `id`                 | UUID PK |                                        |
  | `buyer`              | VARCHAR | Retailer name from request body.       |
  | `model`              | VARCHAR | Printer model name.                    |
  | `quantity`           | INTEGER |                                        |
  | `unit_price`         | NUMERIC | Wholesale price at time of order.      |
  | `total_price`        | NUMERIC |                                        |
  | `status`             | ENUM    | `pending → released → in_progress → shipped → delivered` |
  | `placed_day`         | INTEGER |                                        |
  | `expected_delivery_day` | INTEGER |                                     |
  | `shipped_day`        | INTEGER | nullable                               |
  | `delivered_day`      | INTEGER | nullable                               |

  Status lifecycle for sales orders:

  ```
  pending → released → in_progress → shipped → delivered
      ↓
  cancelled | rejected (cannot fulfil within lead time or out of stock)
  ```

  The "ironclad rule" applies: a sales order placed on day N is not
  delivered before day `N + lead_time_days`. The manufacturer's lead time
  for finished printers is configurable (default: 2 days).

- **`WholesalePrice`** table (or column on an existing `Product` row):
  one wholesale price per finished printer model, editable via CLI and
  visible via `GET /api/prices`.

Existing `ManufacturingOrder`, `PurchaseOrder`, and `Inventory` tables are
unchanged.

### 5.2 New REST endpoints (manufacturer, port 8002)

| Method | Path                        | Purpose                                         |
|--------|-----------------------------|-------------------------------------------------|
| POST   | `/api/orders`               | Retailer places a purchase order for printers.  |
| GET    | `/api/orders`               | List sales orders. Optional `?status=` filter.  |
| GET    | `/api/orders/{id}`          | Single sales order — the retailer polls this.   |
| GET    | `/api/prices`               | Wholesale prices per model.                     |
| PUT    | `/api/prices/{model}`       | Update wholesale price for a model.             |

`POST /api/orders` request body:

```json
{ "buyer": "PrinterWorld", "model": "P3D Classic", "quantity": 10 }
```

Response: persisted sales order including `unit_price`, `total_price`,
`placed_day`, `expected_delivery_day`, `status`.

The manufacturer's sales service layer is separate from its procurement
service layer. New file: `manufacturer/backend/app/services/sales_service.py`.

### 5.3 Day-advance changes

The manufacturer's existing `SimulationService.advance_day()` gains one
additional step: process pending sales orders through the production pipeline.

Extended day-advance sequence for the manufacturer:

1. (existing) Poll provider for pending purchase-order deliveries; update
   raw-material inventory.
2. **(new)** For each pending sales order the manufacturer has capacity and
   materials for: run `pending → released → in_progress → shipped`. Mark
   `shipped_day`.
3. **(new)** For each sales order where `expected_delivery_day == current_day`:
   run `shipped → delivered`. The retailer will see this on its next poll.
4. (existing) Increment `current_day`.
5. Write event rows for every transition plus `DAY_ADVANCED`.

Production capacity is shared: if the manufacturer is producing for both
its own manufacturing orders and retailer sales orders, they compete for the
same daily capacity.

### 5.4 New CLI commands (manufacturer)

```text
manufacturer-cli sales orders [--status S]   # list inbound sales orders
manufacturer-cli sales order <order_id>      # detail for one sales order
manufacturer-cli price list                  # current wholesale prices
manufacturer-cli price set <model> <price>   # set wholesale price
```

These are added to the existing `manufacturer-cli` entrypoint.

---

## 6. Turn engine

### 6.1 Overview

The turn engine is a Python package at `engine/`. Run via:

```bash
.venv/bin/python -m engine \
    --scenario engine/scenarios/week7-default.json \
    --days 5 \
    [--seed 42] \
    [--log-dir logs/]
```

The engine is **headless** — it communicates with all three apps exclusively
over their REST APIs. It does not import any `app.*` module from any of the
three services.

### 6.2 Scenario file format

`engine/scenarios/week7-default.json`:

```json
{
  "seed": 42,
  "base_demand": { "mean": 5, "variance": 2 },
  "base_price": 799,
  "days": [
    { "day": 1 },
    { "day": 2, "demand_modifier": 1.5 },
    { "day": 3, "supply_modifier": 0.7 },
    { "day": 4 },
    { "day": 5, "demand_modifier": 0.8 }
  ],
  "apps": {
    "provider":     { "url": "http://localhost:8001" },
    "manufacturer": { "url": "http://localhost:8002" },
    "retailer":     { "url": "http://localhost:8003" }
  }
}
```

Fields per day entry:

| Field             | Default | Meaning                                              |
|-------------------|---------|------------------------------------------------------|
| `demand_modifier` | 1.0     | Scales mean customer demand up/down.                 |
| `supply_modifier` | 1.0     | Injected into manufacturer and provider agent prompts. |
| `price_shock`     | null    | Optional dict `{model: delta}` to shift retail prices temporarily. |

### 6.3 Customer demand generation

At the start of each day, before any agent decisions, the engine generates
customer orders for each retailer:

```python
import random

def generate_customer_demand(
    day: int,
    signal: dict,
    retailer_prices: dict[str, float],
    base_price: float,
    rng: random.Random,
) -> list[tuple[str, int]]:
    base = signal.get("base_demand", {"mean": 5, "variance": 2})
    modifier = signal.get("demand_modifier", 1.0)
    orders: list[tuple[str, int]] = []
    for model, price in retailer_prices.items():
        mean_orders = base["mean"] * modifier
        price_factor = max(0.2, 1.0 - (price - base_price) / base_price)
        adjusted_mean = mean_orders * price_factor
        n = max(0, int(rng.gauss(adjusted_mean, base["variance"])))
        orders.extend([(model, 1)] * n)
    return orders
```

Higher retail prices reduce demand. A `demand_modifier > 1.0` raises the
whole curve; `< 1.0` lowers it. The `rng` is seeded from `--seed` so runs
are reproducible. Each generated order is POSTed individually to
`POST /api/orders` on the retailer.

### 6.4 Order of operations per turn

The following sequence runs for each simulated day:

```
Turn Engine
  │
  ├─ 1. Read today's signals from scenario file
  │
  ├─ 2. Fetch retailer prices (GET /api/catalog on retailer)
  │
  ├─ 3. Generate customer demand → POST /api/orders to retailer (one per unit)
  │
  ├─ 4. Run RETAILER agent (stub or LLM)
  │       └─ Inspect stock; if below threshold, POST /api/purchases to manufacturer
  │
  ├─ 5. Run MANUFACTURER agent (stub or LLM)
  │       └─ Inspect sales orders; release production; inspect raw materials;
  │          order parts from provider if low
  │
  ├─ 6. Run PROVIDER agent (stub — no LLM this week)
  │       └─ No decisions for now; stub is a no-op
  │
  ├─ 7. Advance days (in order):
  │       POST /api/day/advance → retailer
  │       POST /api/day/advance → manufacturer
  │       POST /api/day/advance → provider
  │
  └─ 8. Collect KPIs from all three apps → append to logs/kpi.csv
```

**Rationale for advance order (retailer → manufacturer → provider):**
downstream actors advance first. When the retailer advances, it polls the
manufacturer for deliveries — the manufacturer's state for that day is
already set. When the manufacturer advances, it polls the provider for
raw-material deliveries — the provider's state for that day is already set.
The provider advances last, transitioning its own orders through
`in_progress → shipped → delivered` so those transitions are visible to the
manufacturer on the *next* day. This keeps the ironclad lead-time rule
intact across all three hops.

> Note: this reverses the Week 6 manual convention (provider first,
> manufacturer second). Under the turn engine the sequencing guarantees
> are provided by the engine itself, so the Week 6 manual order is
> superseded. Manual operation (without the engine) should still use the
> engine's order for consistency.

### 6.5 KPI log

After each day advance, the engine calls the following read endpoints and
appends one row to `logs/kpi.csv`:

| Column                        | Source                                     |
|-------------------------------|--------------------------------------------|
| `day`                         | Engine counter                             |
| `retailer_stock_total`        | Sum of `GET /api/stock` on retailer        |
| `retailer_pending_orders`     | Count from `GET /api/orders?status=pending` |
| `retailer_backordered`        | Count from `GET /api/orders?status=backordered` |
| `manufacturer_finished_stock` | Finished-printer inventory on manufacturer |
| `manufacturer_pending_sales`  | Count of pending sales orders              |
| `manufacturer_capacity_used`  | From `GET /api/production/status`          |
| `provider_stock_control_board`| `GET /api/stock` on provider               |
| `demand_modifier`             | From scenario file                         |

The CSV is created fresh each run (no append across runs). A `--log-dir`
flag controls where it lands; default is `logs/` relative to cwd.

### 6.6 Package layout

```text
engine/
├── __main__.py        # CLI entry point (Typer)
├── runner.py          # turn loop, wires together demand/agents/advance/kpi
├── demand.py          # generate_customer_demand()
├── agents.py          # RetailerAgent, ManufacturerAgent, ProviderAgent stubs
├── kpi.py             # KPI collection and CSV writing
└── scenarios/
    └── week7-default.json
```

The engine has no SQLAlchemy dependency. It speaks only HTTP.

---

## 7. Skill file: manufacturer-manager

### 7.1 Location and format

`skills/manufacturer-manager.md` is a structured Markdown file checked into
the repository. It defines the manufacturer-manager agent's persona, available
commands, decision framework, market-signal interpretation, and output format.
It is **not** executable itself — it is a prompt document loaded by the turn
engine and passed to `claude --print` (or the agent stub) at runtime.

### 7.2 Content specification

The skill file must contain the following sections:

**`## Your Role`** — one paragraph describing the manufacturer-manager's
position in the supply chain (buys raw materials from providers, converts them
to finished printers, sells wholesale to retailers).

**`## Available Commands`** — an exhaustive list of CLI commands the agent
may call, grouped by concern (check state, purchasing, production, pricing).
Each command gets a one-line description. Commands the agent must *not* call
(`day advance`, anything on provider or retailer directly) are listed under
**`## DO NOT`**.

**`## Decision Framework`** — a numbered, step-by-step procedure the agent
follows each day, in order:

1. **Assess.** Run read-only commands; summarise state in 2–3 sentences.
2. **Fulfil what you can.** Release pending sales orders where parts are
   in stock and capacity is available. Prioritise oldest orders.
3. **Order what you need.** For each part where stock is below two days
   of expected consumption, check suppliers and place the best purchase
   order. Justify supplier choice in one sentence.
4. **Adjust prices.** If orders exceed capacity by > 50% for 2+ consecutive
   days, raise wholesale prices 5–10%. If utilisation < 40% for 2+ days,
   lower them 5–10%. Never below cost + 15% margin.
5. **Log your reasoning.** Before each mutating command, print one line:
   `"releasing order 17 because P3D-Classic stock=8 and all parts available"`.

**`## Market Signals`** — how to interpret `demand_modifier` and
`supply_modifier` values injected by the turn engine into the prompt:

- `demand_modifier > 1.5`: high-demand period. Build inventory ahead;
  consider raising prices.
- `supply_modifier < 0.7`: constrained supply. Order earlier and larger.
- No signal / modifier ≈ 1.0: business as usual.

**`## When Done`** — the agent prints a 3–5 bullet summary of actions taken
and their rationale, then exits. It does not call `day advance`.

### 7.3 Versioning

The skill file carries a `## Version` line at the top (e.g. `v1.0 — Week 7`).
Breaking changes (new commands added, decision framework revised) increment
the version so diffs remain readable.

---

## 8. LLM integration (Milestone 5)

### 8.1 Mechanism

`engine/agents.py` contains a `ManufacturerAgent` class with two
implementations selected at runtime:

```python
class ManufacturerAgent:
    def decide(self, day: int, signals: dict) -> str:
        ...

class StubManufacturerAgent(ManufacturerAgent):
    """Deterministic rules: reorder at 2× daily consumption; release all
    pending sales orders if capacity allows."""

class LLMManufacturerAgent(ManufacturerAgent):
    """Calls `claude --print` with the skill file + today's state snapshot."""
```

The engine selects the implementation based on `--agent manufacturer=llm`
flag. Default (no flag) is the stub.

### 8.2 LLM call design

`LLMManufacturerAgent.decide()`:

1. Reads `skills/manufacturer-manager.md`.
2. Calls read-only manufacturer API endpoints to build a state snapshot
   (stock, pending sales orders, pending purchase orders, capacity).
3. Constructs a prompt: skill file + state snapshot + today's market signals.
4. Calls `claude --print` via `subprocess.run`, capturing stdout.
5. Parses the output for `manufacturer-cli` commands (lines that start with
   `manufacturer-cli`).
6. Executes each command via `subprocess.run` in order, capturing stdout/stderr.
7. Writes the full agent transcript (prompt + LLM output + command outputs)
   to `logs/manufacturer-agent-day-{N}.txt`.

The agent **never** calls `day advance`. The engine validates this by
checking parsed commands before execution and raising `AgentProtocolError`
if a forbidden command appears.

### 8.3 Acceptance

Milestone 5 is complete when:

- `skills/manufacturer-manager.md` exists and passes a schema check
  (all required sections present).
- Running `python -m engine --scenario ... --days 5 --agent manufacturer=llm`
  completes without error.
- `logs/manufacturer-agent-day-*.txt` files contain non-empty LLM output.
- The manufacturer event log contains at least one `SALES_ORDER_RELEASED`
  event that was triggered by the agent.

---

## 9. Cross-app contract additions (Week 7)

| Concern             | Rule                                                                |
|---------------------|---------------------------------------------------------------------|
| Retailer → Manufacturer | Same polling pattern as manufacturer → provider: POST to place order; GET `{id}` to track status. |
| Ironclad rule       | Applies at all three hops. Minimum lead time 1 day each.            |
| Network failure     | Retailer surfaces errors from manufacturer; engine surfaces errors from any app. No silent swallowing. |
| Idempotency         | Order placement is not idempotent. Engine must not retry on transient failure; surface and abort. |
| Auth                | None this week.                                                     |
| Schema version      | Manufacturer's new `/api/orders` (sales) returns `schema_version: "2"`. Provider's contract is `schema_version: "1"` and unchanged. |

---

## 10. Testing strategy

### 10.1 Retailer tests (`retailer/tests/`)

- Unit tests for `retailer/app/services/`:
  - Order fulfillment from stock.
  - Backorder enqueue and auto-fulfil on stock arrival.
  - Price constraint enforcement (below-margin price rejected).
  - Day-advance sequence: poll manufacturer, update stock, resolve backorders.
- One integration test using FastAPI `TestClient`: place customer order →
  purchase from manufacturer (mocked via `httpx.MockTransport`) → advance
  day → verify fulfilled.

### 10.2 Manufacturer sales tests (`manufacturer/backend/tests/`)

- Unit tests for `sales_service.py`:
  - Sales order creation, status transitions.
  - Capacity contention (sales orders compete with manufacturing orders).
  - Wholesale price read/write.
- Extend `test_operations_flow.py` to include a sales order cycle.

### 10.3 Turn engine tests (`engine/tests/`)

- Unit tests for `demand.py` (seeded RNG, price elasticity).
- Integration test: spin up all three apps with TestClient / in-process
  servers (or mock HTTP) and run a 3-day engine loop. Assert:
  - KPI CSV has 3 rows.
  - At least one customer order is fulfilled.
  - All three apps' `current_day` == 3 after the run.

### 10.4 End-to-end acceptance scenario

The five-day acceptance scenario (see §11) is the regression gate for Week 7.
It is run by hand and verified against the KPI log. A focused pytest fixture
(`tests/test_week7_e2e.py`) uses mocked HTTP to reproduce the same scenario
without booting real processes.

### 10.5 Lint and type checking

```bash
# Ruff (whole repo)
.venv/bin/ruff check .

# mypy — run each app from its own root
(cd retailer           && ../.venv/bin/mypy --config-file ../setup.cfg --explicit-package-bases app cli)
(cd manufacturer/backend && ../../.venv/bin/mypy --config-file ../../setup.cfg app)
(cd engine             && ../.venv/bin/mypy --config-file ../setup.cfg .)
```

The retailer and engine packages must be mypy-strict clean from day one.

---

## 11. Five-day acceptance scenario

Setup (day 0):

- Provider: 500 Control Boards in stock, on day 0.
- Manufacturer: 5 Control Boards, 0 finished printers, on day 0.
- Retailer: 0 printers, on day 0. `markup_pct = 30`.
- Scenario file: `base_demand = {mean: 3, variance: 1}`, no modifiers.

Run:

```bash
python -m engine \
  --scenario engine/scenarios/week7-acceptance.json \
  --days 5 \
  --seed 42 \
  --log-dir logs/acceptance/
```

Expected outcomes:

| Day | Expected event                                                            |
|-----|---------------------------------------------------------------------------|
| 1   | Engine generates ~3 customer orders per model → posted to retailer.       |
|     | Retailer agent places purchase order with manufacturer (no stock yet).    |
|     | Manufacturer agent orders Control Boards from provider (stock low).       |
|     | All three apps advance.                                                   |
| 2–3 | Customer orders accumulate as backordered; manufacturer processes POs.    |
| 4   | Provider delivers Control Boards; manufacturer completes production.       |
|     | Manufacturer delivers printers to retailer.                               |
| 5   | Retailer auto-fulfils backordered customer orders from newly arrived stock.|
|     | KPI log shows `retailer_backordered` drops to 0 (or near 0).             |

Validation checks:

- `logs/acceptance/kpi.csv` has 5 rows with `day` 1–5.
- Retailer event log contains at least one `CUSTOMER_ORDER_FULFILLED`.
- Manufacturer event log contains at least one `SALES_ORDER_DELIVERED`.
- Provider event log contains at least one `ORDER_DELIVERED`.
- All three apps report `current_day = 5`.

---

## 12. Milestones

### M1 — Retailer Data Model

**Scope:** `retailer/app/models/models.py`, `retailer/app/utils/database.py`,
`retailer/app/utils/config.py`, `retailer/seed/seed-retailer.json`,
`retailer/scripts/seed_data.py`.

No service logic yet. Config loading must be multi-instance safe.

**Gate:** `retailer-cli --config retailer.json catalog` and
`retailer-cli --config retailer.json stock` return empty-but-valid JSON.
mypy passes on the retailer models package.

---

### M2 — Retailer Service + CLI + REST

**Scope:** Full service layer (`order_service.py`, `stock_service.py`,
`day_service.py`, `event_service.py`), all REST routes
(`retailer/app/api/routes/`), full CLI (`retailer/cli/__main__.py`),
`retailer/main.py`.

**Gate:** All checklist commands in §4.5 succeed without error. A unit test
that mocks the manufacturer HTTP calls demonstrates:
- Customer order fulfilled from stock.
- Customer order backordered when stock is 0.
- Day advance with mocked manufacturer delivery auto-fulfils the backorder.

---

### M3 — Manufacturer Sales API

**Scope:** `manufacturer/backend/app/services/sales_service.py`,
`manufacturer/backend/app/api/routes/sales.py`,
`manufacturer/backend/app/models/models.py` (new `SalesOrder` and
`WholesalePrice` tables), new CLI commands (`sales`, `price`).

**Gate:** From the retailer CLI (with real running manufacturer):
1. `retailer-cli purchase create "P3D Classic" 5` succeeds.
2. Over 3 day advances, `retailer-cli purchase list` shows status reaching
   `delivered`.
3. `retailer-cli stock` shows 5 printers.

---

### M4 — Turn Engine (stub mode)

**Scope:** `engine/` package: `__main__.py`, `runner.py`, `demand.py`,
`agents.py` (stub implementations only), `kpi.py`,
`engine/scenarios/week7-default.json`.

**Gate:** `python -m engine --scenario engine/scenarios/week7-default.json --days 3 --seed 42` completes without error against live running apps. `logs/kpi.csv` has 3 rows. Event logs across all three apps tell a coherent story (at least one order at each layer).

---

### M5 — Skill File + LLM Upgrade

**Scope:** `skills/manufacturer-manager.md`,
`engine/agents.py` (`LLMManufacturerAgent` implementation).

**Gate:** Five-day acceptance scenario (§11) runs via:

```bash
python -m engine \
  --scenario engine/scenarios/week7-acceptance.json \
  --days 5 \
  --seed 42 \
  --agent manufacturer=llm \
  --log-dir logs/acceptance/
```

All validation checks in §11 pass. `logs/acceptance/manufacturer-agent-day-*.txt` files exist and contain non-empty LLM output. Manufacturer event log shows at least one decision-triggered `SALES_ORDER_RELEASED`.

---

## 13. Open questions

- **Retailer-to-manufacturer auth:** Still none. If Week 8 adds a second
  retailer instance, we may need a `buyer` header or API key. Track as a
  follow-up.
- **Sales order lead time:** Default of 2 days for finished-printer delivery
  is a placeholder. The manufacturer config should expose this as
  `sales_lead_time_days` for fine-tuning in Week 8 market experiments.
- **Provider agent (M5):** Provider stays a no-op stub in Week 7. Pricing
  intelligence for the provider (dynamic price adjustments) is deferred to
  Week 8.
- **Retailer LLM upgrade:** Deferred to Week 8 alongside the multi-retailer
  market experiment.
- **`claude --print` availability:** The LLM upgrade assumes `claude` CLI is
  on PATH in the dev environment. If it is not, `LLMManufacturerAgent` must
  fall back to the stub with a warning rather than crashing. Add a health
  check at engine startup.
- **Day counter alignment:** At the start of a run the engine should verify
  that all three apps are on the same simulated day. If they diverge (e.g.
  after a failed partial run), the engine must abort with a clear error rather
  than silently advancing misaligned apps.
