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
```
Act:
```
bin/manufacturer-cli production release ORDER_ID
bin/manufacturer-cli purchase create --supplier "SUPPLIER_NAME" --product "PRODUCT_NAME" --qty QUANTITY
bin/manufacturer-cli price set MODEL_NAME NEW_PRICE
bin/manufacturer-cli open-assembly-line
bin/manufacturer-cli hire-worker
```

## DO NOT
- Do not call `day advance`.
- Do not release beyond daily capacity shown by `capacity`.
- Do not order parts already inbound as PENDING in `purchase list`.
- Do not invent flags, product names, supplier names, or order IDs.
- Do not choose a slower supplier when a faster valid one can meet the need.

## Decision Framework

Follow these steps, running the appropriate CLI commands:

1. **Assess**: Check current state by running (in order):
   - `bin/manufacturer-cli day current`
   - `bin/manufacturer-cli capacity`
   - `bin/manufacturer-cli inventory`
   - `bin/manufacturer-cli sales orders --status PENDING`
   - `bin/manufacturer-cli production status`
   - `bin/manufacturer-cli purchase list`
   
   Then interpret what you learned.

2. **Fulfil**: For each PENDING order that fits within daily capacity:
   - Run `bin/manufacturer-cli production release <ORDER_ID>`

3. **Order**: For materials below 50 units not already inbound:
   - Run `bin/manufacturer-cli suppliers catalog "SUPPLIER_NAME"` to find suppliers
   - For each material, run `bin/manufacturer-cli purchase create --supplier "SUPPLIER_NAME" --product "PRODUCT_NAME" --qty <QUANTITY>`

4. **Adjust**: Check current prices:
   - Run `bin/manufacturer-cli price list`
   
   Then apply price changes based on demand_modifier:
   - If demand_modifier > 1.5: run `bin/manufacturer-cli price set <MODEL_NAME> <NEW_PRICE>` (up 10% for each model)
   - If demand_modifier < 0.5: run `bin/manufacturer-cli price set <MODEL_NAME> <NEW_PRICE>` (down 5% for each model)
   - Otherwise: no changes

5. **Log**: Summarize what changed in 3–5 bullets.

## Market Signals
`demand_modifier`: 1.0 normal, high stronger demand, low weaker demand. `supply_modifier`: lead-time risk; Week 7 is normally 1.0. Treat 0.8 to 1.2 demand as steady.

## When Done
Print 3 to 5 bullets:
```
- Day N complete.
- Released N sales order(s).
- Placed N purchase order(s).
- Price changes: none or MODEL to PRICE.
- Inventory concern: none or MATERIAL at N units.
```
Stop.
