# PRD — Week 6: The Supply Chain (Part 1)

## Purpose

Week 5 delivered a single web application that simulates a 3D printer factory.
Week 6 turns that single app into the first half of a **distributed
supply-chain simulation**. We add a second, fully independent application —
the **provider** — that sells raw materials to the manufacturer over a REST
API. Each app owns its own database, its own simulated-day counter, and its
own command-line interface. A human operator drives both apps manually this
week; LLM agents and a turn engine come in Week 7 and Week 8.

This PRD is scoped strictly to the Week 6 deliverable. Retailers and end
customers are out of scope until Week 7.

## Document status

- Date: 2026-04-29
- Replaces (for Week 6 work) the role of `docs/PRD.md` and `docs/PRD2.md`,
  which describe the Week 5 single-app system. Those PRDs stay in the
  repository as historical artefacts.
- Tech stack is **deliberately** different from the suggestions in the
  course brief. See section "Tech stack: deviations from the brief".

## 1. Project summary (Week 6)

By the end of Week 6 the repository contains two cooperating processes:

- **manufacturer** (Week 5 app, extended): React + Vite + TypeScript frontend
  on port 3000, FastAPI backend on port 8000, SQLite database. Existing UI
  and existing REST API are preserved. New: a Python CLI (`manufacturer-cli`)
  and outbound HTTP calls to the provider for procurement.
- **provider** (new): a headless service. FastAPI backend on port 8001 with
  Swagger docs, SQLite database, Python CLI (`provider-cli`). No browser UI.

Both apps are started independently in their own terminals. The manufacturer
talks to the provider over REST. Each app advances its own simulated day.

## 2. Goals and non-goals

### 2.1 Goals

- Two separate processes communicate over a **versioned, documented REST
  contract**, not by sharing a database or Python module.
- A `provider-cli` and a `manufacturer-cli` are usable by a human today and,
  later, by an agent. The two CLIs follow the same `<resource> <action>`
  pattern.
- Every meaningful state change in either app is written to an `events`
  table that doubles as an audit trail.
- The five-day manual scenario from the Week 6 brief (place a 50-PCB order
  with a 3-day lead time, advance both apps day by day, see the parts arrive
  in the manufacturer's inventory on day 4) runs end-to-end.
- All Week 5 functionality (React dashboard, manufacturing orders,
  internal purchase orders, JSON export/import) keeps working unchanged.

### 2.2 Non-goals

- No retailer app, no end-customer demand from outside the manufacturer.
- No turn engine that orchestrates the day across processes. A human runs
  `provider-cli day advance`, then `manufacturer-cli day advance`, in that
  order.
- No LLM agent decision-making.
- No market signals (seasons, sales events, supply disruptions).
- No replacement of the Week 5 internal supplier model. The Week 5
  `Supplier`/`PurchaseOrder` tables continue to model the manufacturer's
  *internal* view of procurement; the new external provider sits behind one
  of those supplier rows. Section 6.2 explains the bridge.

## 3. Tech stack: deviations from the brief

The course brief suggests Streamlit, matplotlib, SimPy. We deliberately use a
different stack and continue with it for Week 6:

| Layer              | Brief's suggestion        | Our choice                                  |
|--------------------|---------------------------|---------------------------------------------|
| Manufacturer UI    | Streamlit                 | React 18 + Vite + TypeScript + Bootstrap    |
| Charts             | matplotlib                | Plotly                                      |
| Simulation engine  | SimPy                     | Custom turn-based service code              |
| Backend (both apps)| FastAPI + Pydantic        | FastAPI + Pydantic + SQLAlchemy (kept)      |
| Persistence        | SQLite (per app)          | SQLite (per app) (kept)                     |
| CLI (new)          | typer or click            | **Typer** (new dependency, Python-native)   |
| Cross-app HTTP     | httpx                     | **httpx** (kept; already in requirements)   |
| Tooling            | n/a                       | pytest, ruff, mypy (kept)                   |

The React + FastAPI choice was made and justified during Week 5 (see
`docs/PRD2.md` §3.1). Carrying the same backend stack into the provider lets
us reuse SQLAlchemy patterns, Pydantic schemas, and the same tests/lint
toolchain. Typer is added for the CLI because it composes naturally with
FastAPI (both are Pydantic-friendly, both auto-generate help/docs) and
because the brief explicitly accepts it.

## 4. Repository layout

```text
printer-factory-sim/
├── CLAUDE.md                          # living contract for Claude Code
├── README.md
├── requirements.txt                   # shared Python deps for both apps
├── .gitignore
├── .devcontainer/                     # devcontainer setup (manufacturer)
├── scripts/
│   └── dev-start.sh                   # starts manufacturer (backend+frontend)
├── docs/
│   ├── PRD.md                         # Week 5 original PRD
│   ├── PRD2.md                        # Week 5 retrospective PRD
│   ├── PRD-week6.md                   # this file
│   └── report.md                      # Week 5 report (work in progress)
├── manufacturer/
│   ├── backend/                       # FastAPI app (Week 5, extended in Week 6)
│   │   ├── main.py
│   │   ├── app/
│   │   │   ├── api/routes/
│   │   │   ├── services/
│   │   │   ├── models/
│   │   │   ├── schemas/
│   │   │   └── utils/
│   │   ├── cli/                       # NEW in Week 6 — Typer CLI
│   │   ├── scripts/seed_data.py
│   │   ├── tests/
│   │   └── printer_factory_sim.db     # gitignored
│   └── frontend/                      # React + Vite + TS dashboard
└── provider/                          # NEW in Week 6
    ├── main.py                        # FastAPI entrypoint
    ├── app/
    │   ├── api/routes/
    │   ├── services/
    │   ├── models/
    │   ├── schemas/
    │   └── utils/
    ├── cli/                           # Typer CLI for provider-cli
    ├── seed/
    │   └── seed-provider.json         # initial catalog/pricing/stock
    ├── scripts/seed_data.py
    ├── tests/
    └── provider.db                    # gitignored
```

The `manufacturer/` and `provider/` folders mirror each other so a reader who
understands one understands the other. They share `requirements.txt` and the
top-level `.venv/` for ergonomic reasons; if either app outgrows the shared
deps we will split.

## 5. The provider app

### 5.1 Data model

| Entity         | Notes                                                           |
|----------------|-----------------------------------------------------------------|
| `Product`      | A part the provider sells (`pcb`, `extruder`, `kit_piezas`, …). |
| `PricingTier`  | `(product_id, min_quantity, unit_price)`. Quantity-break pricing. |
| `Stock`        | Current on-hand inventory, per product.                         |
| `Order`        | Purchase order received from a buyer (the manufacturer).        |
| `Event`        | Append-only audit log.                                          |
| `SimState`     | Single-row key/value table holding `current_day`.               |

Order lifecycle (state machine):

```
pending → confirmed → in_progress → shipped → delivered
   ↓
rejected (cannot fulfil) | cancelled (sender cancelled)
```

`pending → rejected` and `pending → cancelled` are terminal short-circuits.
Status is stored as an explicit enum column, never as scattered booleans.

The "ironclad rule" applies: parts ordered on day N cannot arrive before day
`N + lead_time_days`. Minimum lead time is 1 day.

### 5.2 REST endpoints (provider, port 8001)

| Method | Path                  | Purpose                                                |
|--------|-----------------------|--------------------------------------------------------|
| GET    | `/api/catalog`        | Products and their pricing tiers.                      |
| GET    | `/api/stock`          | Current inventory.                                     |
| POST   | `/api/orders`         | Place a purchase order. Returns the created order.     |
| GET    | `/api/orders`         | List orders. Optional `?status=pending` filter.        |
| GET    | `/api/orders/{id}`    | Single order with full lifecycle timestamps.           |
| POST   | `/api/day/advance`    | Advance simulated day by 1.                            |
| GET    | `/api/day/current`    | Current simulated day.                                 |
| GET    | `/health`             | Liveness probe.                                        |
| GET    | `/docs`, `/openapi.json` | Auto-generated by FastAPI.                          |

`POST /api/orders` request body:

```json
{ "buyer": "manufacturer", "product_id": 1, "quantity": 50 }
```

Response: the persisted order, including computed `unit_price`,
`total_price`, `placed_day`, `expected_delivery_day`, `status`.

### 5.3 Day-advance behaviour

On `POST /api/day/advance`:

1. Move orders whose `expected_delivery_day == current_day + 1` from
   `shipped` to `delivered`. (Or: collapse intermediate states but keep the
   transitions in the event log — see CLAUDE.md.)
2. For pending orders that the provider has stock for, run
   `pending → confirmed → in_progress → shipped` and set `shipped_day`.
3. Increment `current_day`.
4. Write one event row per transition plus a `DAY_ADVANCED` summary row.

### 5.4 CLI (`provider-cli`)

```text
provider-cli catalog                      # list products with pricing tiers
provider-cli stock                        # show current inventory
provider-cli orders list [--status S]     # list orders, optional filter
provider-cli orders show <order_id>       # detail for one order
provider-cli price set <product> <tier> <price>
provider-cli restock <product> <quantity> # simulated upstream restock
provider-cli day advance                  # process one day
provider-cli day current                  # show current day
provider-cli export                       # dump full state to JSON
provider-cli import <file>                # load full state from JSON
provider-cli serve --port 8001            # start the FastAPI server
```

CLI commands are **thin wrappers** over a service layer in `provider/app/services/`.
The same service layer powers the REST API. No business logic lives in
`api/routes/` or `cli/`.

### 5.5 Seed data

`provider/seed/seed-provider.json` ships with the starting catalogue. The
catalog **must** cover every raw material the manufacturer's BOMs reference,
so the Week 6 scenario can run without manual stitching. At minimum:
`pcb`, `extruder`, `kit_piezas`, `cables_conexion`, `transformador_24v`,
`enchufe_schuko`, `sensor_autonivel`. Lead times default to 3 days; pricing
tiers follow a 1 / 20 / 200 break pattern.

## 6. Manufacturer changes (incremental, Week 5 → Week 6)

### 6.1 New surfaces

- A new Python CLI `manufacturer-cli` that wraps the existing service layer:

  ```text
  manufacturer-cli suppliers list
  manufacturer-cli suppliers catalog <supplier_name>
  manufacturer-cli purchase create --supplier <name> --product <id> --qty <n>
  manufacturer-cli purchase list
  manufacturer-cli inventory                # current stock
  manufacturer-cli day advance              # delegates to existing service
  manufacturer-cli day current
  ```

- A config file `manufacturer/config.json` declaring upstream providers:

  ```json
  {
    "manufacturer": {
      "port": 8002,
      "providers": [
        { "name": "ChipSupply Co", "url": "http://localhost:8001" }
      ]
    }
  }
  ```

  Note the manufacturer's port moves from 8000 (Week 5) to **8002**, to match
  the Week 6 brief's process layout. The dev-container scripts and
  `scripts/dev-start.sh` are updated accordingly. The frontend's Vite proxy
  must follow.

### 6.2 Bridging Week 5 suppliers to Week 6 providers

Week 5 already has a `Supplier` table and a `PurchaseOrder` table that model
procurement *internally*. We do **not** delete them. Instead:

- Each Week 5 `Supplier` row gains an optional `external_provider_url`
  column (and `external_product_id`). When set, it is a real upstream
  provider; when null, it is a stub-only Week 5 supplier kept for legacy
  scenarios.
- When the user (CLI or React UI) creates a purchase order against a
  supplier whose `external_provider_url` is set, the manufacturer service
  layer posts to that provider's `POST /api/orders` and stores the
  provider's order id alongside the local row.
- On `day advance`, for each pending purchase order whose supplier is
  external, the manufacturer polls the provider's `GET /api/orders/{id}`.
  When the provider reports `delivered`, the manufacturer adds the parts to
  inventory and marks its own row delivered. (Polling, not webhooks: see
  Week 6 brief §4.4.)

This keeps the Week 5 React UI working without a rewrite — the Settings
page just learns to display/edit the new column on `Supplier`.

### 6.3 Things that explicitly do not change

- Manufacturing-order workflow (release, reject, block on materials).
- Production-capacity model.
- Event log for manufacturer-side events (already implemented in Week 5).
- JSON full-state export/import.
- The React frontend pages list (`/`, `/orders`, `/inventory`, etc.).

## 7. Cross-app contract

| Concern                | Rule                                                              |
|------------------------|-------------------------------------------------------------------|
| Transport              | HTTP/JSON only. No shared module imports across apps.             |
| Schema version         | Provider returns a `schema_version` field on `/api/catalog` and `/api/orders`. Bumped when a breaking change ships. |
| Time                   | Each app owns its day counter. Human runs provider first, manufacturer second, every day. |
| Network failure        | Manufacturer surfaces the error; never silently swallows it. Retry policy is a one-shot timeout (10s) for Week 6. |
| Idempotency            | Order placement is **not** idempotent in Week 6. The manufacturer must not retry blindly on transient failures — surface the error. |
| Auth                   | None in Week 6. Single-tenant local dev only.                     |

## 8. Five-day manual scenario (acceptance criteria)

Setup (day 0):

- Provider stock: 500 PCBs, lead time 3 days, tier-20 price 32 EUR.
- Manufacturer inventory: 5 PCBs.
- Both apps on day 0.

Day 1:

1. `manufacturer-cli suppliers catalog "ChipSupply Co"` — shows the provider's catalog.
2. `manufacturer-cli purchase create --supplier "ChipSupply Co" --product pcb --qty 50`
3. Provider shows the order `pending` with `expected_delivery_day = 4`.
4. `provider-cli day advance` then `manufacturer-cli day advance`.

Days 2–3: advance both apps each day. Order remains in flight. Event logs
grow on both sides.

Day 4: advance provider first (it ships and delivers); then manufacturer
(it polls, sees the delivery, adds 50 PCBs). `manufacturer-cli inventory`
shows 55 PCBs.

Day 5: place a second order; advance; verify. Same shape, different numbers.

The scenario is the regression test for Week 6. If it passes by hand and via
a small `pytest` smoke, the week is done.

## 9. Testing strategy

- `manufacturer/backend/tests/` keeps the existing Week 5 tests. They must
  still pass after the refactor.
- `provider/tests/` adds:
  - unit tests for the order service (price-tier calculation, stock check,
    expected-delivery math),
  - unit tests for `advance_day()` (state transitions, event rows),
  - one end-to-end test that boots FastAPI in-process (TestClient), places
    an order, advances days, and asserts delivery.
- A new shared smoke test starts both processes and runs the five-day
  scenario via the two CLIs. This is the gate for the Week 6 demo.

## 10. Milestones (suggested, mapped to GitHub Issues)

1. Repo restructure (this PRD, CLAUDE.md, folder moves).
2. Provider data model + SQLAlchemy + seed loader.
3. Provider service layer (catalog, orders, day advance).
4. Provider FastAPI routes + Swagger.
5. Provider CLI (`provider-cli`).
6. Manufacturer CLI (`manufacturer-cli`).
7. Manufacturer outbound integration (`Supplier.external_provider_url`,
   create-order call, polling on day advance).
8. Five-day scenario passes by hand.
9. Tests, lint, mypy clean across both apps.
10. Two-page report + screenshots.

## 11. Open questions / decisions to revisit before coding

- **Should the manufacturer expose its CLI as a separate console script
  entry-point, or as `python -m manufacturer.cli`?** The brief shows
  `manufacturer-cli` as a binary. We will use `python -m` during dev and
  add a `pyproject.toml` console-script before Week 8.
- **Where does the day-advance polling happen on the manufacturer side —
  inside `SimulationService.advance_day()` or in a new
  `ProcurementService`?** Default: extend `SimulationService` step 2
  ("process due purchase-order deliveries") to query external providers
  for purchase orders flagged external. Revisit if it bloats.
- **Do we add a JSON-import command for the provider in Week 6 or punt to
  Week 8?** The Week 6 verification checklist requires JSON round-trip on
  both apps, so: in scope for Week 6.
