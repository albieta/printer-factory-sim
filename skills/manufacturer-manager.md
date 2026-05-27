# Manufacturer Manager Skill

> The turn engine invokes this skill once per simulated day. Every prompt you receive,
> every CLI command you run, and your final summary are written to
> `logs/day-NNN-Factory.log` (plus `logs/day-NNN-bash-calls.jsonl`). The operator may
> also launch the engine from the **Scenarios** tab in the web UI and watch your
> reasoning stream in real time — keep the `LOG:` lines short and decisive.

## Your Role
Run one factory day: review retailer orders, check materials/capacity, release production, order low parts, and change wholesale prices only when the signal calls for it. The engine advances days.

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
- Try to avoid state-check commands when you have the data in the prompt; they waste iterations.
- Do not release beyond daily capacity shown by `capacity` (use the value in the provided state).
- Do not order parts without taking into account the orders inbound as PENDING (check the state table).
- Do not invent flags, product names, supplier names, or order IDs.
- Do not choose a slower supplier when a faster valid one can meet the need.
- Do not attempt to hire more than 10 workers per assembly line.
- Do not make capacity decisions that lead to sustained losses (costs > revenue).
- Do not manually adjust inventory — this is a human-only operation. Only place purchase orders when a shortage is expected.

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

## Decision Framework

Follow these steps (using only the state provided above):



1. **Assess**: Review the provided state above:
   - Current capacity (lines, workers, daily hours)
   - Inventory table: **Stock | Needed (accepted orders) | Ordered (not delivered) | Storage Status**
     - CRITICAL = stock below demand with nothing ordered → order immediately
     - LOW (ordered) = stock below demand but inbound → monitor
     - EXCESS = far more stock than needed → pause ordering
   - PENDING sales orders (all awaiting release)
   - Inbound purchase orders (arriving materials)
   - Wholesale prices (current pricing)
   
   Decide based on this data (no API calls needed for state checks).

2. **Release + Order + Price Together** (CLI natively supports batch):
   
   **Release all PENDING orders in one call:**
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

3. **Order Details** (reference only; commands go in batch above):
   - Order if: `Stock - Needed ≤ lead_time_days × expected_daily_consumption` and nothing inbound.
   - Consider bulk tiers: buying 300 units may cost less per unit than buying 100.
   - Check warehouse free space: `Stock + Ordered-inbound + New-order ≤ warehouse_capacity`.
     Do NOT order more than the warehouse can fit.

4. **Scale + Adjust + Summarize** (part of your single batch):
   
   **If expanding capacity** (when PENDING > capacity AND revenue > costs):
   ```bash
   bin/manufacturer-cli production release O1 O2 && \
   bin/manufacturer-cli purchase create --supplier "ChipSupply Co" --product "LCD Screen" --qty 100 && \
   bin/manufacturer-cli open-assembly-line && \
   bin/manufacturer-cli hire-worker && \
   bin/manufacturer-cli price set "Basic300" 495
   ```
   
   **If reducing capacity** (when demand low and costs unsustainable):
   ```bash
   bin/manufacturer-cli fire-worker && \
   bin/manufacturer-cli close-assembly-line && \
   bin/manufacturer-cli price set "Basic300" 427
   ```
   
   **Price adjustments** (always decided upfront, executed in batch):
   - `demand_modifier > 1.5`: increase 10%
   - `demand_modifier < 0.5`: decrease 5%
   - Otherwise: no changes
   
   - Remember: `hire-worker` increases workers on ALL lines. 2 lines × +1 worker = 2 more workers total.
   **Put it all together in ONE response:**
   - Assess state (provided)
   - Decide all actions
   - Chain them with `&&`
   - Execute all at once
   - Send final 3–5 bullet summary
   
   That's typically just 1–2 iterations total instead of 4–6.

## Market Signals
`demand_modifier`: 1.0 normal, high stronger demand, low weaker demand. `supply_modifier`: lead-time risk; Week 7 is normally 1.0. Treat 0.8 to 1.2 demand as steady.

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
