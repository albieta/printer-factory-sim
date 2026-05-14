# Manufacturer Manager Skill

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
```

## DO NOT
- Do not call `day advance`.
- Do not release beyond daily capacity shown by `capacity`.
- Do not order parts already inbound as PENDING in `purchase list`.
- Do not invent flags, product names, supplier names, or order IDs.
- Do not choose a slower supplier when a faster valid one can meet the need.

## Decision Framework
1. Assess: run day, capacity, inventory, production status, pending sales, purchases, and prices.
2. Fulfil: release oldest PENDING sales orders that fit capacity.
3. Order: for materials below 50 and not inbound, order enough to reach about 200 units.
4. Adjust: if `demand_modifier > 1.5`, raise prices by at most 10 percent; if `< 0.5`, lower by at most 5 percent; otherwise no change.
5. Log: state what changed and why.

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
