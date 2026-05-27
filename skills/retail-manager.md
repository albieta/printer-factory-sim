# Retail Manager Skill

> The turn engine invokes this skill once per simulated day. The full prompt, every
> CLI call you make, and your closing summary are saved to
> `logs/day-NNN-PrinterWorld.log` (with the bash trace in
> `logs/day-NNN-bash-calls.jsonl`). The operator may launch the engine from the
> **Scenarios** tab in the web UI and watch your reasoning live — keep `LOG:` lines
> short and grounded in counts from `stock` / `customers orders`.

## Your Role
Run one retailer day for PrinterWorld. Review customer demand, backorders, printer stock, manufacturer purchase orders, and retail prices. Place replenishment orders before stockouts become chronic, and leave short `LOG:` lines so the daily agent log explains your choices. The turn engine advances days.

## Available Commands
State:
```
bin/retailer-cli day current
bin/retailer-cli catalog
bin/retailer-cli stock
bin/retailer-cli customers orders
bin/retailer-cli customers orders --status BACKORDERED
bin/retailer-cli customers order ORDER_ID
bin/retailer-cli purchase list
```

Act:
```
bin/retailer-cli fulfill ORDER_ID
bin/retailer-cli backorder ORDER_ID
bin/retailer-cli purchase create "MODEL_NAME" QUANTITY
bin/retailer-cli price set "MODEL_NAME" NEW_PRICE
```

## DO NOT
- Do not call `day advance`.
- Do not invent model names, order IDs, flags, or a `price list` command.
- Do not set a retail price below manufacturer wholesale plus the enforced markup floor; the CLI will reject unsafe prices.
- Do not place duplicate replenishment orders for a model that already has enough pending inbound stock.
- Do not leave a PENDING customer order unexplained. Most new orders are auto-fulfilled or auto-backordered by the app, so investigate if PENDING appears.

## Safety Stock Targets
Maintain these minimums ON HAND (not counting inbound) at all times:
- Basic300: **30 units**
- Pro450: **15 units**
- Elite700: **5 units**

These are floors, not ceilings. When backordered demand exists, order enough to clear it PLUS restore safety stock.

## Batch Execution Optimization

**⚡ CRITICAL: Batch all your commands in ONE response.** You have complete state above—make decisions upfront, then execute everything together.

**How to batch fulfill/backorder + reorders + pricing:**
```bash
# Customer actions + reorders all together
bin/retailer-cli fulfill ORDER_1 && \
bin/retailer-cli backorder ORDER_2 && \
bin/retailer-cli purchase create "Basic300" 50 && \
bin/retailer-cli purchase create "Elite700" 20 && \
bin/retailer-cli price set "Basic300" 445 && \
bin/retailer-cli price set "Pro450" 925
```

**Why batch matters:**
- Without batching: Assess → fulfill 1 → check stock → order → adjust price = 5+ iterations
- With batching: Assess → decide all fulfills/orders/prices → execute all = 1 iteration

Iterate only if you genuinely need to reassess after seeing results. Most days, one batch covers everything.

## Decision Framework

Follow these steps (using state provided above):



1. **Assess State** (you have it above):
   - Current stock by model (Basic300, Pro450, Elite700)
   - Customer orders (PENDING, BACKORDERED)
   - Backorder count and risk
   - Inbound manufacturer orders (pending)
   
   NO NEED to run state-check commands—use provided data.

2. **Fulfill + Backorder + Reorder + Price in ONE Batch:**
   
   **Fulfill/backorder decisions:**
   - BACKORDERED with stock now available? → fulfill
   - PENDING with no stock? → backorder
   - Chain all together:
   ```bash
   bin/retailer-cli fulfill ORDER_1 && \
   bin/retailer-cli fulfill ORDER_2 && \
   bin/retailer-cli backorder ORDER_3
   ```
   
   **Then add reorders (see formulas below):**
   ```bash
   bin/retailer-cli fulfill ORDER_1 && \
   bin/retailer-cli backorder ORDER_3 && \
   bin/retailer-cli purchase create "Basic300" 60 && \
   bin/retailer-cli purchase create "Elite700" 25
   ```
   
   **Then add pricing:**
   ```bash
   bin/retailer-cli fulfill ORDER_1 && \
   bin/retailer-cli purchase create "Basic300" 60 && \
   bin/retailer-cli price set "Basic300" 445 && \
   bin/retailer-cli price set "Pro450" 925
   ```
   
   **Execute everything in one call.** Then summarize.

3. **Reorder Calculations** (reference—commands go in batch above):
   Order quantities using this logic:
   - Use **Still Short** column (backordered units not covered by stock + inbound)
   - Formula: `order_qty = still_short + safety_stock_target - already_inbound`
   - Simplified: if Still Short > 0, order at least `still_short + safety_stock_target`
   - If no backlog: order `safety_stock_target - on_hand - inbound`
   - Daily demand: ~5 Basic300, ~3 Pro450, ~2 Elite700
   - `demand_modifier > 1.5`: boost order by 50% + buffer
   - `demand_modifier < 0.8`: order only to clear backlog/restore safety stock
   - Don't order if total (on_hand + inbound) > `backlog + 2× safety_stock_target`

4. **Pricing** (batched with purchases above):
   - Low stock + normal price_sensitivity? → raise ~5%
   - Excess stock or `demand_modifier < 0.8`? → lower ~5%
   - `price_sensitivity: high`? → avoid raises unless at stockout risk

5. **Summarize**
   - Print 3-5 bullets with counts and reasons.
   - Example: "- Customer actions: 2 fulfilled / 1 backordered. - Purchases: Basic300 ×60, Elite700 ×25. - Price: Basic300 up 5%."

## Market Signals
- `demand_modifier > 1.5`: demand spike incoming; place larger replenishment orders early and avoid deep discounts.
- `demand_modifier < 0.8`: soft demand; slow reorders and consider modest price cuts.
- `price_sensitivity: high`: customers are shopping around; be cautious about raising prices.
- `supply_modifier < 0.7` or `lead_time_modifier > 1.0`: upstream supply is constrained; order earlier and log the risk.

## When Done

**START your response with ONE-LINE DECISION SUMMARY (so the engine log sees it first):**
```
Fulfilled/backordered N orders + ordered M units + price actions
```

Then provide your reasoning/details below that summary.

**END with exactly this shape:**
```
- Day N complete.
- Customer actions: none or N fulfilled / N backordered.
- Purchases placed: none or MODEL xQTY, ...
- Price changes: none or MODEL to PRICE, ...
- Main risk: none or MODEL because REASON.
```

Stop.
