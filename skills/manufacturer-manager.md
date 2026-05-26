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
- Assembly line: cost per new line (setup) + daily maintenance cost
- Worker per hour: hourly wage (applied daily, calculated per worker per shift-hours)
- Max workers per line: limit per assembly line
- Materials: varies by supplier and quantity
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

## Decision Framework

**⚡ Note**: Current state is provided above (capacity, inventory, PENDING orders, inbound purchases, prices). Do NOT run state-check commands. Use the provided data to make decisions, then execute your actions in batch.

Follow these steps:

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

2. **Fulfil**: Release PENDING orders that fit within daily capacity:
   - Batch release command: `bin/manufacturer-cli production release ORDER_ID1 ORDER_ID2 ORDER_ID3 ...`
   - Example: `bin/manufacturer-cli production release SO-0001-025 SO-0001-026 SO-0001-027 SO-0001-028`

3. **Order**: For materials below 50 units not already inbound:
   - Batch purchase commands (one per material):
     ```bash
     bin/manufacturer-cli purchase create --supplier "ChipSupply Co" --product "LCD Screen" --qty 100
     bin/manufacturer-cli purchase create --supplier "ChipSupply Co" --product "PLA Filament" --qty 300
     ```

4. **Scale** (optional): Adapt capacity based on demand signals:
   
   **Expand capacity** if demand is consistently high and warehouse capacity is adequate:
   - Batch expand: `bin/manufacturer-cli open-assembly-line && bin/manufacturer-cli hire-worker`
   - Or separate:
     ```bash
     bin/manufacturer-cli open-assembly-line
     bin/manufacturer-cli hire-worker
     bin/manufacturer-cli hire-worker
     ```
   - Only expand if PENDING orders > daily capacity and you can afford it
   
   **Reduce capacity** if demand is low and costs are unsustainable:
   - Batch reduce: `bin/manufacturer-cli fire-worker && bin/manufacturer-cli close-assembly-line`

5. **Adjust**: Price changes based on demand_modifier (use prices from provided state):
   - If demand_modifier > 1.5: increase prices 10%
     ```bash
     bin/manufacturer-cli price set "Basic300" 495
     bin/manufacturer-cli price set "Elite700" 1540
     bin/manufacturer-cli price set "Pro450" 880
     ```
   - If demand_modifier < 0.5: decrease prices 5%
     ```bash
     bin/manufacturer-cli price set "Basic300" 427
     bin/manufacturer-cli price set "Elite700" 1330
     bin/manufacturer-cli price set "Pro450" 760
     ```
   - Otherwise: no changes needed

6. **Log**: Summarize what changed in 3–5 bullets.

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
