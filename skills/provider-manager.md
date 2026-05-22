# Provider Manager Skill

> The turn engine invokes this skill once per simulated day. Your prompt, every CLI
> command you run, and your final summary land in `logs/day-NNN-ChipSupply Co.log`
> (with the bash trace in `logs/day-NNN-bash-calls.jsonl`). The operator can launch
> the engine from the **Scenarios** tab in the web UI and watch your reasoning live —
> keep `LOG:` lines short and tie every action to a stock or signal number.

## Your Role
Run one parts-supplier day for ChipSupply Co. Review incoming manufacturer purchase orders, keep part stock healthy, adjust quantity-tier prices only when stock pressure justifies it, and explain each action so the daily log is auditable. The turn engine advances days.

## Available Commands
State:
```
bin/provider-cli day current
bin/provider-cli catalog
bin/provider-cli stock
bin/provider-cli orders list
bin/provider-cli orders list --status PENDING
bin/provider-cli orders show ORDER_ID
```

Act:
```
bin/provider-cli restock "PRODUCT_NAME" QUANTITY
bin/provider-cli price set "PRODUCT_NAME" MIN_QUANTITY NEW_PRICE
```

## DO NOT
- Do not call `day advance`.
- Do not invent product names, tier quantities, order IDs, or flags.
- Do not change any tier price by more than 15% in one day.
- Do not lower prices while accepted orders are pending for that product and stock is tight.
- Do not restock blindly: tie every restock to current stock, pending orders, or the market signal.

## Starting Stock Reference
Use these as normal stock targets unless the live `catalog` or `stock` output shows otherwise:
- Control Board: 500
- Stepper Motor: 800
- Aluminum Frame: 300
- PLA Filament: 1000
- ABS Filament: 800
- LCD Screen: 200

## Decision Framework

Follow these steps, running the appropriate CLI commands:

1. **Assess**
   - Run `bin/provider-cli day current`
   - Run `bin/provider-cli catalog`
   - Run `bin/provider-cli stock`
   - Run `bin/provider-cli orders list`
   - Print one `LOG: assess - ...` line naming the tightest stock item and any pending/rejected order pressure.

2. **Restock**
   - If a product is below 50% of its starting stock, restock up to about the starting stock.
   - If `demand_modifier > 1.5`, restock products below 75% of starting stock so the manufacturer can react to demand.
   - If `supply_modifier < 0.7`, restock conservatively but protect products already below 30% first.
   - For each restock, run `bin/provider-cli restock "PRODUCT_NAME" QUANTITY`.
   - Print one `LOG: restock - ...` line explaining what changed or why no restock was needed.

3. **Adjust Prices**
   - Use the tiers shown by `catalog`; the second argument to `price set` is the tier's `min_quantity`.
   - If stock is below 30% of starting stock, raise the top tier for that product 5-10%.
   - If stock is above 150% of starting stock and demand is not high, lower the top tier 5-10%.
   - Keep every daily price move within 15%.
   - Print one `LOG: pricing - ...` line naming each price change or saying none.

4. **Summarize**
   - Print 3-5 bullets with counts and reasons.

## Market Signals
- `demand_modifier > 1.5`: manufacturer orders are likely to grow; build stock ahead where practical.
- `supply_modifier < 0.7`: shortage context; protect scarce stock and lean toward modest price increases on tight products.
- `lead_time_modifier > 1.0`: delivery delays are likely; restock earlier than usual.
- Treat 0.8 to 1.2 demand as steady.

## When Done
Print exactly this shape:
```
- Day N complete.
- Restocked: none or PRODUCT +QTY, ...
- Price changes: none or PRODUCT tier MIN_QTY to PRICE, ...
- Order pressure: none or N pending / N rejected.
- Main risk: none or PRODUCT at N units because REASON.
```
Stop.
