# PRD — Week 7: The Supply Chain (Part 2)

## Purpose

Week 6 delivered two cooperating processes — the **manufacturer** (Week 5
factory app, extended) and the **provider** (new headless supplier) — talking
over a documented REST contract. A human drove both apps day by day.

Week 7 completes the supply chain and starts automating it. We add a third
process — the **retailer** — that sells finished printers to end customers.
We replace the human-with-CLI day driver with a **turn engine**: a single
script that injects customer demand, gives each role its turn, and advances
all apps in lock-step. And we introduce the first **Claude Code skill file**
— a markdown document that teaches an LLM agent how to play one role —
exercised end-to-end on the manufacturer.

By the end of Week 7 the system has every moving part it needs for the
fully autonomous Week 8 simulation. What is *not* in scope is full autonomy
across all three roles, market-signal scenarios, or multi-week analysis —
those land in Week 8.

## Document status

- Date: 2026-05-14
- Supersedes (for Week 7 work) the role of `docs/PRD-week6.md` as the
  current source of truth. The Week 6 PRD stays in the repository as a
  historical artefact; its acceptance gate (the five-day manual scenario)
  is preserved and must still pass.
- Tech stack continues the deliberate divergence from the course brief
  (no Streamlit, no SimPy, no matplotlib). See PRD-week6 §3.

## 1. Project summary (Week 7)

By the end of Week 7 the repository contains three cooperating processes
plus an orchestrator:

- **manufacturer** (Week 5/6, extended): React UI on 3000, FastAPI on 8002,
  SQLite. Existing surfaces preserved. New: accepts **inbound sales orders**
  from retailers, exposes sales/production/pricing CLI verbs, and
  consumes a skill file under the turn engine.
- **provider** (Week 6, unchanged): FastAPI on 8001, SQLite. No code
  changes required beyond keeping its CLI/REST contract stable.
- **retailer** (new): headless FastAPI service on 8003, SQLite, Typer CLI
  (`retailer-cli`). Designed from day one to run as multiple instances on
  different ports with different config files.
- **turn engine** (new): `engine/turn_engine.py` — a Python script that
  reads a config + a scenario, injects customer demand, runs each role's
  turn (deterministic stub or `claude --print` subprocess), and advances
  all three apps. Captures per-role agent output to `logs/`.
- **skill** (new): `skills/manufacturer-manager.md` — the first executable
  role contract. Run end-to-end for at least one full day.

Cross-app communication remains HTTP/JSON only. Each app keeps its own
database and its own simulated-day counter. The turn engine never reaches
into a database — it talks to each app through the same REST surface a
human or agent would use.

## 2. Goals and non-goals

### 2.1 Goals

- **Three apps on three ports** can be started independently and serve
  their REST surfaces (`/health`, `/docs`, `/api/...`) cleanly.
- A `retailer-cli` exists and follows the same `<resource> <action>`
  pattern as `manufacturer-cli` and `provider-cli`.
- A retailer can place purchase orders with the manufacturer; the
  manufacturer accepts inbound sales orders, processes them through the
  same lifecycle the provider already implements, and ships finished
  printers back.
- A **deterministic** turn engine runs a 3-day smoke scenario without
  errors and without human input — customer demand injected, each role
  ticked, all apps advanced.
- The same turn engine runs **one full day with the manufacturer driven
  by Claude Code via `--print`**, and the manufacturer's event log shows
  agent-driven decisions (PO created, manufacturing order released,
  price adjusted, etc.).
- Agent output is persisted to `logs/day-NNN-role.log` for later
  analysis.
- JSON full-state export/import works for all three apps.
- All Week 5 and Week 6 functionality keeps working unchanged: React
  dashboard, manual scenario, provider/manufacturer five-day handoff.

### 2.2 Non-goals

- No full autonomy across all three roles. Retailer and provider remain
  stubs (no LLM) in the engine this week. Skill files for those roles
  arrive in Week 8.
- No market-signal logic beyond the bare `demand_modifier` plumbing
  needed to make the scenario file shape stable for Week 8. Seasons,
  sales events, supply disruptions are Week 8.
- No multi-retailer experiments — the engine *supports* a list of
  retailers in its config, but the smoke scenario uses one.
- No turn-engine web UI. It is a CLI script.
- No customer-as-LLM modelling. Customer demand is a deterministic
  gaussian function of price and modifier.
- No analytical dashboards over agent logs. Logs are written to disk
  and read by humans this week.

## 3. Architecture

```text
            ┌──────────────────────────────────────────┐
            │           turn_engine.py                 │
            │  (orchestrator: reads scenario,          │
            │   injects demand, calls each role,       │
            │   advances all apps, captures logs)      │
            └────┬───────────────┬──────────────────┬──┘
                 │ HTTP          │ HTTP             │ HTTP
                 │ + subprocess  │ + subprocess     │ + subprocess
                 ▼               ▼                  ▼
         ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
         │  retailer    │ │ manufacturer │ │  provider    │
         │  :8003       │◀┤ :8002        │◀┤ :8001        │
         │  retailer.db │ │ printer_…db  │ │ provider.db  │
         └──────────────┘ └──────────────┘ └──────────────┘
                ▲                ▲                  ▲
                │                │                  │
         end customers     retailers buy      manufacturer buys
         (synthetic        printers           parts (Week 6 path
         demand)           (sales orders)     unchanged)
```

Hard rules carried forward from Week 6 and reinforced this week:

- No app reads any other app's database. All cross-app communication
  goes through HTTP/JSON.
- CLIs and REST routes are thin wrappers over a single service layer
  per app. The turn engine is a fourth, *separate* surface — it does
  not import services from any app; it calls REST.
- Every meaningful state change writes an `Event` row in the app that
  owns the state. The retailer gets its own `Event` table.
- Each app owns its own simulated-day counter. The turn engine is
  the only entity allowed to call `/api/day/advance` on any app once
  the engine is in use. Skills explicitly forbid agents from
  advancing the day themselves (see §6.2).

### 3.1 Order of operations per turn

Within one engine tick (one simulated day):

```text
1. Read today's market signal from the scenario file.
2. For each retailer in config: generate customer orders
   (deterministic gaussian; demand falls as price rises).
3. Each retailer takes its turn:
     fulfil what it can from stock, backorder the rest,
     order from manufacturer if low.
4. The manufacturer takes its turn:
     release sales orders to production where parts allow,
     order parts from the provider where stock is low,
     adjust wholesale prices if asked to by the skill.
5. The provider takes its turn:
     (Week 7: deterministic — nothing happens here beyond
      day advance.)
6. The engine POSTs /api/day/advance to retailer, then
   manufacturer, then provider — in that fixed order.
```

Downstream-first (customer demand → retailer → manufacturer → provider)
mirrors how a real supply chain reacts: an upstream actor only sees
demand once the downstream actor has decided what to ask for. The
order is deliberate. Deviating from it requires updating this PRD.

## 4. The retailer app (new)

### 4.1 Data model

| Entity            | Notes                                                            |
|-------------------|------------------------------------------------------------------|
| `CatalogEntry`    | `(product_name, retail_price)`. One row per printer model sold.  |
| `Stock`           | `(product_name, quantity)`. Finished-printer inventory.          |
| `CustomerOrder`   | An order placed by an end customer (synthetic in Week 7).        |
| `PurchaseOrder`   | An order this retailer placed with the manufacturer.             |
| `Event`           | Append-only audit log, mirroring the provider's pattern.         |
| `SimState`        | Single-row key/value table holding `current_day`.                |

`CustomerOrder` lifecycle:

```text
pending → fulfilled
   │
   └──► backordered ──► fulfilled   (when stock arrives)
   │
   └──► cancelled                    (sender cancelled)
```

`PurchaseOrder` lifecycle on the retailer side mirrors the manufacturer's
PO state machine (`pending → delivered | rejected`). The actual lifecycle
on the wire is owned by the manufacturer; the retailer polls on
day advance, exactly the same way the manufacturer polls the provider
today (Week 6 §6.2).

### 4.2 REST endpoints (retailer, default port 8003)

| Method | Path                       | Purpose                                              |
|--------|----------------------------|------------------------------------------------------|
| GET    | `/api/catalog`             | Models with retail prices.                           |
| GET    | `/api/stock`               | Finished-printer inventory.                          |
| POST   | `/api/orders`              | Customer places an order. Body: `{customer, model, quantity}`. |
| GET    | `/api/orders`              | List customer orders. Optional `?status=`.           |
| GET    | `/api/orders/{id}`         | Single customer order detail.                        |
| POST   | `/api/purchases`           | Place a purchase order with the manufacturer.        |
| GET    | `/api/purchases`           | List purchase orders the retailer has placed.        |
| POST   | `/api/day/advance`         | Advance simulated day by 1.                          |
| GET    | `/api/day/current`         | Current simulated day.                               |
| GET    | `/health`                  | Liveness probe.                                      |
| GET    | `/docs`, `/openapi.json`   | Auto-generated by FastAPI.                           |

`POST /api/orders` returns the persisted customer order including
`status` (`pending` immediately becomes `fulfilled` if stock is
available, otherwise `backordered`), `placed_day`, `unit_price`,
`total_price`.

### 4.3 CLI (`retailer-cli`)

```text
retailer-cli catalog                        # models and retail prices
retailer-cli stock                          # current finished-printer inventory
retailer-cli customers orders [--status S]  # list customer orders
retailer-cli customers order <id>           # detail for one order
retailer-cli fulfill <id>                   # ship to customer from stock
retailer-cli backorder <id>                 # mark as backordered explicitly
retailer-cli purchase list                  # POs placed with the manufacturer
retailer-cli purchase create <model> <qty>  # order printers from manufacturer
retailer-cli price set <model> <price>      # set retail price (>= wholesale × 1.15)
retailer-cli day advance                    # advance one day
retailer-cli day current                    # show current day
retailer-cli export                         # dump full state to JSON
retailer-cli import <file>                  # load full state from JSON
retailer-cli serve --config <path> --port <n>  # start the FastAPI server
```

CLI commands are thin wrappers over `retailer/app/services/`. The REST
routes use the same service layer. No business logic in `cli/` or
`api/routes/`.

### 4.4 Key behaviour

- **Customer order fulfilment**: when a `POST /api/orders` arrives, if
  stock is available it is decremented atomically and the order is
  written as `fulfilled` (with an event row). If not, the order is
  written as `backordered` and a `CustomerOrderBackordered` event row
  is appended.
- **Day advance**:
  1. Poll the manufacturer for each of this retailer's pending POs
     (`GET /api/sales/orders/{id}` on the manufacturer; see §5).
     If the manufacturer reports the PO `delivered`, increment local
     finished-printer stock and emit `PurchaseOrderDelivered`.
  2. Re-scan `backordered` customer orders. For each one whose model
     now has stock, decrement and flip status to `fulfilled` (emit a
     `BackorderFulfilled` event with both day stamps).
  3. Increment `current_day`. Emit `DayAdvanced`.
- **Pricing rule**: `retail_price >= wholesale_price × (1 + markup_pct/100)`
  where `markup_pct` comes from config and defaults to **30** with a
  hard floor of **15**. `price set` rejects (HTTP 400 / non-zero CLI exit)
  any value that violates the floor.

### 4.5 Configuration

Each retailer instance reads a JSON config file (path passed to
`retailer-cli serve --config`). No paths or ports may be hard-coded in
`.py` files:

```json
{
  "retailer": {
    "name": "PrinterWorld",
    "port": 8003,
    "db_path": "retailer/data/printerworld.db",
    "manufacturer": { "name": "Factory", "url": "http://localhost:8002" },
    "markup_pct": 30
  }
}
```

Designed for multiple instances: `retailer-cli serve --config retailer-1.json`
and `retailer-cli serve --config retailer-2.json --port 8005` must both
work side-by-side on different DB files. Week 7 only exercises one
instance, but the seams must be there.

### 4.6 Seed data

`retailer/seed/seed-retailer.json` ships with starting state aligned to
the manufacturer's BOM (printer model names match
`manufacturer/.../starter_profile.py`):

| Model      | Initial stock | Retail price (EUR) |
|------------|---------------|--------------------|
| Basic300   | 5             | 650                |
| Pro450     | 3             | 1,200              |
| Elite700   | 1             | 2,000              |

Retail prices are chosen to clear the 15 % floor over the wholesale
prices the manufacturer will set in §5.6.

## 5. Manufacturer changes (Week 6 → Week 7)

The manufacturer remains the most-changed app this week. Existing
Week 5/6 surfaces stay; the additions below are incremental.

### 5.1 New inbound surface: sales orders

The manufacturer learns to accept orders **from** retailers, in addition
to placing orders **with** providers (Week 6 outbound path, unchanged).

We add a new table `SalesOrder` rather than overloading the existing
`PurchaseOrder` table. Rationale: the existing `PurchaseOrder` models the
manufacturer's *outbound* procurement; adding a `direction` column would
collide with the per-direction state machines and FK relationships.
A new table mirrors how Week 6 introduced the provider's `Order` —
symmetric design, clear ownership.

```text
SalesOrder
  id (uuid)
  reference_code           # e.g. SO-0001
  retailer_name            # buyer
  product_id               # finished printer FK
  quantity
  status                   # PENDING → CONFIRMED → IN_PROGRESS → SHIPPED → DELIVERED
                           #         | REJECTED | CANCELLED
  unit_price               # wholesale price snapshot at order time
  total_price
  placed_day
  expected_ship_day
  shipped_day
  delivered_day
```

### 5.2 New REST endpoints

| Method | Path                          | Purpose                                                                |
|--------|-------------------------------|------------------------------------------------------------------------|
| POST   | `/api/sales/orders`           | Retailer places a sales order. Body: `{retailer, model, quantity}`.    |
| GET    | `/api/sales/orders`           | List sales orders. Optional `?status=`.                                |
| GET    | `/api/sales/orders/{id}`      | Single sales order with full lifecycle timestamps.                     |
| POST   | `/api/production/release`     | Release a sales order to production. Body: `{order_id}`.               |
| GET    | `/api/production/status`      | What is currently in progress.                                         |
| GET    | `/api/capacity`               | Daily assembly capacity and current-day utilisation.                   |
| GET    | `/api/prices`                 | Wholesale prices per model.                                            |
| POST   | `/api/prices`                 | Set wholesale price. Body: `{model, price}`.                           |

These are additions; Week 5/6 endpoints continue unchanged. The new path
group `/api/sales/...` keeps the namespace tidy and avoids collisions
with the existing internal `manufacturing_orders` endpoints.

### 5.3 New CLI verbs

```text
manufacturer-cli sales orders [--status S]   # list inbound sales orders
manufacturer-cli sales order <id>            # detail for one sales order
manufacturer-cli production release <id>     # release a sales order
manufacturer-cli production status           # current in-progress work
manufacturer-cli capacity                    # daily capacity + utilisation
manufacturer-cli price list                  # wholesale prices
manufacturer-cli price set <model> <price>   # set wholesale price
```

The existing `manufacturer-cli suppliers / purchase / inventory / day /
export / import` verbs stay.

### 5.4 Day-advance logic

Day advance on the manufacturer grows three new responsibilities while
keeping the Week 6 behaviour intact. The full ordered sequence becomes:

1. **Production progression** (new): orders released on previous days
   whose BOM materials are now in stock and whose assembly hours are
   complete move forward:
   - `confirmed → in_progress`: consume materials, decrement inventory,
     emit `MaterialConsumed` events.
   - `in_progress → shipped`: production duration elapsed; emit
     `OrderShipped` (decrement finished-printer stock at this point
     if no further hand-off step is added).
   - `shipped → delivered`: arrived at the retailer (one-day shipping
     latency for simplicity; the retailer polls and adds to its stock).
2. **Sales-order pricing/release sanity** (new): nothing automatic — the
   skill (or the human) must explicitly release orders. The day-advance
   path just verifies capacity invariants and emits
   `ProductionBlockedCapacity` if needed.
3. **Outbound procurement polling** (unchanged from Week 6): for each
   of *the manufacturer's own* pending purchase orders that targets an
   external provider, poll `GET /api/orders/{id}` and receive on
   delivery.
4. **Day counter increment + `DayAdvanced` event** (unchanged).

### 5.5 What does not change

- The Week 5 React UI keeps rendering manufacturing orders, internal
  inventory, and the procurement page. We do not add a retail-orders
  page in Week 7 (Week 8, if at all).
- `simulation_config.sim_date` remains the canonical day counter.
- Existing event types stay; we add `SALES_ORDER_PLACED`,
  `SALES_ORDER_RELEASED`, `SALES_ORDER_SHIPPED`, `SALES_ORDER_DELIVERED`,
  `WHOLESALE_PRICE_CHANGED`.

### 5.6 Wholesale price defaults

Seeded into the manufacturer at startup (if not already set):

| Model    | Wholesale (EUR) |
|----------|-----------------|
| Basic300 | 450             |
| Pro450   | 800             |
| Elite700 | 1,400           |

Retail floors at +15 % → 517.50 / 920 / 1,610 — the seed retail prices
clear all three.

## 6. The turn engine (new)

### 6.1 Layout

```text
engine/
├── turn_engine.py            # main script
├── demand.py                 # deterministic customer-demand generator
├── agent_runner.py           # subprocess wrapper for `claude --print`
└── __init__.py
config/
└── sim.json                  # which retailer/manufacturer/provider URLs + skills
scenarios/
└── smoke-test.json           # minimal scenario for Week 7
skills/
└── manufacturer-manager.md   # first skill (see §7)
logs/                         # per-day, per-role agent stdout (gitignored)
```

### 6.2 Phases

The engine is built in two phases, both shipped this week.

**Phase 1 — deterministic.** Every role's "make decisions" hook is a
stub: it prints `[stub] {role} would decide here` and returns. The
engine still injects customer demand, calls each app's day-advance, and
captures the per-day artifact. This proves the plumbing in isolation.

**Phase 2 — one agent.** Swap the manufacturer's stub for
`claude --print` invoked via `subprocess.run`. Retailer and provider
stay as stubs. The skill file (§7) is the only thing that changes
agent behaviour; the engine code stays the same.

### 6.3 `claude --print` invocation

```python
result = subprocess.run(
    ["claude", "--print", "--prompt", prompt],
    capture_output=True,
    text=True,
    cwd=role_working_dir,
    timeout=180,
)
Path(f"logs/day-{day:03d}-{role}.log").write_text(result.stdout)
```

- **Timeout**: 180 s per role. If a role's subprocess times out, the
  engine logs the timeout, writes a `[timeout]` marker into the log
  file, and moves on. A stuck agent does not freeze the simulation.
- **Working directory**: each role's CWD is the repo root so relative
  paths in the skill file (e.g. `./manufacturer-cli`) resolve. We add
  a convenience shim — `bin/manufacturer-cli` shell wrapper that
  execs `.venv/bin/python -m manufacturer.cli "$@"` — so the skill
  can use the binary-style name the brief describes.
- **Prompt shape**: the engine builds a small prompt that names the
  skill file, the current day, and the day's market signal (JSON).
  It does not paste the database — the agent uses the CLI to inspect
  state.

### 6.4 Customer demand generator

```python
def generate_customer_demand(day, signal, retailer_prices, base_price):
    base = signal.get("base_demand", {"mean": 5, "variance": 2})
    modifier = signal.get("demand_modifier", 1.0)
    orders = []
    for model, price in retailer_prices.items():
        mean_orders = base["mean"] * modifier
        price_factor = max(0.2, 1.0 - (price - base_price) / base_price)
        n = max(0, int(random.gauss(mean_orders * price_factor, base["variance"])))
        orders.extend([(model, 1)] * n)
    return orders
```

`base_price` for each model is the seeded retail price in §4.6. Demand
falls as the retailer's price rises above the seeded price; the floor of
`0.2` prevents demand from collapsing to zero on a small price bump.
`random.seed(day)` is called once per turn so the scenario is
reproducible — Week 8 will toggle this off for stochastic runs.

### 6.5 Scenario file shape

`scenarios/smoke-test.json`:

```json
{
  "scenario_name": "smoke-test",
  "base_demand": {"mean": 4, "variance": 1},
  "events": [
    {
      "name": "normal",
      "start_day": 1,
      "end_day": 10,
      "demand_modifier": 1.0,
      "description": "Steady state"
    }
  ]
}
```

Richer scenarios (seasons, supply shocks, sales events) are Week 8.
The shape is fixed in Week 7 so Week 8 can extend without breaking
the engine.

### 6.6 Engine config

`config/sim.json` enumerates the apps and (optionally) which skill
file each role uses:

```json
{
  "retailers": [
    {
      "name": "PrinterWorld",
      "url": "http://localhost:8003",
      "path": ".",
      "skill": null
    }
  ],
  "manufacturer": {
    "name": "Factory",
    "url": "http://localhost:8002",
    "path": ".",
    "skill": "skills/manufacturer-manager.md"
  },
  "providers": [
    {
      "name": "ChipSupply Co",
      "url": "http://localhost:8001",
      "path": ".",
      "skill": null
    }
  ]
}
```

`skill: null` means deterministic stub (Phase 1 behaviour for that role).

### 6.7 Running

```bash
.venv/bin/python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 3
```

Three simulated days, all three apps advanced once per tick, customer
demand injected at the retailer, manufacturer driven by Claude Code,
all output captured to `logs/day-001-*.log`, etc.

## 7. The first skill file

`skills/manufacturer-manager.md` is the executable contract between us
(the designers) and the LLM agent playing the manufacturer's role. Its
job is to be **small, specific, and impossible to misinterpret in the
ways that matter**. The verbatim skill text lives in the file itself;
the requirements below are the design constraints the file must satisfy.

### 7.1 Required sections

1. **Your Role** — one short paragraph naming the role and listing the
   day's responsibilities (review inbound sales orders, check
   inventory, release production, order parts, adjust prices).
2. **Available Commands** — every CLI invocation the agent may run,
   exact form. Grouped: "Check current state" / "Purchasing" /
   "Production" / "Pricing". The agent must not invent commands.
3. **DO NOT** — explicit forbiddens. At minimum:
   - Do **not** call `day advance` (the engine owns that).
   - Do **not** release more orders than daily capacity allows.
   - Do **not** order parts that will arrive after the orders needing
     them are overdue, when a faster supplier is available.
4. **Decision framework** — a numbered five-step process: Assess →
   Fulfil → Order → Adjust → Log reasoning. Each step names the CLI
   commands it should drive.
5. **Market signals** — how to interpret `demand_modifier` and
   `supply_modifier` numbers passed in the prompt. Week 7 only ships
   the `demand_modifier ≈ 1.0` case; Week 8 will exercise the others.
6. **When done** — print a 3–5 bullet summary and exit. No day advance.

### 7.2 Iteration loop

The skill file is expected to be rewritten 3–5 times before it behaves.
If the agent does something stupid on the smoke run, **rewrite the
skill, not the code**. This is the discipline the week is trying to
establish.

## 8. Repository layout (after Week 7)

```text
printer-factory-sim/
├── CLAUDE.md                          # updated for Week 7
├── README.md                          # updated with turn-engine usage
├── requirements.txt
├── .gitignore                         # add logs/
├── docs/
│   ├── PRD.md                         # Week 5 (frozen)
│   ├── PRD2.md                        # Week 5 retrospective (frozen)
│   ├── PRD-week6.md                   # Week 6 (frozen)
│   ├── PRD-week7.md                   # this file
│   ├── report-week6.md                # frozen
│   └── report-week7.md                # new; written at end of week
├── manufacturer/                      # extended in §5
├── provider/                          # unchanged from Week 6
├── retailer/                          # NEW
│   ├── main.py
│   ├── app/{api,services,models,schemas,utils}/
│   ├── cli/                           # retailer-cli (Typer)
│   ├── seed/seed-retailer.json
│   ├── scripts/seed_data.py
│   └── tests/
├── engine/                            # NEW — turn engine
│   ├── __init__.py
│   ├── turn_engine.py
│   ├── demand.py
│   └── agent_runner.py
├── config/
│   └── sim.json                       # NEW
├── scenarios/
│   └── smoke-test.json                # NEW
├── skills/
│   └── manufacturer-manager.md        # NEW
├── bin/
│   ├── manufacturer-cli               # shell shim → python -m manufacturer.cli
│   ├── provider-cli                   # shell shim → python -m provider.cli
│   └── retailer-cli                   # shell shim → python -m retailer.cli
└── logs/                              # gitignored
```

Mirroring `manufacturer/` and `provider/`, the new `retailer/` is also
self-contained. The shared `.venv/` and `requirements.txt` stay at the
root.

## 9. Cross-app contract (additions to Week 6 §7)

| Concern             | Rule                                                                                  |
|---------------------|---------------------------------------------------------------------------------------|
| Day-advance owner   | Once the engine is in use, only the engine calls `/api/day/advance` on any app. Skills explicitly forbid agents from doing so. |
| Day-advance order   | Engine advances retailer → manufacturer → provider (downstream first), every turn.    |
| Polling             | Retailer polls the manufacturer for PO arrivals exactly the way the manufacturer polls the provider in Week 6 (one-shot, 10 s timeout, surface errors). |
| Schema version      | The manufacturer's new endpoints follow the same `schema_version` convention as Week 6. |
| Auth                | None. Single-tenant local dev only. Week 8 may add a static-token check.              |

## 10. Acceptance criteria (Week 7)

### 10.1 Plumbing (Phase 1, deterministic engine)

- All three apps start independently:
  - `provider-cli serve --port 8001`
  - `manufacturer-cli serve --port 8002` (or existing `dev-start.sh`)
  - `retailer-cli serve --config retailer/seed/retailer-1.json --port 8003`
- `retailer-cli` core commands work (catalog, stock, customers orders,
  purchase create, day current).
- Manufacturer accepts `POST /api/sales/orders` from the retailer and
  processes the order through to delivery.
- Customer-demand generator injects orders at the retailer (visible
  via `retailer-cli customers orders`).
- `python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 3`
  runs to completion with `skill: null` for every role and zero errors.

### 10.2 First agent (Phase 2)

- `skills/manufacturer-manager.md` exists, contains every required
  section from §7.1, and is concise (< 2 KB body).
- `python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 1`
  with `skill: skills/manufacturer-manager.md` for the manufacturer:
  - completes within 5 minutes wall-clock,
  - writes `logs/day-001-manufacturer.log` with the agent's reasoning,
  - leaves at least one new row each in `events` (typed
    `SALES_ORDER_RELEASED` or `PO_CREATED`) on the manufacturer.
- A second day with the same skill still produces a sensible decision
  log (manual inspection — this is the iteration gate, not a test
  assertion).

### 10.3 Regression

- Week 6 five-day manual scenario still runs end-to-end.
- `pytest manufacturer/backend/tests provider/tests retailer/tests`
  passes.
- `ruff check .` clean; `mypy --strict` clean on retailer service
  layer and on the new manufacturer service code.
- JSON export/import round-trips for all three apps.
- React UI still renders manufacturing orders, internal inventory,
  procurement, with no functional regression.

## 11. Testing strategy

- **Retailer** (`retailer/tests/`, new):
  - service-layer unit tests for `place_customer_order`,
    `fulfil_from_stock`, `auto_fulfil_backorders_on_day_advance`,
    `place_purchase_order_with_manufacturer`, pricing-floor validation.
  - one end-to-end test using `TestClient`: customer orders →
    backorder when stock is empty → place PO → poll → fulfil on
    delivery.
- **Manufacturer** (`manufacturer/backend/tests/`, extended):
  - service test for `SalesOrderService.create_from_retailer`,
    `release_to_production`, `ship_when_capacity_allows`.
  - one cross-app smoke using `httpx.MockTransport` to assert the
    retailer-poll/manufacturer-respond handshake on day advance.
- **Engine** (`engine/tests/`, new and small):
  - unit test for `demand.generate_customer_demand` (deterministic with
    `random.seed`).
  - one integration test that boots all three apps as in-process
    `TestClient`s and runs `turn_engine.run_day` for 2 days with all
    stubs (no `claude --print` in CI — too slow and requires the agent).
- The Phase 2 agent run is **not** a CI test. It is run manually
  before submitting the report and the logs are committed (as part of
  the report's artifacts) but not asserted on.

## 12. Milestones

Suggested issue breakdown (each item one GitHub Issue, referenced in
the commit that closes it):

1. Retailer scaffolding — models, schemas, seed loader, SQLAlchemy.
2. Retailer service layer — catalog, stock, customer orders,
   backorder/fulfil, purchase orders, pricing floor.
3. Retailer REST + Swagger.
4. Retailer CLI (`retailer-cli`) including config-file support.
5. Manufacturer sales-orders inbound (`SalesOrder` model, service,
   `/api/sales/...` routes, `manufacturer-cli sales|production|price`
   verbs).
6. Manufacturer day-advance: production progression + ship to retailer.
7. Customer demand generator + smoke scenario file + sim config.
8. Turn engine Phase 1 (deterministic): one full 3-day run with all
   stubs and `logs/` capture.
9. `skills/manufacturer-manager.md` v1 + Phase 2 invocation through
   `claude --print` + manual iteration on the skill until day 1 looks
   sane.
10. Report (`docs/report-week7.md`) + screenshots + PDF.

## 13. Open questions / decisions to revisit before coding

- **Two databases for the retailer?** Multiple retailer instances need
  separate DBs. Initial answer: the config file's `db_path` decides;
  no shared DB. Confirmed before scaffolding.
- **Should the manufacturer ship printers to retailers physically, or
  fulfil instantaneously on day advance?** Week 7 default: one-day
  shipping latency between `shipped` and `delivered` to mirror the
  provider/manufacturer Week 6 latency. Revisit if the smoke scenario
  drags.
- **Where do agent logs live for the long term?** `logs/` is
  gitignored in Week 7; the report copies the *interesting* excerpts
  into `docs/report-week7.md`. Week 8 may want a structured log store
  for analytics.
- **`bin/<app>-cli` shell shims or `pyproject.toml` console scripts?**
  Week 7 uses shell shims for speed; Week 8 will move to console
  scripts via `pyproject.toml` when we package the project.
- **Engine sequencing: retailer-first vs manufacturer-first.** We
  chose downstream-first (§3.1) deliberately. Document this choice in
  the report and be ready to defend it during the live demo.
