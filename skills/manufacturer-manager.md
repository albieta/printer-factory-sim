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
```
Financial Costs:
- Assembly line: customizable cost per new line
- Worker per hour: customizable hourly wage
- Max workers per line: configurable limit per assembly line
- Materials: varies by supplier and quantity
- Check actual costs with `bin/manufacturer-cli financial summary`

## DO NOT
- Do not call `day advance`.
- Do not release beyond daily capacity shown by `capacity`.
- Do not order parts already inbound as PENDING in `purchase list`.
- Do not invent flags, product names, supplier names, or order IDs.
- Do not choose a slower supplier when a faster valid one can meet the need.
- Do not attempt to hire more than 10 workers per assembly line.
- Do not make capacity decisions that lead to sustained losses (costs > revenue).

## Decision Framework

Follow these steps, running the appropriate CLI commands:

1. **Assess**: Check current state by running (in order):
   - `bin/manufacturer-cli day current`
   - `bin/manufacturer-cli financial summary` (check costs, revenue, profit margin)
   - `bin/manufacturer-cli capacity`
   - `bin/manufacturer-cli inventory`
   - `bin/manufacturer-cli sales orders --status PENDING`
   - `bin/manufacturer-cli production status`
   - `bin/manufacturer-cli purchase list`
   
   Then interpret what you learned, including financial health.

2. **Fulfil**: For each PENDING order that fits within daily capacity:
   - Run `bin/manufacturer-cli production release <ORDER_ID>`

3. **Order**: For materials below 50 units not already inbound:
   - Run `bin/manufacturer-cli suppliers catalog "SUPPLIER_NAME"` to find suppliers
   - For each material, run `bin/manufacturer-cli purchase create --supplier "SUPPLIER_NAME" --product "PRODUCT_NAME" --qty <QUANTITY>`

4. **Scale** (optional): If demand is consistently high and warehouse capacity is adequate, consider capacity expansion:
   - Run `bin/manufacturer-cli open-assembly-line` (check cost with `financial summary`, increases production capacity)
   - Run `bin/manufacturer-cli hire-worker` (check hourly cost with `financial summary`, up to the configured limit per line)
   - Only expand if profitable (revenue growth > cost of expansion)

5. **Adjust**: Check current prices:
   - Run `bin/manufacturer-cli price list`
   
   Then apply price changes based on demand_modifier:
   - If demand_modifier > 1.5: run `bin/manufacturer-cli price set <MODEL_NAME> <NEW_PRICE>` (up 10% for each model)
   - If demand_modifier < 0.5: run `bin/manufacturer-cli price set <MODEL_NAME> <NEW_PRICE>` (down 5% for each model)
   - Otherwise: no changes

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
