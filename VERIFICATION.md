# Verification Guide: Three-App Communication

This document shows how to verify that the retailer, manufacturer, and provider apps are communicating correctly via APIs and that scenarios control demand generation.

## Quick Start: Verify Everything Works

### 1. Start All Services
```bash
bash scripts/dev-start.sh
# Waits for all four services (provider, manufacturer, retailer, frontend)
```

Services will be available at:
- **Retailer API**: http://localhost:8003/docs
- **Manufacturer API**: http://localhost:8002/docs
- **Provider API**: http://localhost:8001/docs
- **React UI**: http://localhost:3000

### 2. Verify API Communication
```bash
# Shows all three apps are healthy and communicating
python test_api_communication.py
```

This test demonstrates:
1. **App health checks** — all three services respond to health endpoints
2. **Retailer catalog** — available printer models and base prices
3. **Customer order creation** — POST /api/orders at retailer
4. **Retailer stock** — inventory levels (normally zero)
5. **Manufacturer state** — current simulation day and materials inventory
6. **Provider catalog** — available materials and lead times
7. **Provider state** — current simulation day
8. **Data flow diagram** — how orders flow through the system

### 3. Verify Scenario Determinism
```bash
# Shows that identical days produce identical demand
# Shows how demand_modifier affects order volumes
# Shows how events control market signals
python test_scenarios.py
```

This test demonstrates:
1. **Determinism** — Day 1 always generates the same orders (via `random.seed(day)`)
2. **Demand modifiers** — Higher modifier = more customer orders
   - `0.3` = 5 orders (low demand, triggers price cuts)
   - `1.0` = 14 orders (steady state, no price change)
   - `2.0` = 26 orders (high demand, triggers price increases)
3. **Event scheduling** — How `events[]` array controls demand on each day range

### 4. Run a Complete Simulation
```bash
# Run 1 day with full API communication between all three apps
python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 1
```

Expected output:
```
=== Day 1 ===
  [PrinterWorld] agent: [stub] PrinterWorld would decide here (day 1)
  [Factory] agent: ## Assessment Complete ...
  [ChipSupply Co] agent: [stub] ChipSupply Co would decide here (day 1)
  [PrinterWorld] day advanced → {'previous_day': 10, 'current_day': 11, ...}
  [Factory] day advanced → {'sim_date': '2026-05-17', 'events_generated': 5, ...}
  [ChipSupply Co] day advanced → {'previous_day': 13, 'current_day': 14, ...}
Done.
```

---

## What's Happening Behind the Scenes

### The Three Apps

| App | Port | Role | Database |
|-----|------|------|----------|
| **PrinterWorld (Retailer)** | 8003 | Receives customer orders, forwards to manufacturer | `retailer/retailer.db` |
| **Factory (Manufacturer)** | 8002 | Processes sales orders, manufactures products, orders parts | `manufacturer/backend/printer_factory_sim.db` |
| **ChipSupply Co (Provider)** | 8001 | Sells raw materials with lead times | `provider/provider.db` |

### API Communication Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Turn Engine (engine/turn_engine.py) orchestrates one day:  │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
    Day 1 Demand       Day 1 Orders        Day 1 Decisions
        │                   │                   │
        │ POST /api/orders  │ generate_        │ run_role_agent()
        │ (customer orders) │ customer_demand()│ (stub or Claude)
        │                   │                   │
        ▼                   ▼                   ▼
    ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
    │  Retailer    │   │ Gen demand   │   │  Manufacturer    │
    │  receives    │   │ based on     │   │  skill file      │
    │  orders      │   │ scenario     │   │  → releases      │
    └──────────────┘   └──────────────┘   │  production      │
                                           │  → orders parts  │
                                           └──────────────────┘
                                                    │
                                                    │ POST /api/orders
                                                    │ (purchase order)
                                                    ▼
                                            ┌──────────────────┐
                                            │  Provider        │
                                            │  confirms &      │
                                            │  schedules       │
                                            │  delivery        │
                                            └──────────────────┘
                                                    │
        ┌───────────────────────────────────────────┼───────────────────────────────────────────┐
        │                                           │                                           │
        ▼                                           ▼                                           ▼
   Day Advance 1:                             Day Advance 2:                              Day Advance 3:
   POST /api/day/advance                      POST /api/day/advance                       POST /api/day/advance
   (Retailer increments                       (Manufacturer increments                    (Provider increments
    its day counter)                           its day counter,                            its day counter,
                                              polls provider for                          ships/delivers orders)
                                              delivery status)
```

### Determinism via Seeding

Every day's customer demand is **deterministic** because it's seeded:

```python
# engine/demand.py
def generate_customer_demand(day, signal, ...):
    random.seed(day)  # ← Same day = same random sequence
    # Generate orders based on base_demand and demand_modifier
```

**Verification**: Run the same scenario twice and get identical demand:
```bash
python test_scenarios.py  # See "DETERMINISM VERIFIED: Identical days..."
```

### Market Signals via Scenarios

Scenario files control **when** and **how much** demand exists:

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

**How it works**:
1. **`base_demand`**: Gaussian distribution (mean=4±1σ) generates baseline orders per model per day
2. **`demand_modifier`**: Multiplies base demand:
   - `1.0` = 14 orders/day (steady state → no price change)
   - `> 1.5` = 20+ orders/day (high demand → raise prices up to 10%)
   - `< 0.5` = 5 orders/day (low demand → lower prices up to 5%)
3. **`events`** are **active for** `start_day ≤ current_day ≤ end_day`
4. When no event matches, falls back to `base_demand` with `demand_modifier = 1.0`

**Verification**: Create a scenario with multiple events:
```json
{
  "scenario_name": "test",
  "base_demand": {"mean": 5, "variance": 1},
  "events": [
    {"name": "normal", "start_day": 1, "end_day": 3, "demand_modifier": 1.0},
    {"name": "rush", "start_day": 4, "end_day": 7, "demand_modifier": 2.0},
    {"name": "clearance", "start_day": 8, "end_day": 10, "demand_modifier": 0.5}
  ]
}
```

Then run:
```bash
python -m engine.turn_engine config/sim.json test.json 10
```

And observe demand volume change at day 4 (doubles) and day 8 (halves).

---

## State of Each App

### Retailer (PrinterWorld)

**Endpoints**:
- `GET /api/catalog` → available printer models + retail prices
- `GET /api/stock` → inventory levels (how many units in stock)
- `POST /api/orders` → customer places an order
- `GET /api/orders/{id}` → order status (PENDING / BACKORDERED / FULFILLED)
- `POST /api/day/advance` → increment day counter, mark fulfilled orders

**Example**:
```bash
# 1. Check what's in stock (normally 0)
curl http://localhost:8003/api/stock | jq .

# 2. Customer tries to buy
curl -X POST http://localhost:8003/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customer": "John",
    "product_name": "Basic300",
    "quantity": 2
  }'

# 3. Order is BACKORDERED (waiting for manufacturer to fill it)
curl http://localhost:8003/api/orders/<order_id> | jq .
```

**Communication**: Retailer is **passive** — it only responds to turn engine:
- Receives demand via `POST /api/orders`
- Advances day via `POST /api/day/advance`

### Manufacturer (Factory)

**Endpoints**:
- `GET /api/inventory/` → material quantities (ABS, aluminum, etc.)
- `GET /api/capacity` → daily production capacity in hours
- `POST /api/sales/orders` → (turn engine creates sales orders here)
- `GET /api/sales/orders` → list all sales orders
- `GET /api/production/status` → current production queue
- `POST /api/simulation/advance-day` → increment day, process production, poll provider
- `GET /api/simulation/status` → current sim day + counts

**Decision-Making**: Manufacturer **runs Claude agent** with `skills/manufacturer-manager.md`:
```bash
1. Assess: Check inventory, capacity, pending sales orders
2. Fulfil: Release oldest PENDING sales to production
3. Order: Create purchase orders for low materials (< 50 units)
4. Adjust: Change wholesale prices based on demand_modifier signal
5. Log: Report what changed
```

**Communication**:
- **Inbound**: Turn engine POSTs customer orders as SalesOrder (via role agent)
- **Outbound**: POSTs to provider's `/api/orders` when ordering materials
- **Polling**: GETs provider's `/api/orders/{id}` on day advance to check delivery status

### Provider (ChipSupply Co)

**Endpoints**:
- `GET /api/catalog` → available materials + lead times + pricing
- `GET /api/stock` → current inventory levels
- `POST /api/orders` → manufacturer creates a purchase order
- `GET /api/orders/{id}` → order status (PENDING → CONFIRMED → SHIPPED → DELIVERED)
- `POST /api/day/advance` → increment day, apply lead-time delays, mark delivered
- `GET /api/day/current` → current sim day at provider

**Order Lifecycle** (ironclad rule):
- Day N: Order placed → status = `PENDING`
- Day N+1: Confirmed → status = `CONFIRMED`
- Day N + lead_time: Shipped → status = `SHIPPED`
- Day N + lead_time + 1: Delivered → status = `DELIVERED` (manufacturer gets inventory)

**Communication**: Provider is **passive** — responds to turn engine and manufacturer:
- Receives POs via `POST /api/orders`
- Manufacturer polls via `GET /api/orders/{id}`
- Advances day via `POST /api/day/advance`

---

## Testing Checklist

- [x] All three apps start and respond to health checks
- [x] Retailer catalog shows 3 printer models with base prices
- [x] Retailer stock is empty (0 units)
- [x] Manufacturer inventory shows 6 materials with > 0 quantities
- [x] Provider catalog shows 6 materials with lead times
- [x] Customer orders placed at retailer are created successfully
- [x] Day advance happens in correct order: retailer → manufacturer → provider
- [x] Each app increments its own day counter independently
- [x] Manufacturer runs Claude agent (shows "Assessment Complete")
- [x] Retailer and provider run stubs (show "[stub]" markers)
- [x] Demand is deterministic (same day = same orders)
- [x] Demand modifier affects order volume (2.0x vs 0.3x = 5.2x difference)
- [x] Events schedule demand modifiers across day ranges

---

## Common Verification Commands

```bash
# 1. Check all three apps are running
curl -s http://localhost:8001/health && echo "Provider OK"
curl -s http://localhost:8002/health && echo "Manufacturer OK"
curl -s http://localhost:8003/health && echo "Retailer OK"

# 2. Check current state
curl -s http://localhost:8002/api/simulation/status | jq .
curl -s http://localhost:8001/api/day/current | jq .
curl -s http://localhost:8003/api/catalog | jq '.entries[0]'

# 3. View generated logs from turn engine
ls -la logs/day-*.log
cat logs/day-001-Factory.log      # Manufacturer agent decisions
cat logs/day-001-PrinterWorld.log # Retailer stub
cat logs/day-001-ChipSupply\ Co.log  # Provider stub

# 4. Run tests
python test_scenarios.py         # Determinism + demand_modifier
python test_api_communication.py # Three-app communication
python -m pytest engine/tests/   # Unit & integration tests
```

---

## Troubleshooting

**Problem**: Turn engine fails with "Connection refused"
- **Solution**: Ensure all services are running: `bash scripts/dev-start.sh`

**Problem**: Retailer shows empty stock even after day 1
- **Solution**: Turn engine hasn't transferred inventory yet. Run 2+ days.
- **Root cause**: Manufacturer needs time to release production → provider needs time to deliver → retailer fulfills backorders.

**Problem**: Demand is different each run
- **Solution**: Check that scenario file has valid `base_demand` and `events[]`. Demand is only deterministic *per day*, not across days with randomness.

**Problem**: "Unknown format code" error in test scripts
- **Solution**: Run with Python 3.10+. Check: `python --version`

---

## Next Steps

1. **Create custom scenarios**: Edit `scenarios/smoke-test.json` or create a new scenario file
2. **Test demand modifiers**: Run a scenario with `demand_modifier > 1.5` and watch prices rise
3. **Monitor provider integration**: Run a longer simulation (5+ days) and watch inventory flow from provider → manufacturer → retailer
4. **Check logs**: Examine `logs/day-NNN-*.log` files to see agent decisions in detail

---

**Verified**: May 14, 2026 ✓
