# Provider App

The **provider** application is an independent FastAPI service that sells raw
materials to the manufacturer over a REST API. It has its own SQLite database
(`provider/provider.db`) and its own simulated-day counter that the operator
advances separately from the manufacturer.

Full design rationale: [`docs/PRD-week6.md`](../docs/PRD-week6.md).
Conventions for the whole repo: [`CLAUDE.md`](../CLAUDE.md).

---

## Quick start

```bash
# 1. Seed the database (idempotent — safe to re-run)
cd provider
../.venv/bin/python scripts/seed_data.py
cd ..

# 2. Start the server
.venv/bin/python -m provider.cli serve --port 8001
```

Swagger UI: `http://localhost:8001/docs`

To start the whole stack (provider + manufacturer API + React UI):

```bash
bash scripts/dev-start.sh
```

---

## CLI reference

All commands are run from the **repository root** as
`.venv/bin/python -m provider.cli <command>`.

### `catalog`

List all products with lead times, current stock, and quantity-break pricing.

```bash
.venv/bin/python -m provider.cli catalog
```

Output columns: `id | product | lead (days) | stock | pricing tiers`

---

### `stock`

Show current on-hand inventory for every product.

```bash
.venv/bin/python -m provider.cli stock
```

Output columns: `product_id | product | quantity`

---

### `orders list [--status STATUS]`

List orders received from buyers, newest first. Optionally filter by lifecycle
status.

```bash
.venv/bin/python -m provider.cli orders list
.venv/bin/python -m provider.cli orders list --status PENDING
.venv/bin/python -m provider.cli orders list --status DELIVERED
```

Valid status values: `PENDING`, `CONFIRMED`, `IN_PROGRESS`, `SHIPPED`,
`DELIVERED`, `REJECTED`, `CANCELLED`.

Output columns: `id | buyer | product | qty | status | due_day`

---

### `orders show <order_id>`

Show full JSON detail for one order.

```bash
.venv/bin/python -m provider.cli orders show 1
```

JSON fields: `id`, `buyer`, `product`, `quantity`, `unit_price`, `total_price`,
`placed_day`, `expected_delivery_day`, `shipped_day`, `delivered_day`,
`status`, `status_reason`.

---

### `price set <product> <min_quantity> <unit_price>`

Create or update a quantity-break pricing tier for a product. `product` can be
the product name (e.g., `"Control Board"`) or its numeric id.

```bash
.venv/bin/python -m provider.cli price set "Control Board" 1 40.00
.venv/bin/python -m provider.cli price set "Control Board" 20 32.00
.venv/bin/python -m provider.cli price set 1 200 25.00
```

`min_quantity` must be a positive integer. `unit_price` must be a positive
decimal. An existing tier with the same `(product, min_quantity)` pair is
updated in place; a new one is created otherwise.

---

### `restock <product> <quantity>`

Add stock units to a product. Simulates an upstream delivery to the provider.
`product` can be the product name or its numeric id.

```bash
.venv/bin/python -m provider.cli restock "Control Board" 200
.venv/bin/python -m provider.cli restock 1 500
```

`quantity` must be a positive integer.

---

### `day current`

Show the provider's current simulated day.

```bash
.venv/bin/python -m provider.cli day current
```

---

### `day advance`

Advance the provider's simulated day by one tick. This:

1. Delivers any `SHIPPED` orders whose `expected_delivery_day` equals the new day.
2. Walks all `PENDING` orders through `CONFIRMED → IN_PROGRESS → SHIPPED`, setting `shipped_day`.
3. Increments the day counter.
4. Writes audit events for every transition and a summary `DAY_ADVANCED` event.

Returns a JSON summary: `previous_day`, `current_day`, `orders_shipped`,
`orders_delivered`.

```bash
.venv/bin/python -m provider.cli day advance
```

**Always advance the provider before the manufacturer** on the same simulated
day (the manufacturer polls provider order status during its own day advance).

---

### `export`

Dump the full provider state to JSON on stdout. Includes sim_state, products,
pricing tiers, stock, orders, and events.

```bash
.venv/bin/python -m provider.cli export > snapshot.json
.venv/bin/python -m provider.cli export | python -m json.tool   # pretty-print
```

---

### `import <path>`

Replace the provider's entire state from a JSON snapshot produced by `export`.
The snapshot must carry a matching `schema_version` field.

```bash
.venv/bin/python -m provider.cli import snapshot.json
```

---

### `serve [--host HOST] [--port PORT]`

Start the FastAPI server. Defaults: host `0.0.0.0`, port `8001`.

```bash
.venv/bin/python -m provider.cli serve
.venv/bin/python -m provider.cli serve --port 8001
.venv/bin/python -m provider.cli serve --host 127.0.0.1 --port 9000
```

---

## REST API reference

Base URL: `http://localhost:8001`

| Method | Path                  | Description                                                   |
|--------|-----------------------|---------------------------------------------------------------|
| GET    | `/health`             | Liveness probe. Returns `{"status": "ok"}`.                   |
| GET    | `/api/catalog`        | Products, pricing tiers, and stock quantities.                |
| GET    | `/api/stock`          | Current inventory for all products.                           |
| POST   | `/api/orders`         | Place a new order. Returns the created order.                 |
| GET    | `/api/orders`         | List orders. Optional `?status=PENDING` filter.               |
| GET    | `/api/orders/{id}`    | Single order with full lifecycle timestamps.                  |
| POST   | `/api/day/advance`    | Advance the simulated day by 1.                               |
| GET    | `/api/day/current`    | Current simulated day.                                        |
| GET    | `/api/events`         | Audit log. Optional `?event_type=`, `?from_day=`, `?to_day=`, `?limit=` filters. |
| GET    | `/docs`               | Swagger UI (interactive).                                     |
| GET    | `/openapi.json`       | OpenAPI schema.                                               |

### Place an order — `POST /api/orders`

```json
{ "buyer": "manufacturer", "product_id": 1, "quantity": 50 }
```

**Response (201):**

```json
{
  "schema_version": 1,
  "order": {
    "id": 1,
    "buyer": "manufacturer",
    "product_id": 1,
    "product_name": "Control Board",
    "quantity": 50,
    "unit_price": "32.00",
    "total_price": "1600.00",
    "placed_day": 1,
    "expected_delivery_day": 3,
    "shipped_day": null,
    "delivered_day": null,
    "status": "PENDING",
    "status_reason": null,
    "created_at": "2026-01-01T00:00:00"
  }
}
```

**Error responses:**
- `400` — invalid request (quantity ≤ 0, insufficient stock, lead_time_days < 1)
- `404` — product not found

Stock is reserved atomically at placement. Rejected orders (insufficient stock)
are also persisted so the audit log is complete.

---

## Order lifecycle

```
PENDING → CONFIRMED → IN_PROGRESS → SHIPPED → DELIVERED
    ↓
REJECTED (insufficient stock at placement time)
CANCELLED (not yet implemented in Week 6)
```

The **ironclad rule**: an order placed on day N cannot arrive before day
`N + lead_time_days` (minimum lead time: 1 day). The `expected_delivery_day`
field encodes this constraint.

---

## Advancing days — the correct order

The human operator (or a future turn engine) must advance days in this sequence:

```bash
# 1. Provider processes its day (ships pending orders, delivers due shipments)
.venv/bin/python -m provider.cli day advance

# 2. Manufacturer processes its day (polls provider, receives delivered stock)
.venv/bin/python -m manufacturer.cli day advance
```

Reversing the order means the manufacturer polls for status before the provider
has processed the transition, so deliveries arrive one day late.

---

## Five-day scenario (acceptance test)

This is the Week 6 acceptance scenario from `docs/PRD-week6.md §8`.

**Setup (day 0):** Provider has 500 Control Boards (lead 2 days, tier-20 price 32 EUR).
Manufacturer has 5 Control Boards.

**Day 1:**

```bash
# Check the catalog
.venv/bin/python -m manufacturer.cli suppliers catalog "ChipSupply Co"

# Place order for 50 Control Boards
.venv/bin/python -m manufacturer.cli purchase create \
    --supplier "ChipSupply Co" --product "Control Board" --qty 50

# Verify order is PENDING with expected_delivery_day = 3
.venv/bin/python -m provider.cli orders list

# Advance both apps
.venv/bin/python -m provider.cli day advance
.venv/bin/python -m manufacturer.cli day advance
```

**Day 2:** Repeat day advance. Order remains SHIPPED in provider.

**Day 3:**

```bash
# Provider delivers the order
.venv/bin/python -m provider.cli day advance

# Manufacturer polls and receives 50 Control Boards
.venv/bin/python -m manufacturer.cli day advance

# Verify 55 Control Boards
.venv/bin/python -m manufacturer.cli inventory
```

---

## Tests

```bash
.venv/bin/pytest provider/tests
```

Run the provider tests separately from the manufacturer tests — both packages
have a top-level `app/` module and pytest would confuse them if collected
together.

---

## Seed data

`provider/seed/seed-provider.json` ships the starting catalogue. The seed
covers all six materials referenced by the manufacturer's BOMs:

| Product        | Lead (days) | Initial stock | Pricing tiers (qty → €/unit) |
|----------------|-------------|---------------|-------------------------------|
| Control Board  | 3           | 500           | 1→40 / 20→32 / 200→25         |
| Stepper Motor  | 5           | 800           | 1→15 / 100→13.50 / 400→12     |
| Aluminum Frame | 7           | 300           | 1→45 / 50→42 / 200→38         |
| PLA Filament   | 4           | 1000          | 1→25 / 100→22.50 / 500→20     |
| ABS Filament   | 5           | 800           | 1→30 / 150→27 / 600→24        |
| LCD Screen     | 6           | 200           | 1→50 / 50→47 / 250→43         |
