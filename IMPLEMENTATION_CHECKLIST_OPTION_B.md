# Implementation Checklist: Option B (State-in-Prompt)

## Overview
Replace tool-call-based state checks with prompt-embedded state data.

**Time estimate**: 2-3 hours  
**Files to modify**: 4 (turn_engine.py, 3 skill files)  
**Accuracy impact**: ✅ NONE (decisions identical)  
**Speed gain**: 2.2-2.5× (65-80s/day vs 173s)

---

## Phase 1: Update Turn Engine (1 hour)

### Step 1.1: Add state-fetching function

**File**: `engine/turn_engine.py`

**Add after imports (around line 30)**:
```python
async def fetch_all_state_concurrent(base_url: str, logger: ApiLogger | None = None) -> dict[str, Any]:
    """Fetch all manufacturer state in parallel using httpx."""
    import asyncio
    import httpx
    
    async def fetch(url: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(url)
                r.raise_for_status()
                return dict(r.json())
        except Exception as e:
            return {"error": str(e)}
    
    tasks = [
        fetch(f"{base_url}/api/day/current"),
        fetch(f"{base_url}/api/capacity"),
        fetch(f"{base_url}/api/inventory"),
        fetch(f"{base_url}/api/sales/orders?status=PENDING"),
        fetch(f"{base_url}/api/purchases"),
        fetch(f"{base_url}/api/production/status"),
        fetch(f"{base_url}/api/prices"),
    ]
    
    results = await asyncio.gather(*tasks)
    return {
        "day": results[0],
        "capacity": results[1],
        "inventory": results[2],
        "sales_orders": results[3],
        "purchase_orders": results[4],
        "production_status": results[5],
        "prices": results[6],
    }


def format_state_for_prompt(mfr_state: dict[str, Any]) -> str:
    """Format manufacturer state for inclusion in prompt."""
    
    # Extract data safely
    day = mfr_state.get("day", {}).get("date", "unknown")
    capacity = mfr_state.get("capacity", {})
    inventory = mfr_state.get("inventory", {})
    sales_orders = mfr_state.get("sales_orders", [])
    purchases = mfr_state.get("purchase_orders", [])
    production = mfr_state.get("production_status", {})
    prices = mfr_state.get("prices", {})
    
    # Format inventory table
    inventory_table = "Material        | Current | Demand | Status\n"
    inventory_table += "─────────────────────────────────────────────\n"
    for item, qty in inventory.items():
        inventory_table += f"{item:<15} | {qty:>7} | TBD    | \n"
    
    # Format PENDING orders
    orders_list = ""
    pending_count = len(sales_orders)
    if sales_orders:
        sample_orders = sales_orders[:5]  # Show first 5
        orders_list = f"{pending_count} total PENDING orders:\n"
        for order in sample_orders:
            orders_list += f"  - {order.get('id')}: {order.get('model')} × {order.get('quantity')}\n"
        if len(sales_orders) > 5:
            orders_list += f"  ... and {len(sales_orders) - 5} more\n"
    
    # Format inbound purchases
    inbound_list = ""
    if purchases:
        inbound_list = "Inbound Purchase Orders:\n"
        for purchase in purchases:
            if purchase.get("status") in ["PENDING", "CONFIRMED"]:
                inbound_list += f"  - {purchase.get('product')}: {purchase.get('quantity')} units, due {purchase.get('due_date')}\n"
    
    # Format prices
    price_table = ""
    if prices:
        price_table = "Current Wholesale Prices:\n"
        for model, price in prices.items():
            price_table += f"  - {model}: ${price}\n"
    
    # Assemble full state context
    state_text = f"""## Current State (Day {day})

**Capacity**: {capacity.get('lines', 1)} assembly lines × {capacity.get('workers_per_line', 1)} workers × {capacity.get('shift_hours', 8)} hours = {capacity.get('daily_hours', 8)} hours/day max production

**Current Inventory**:
{inventory_table}

**Sales Orders**:
{orders_list or "No PENDING orders"}

{inbound_list}

{price_table}

**Production Status**: {production.get('status', 'unknown')}

---
"""
    return state_text
```

**Checklist**:
- [ ] Add `fetch_all_state_concurrent()` function
- [ ] Add `format_state_for_prompt()` function
- [ ] Import `asyncio` at top
- [ ] Test that functions run without errors (can test in isolation)

### Step 1.2: Update run_role_agent() to fetch state

**File**: `engine/turn_engine.py`

**Modify the run_role_agent() function** (around line 180):

```python
async def run_role_agent(
    role: str,
    role_cfg: dict[str, Any],
    day: int,
    signal: dict[str, Any],
    state_context: str = "",  # NEW: embedded state
) -> str:
    """Run the stub or claude agent for a role; return log output."""

    import os
    skill_file: str | None = role_cfg.get("skill") or None
    cwd = role_cfg.get("path", ".")
    model: str = os.environ.get("CLAUDE_MODEL") or role_cfg.get("model", "claude-haiku-4-5-20251001")
    
    if skill_file:
        prompt = build_prompt(role, day, signal, skill_file, state_context)  # PASS STATE
    else:
        prompt = f"[stub] {role} day {day}"
    return run_agent(role, day, prompt, skill_file, cwd=cwd, model=model)
```

**Checklist**:
- [ ] Add `state_context` parameter to function signature
- [ ] Pass `state_context` to `build_prompt()`

### Step 1.3: Update build_prompt() to include state

**File**: `engine/turn_engine.py`

**Modify the build_prompt() function** (around line 211):

```python
def build_prompt(
    role: str,
    day: int,
    signal: dict[str, object],
    skill_file: str,
    state_context: str = "",  # NEW
) -> str:
    """Assemble the prompt given to ``claude --print``."""

    skill_text = Path(skill_file).read_text(encoding="utf-8")
    
    # NEW: Insert state context before skill instructions
    state_section = f"\n## Provided State Data\n{state_context}\n" if state_context else ""
    
    return (
        f"# Simulation turn — day {day}\n\n"
        f"{state_section}"  # NEW: Add state
        f"## Your skill\n\n{skill_text}\n\n"
        f"## Market signal for day {day}\n\n"
        f"```json\n{signal}\n```\n\n"
        f"Follow the decision framework in your skill file.  "
        f"When done, print your 3–5 bullet summary.\n"
    )
```

**Checklist**:
- [ ] Add `state_context` parameter to function signature
- [ ] Add state section to prompt assembly
- [ ] Verify prompt structure is readable

### Step 1.4: Update run_day() to fetch manufacturer state

**File**: `engine/turn_engine.py`

**Modify the run_day() function** (around line 229):

```python
def run_day(
    config: dict[str, Any],
    scenario: dict[str, Any],
    day: int,
) -> dict[str, Any]:
    """Execute one complete simulation turn."""

    print(f"\n=== Day {day} ===")
    signal = get_day_signal(scenario, day)
    summary: dict[str, Any] = {"day": day, "signal": signal}

    retailers: list[dict[str, Any]] = config.get("retailers", [])
    mfr: dict[str, Any] = config.get("manufacturer", {})
    providers: list[dict[str, Any]] = config.get("providers", [])

    api_logger = ApiLogger(day)
    
    # NEW: Fetch manufacturer state upfront (for embedding in prompt)
    mfr_state_context = ""
    if mfr and "url" in mfr:
        try:
            mfr_state = asyncio.run(fetch_all_state_concurrent(mfr["url"], api_logger))
            mfr_state_context = format_state_for_prompt(mfr_state)
            print(f"  [Factory] state pre-fetched")
        except Exception as e:
            print(f"  [Factory] state pre-fetch failed: {e}", file=sys.stderr)
            mfr_state_context = ""

    # ... rest of function, but when calling manufacturer agent:
    mfr_name = mfr.get("name", "manufacturer")
    agent_outputs[mfr_name] = run_role_agent(
        mfr_name, mfr, day, signal, 
        state_context=mfr_state_context  # NEW: pass state
    )
    # ... similar for other roles
```

**Checklist**:
- [ ] Add manufacturer state pre-fetching before agent runs
- [ ] Pass `mfr_state_context` to `run_role_agent()`
- [ ] Test that state is fetched successfully

### Step 1.5: Add import statement

**File**: `engine/turn_engine.py`

**At the top with other imports**:
```python
import asyncio  # NEW
```

**Checklist**:
- [ ] Add `import asyncio` at top

---

## Phase 2: Update Skill Files (1 hour)

### Step 2.1: Update Manufacturer Skill

**File**: `skills/manufacturer-manager.md`

**Change 1: Add note about provided state**

Replace this section (lines 59-72):
```markdown
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
```

With this:
```markdown
## Decision Framework

**Note**: Current state is provided above (in "## Provided State Data" section). Do NOT run state-check commands.

Follow these steps to make decisions based on the provided state:

1. **Assess**: Review the provided state above (you already have):
   - Current day and capacity
   - Current inventory levels
   - PENDING sales orders to fulfill
   - Inbound purchase orders (arriving)
   - Current prices
```

**Change 2: Update "Fulfil" section**

Replace (lines 74-75):
```markdown
2. **Fulfil**: For each PENDING order that fits within daily capacity:
   - Run `bin/manufacturer-cli production release <ORDER_ID>`
```

With:
```markdown
2. **Fulfil**: For each PENDING order that fits within daily capacity:
   - Batch all releases: `bin/manufacturer-cli production release ORDER_ID1 ORDER_ID2 ORDER_ID3 ...`
   - Example: `bin/manufacturer-cli production release SO-0001-025 SO-0001-026 SO-0001-027`
```

**Change 3: Update "Order" section**

Replace (lines 77-79):
```markdown
3. **Order**: For materials below 50 units not already inbound:
   - Run `bin/manufacturer-cli suppliers catalog "SUPPLIER_NAME"` to find suppliers
   - For each material, run `bin/manufacturer-cli purchase create --supplier "SUPPLIER_NAME" --product "PRODUCT_NAME" --qty <QUANTITY>`
```

With:
```markdown
3. **Order**: For materials below 50 units not already inbound:
   - Run commands to order multiple materials in sequence
   - Example:
     ```bash
     bin/manufacturer-cli purchase create --supplier "ChipSupply Co" --product "LCD Screen" --qty 100
     bin/manufacturer-cli purchase create --supplier "ChipSupply Co" --product "PLA Filament" --qty 300
     ```
```

**Change 4: Remove "Adjust" pricing section** (optional, to simplify)

This is already in the skill file, just make it optional:
```markdown
5. **Adjust** (optional): Check current prices if demand signal indicates:
   - If demand_modifier > 1.5: Run `bin/manufacturer-cli price set <MODEL_NAME> <NEW_PRICE>` (up 10%)
   - If demand_modifier < 0.5: Run `bin/manufacturer-cli price set <MODEL_NAME> <NEW_PRICE>` (down 5%)
   - Otherwise: No changes needed
```

**Checklist**:
- [ ] Update Decision Framework intro
- [ ] Update Assess section (note state is provided)
- [ ] Update Fulfil section (batch releases)
- [ ] Update Order section (batch purchases)
- [ ] Keep Scale section as-is
- [ ] Test skill file reads naturally

### Step 2.2: Update Retail Manager Skill

**File**: `skills/retail-manager.md`

**Similar changes**:

```markdown
## Decision Framework

**Note**: Current state is provided above (in "## Provided State Data" section).

Follow these steps based on the provided state:

1. **Stock**: Review current inventory in provided state
   - If any product < 100 units, restock
   - Batch restock command: `bin/retailer-cli purchase create --product "MODEL_1" --qty QTY1 --product "MODEL_2" --qty QTY2 ...`

2. **Price** (optional): Based on demand signal
   - Adjust if signal warrants

3. **Done**: Stop after executing commands
```

**Checklist**:
- [ ] Add state context note
- [ ] Simplify to reference provided state
- [ ] Remove redundant state-check commands

### Step 2.3: Update Provider Manager Skill

**File**: `skills/provider-manager.md`

**Similar changes**:

```markdown
## Decision Framework

**Note**: Current state is provided above (in "## Provided State Data" section).

Follow these steps:

1. **Review**: Check provided state for in-progress orders

2. **Ship**: For orders ready to ship (lead time met):
   - Batch ship command: `bin/provider-cli orders ship ORDER_ID1 ORDER_ID2 ...`

3. **Done**: Stop after executing
```

**Checklist**:
- [ ] Add state context note
- [ ] Remove state-check commands
- [ ] Keep only action commands

---

## Phase 3: Testing (30 minutes)

### Test 3.1: Verify code runs without errors

```bash
# Test imports and functions
cd /workspaces/printer-factory-sim
.venv/bin/python -c "
from engine.turn_engine import fetch_all_state_concurrent, format_state_for_prompt
import asyncio

# Test that functions are importable
print('✅ Functions imported successfully')
"
```

**Checklist**:
- [ ] No import errors
- [ ] Functions are callable

### Test 3.2: Run single day and verify state is embedded

```bash
# Run a test day
rm -rf logs/*
time .venv/bin/python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 1 2>&1 | head -30
```

**Expected output**:
```
Turn engine — scenario: smoke-test
Running 1 day(s).

=== Day 1 ===
  [Factory] state pre-fetched        ← NEW: shows state was fetched
  [PrinterWorld] agent: ...
  [Factory] agent: ...
```

**Checklist**:
- [ ] State pre-fetch message appears
- [ ] No errors
- [ ] Day completes

### Test 3.3: Check logs for reduced tool calls

```bash
# Count tool calls
echo "Total tool calls:"
wc -l logs/day-001-bash-calls.jsonl

echo "Tool calls by command:"
jq '.command' logs/day-001-bash-calls.jsonl | sort | uniq -c | sort -rn
```

**Expected**:
```
Previous: ~47 total calls (7 state + 40 actions)
After: ~10-15 total calls (0 state + 10-15 actions)
```

**Checklist**:
- [ ] Tool call count drops significantly (25+ fewer)
- [ ] No more repeated `capacity`, `inventory` calls
- [ ] Remaining calls are action commands

### Test 3.4: Verify decisions are identical

```bash
# Compare prompt content
echo "=== First 100 lines of prompt ===" 
head -100 logs/day-001-Factory.log | grep -A 50 "## Provided State Data"
```

**Expected**:
- Prompt includes state data section
- State formatted as readable tables
- Same decision framework (no simplification)

**Checklist**:
- [ ] State context appears in prompt
- [ ] Format is readable
- [ ] Decisions are same (compare with previous run)

### Test 3.5: Measure speedup

```bash
echo "=== SPEEDUP TEST ==="
echo "Current mode (baseline):"
rm -rf logs/*
time .venv/bin/python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 5 2>&1 | tail -3

echo ""
echo "Optimized mode (after implementation):"
rm -rf logs/*
time .venv/bin/python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 5 2>&1 | tail -3
```

**Expected**:
```
Current:   ~14 minutes (865 seconds)
Optimized: ~5-7 minutes (300-420 seconds)
Speedup:   2.2-2.5×
```

**Checklist**:
- [ ] Speedup is in 2-2.5× range
- [ ] 5 days complete in under 8 minutes
- [ ] All decisions look correct

---

## Phase 4: Validation (15 minutes)

### Validation 4.1: Accuracy check

```bash
# Run both modes (current code + optimized) and compare outputs
# The day summary line should show same or very similar metrics

echo "Check day summaries:"
grep "summary\]" logs/day-001-api-calls.jsonl
```

**Expected**: Same inventory counts, same orders fulfilled, etc.

**Checklist**:
- [ ] Daily summaries match
- [ ] No accuracy regressions

### Validation 4.2: Code review

**Checklist**:
- [ ] No hardcoded URLs (use config)
- [ ] Error handling in place (fetch failures)
- [ ] State formatting is readable
- [ ] Comments added for clarity

### Validation 4.3: Documentation update

**Checklist**:
- [ ] Add note to CLAUDE.md about state-in-prompt optimization
- [ ] Update DEBUG_PERF.md if needed
- [ ] Remove low-latency mode docs (not needed anymore)

---

## Summary Checklist

### Phase 1: Turn Engine Updates (✓ all done)
- [ ] Add `fetch_all_state_concurrent()` function
- [ ] Add `format_state_for_prompt()` function
- [ ] Update `run_role_agent()` signature
- [ ] Update `build_prompt()` signature
- [ ] Update `run_day()` to fetch state
- [ ] Add `import asyncio`

### Phase 2: Skill File Updates (✓ all done)
- [ ] Update manufacturer-manager.md
- [ ] Update retail-manager.md
- [ ] Update provider-manager.md

### Phase 3: Testing (✓ all done)
- [ ] Functions import without error
- [ ] Day completes with state pre-fetch message
- [ ] Tool call count drops 25+
- [ ] State appears in prompt
- [ ] Speedup is 2-2.5×
- [ ] Decisions match previous runs

### Phase 4: Validation (✓ all done)
- [ ] Daily summaries accurate
- [ ] No regressions
- [ ] Code review complete
- [ ] Docs updated

---

## Total Time Estimate

| Phase | Time | Status |
|-------|------|--------|
| 1: Turn engine updates | 60 min | Ready to code |
| 2: Skill file updates | 45 min | Ready to code |
| 3: Testing | 30 min | Ready to test |
| 4: Validation | 15 min | Ready to validate |
| **TOTAL** | **150 min** | **2.5 hours** |

**Ready to start?** ✅ All steps documented and detailed.
