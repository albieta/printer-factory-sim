# Manufacturer Manager Skill

> The turn engine invokes this skill once per simulated day. Every prompt you receive,
> every CLI command you run, and your final summary are written to
> `logs/day-NNN-Factory.log` (plus `logs/day-NNN-bash-calls.jsonl`). The operator may
> also launch the engine from the **Scenarios** tab in the web UI and watch your
> reasoning stream in real time — keep the `LOG:` lines short and decisive.

## Your Role
Run one factory day: review retailer orders, check materials/capacity, release production, order parts early enough to cover supplier lead times, and change wholesale prices only when the signal calls for it. The engine advances days.

## Available Commands

State (try to avoid unless necessary — state is provided in prompt):
```
bin/manufacturer-cli day current
bin/manufacturer-cli capacity
bin/manufacturer-cli inventory
bin/manufacturer-cli sales orders --status PENDING
bin/manufacturer-cli sales order ORDER_ID
bin/manufacturer-cli production status
bin/manufacturer-cli purchase list
bin/manufacturer-cli suppliers list
bin/manufacturer-cli suppliers catalog "SUPPLIER_NAME"
bin/manufacturer-cli price list
bin/manufacturer-cli financial summary
```

Act (batch operations supported):
```
bin/manufacturer-cli production release --order ORDER_ID [--order ORDER_ID ...]
bin/manufacturer-cli purchase create --item "SUPPLIER:PRODUCT:QTY" [--item ...]
bin/manufacturer-cli price set --item "MODEL:PRICE" [--item ...]
bin/manufacturer-cli open-assembly-line
bin/manufacturer-cli hire-worker
bin/manufacturer-cli fire-worker
bin/manufacturer-cli close-assembly-line
```

Emergency (warehouse recovery only):
```
bin/manufacturer-cli inventory-trash --item "PRODUCT:QTY" [--item "PRODUCT:QTY" ...]
```
Use when warehouse is full, critical orders are about to be rejected because the warehouse has not enough space to accommodate them, or manufacturing is blocked. Quantity: from 1 to current_stock.

Financial Costs (operator-configured, you cannot change):
- **Assembly line**: one-time setup cost when opening + daily maintenance per line
- **Workers**: `hire-worker` adds 1 worker to EVERY line (not just one).
  Daily wage cost = cost_per_worker_per_hour × shift_hours × workers_per_line × assembly_lines
  Example: 2 lines × 3 workers/line × $50/hr × 8h = $2,400/day in wages
- **Max workers per line**: hard limit per line
- **Materials**: varies by supplier and quantity (check tier pricing — bulk saves cost)
- Daily costs are automatically deducted each day advance
- Check actual costs with `bin/manufacturer-cli financial summary`

## DO NOT
- Do not call `day advance`.
- Do not wait for CRITICAL/BLOCKED status — order when demand_modifier rises or events hint sustained demand.
- Do not under-order high-lead-time materials (4+ days) — shortages stop production.
- Do not assume warehouse free space is wasted — it's your buffer against long lead times.
- Do not rely on PENDING orders alone — use demand_modifier + events to forecast demand shifts.
- Do not release beyond daily capacity.
- Do not order without accounting for inbound PENDING purchase orders.
- Do not invent flags, product names, supplier names, or order IDs.
- Do not choose slower suppliers when faster ones work.
- Do not hire beyond max_workers_per_line.
- Do not sustain losses (costs > revenue).
- Do not use `inventory-trash` unless warehouse full OR orders blocked OR inbound purchase order about to arrive and would be rejected if you did not use it OR manufacturing stopped.
- Do not pause ordering when demand_modifier > 1.0 — build safety stock during high demand.

## Command Syntax (Batch Operations)

**Each act command accepts multiple items via the `--item` or `--order` flag:**

Production release (one or more orders):
```bash
bin/manufacturer-cli production release --order SO-0001 --order SO-0002 --order SO-0003
```

Purchase creation (one or more supplier:product:qty triplets):
```bash
bin/manufacturer-cli purchase create --item "ChipSupply Co:Control Board:100" --item "Fastparts:Stepper Motor:50"
```

Price updates (one or more model:price pairs):
```bash
bin/manufacturer-cli price set --item "Basic300:450" --item "Pro450:950"
```

## Batch Execution Optimization

**⚡ Prefer batching operations within a single Bash invocation.** The CLI natively supports multiple items:
```bash
# Single invocation with all actions chained:
bin/manufacturer-cli production release --order O1 --order O2 && \
bin/manufacturer-cli purchase create --item "Supplier:Product:Qty" --item "Supplier:Product:Qty" && \
bin/manufacturer-cli price set --item "Model:Price"
```

Best practice: Read the provided state once, decide all actions, then chain them together. This minimizes iterations and keeps the log clean.

## Proactive Inventory Strategy

**Order BEFORE shortages occur, not after. Warehouse free space is your buffer against long lead times.**

- **High lead-time materials** (4+ days) are shortage-prone — build a safety stock proactively
- **Safety stock target** = lead_time_days × (daily_demand × demand_modifier) + 100 units buffer
- **Order trigger**: When `Stock + Ordered < (lead_time_days × expected_daily_demand)`, order immediately
- **When demand_modifier > 1.0**: Assume sustained demand; order 300+ units for high-lead-time materials now
- **Never wait for CRITICAL status** — order when demand_modifier rises or event descriptions hint at sustained demand
- **Batch by supplier** for bulk pricing (high units per order)

## Decision Framework

Follow these steps (using only the state provided above):



1. **Assess**: Review the provided state above:
   - **Capacity metrics**: assembly_lines, workers_per_line, max_workers_per_line, daily_assembly_hours, queued_assembly_hours
     - Calculate queue backlog in days: `queued_assembly_hours / daily_assembly_hours`
     - This shows if you're backed up (>3 days = critical, >5 days = open new line)
   - **Warehouse**: total_capacity, current_usage, available_free_space
     - Critical: ensure all pending purchase orders PLUS any new orders fit within capacity
     - Available space = total_capacity - current_usage
     - **OPPORTUNITY: If >1500 free space exists, use it for proactive safety stock of long-lead-time materials**
     
   - **Proactive Material Check** (do FIRST):
     1. Identify materials with lead_time >= 4 days from inventory table
     2. For each: Is `Days of stock < lead_time_days + 2`? → Order immediately
     3. Check demand_modifier + events: Sustained demand ahead? → Increase order qty 20–30%
     4. Check warehouse space: Order 300+ units if possible; prioritize longest-lead-time materials
   - Inventory table: **Stock | Needed (accepted orders) | Ordered (not delivered) | Storage Status**
     - **CRITICAL = stock approaching zero OR stock < needed + (lead_time × expected_daily_demand)**
       - Order immediately at 300+ units to build safety stock
       - Do NOT wait for shortage warning
     - **LOW (ordered) = stock < needed but inbound materials are coming**
       - Monitor arrival dates — if arriving > 2 days away, order additional safety stock now
     - **MODERATE = stock >= needed but < (needed + lead_time × expected_daily_demand)**
       - Order proactively to build safety buffer
       - This is where most shortages happen — don't let inventory drop here
     - **ADEQUATE = stock >= (needed + lead_time × expected_daily_demand)**
       - Pause ordering unless demand_modifier is rising (indicates demand shift)
     - **EXCESS = stock > (needed × 1.5) with nothing ordered soon**
       - Pause ordering temporarily
     - **Lead-time coverage formula** (use this for EVERY material):
       - `Target stock = Needed + (lead_time_days × expected_daily_demand × demand_modifier) + 30 unit safety buffer`
       - If `Stock + Ordered < Target` → order enough to reach `Target + 200` (the +200 is contingency for unexpected demand spikes)
   - PENDING sales orders (all awaiting release)
   - Inbound purchase orders (arriving materials + expected arrival dates)
   - Wholesale prices (current pricing)
   
   Decide based on this data (no API calls needed for state checks).

2. **Release + Order + Price Together** (CLI natively supports batch):
   
   **Release PENDING orders in one call:**
   ```bash
   bin/manufacturer-cli production release --order SO-0001-025 --order SO-0001-026 --order SO-0001-027
   ```

   **Order all needed materials in one call:**
   ```bash
   bin/manufacturer-cli purchase create --item "ChipSupply Co:LCD Screen:100" --item "ChipSupply Co:PLA Filament:300"
   ```
   
   **Adjust all prices in one call:**
   ```bash
   bin/manufacturer-cli price set --item "Basic300:495" --item "Elite700:1540"
   ```
   
   **Execute all three in sequence (if needed, chain with &&):**
   ```bash
   bin/manufacturer-cli production release --order O1 --order O2 --order O3 && \
   bin/manufacturer-cli purchase create --item "Supplier:Product:Qty" --item "Supplier:Product:Qty" && \
   bin/manufacturer-cli price set --item "Model:Price" --item "Model:Price"
   ```

   **Why one batch:** All decisions are independent. Decide releases → purchases → pricing in your head, then execute all at once. No waiting between steps.

3. **Order Details + Proactive Shortage Prevention** (reference only; commands go in batch above):
   
   **Use the Inventory table provided in state** — it has three key columns per material:
   - **Stock**: Current inventory of this material
   - **Needed (accepted orders)**: Total BOM demand from all PENDING sales orders
   - **Ordered (not delivered)**: Inbound materials not yet arrived
   - **Supplier lead_time_days**: How long this material takes to arrive (critical to ordering decision)
   
   **MATERIAL ORDERING BY LEAD TIME**:
   - **High lead_time (4+ days)**: Order when `Stock + Ordered < 7 × daily_demand`. Target: 500–800 units.
   - **Medium lead_time (2–3 days)**: Order when `Stock + Ordered < 5 × daily_demand`. Target: 200–300 units.
   - **Low lead_time (1 day)**: Order when `Stock + Ordered < 3 × daily_demand`. Target: 100–200 units.

   WARNING: The target stock levels above are general guidelines. If you detect a material is proportionally more demanded than others, or if demand_modifier is rising, you may want to order more or less aggressively.
   
   **Order Trigger**:
   - Calculate: `Target = Needed + (lead_time_days × expected_daily_demand × demand_modifier) + 200 buffer`
   - If `Stock + Ordered < Target` → Order immediately
   - If `demand_modifier > 1.2` → Order 400+ units regardless of current stock (demand surge)
   - **Never order more than warehouse capacity allows**. If space tight, reduce qty to 200–300 units.
   
   **Warehouse Capacity Check** (CRITICAL to avoid "Receipt rejected because warehouse would exceed capacity"):
   - `Available free space = warehouse_capacity - current_usage`
   - **Simple rule**: Do NOT place an order if `(Stock + new_order_qty) > warehouse_capacity`
   - Example: Stock=1000, warehouse_capacity=8400, new_order=600 → Check: 1000+600=1600 ≤ 8400 ✓ OK to order
   - Example: Stock=8200, warehouse_capacity=8400, new_order=300 → Check: 8200+300=8500 > 8400 ✗ DO NOT order
   
   **Order size**: 
   - Aim for 250–400 units (balances bulk pricing, material need, and warehouse space)
   - If warehouse is tight (<500 free units), reduce to 200 units max if possible
   - Consider bulk pricing tiers: 300+ units often have significant discounts
   
   **Warehouse Recovery** (EMERGENCY FUNCTION):
   
   **Deadlock condition**: Incoming critical purchase orders are **rejected/cancelled on delivery**, or expected to be rejected/cancelled because there's no enough space for them AND there is the risk at the same time sales orders become **BLOCKED (Material Shortage)** waiting for those materials to arrive.

   If an inbound purchase order is rejected/cancelled due to space, the materials won't arrive, which causes pending sales orders that need those materials to become BLOCKED. This creates a deadlock where you can't free up space because the critical materials never arrive, and the orders never release because they're waiting for those materials.
   
   **To break deadlock**:
   1. **Detect**: Sales orders show "BLOCKED — Material Shortage" AND inbound purchase orders are being rejected/cancelled or expected to be rejected due to space (check state for both conditions)
   2. **Identify**: Find excess materials taking up space that are NOT needed for pending orders (or the least critical materials if all are needed)
   3. **Calculate**: Trash enough to make room for critical incoming materials (quantity = from 1 to current_stock)
   4. **Act**: Use `bin/manufacturer-cli inventory-trash --item "MATERIAL_NAME:QUANTITY"` immediately
   5. **Result**: Critical materials can arrive, manufacturing resumes, orders proceed
   
   **Deadlock example scenario**:
   ```
   Warehouse usage: 8300/8400 (98.8% full) — CRITICAL
   
   Pending sales orders: 50 Elite700 printers
   ├─ Status: BLOCKED — waiting for ABS Filament
   └─ Need: 300 ABS Filament units
   
   Current inventory:
   ├─ ABS Filament: 20 units (FAR SHORT, need 300) — CRITICAL SHORTAGE
   └─ PLA Filament: 450 units (not needed for pending orders) — EXCESS
   
   Inbound purchase order: 400 ABS Filament from provider
   └─ Status: WILL BE REJECTED on arrival (no warehouse space) and the delivery will be lost, leaving us with 20 ABS units and blocked orders
   ```
   
   **Emergency action**: **TRASH PLA Filament:300**
   - Frees 200 units → warehouse becomes 8000/8400 
   - Incoming 400 ABS Filament CAN NOW ARRIVE (fits in freed space)
   
   **Immediate result**:
   - ✓ ABS Filament order delivered successfully (400 units)
   - ✓ Total ABS available: 20 + 400 = 420 units (need 300)
   - ✓ Manufacturing resumes (unblocked)
   - ✓ 50 Elite700 orders complete
   
   **CRITICAL**: This is an emergency function. Use when:
   - Purchase orders are about to be rejected/cancelled due to space OR
   - Sales orders are blocked waiting for those materials

   **CRITICAL**: Do not hesitate to use the trash function if necessary to accommodate incoming materials. It's better to trash excess materials than to let critical orders be blocked indefinitely or lose important incoming materials.

4. **Scale + Adjust + Summarize** (part of your single batch):

   **Assembly Queue Backlog Rules** (use queued_assembly_hours from state):
   - Calculate queue backlog in days: `backlog_days = queued_assembly_hours / daily_assembly_hours`
   - **This is your primary scaling signal** — it directly shows production pressure
   
   **Worker/Line Flexibility Strategy** (focus on cost optimization):
   - **Hiring preferred over opening lines**: 1 worker adds throughput at ~$400/day (wage), opening line costs $100/day maintenance
     - Hire workers FIRST when backlog > 1.5 days; only open lines for > 5 days backlog with sustained demand
   - **Firing preferred over closing lines**: When demand drops, fire workers first (reduces wages), keep lines open until forced to close
   - **Max workers enforcement**: Do NOT hire beyond `max_workers_per_line` per line (hard limit, shown in state)
   
   **ROI check BEFORE any hire or open** (always do this first):
   - Daily cost of 1 worker: `cost_per_worker_per_hour × shift_hours`
   - Daily cost of 1 line: `cost_per_assembly_line_per_day` + workers on that line
   - Forecast: Will the increased capacity be used (do you have pending/forecast orders)?
   - Daily sales at full capacity (use price × qty of fulfilled orders as proxy)
   - Only hire if: `expected_daily_revenue > 1.2 × new_worker_daily_cost` (payback in 20 days)
   
   | Backlog (days) | Demand Signal | Action |
   |---|---|---|
   | > 5 days | sustained (3+ day event) | CRITICAL: Open a line AND hire workers if ROI passes |
   | 3–5 days | demand_modifier > 1.2 | Hire ONE worker (cheapest throughput boost) |
   | 1.5–3 days | demand_modifier > 1.0 | Hire ONE worker IF: ROI passes AND backlog > 1.5 days last 2 turns |
   | 0.5–1.5 days | — | HOLD; no changes (borderline backlog) |
   | < 0.5 days (2+ turns) | demand_modifier < 0.8 | FIRE ONE worker per line to cut wage costs |
   | Near $0 (idle) | demand_modifier < 0.5 | CLOSE lines if workers already at minimum per line |

   **How to tell if demand is sustained** (you can see this in the prompt):
   - Look at "Market signal for day N" section—check `active_events` and `event_descriptions`
   - "over 3 days", "sustained for 5 days", "continuing" → long-term demand; safe to hire/open
   - "sudden spike", "one-day event", "spike ends day X" → temporary; do NOT hire/open
   - When in doubt, assume demand is temporary and use firings/closures instead
   
   **If expanding capacity**:
   ```bash
   # First choice: hire ONE worker (cheaper, more flexible)
   bin/manufacturer-cli hire-worker
   
   # For critical backlog > 5 days with sustained demand signal only:
   bin/manufacturer-cli open-assembly-line && bin/manufacturer-cli hire-worker
   ```
   
   **If reducing capacity** (when backlog < 0.5 days 2+ days in a row):
   ```bash
   # First choice: fire ONE worker per line (cheaper, keeps lines open for recovery)
   bin/manufacturer-cli fire-worker
   
   # Only if workers already at 1 worker per line minimum:
   bin/manufacturer-cli close-assembly-line
   ```
   
   **Price adjustments** — raise when supply is tight, lower when oversupplied:

   | Condition | Action |
   |-----------|--------|
   | Backlog > 5 days OR demand_modifier > 1.5 | Raise all prices **10–15%** |
   | Backlog > 3 days OR demand_modifier > 1.2 | Raise all prices **8%** |
   | Backlog > 1.5 days OR demand_modifier > 1.0 | Raise all prices **5%** |
   | demand_modifier < 0.7 AND backlog < 0.5 days | Lower all prices **5%** |
   | demand_modifier < 0.5 | Lower all prices **8%** |

   Use the backlog_days shown in the state. A saturated queue means you can charge more — production is the bottleneck, not demand.

   - Remember: `hire-worker` increases workers on ALL lines. 2 lines × +1 worker = 2 more workers total.
   **Put it all together in ONE response:**
   - Assess state (provided)
   - Decide all actions
   - Chain them with `&&`
   - Execute all at once
   - Send final 3–5 bullet summary
   
   That's typically just 1–2 iterations total instead of 4–6.

## Demand Forecasting & Market Signals

**Use demand_modifier + events to predict shortage windows:**

- `demand_modifier 0.9–1.1` = steady; `>1.2` = sustained demand surge (order 300+ units for long-lead materials)
- `demand_modifier rising` = demand acceleration signal (order aggressively day 1 of rise; don't wait for peak)
- `demand_modifier < 0.8` = prepare to reduce orders and fire workers
- **Event keywords** ("sustained", "days X–Y", "holiday") = multi-day demand (order before event starts, not after)
- **Combined signal**: demand_modifier > 1.3 + backlog > 3 days = critical surge (build 50+ days stock for high-lead materials)

## When Done

**START your response with a ONE-LINE DECISION SUMMARY — no title, just the decision itself:**
```
Released N orders + ordered M materials (NNN units) + price actions → focus on XXXX
```
(That's it for the first line. No "Decision Summary:" label — just the content.)

Then provide your reasoning/details below that summary.

**END with 3–7 bullet-point summary:**
```
- Day N complete.
- Released N sales order(s).
- Placed N purchase order(s).
- Capacity: N lines × M workers × H hours = T total hours.
- Price changes: none or MODEL to PRICE.
- Financial: Profit $X or concern: loss trend / low margin.
- Inventory concern: none or MATERIAL at N units.
```

Stop.
