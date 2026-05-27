# Manufacturer Manager Skill

> The turn engine invokes this skill once per simulated day. Every prompt you receive,
> every CLI command you run, and your final summary are written to
> `logs/day-NNN-Factory.log` (plus `logs/day-NNN-bash-calls.jsonl`). The operator may
> also launch the engine from the **Scenarios** tab in the web UI and watch your
> reasoning stream in real time — keep the `LOG:` lines short and decisive.

## Your Role
Run one factory day: review retailer orders, check materials/capacity, release production, order low parts, and change wholesale prices only when the signal calls for it. The engine advances days.

## Available Commands
State:
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
Act:
```
bin/manufacturer-cli production release ORDER_ID
bin/manufacturer-cli purchase create --supplier "SUPPLIER_NAME" --product "PRODUCT_NAME" --qty QUANTITY
bin/manufacturer-cli price set MODEL_NAME NEW_PRICE
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
- Do not release beyond daily capacity shown by `capacity`.
- Do not order parts already inbound as PENDING in `purchase list`.
- Do not invent flags, product names, supplier names, or order IDs.
- Do not choose a slower supplier when a faster valid one can meet the need.
- Do not attempt to hire more than 10 workers per assembly line.
- Do not make capacity decisions that lead to sustained losses (costs > revenue).
- Do not manually adjust inventory — this is a human-only operation. Only place purchase orders when a shortage is expected.

## Batch Execution Optimization

**⚡ CRITICAL: Batch all your tool calls in ONE response.** Multiple commands can run in a single iteration:
- Instead of: Check state → wait → decide → wait → execute
- Do this: Decide what you need to do → execute ALL commands together

**How to batch:**
Chain commands with `&&` to run them sequentially in one call:
```bash
# Good: All commands in one batch
bin/manufacturer-cli production release O1 O2 O3 && \
bin/manufacturer-cli purchase create --supplier "ChipSupply Co" --product "LCD Screen" --qty 100 && \
bin/manufacturer-cli purchase create --supplier "ChipSupply Co" --product "PLA Filament" --qty 300 && \
bin/manufacturer-cli price set "Basic300" 495
```

The key: You already have the state provided above. Use it directly without running state-check commands. Figure out all your actions, then batch-execute them in one response.

**Why batch matters:** 
- Iteration 1: You make ALL decisions and execute ALL commands together
- Iteration 2 (optional): Only if Claude needs to reassess based on results
- Without batching: You'd need 4+ iterations (check → decide → execute per action)
- With batching: Typically 1-2 iterations total

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

2. **Fulfil + Order + Price Together** (all in ONE batch):
   
   **Release orders:**
   ```bash
   bin/manufacturer-cli production release SO-0001-025 SO-0001-026 SO-0001-027
   ```
   
   **Combine with purchase orders (chain with &&):**
   ```bash
   bin/manufacturer-cli production release SO-0001-025 SO-0001-026 && \
   bin/manufacturer-cli purchase create --supplier "ChipSupply Co" --product "LCD Screen" --qty 100 && \
   bin/manufacturer-cli purchase create --supplier "ChipSupply Co" --product "PLA Filament" --qty 300
   ```
   
   **Add pricing adjustments in the same batch:**
   ```bash
   bin/manufacturer-cli production release SO-0001-025 SO-0001-026 && \
   bin/manufacturer-cli purchase create --supplier "ChipSupply Co" --product "LCD Screen" --qty 100 && \
   bin/manufacturer-cli price set "Basic300" 495 && \
   bin/manufacturer-cli price set "Elite700" 1540
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
Print 3 to 7 bullets:
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
