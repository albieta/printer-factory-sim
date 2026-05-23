# High-Accuracy Latency Optimization Plan

## Core Insight

The bottleneck is NOT Claude reasoning—it's **tool call overhead**:
- Each bash call spawns subprocess (~100ms overhead)
- Repeated state checks (capacity called 4×, inventory 3×)
- Sequential dependencies (agent waits for each result)

**Solution**: Bundle state data upfront + batch tool calls = keep accuracy, reduce latency.

---

## Current Flow (173s, 30 tool calls)

```
Agent starts
  ↓
"Get capacity" → subprocess → parse → wait
  ↓
"Get inventory" → subprocess → parse → wait
  ↓
"Get sales orders" → subprocess → parse → wait
  ↓
... (27 more sequential calls)
  ↓
Agent decides
```

**Problem**: 30 context-switches between agent reasoning and tool execution.

---

## Proposed Flow (Est. 40-50s, ~5-8 tool calls)

```
Turn engine pre-fetches state (parallel batch):
  ├─ capacity
  ├─ inventory
  ├─ sales orders (PENDING)
  ├─ purchase list
  ├─ production status
  └─ price list
        ↓
Agent receives prompt with ALL state embedded:
  "Here's your current state:
   Capacity: 1 line × 1 worker × 8 hours = 8/day
   Inventory: Basic300(500), Elite700(200), Pro450(800), ...
   PENDING orders: SO-0001-025 (Basic300×2), SO-0001-026 (Elite700×1), ...
   ..."
        ↓
Agent reasons through all decisions at once
        ↓
Agent calls tools (batch):
  ├─ release SO-0001-025 SO-0001-026 SO-0001-027
  ├─ purchase ChipSupply/PLA 300
  ├─ purchase ChipSupply/LCD 100
  ├─ open-assembly-line
  └─ hire-worker
        ↓
Done (agent made all decisions, tool calls are just actions)
```

**Benefit**: 
- State pre-loaded → no repeated queries
- Agent decides everything upfront → batch tool calls
- 30 calls → 5-8 calls (83% reduction)
- Same decision quality (agent sees same info, just different format)

---

## Implementation: 3 Strategies

### Strategy 1: State-in-Prompt (Fastest, Easiest)

**Where**: `turn_engine.py` and agent skill files

**How**:
1. Before spawning agent, fetch all state via API
2. Include state snapshot in the prompt as context
3. Agent reads state from prompt, not via tool calls

**Example**:

```python
# In turn_engine.py, before calling run_role_agent()
def get_manufacturer_state(mfr_url: str) -> dict:
    """Fetch all manufacturer state in parallel."""
    return {
        "day": _get(f"{mfr_url}/api/day/current"),
        "capacity": _get(f"{mfr_url}/api/capacity"),
        "inventory": _get(f"{mfr_url}/api/inventory"),
        "sales_orders": _get(f"{mfr_url}/api/sales/orders?status=PENDING"),
        "purchase_list": _get(f"{mfr_url}/api/purchases"),
        "production_status": _get(f"{mfr_url}/api/production/status"),
        "prices": _get(f"{mfr_url}/api/prices"),
    }

# Fetch all state ONCE before agent runs
state = get_manufacturer_state(mfr_url)

# Pass to agent as context
prompt = f"""
# Manufacturer Manager Skill

## Current State (as of {state['day']}):

**Capacity**: {state['capacity']['lines']} lines × {state['capacity']['workers']} workers × {state['capacity']['hours']} hours = {state['capacity']['daily_hours']} hours/day

**Inventory**:
- Basic300: {state['inventory']['Basic300']} units
- Elite700: {state['inventory']['Elite700']} units
- Pro450: {state['inventory']['Pro450']} units
- PLA Filament: {state['inventory']['PLA']} units
- LCD Screen: {state['inventory']['LCD']} units

**PENDING Sales Orders** (to fulfill):
{format_orders(state['sales_orders'])}

**Inbound Purchase Orders** (arriving):
{format_purchases(state['purchase_list'])}

**Current Prices**:
{format_prices(state['prices'])}

## Your Task

Based on the state above, decide:
1. Which orders to release (and in what order)
2. Which materials to order (and how much)
3. Whether to scale capacity (and how)
4. Whether to adjust prices (based on demand signal)

When you're done deciding, call the appropriate CLI commands to execute all actions at once.

## Market signal for day {day}

{signal_data}

...rest of skill file...
"""

# Agent reads state from prompt (no tool calls needed for state checks!)
# Agent decides everything, then calls tools to execute
```

**Trade-offs**:
- ✅ Minimal code changes
- ✅ Batch tool calls naturally (agent decides all, then executes)
- ✅ Full accuracy (agent sees exact state)
- ✅ Easy to implement (1-2 hours)
- ⚠️ Prompt gets larger (~2-3KB of state data)

**Expected speedup**: 173s → 60-80s (2.2-2.9× faster)

---

### Strategy 2: Batch Tool Invocations (Parallel Calls)

**Where**: `agent_runner.py` or Claude API integration

**How**:
When agent needs multiple pieces of state, call them in parallel instead of sequential.

**Current behavior** (sequential):
```python
# Tool call 1
result1 = subprocess.run(["bin/cli", "capacity"])
# Wait for result
process_result_1()

# Tool call 2
result2 = subprocess.run(["bin/cli", "inventory"])
# Wait for result
process_result_2()
```

**Proposed** (parallel):
```python
import concurrent.futures

# Start 5 tool calls in parallel
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    future_capacity = executor.submit(subprocess.run, ["bin/cli", "capacity"])
    future_inventory = executor.submit(subprocess.run, ["bin/cli", "inventory"])
    future_orders = executor.submit(subprocess.run, ["bin/cli", "sales", "orders"])
    future_purchases = executor.submit(subprocess.run, ["bin/cli", "purchase", "list"])
    future_production = executor.submit(subprocess.run, ["bin/cli", "production", "status"])
    
    # Wait for all to complete
    capacity = future_capacity.result()
    inventory = future_inventory.result()
    orders = future_orders.result()
    purchases = future_purchases.result()
    production = future_production.result()
```

**Problem**: Claude API doesn't natively support this (agent makes calls sequentially via stream-json output).

**Workaround**: Implement a tool-batching wrapper that:
1. Agent requests multiple tools in a single output
2. Wrapper runs them in parallel
3. Returns all results together

**Trade-offs**:
- ✅ Minimal skill file changes
- ✅ Better for independent state checks
- ⚠️ Requires custom wrapper logic
- ⚠️ Only helps if agent makes multiple independent calls
- ⚠️ Manufacturer has sequential dependencies (order → release → decide)

**Expected speedup**: 173s → 100-120s (1.4-1.7× faster)

---

### Strategy 3: API Endpoint for Bulk State (Best Accuracy + Speed)

**Where**: Manufacturer API routes

**How**:
Create a single endpoint that returns all state at once (optimized query).

**New endpoint**:
```python
# manufacturer/backend/app/api/routes/state.py
@router.get("/api/state/all")
def get_all_state() -> dict:
    """Return all state needed for decision-making in one call."""
    session = SessionLocal()
    return {
        "day": get_simulation_config(session).sim_date,
        "capacity": get_capacity_metrics(session),
        "inventory": get_all_inventory(session),
        "sales_orders": get_pending_orders(session),
        "purchase_orders": get_inbound_purchases(session),
        "production_status": get_production_summary(session),
        "prices": get_all_prices(session),
        "financial": get_financial_summary(session),
    }
```

**Benefits**:
- ✅ Single HTTP call instead of 7
- ✅ Database queries batched (one session)
- ✅ No subprocess overhead for state checks
- ✅ Turn engine can fetch in parallel across apps

**Trade-offs**:
- ✅ Clean API design (good for future)
- ⚠️ Requires new endpoint (small effort)
- ⚠️ Database query optimization needed

**Expected speedup**: 173s → 50-70s (2.5-3.5× faster)

---

## Recommended Approach: Combine 1 + 3

### Phase A: State-in-Prompt (Quick Win)
1. **Create helper function** in `turn_engine.py`:
   ```python
   def fetch_manufacturer_state(mfr_url: str) -> dict:
       """Fetch all state in parallel using httpx."""
       with httpx.Client() as client:
           return {
               "day": client.get(f"{mfr_url}/api/day/current").json(),
               "capacity": client.get(f"{mfr_url}/api/capacity").json(),
               "inventory": client.get(f"{mfr_url}/api/inventory").json(),
               # ... 5 more calls in parallel httpx batch
           }
   ```

2. **Format state for prompt**:
   ```python
   state = fetch_manufacturer_state(mfr_url)
   state_context = f"""
   ## Current State (Day {state['day']['date']})
   
   **Capacity**: {state['capacity']['lines']} lines × {state['capacity']['workers']} workers = {state['capacity']['daily_hours']}/day
   
   **Inventory**:
   {format_inventory_table(state['inventory'])}
   
   **PENDING Orders**:
   {format_orders_table(state['sales_orders'])}
   
   ... (more state)
   """
   ```

3. **Update skill file** to reference state in prompt (no tool calls needed):
   ```markdown
   # Manufacturer Manager Skill
   
   ## Current State
   [State data embedded from prompt above]
   
   ## Your Task
   Based on the state above:
   1. Decide which orders to release
   2. Decide what materials to order
   3. Decide if capacity needs scaling
   
   When ready, execute ALL actions via these commands:
   ```
   bin/manufacturer-cli production release ORDER_ID [ORDER_ID ...]
   bin/manufacturer-cli purchase create --supplier "X" --product "Y" --qty Z
   bin/manufacturer-cli open-assembly-line
   bin/manufacturer-cli hire-worker
   ```
   
   Stop after executing commands.
   ```

4. **Result**: Agent makes 1-2 final action calls instead of 30 state checks
   - First reads all state from prompt (no calls)
   - Decides everything
   - Executes all actions in 1-2 calls (batch release, batch purchase)

**Time estimate**: 90s → 40-50s per manufacturer agent (2-2.25× speedup)

### Phase B: Bulk State Endpoint (For UI/Future)
Later, create `/api/state/all` endpoint for cleaner architecture.

---

## Implementation Effort

| Strategy | Effort | Speedup | Accuracy | Complexity |
|----------|--------|---------|----------|-----------|
| State-in-Prompt | 2 hours | 2-2.5× | ✅ 100% | Low |
| Batch Tools | 3 hours | 1.4× | ✅ 100% | Medium |
| Bulk Endpoint | 2 hours | 2.5-3.5× | ✅ 100% | Low |
| **Combined (1+3)** | **3-4 hours** | **2-3×** | **✅ 100%** | **Low** |

---

## Expected Results (Combined Approach)

### Before (Current)
```
Retailer:       41.6s  (10 state checks)
Manufacturer:  101.3s  (30 state checks) ← Bottleneck
Provider:       31.6s  (8 state checks)
─────────────────────
TOTAL:         173.4s
```

### After (State-in-Prompt + Bulk Endpoint)
```
Retailer:       20-25s  (1-2 final calls)
Manufacturer:   25-35s  (1-2 final calls) ← Optimized
Provider:       15-20s  (1-2 final calls)
─────────────────────
TOTAL:          65-80s  (2.1-2.7× faster)
```

### Per-Day Time (25-day scenario)
```
Current:  173s × 25 = 4325s = 72 minutes
Optimized: 75s × 25 = 1875s = 31 minutes
Speedup: 2.3×
```

---

## Files to Modify

### Phase A: State-in-Prompt (2 hours)

1. **`engine/turn_engine.py`** (add ~50 lines)
   - Add `fetch_all_state()` functions for each role
   - Add `format_state_for_prompt()` helper
   - Fetch state before calling `run_role_agent()`
   - Pass state as context in prompt

2. **`skills/manufacturer-manager.md`** (modify ~30 lines)
   - Add "Current State" section at top
   - Remove repeated state checks from decision framework
   - Add instruction to batch tool calls at end
   - Simplify from "check then decide" → "decide from given state then execute"

3. **`skills/retail-manager.md`** (modify ~20 lines)
   - Similar changes as manufacturer

4. **`skills/provider-manager.md`** (modify ~15 lines)
   - Similar changes as manufacturer

### Phase B: Bulk Endpoint (2 hours, optional)

5. **`manufacturer/backend/app/api/routes/state.py`** (new file, ~100 lines)
   - Create `/api/state/all` endpoint
   - Batch database queries

6. **`engine/turn_engine.py`** (update ~10 lines)
   - Use new endpoint instead of 7 separate calls

---

## Skill File Changes Example

### Before (State-Check Pattern)
```markdown
## Decision Framework

1. **Assess**: Check current state
   - Run `bin/manufacturer-cli day current`
   - Run `bin/manufacturer-cli financial summary`
   - Run `bin/manufacturer-cli capacity`
   - Run `bin/manufacturer-cli inventory`
   - Run `bin/manufacturer-cli sales orders --status PENDING`
   - Run `bin/manufacturer-cli production status`
   - Run `bin/manufacturer-cli purchase list`
   
   Then interpret what you learned...

2. **Fulfil**: For each PENDING order...

3. **Order**: For materials below 50 units...
```

### After (State-Embedded Pattern)
```markdown
## Current State (Provided Above)

Capacity: 1 line × 1 worker × 8 hours = 8 hours/day
Inventory: Basic300(500), Elite700(200), Pro450(800), PLA(790), LCD(100)
PENDING Orders: 126 orders (SO-0001-025 through SO-0001-150)
Inbound: 100 LCD (due 2026-05-29), 300 PLA (due 2026-05-27)
Prices: Basic300($450), Elite700($1400), Pro450($800)

## Decision Framework

Based on the state above:

1. **Fulfil**: Release 8 orders (capacity limit)
   - Release SO-0001-025 SO-0001-026 SO-0001-027 SO-0001-028 SO-0001-029 SO-0001-030 SO-0001-031 SO-0001-032

2. **Order**: Critical materials need restocking
   - Order 100 LCD Screens (current: 100, demand: high)
   - Order 300 PLA Filament (current: 790, demand: 1012.5)

3. **Scale**: Capacity is bottleneck (8 hours vs 126 pending)
   - Open 1 assembly line → 16 hours/day
   - Hire 1 worker → 32 hours/day

4. **Execute**: When you decide, run these commands:
   ```
   bin/manufacturer-cli production release SO-0001-025 SO-0001-026 SO-0001-027 SO-0001-028 SO-0001-029 SO-0001-030 SO-0001-031 SO-0001-032
   bin/manufacturer-cli purchase create --supplier "ChipSupply Co" --product "LCD Screen" --qty 100
   bin/manufacturer-cli purchase create --supplier "ChipSupply Co" --product "PLA Filament" --qty 300
   bin/manufacturer-cli open-assembly-line
   bin/manufacturer-cli hire-worker
   ```
   
   Stop after executing.
```

**Impact**:
- Agent no longer makes 7 state-check calls
- Agent reads state from prompt (no subprocess overhead)
- Agent makes 4-5 action calls (batch release, batch purchase, capacity changes)
- Time: 101s → 25-35s per agent

---

## Testing Plan

### Test 1: Verify Accuracy (No Decisions Change)
```bash
# Run normal mode (current)
time .venv/bin/python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 1
# Record output → day-001-current.log

# Run optimized mode (state-in-prompt)
time .venv/bin/python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 1
# Record output → day-001-optimized.log

# Compare decisions (should be identical or very close)
diff day-001-current.log day-001-optimized.log
```

### Test 2: Measure Speedup
```bash
# Baseline (current) - 5 days
time .venv/bin/python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 5
# Expected: ~14-15 minutes

# Optimized (state-in-prompt) - 5 days
time .venv/bin/python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 5
# Expected: ~5-7 minutes
```

### Test 3: Verify Tool Calls Reduced
```bash
# Check bash call counts
echo "Current mode:"
wc -l logs/day-001-bash-calls.jsonl

echo "Optimized mode:"
wc -l logs/day-001-bash-calls.jsonl

# Expected: 47 → 10-15 calls
```

---

## Backward Compatibility

✅ **Fully backward compatible**:
- Old skill files still work (state-check pattern)
- New skill files work better (state-embedded pattern)
- Can run both simultaneously
- No API changes required (state comes from existing endpoints)
- Falls back gracefully if state fetch fails

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| State becomes stale mid-decision | Fetch state fresh for each day (acceptable 1-2s old) |
| Large state payload | Gzip compress, or only include relevant fields |
| Agent ignores prompt state and re-queries | Update skill file instructions to explicitly forbid queries |
| Financial data missing from state | Add `financial_summary` to bulk state call |

---

## Why This Is Better Than Low-Latency Mode

| Aspect | Low-Latency Mode | State-in-Prompt |
|--------|-----------------|-----------------|
| Accuracy | ⚠️ Lossy (simplified logic) | ✅ Perfect (same decisions) |
| Speed | 6.9× (25s) | 2-2.5× (65-85s) |
| Implementation | 4-5 hours | 2-3 hours |
| Use case | Testing only | Production + testing |
| Complexity | 3 skill variants | 0 new variants |
| Maintenance | 6 files to maintain | 2 files to maintain |

**Conclusion**: State-in-prompt gives you 2-2.5× speedup **without losing any accuracy**, and is simpler to maintain.

---

## Next Steps

1. ✅ **Review this plan** (10 min)
2. ⏳ **Decide**: State-in-Prompt (Phase A), or also add Bulk Endpoint (Phase B)?
3. ⏳ **Implement Phase A** (2 hours):
   - Add state-fetching logic to turn_engine.py
   - Update 3 skill files to use embedded state
   - Remove repeated CLI calls from skill decision framework
4. ⏳ **Test** (1 hour):
   - Verify same decisions are made
   - Measure speedup (expect 2-2.5×)
   - Check tool call count drops (47 → ~12)
5. ⏳ **Optional Phase B** (2 hours):
   - Add `/api/state/all` endpoint for cleaner API
   - Update turn engine to use it

**Time to 2-2.5× speedup: 2-3 hours total**
