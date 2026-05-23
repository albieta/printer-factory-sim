# Low-Latency Mode Implementation Plan

## Goal
Add a **low-latency mode** parameter that reduces single-day execution from ~170s to <30s while maintaining simulation consistency.

## Problem Analysis

### Current State (Normal Mode)
- **Time per day**: 173s (Haiku)
- **Bottleneck**: Manufacturer agent (101s)
  - 30 tool calls
  - Complex skill file (112 lines, 6-step framework)
  - Repeated state checks
  - Decision branching (scaling, pricing, ordering)

### Target (Low-Latency Mode)
- **Time per day**: 20-35s per day
  - Retailer: 10-15s
  - Manufacturer: 10-15s
  - Provider: 5-10s
  - Overhead: 2-3s

### Strategy
Use **simpler skill files** that make **fewer, batched tool calls** with **less reasoning**.

---

## Implementation: 4-Phase Plan

### Phase 1: Create Low-Latency Skill Files

**Files to create**:

#### `skills/retail-manager-fast.md` (Lightweight)
```markdown
# Retail Manager — Fast Mode

Role: Check stock briefly, place restocking orders if needed.

Commands:
```bash
bin/retailer-cli catalog  # Check prices
bin/retailer-cli stock    # Check inventory
bin/retailer-cli purchase create --product MODEL --qty N  # Restock
```

Decision: If stock < 50 units, restock to 200.

Summary: 1-2 bullets.
```

**Expected**: 10-15s (vs 42s normal)  
**Tradeoff**: No price adjustments, no demand analysis, bare-minimum restocking

#### `skills/manufacturer-manager-fast.md` (Lightweight)
```markdown
# Manufacturer Manager — Fast Mode

Role: Release ready orders, order critical materials.

Commands:
```bash
bin/manufacturer-cli sales orders --status PENDING | head -5  # Top 5 pending
bin/manufacturer-cli purchase list  # Check inbound
bin/manufacturer-cli production release ORDER_ID  # Release one order
bin/manufacturer-cli purchase create --supplier NAME --product MAT --qty N  # Order materials
```

Decision:
1. Get 5 pending orders
2. Check capacity: How many can we release?
3. Release N orders
4. Find critical material shortages (stock < 50)
5. Order 200 units of each critical material
6. Done.

Summary: 2-3 bullets (orders released, materials ordered, done).
```

**Expected**: 10-15s (vs 101s normal)  
**Tradeoff**: No scaling, no pricing, only 5 orders max per day, simple logic

#### `skills/provider-manager-fast.md` (Lightweight)
```markdown
# Provider Manager — Fast Mode

Role: Check orders, ship when ready.

Commands:
```bash
bin/provider-cli orders list --status IN_PROGRESS  # Get in-progress orders
bin/provider-cli orders show ID  # Check one order
bin/provider-cli orders ship ID  # Ship it
```

Decision:
1. Get in-progress orders (max 5)
2. Ship each if lead time is met
3. Done.

Summary: 1-2 bullets.
```

**Expected**: 5-10s (vs 32s normal)  
**Tradeoff**: No complex logic, just ship-ready orders

---

### Phase 2: Add Mode Parameter to Turn Engine

**File**: `engine/turn_engine.py`

**Change 1**: Add parameter to `run_role_agent()`

```python
def run_role_agent(
    role: str,
    role_cfg: dict[str, Any],
    day: int,
    signal: dict[str, Any],
    low_latency: bool = False,  # NEW
) -> str:
    """Run the stub or claude agent for a role; return log output."""
    import os
    skill_file: str | None = role_cfg.get("skill") or None
    
    # NEW: Switch skill file based on mode
    if low_latency and skill_file:
        fast_variant = skill_file.replace(".md", "-fast.md")
        if Path(fast_variant).exists():
            skill_file = fast_variant
    
    # ... rest of function
```

**Change 2**: Add parameter to `run_day()`

```python
def run_day(
    config: dict[str, Any],
    scenario: dict[str, Any],
    day: int,
    low_latency: bool = False,  # NEW
) -> dict[str, Any]:
    # ... existing code ...
    
    # Pass low_latency to agent runners
    for r_cfg in retailers:
        role = r_cfg.get("name", "retailer")
        agent_outputs[role] = run_role_agent(role, r_cfg, day, signal, low_latency)
    
    # ... similar for manufacturer and providers
```

**Change 3**: Add parameter to `main()`

```python
def main(argv: list[str]) -> int:
    # ... parsing ...
    
    low_latency = os.environ.get("CLAUDE_LOW_LATENCY", "").lower() == "true"
    
    for day in range(1, num_days + 1):
        run_day(config, scenario, day, low_latency)
```

---

### Phase 3: Update Scenario Runner & API

**File**: `manufacturer/backend/app/services/scenario_runner.py`

```python
def start(
    self,
    config_name: str,
    scenario_name: str,
    days: int,
    model: str = "claude-haiku-4-5-20251001",
    thinking_enabled: bool = False,
    low_latency: bool = False,  # NEW
    # ... other params
) -> dict[str, Any]:
    # ... existing code ...
    
    env = os.environ.copy()
    env["CLAUDE_MODEL"] = model
    env["CLAUDE_THINKING_ENABLED"] = "true" if thinking_enabled else "false"
    env["CLAUDE_LOW_LATENCY"] = "true" if low_latency else "false"  # NEW
    # ... other env vars
```

**File**: `manufacturer/backend/app/api/routes/scenarios.py`

```python
class ScenarioStartRequest(BaseModel):
    config: str
    scenario: str
    days: int
    model: str = Field(default="claude-haiku-4-5-20251001")
    thinking_enabled: bool = Field(default=False)
    low_latency: bool = Field(default=False, description="Fast mode: simpler decisions, fewer tool calls")  # NEW
    # ... other fields
```

---

### Phase 4: Update UI (React Scenarios Tab)

**File**: `manufacturer/frontend/src/pages/ScenariosPage.tsx`

Add to the form before "Start Run":

```typescript
<Form.Group className="mb-3">
  <Form.Label>Agent Mode</Form.Label>
  <Form.Select
    value={mode}
    onChange={(e) => setMode(e.target.value as "normal" | "fast")}
  >
    <option value="normal">Normal (Full Reasoning, ~170s/day)</option>
    <option value="fast">Low-Latency (Fast, ~25s/day)</option>
  </Form.Select>
  <Form.Text>
    Normal: Complex decisions, all features. Fast: Simplified logic, core features only.
  </Form.Text>
</Form.Group>
```

In the request payload:

```typescript
const payload: ScenarioStartRequest = {
  config: selectedConfig,
  scenario: selectedScenario,
  days: numDays,
  model: selectedModel,
  thinking_enabled: thinkingEnabled,
  low_latency: mode === "fast",  // NEW
};
```

---

## Expected Timeline Impact

### Normal Mode (No Change)
- 1 day: 173s
- 5 days: 865s (~14m)
- 25 days: 4325s (~72m)

### Low-Latency Mode
- 1 day: 25s
- 5 days: 125s (~2m)
- 25 days: 625s (~10m)

**Speedup**: 6.9× faster per day

---

## Implementation Checklist

- [ ] **Phase 1**: Create 3 `-fast.md` skill files
  - [ ] `skills/retail-manager-fast.md`
  - [ ] `skills/manufacturer-manager-fast.md`
  - [ ] `skills/provider-manager-fast.md`

- [ ] **Phase 2**: Update turn_engine.py
  - [ ] Add `low_latency` parameter to `run_role_agent()`
  - [ ] Add skill file switching logic
  - [ ] Add parameter to `run_day()`
  - [ ] Add parameter to `main()` with env var

- [ ] **Phase 3**: Update scenario runner & API
  - [ ] Add `low_latency` to `ScenarioRunner.start()`
  - [ ] Add env var passing
  - [ ] Add `low_latency` to `ScenarioStartRequest` Pydantic model

- [ ] **Phase 4**: Update React UI
  - [ ] Add mode selector dropdown
  - [ ] Update request payload
  - [ ] Test full flow

- [ ] **Testing**
  - [ ] Verify fast mode skill files work
  - [ ] Measure timing of all 3 agents in fast mode
  - [ ] Ensure toggle works end-to-end (UI → scenario runner → engine)
  - [ ] Verify logs show `-fast.md` was used
  - [ ] Run 5-day scenario in both modes and compare metrics

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Fast mode is *too* simple, breaks simulation | Use fast-mode files only for UI testing; keep normal mode for real scenarios |
| Users forget to toggle and get wrong results | Add banner in UI: "Running in FAST mode" if enabled |
| Skill files out of sync with normal versions | Document that fast files are intentionally simple; review together on updates |
| Skills reference CLI commands that don't exist | Test each `-fast.md` file by running manually before release |

---

## Future Enhancements

1. **Adaptive latency**: Adjust skill complexity based on scenario parameters
2. **Caching**: Cache agent responses for identical inputs (days 1-5 might look same)
3. **Parallelization**: Run retailer + provider concurrently (only manufacturer is sequential-heavy)
4. **Streaming**: Show agent decisions in real-time instead of waiting for full day
5. **Model selection**: Let users choose between Haiku (fast) and Sonnet (more powerful) per role
