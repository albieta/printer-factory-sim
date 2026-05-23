# Latency Investigation & Fix Plan — Executive Summary

## What We Tested

✅ **Verified the model and configuration** by running a single simulated day with real Claude agents.

### Test Results

| Metric | Result |
|--------|--------|
| **Model Used** | ✅ Confirmed `claude-haiku-4-5-20251001` |
| **Thinking Mode** | ✅ Off (no `--thinking` or budget flags) |
| **Single Day Time** | 173 seconds (2m 53s) |
| **Baseline (API Only)** | 2.3 seconds |

### Per-Agent Breakdown

```
Retailer:       41.6s  (24% of total)
Manufacturer:  101.3s  (58% of total) ← BOTTLENECK
Provider:       31.6s  (18% of total)
─────────────────────
TOTAL:         173.4s  (100%)
```

**Key Finding**: Manufacturer agent takes ~3× longer than the others.

## Why Is It Slow?

The Manufacturer agent is slow because:

1. **Complex decision framework** (112-line skill file)
   - 6-step reasoning process
   - Multiple conditional branches (scaling decisions, pricing adjustments)
   - Requires understanding financial constraints

2. **Many tool calls** (~30 per day)
   - Repeated state checks (capacity checked 4 times, inventory 3 times)
   - Each call spawns a subprocess + CLI parsing
   - Agent must reason about each result before next call

3. **Sequential dependencies**
   - Can't parallelize: each tool call depends on previous result
   - Agent is waiting for tool results between decisions

4. **CLI Issues**
   - Skill file references `bin/manufacturer-cli financial summary` which doesn't exist
   - Causes error retries and wasted tokens

## What's NOT the Problem

❌ **Not thinking mode** — extended thinking is OFF  
❌ **Not a bigger model** — Haiku is correctly configured  
❌ **Not network latency** — API overhead is only 2.3s baseline  
❌ **Not token limits** — Haiku can handle these prompts easily  

**Conclusion**: The slowness is due to **skill file complexity** and **sequential tool dependencies**, not the model choice.

---

## Solution: Low-Latency Mode

We propose adding a **low-latency mode** that uses simplified skill files and reduces single-day time from **173s → ~25s** (6.9× speedup).

### How It Works

1. **Two skill file variants per role**:
   - `retail-manager.md` (normal, 96 lines) vs `retail-manager-fast.md` (simple, ~30 lines)
   - `manufacturer-manager.md` (normal, 112 lines) vs `manufacturer-manager-fast.md` (simple, ~40 lines)
   - `provider-manager.md` (normal, 88 lines) vs `provider-manager-fast.md` (simple, ~25 lines)

2. **New parameter**: `--low-latency` or `low_latency=true`
   - When enabled, engine uses `-fast.md` variant of each skill
   - Falls back to normal `.md` if fast variant doesn't exist

3. **Updated UI**: Dropdown in Scenarios tab
   ```
   Agent Mode: [ Normal (Full Reasoning, ~170s/day) ] vs
               [ Low-Latency (Fast, ~25s/day) ]
   ```

### Expected Performance

| Metric | Normal Mode | Low-Latency Mode |
|--------|-------------|------------------|
| Time per day | 173s | ~25s |
| Tool calls | ~48 | ~15 |
| Reasoning | Complex (6 steps) | Simple (2-3 steps) |
| Use case | Final production scenarios | Testing, UI demos, rapid iteration |

### Trade-offs

| Normal Mode | Low-Latency Mode |
|------------|-----------------|
| Complex multi-step decisions | Simplified heuristics |
| Scaling, pricing adjustments | Core operations only |
| Full financial analysis | Basic checks |
| 170s/day = 70 min for 25 days | 25s/day = 10 min for 25 days |

---

## Implementation Roadmap

### 4 Phases (Est. 2-4 hours work)

**Phase 1: Create fast skill files** (30 min)
- Write 3 simplified skill files (30-40 lines each)
- Test manually with `bin/manufacturer-cli` etc.

**Phase 2: Update turn engine** (30 min)
- Add `low_latency` parameter
- Implement skill file switching logic
- Add env var support

**Phase 3: Update backend API** (20 min)
- Add `low_latency` to `ScenarioStartRequest`
- Pass env var to subprocess
- Update `scenario_runner.py`

**Phase 4: Update React UI** (20 min)
- Add mode selector dropdown
- Connect to new `low_latency` parameter
- Add labels/help text

**Testing & Polish** (20 min)
- Verify timing improvements
- Test edge cases
- Update docs

---

## Files to Create/Modify

### Create
- [ ] `skills/retail-manager-fast.md` — simplified retail skill
- [ ] `skills/manufacturer-manager-fast.md` — simplified manufacturer skill
- [ ] `skills/provider-manager-fast.md` — simplified provider skill

### Modify
- [ ] `engine/turn_engine.py` — add `low_latency` parameter & logic
- [ ] `manufacturer/backend/app/services/scenario_runner.py` — add env var
- [ ] `manufacturer/backend/app/api/routes/scenarios.py` — add `low_latency` field
- [ ] `manufacturer/frontend/src/pages/ScenariosPage.tsx` — add UI selector

### Documentation
- [ ] `LATENCY_FIX_PLAN.md` — detailed implementation guide (CREATED)
- [ ] Update `CLAUDE.md` — add low-latency mode section
- [ ] Update README — mention latency modes

---

## Quick Start for Low-Latency Testing

Once implemented, users can run fast mode like this:

### From CLI
```bash
CLAUDE_LOW_LATENCY=true python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 5
# Expected: ~2 min 5 days (vs ~14 min normal)
```

### From UI
1. Open http://localhost:3000/scenarios
2. Select config & scenario
3. **Click** "Agent Mode: Low-Latency"
4. Click "Start Run"
5. Watch 5 days complete in ~2-3 minutes instead of 14

---

## Appendix: Test Logs

All test results are documented in:
- `PERF_TEST_RESULTS.md` — detailed timing breakdown
- `DEBUG_PERF.md` — debugging guide for future reference
- `logs/day-001-*.log` — raw agent logs with full prompt/response/tool calls

To re-run tests:
```bash
# Stub scenario (baseline only)
.venv/bin/python -m engine.turn_engine config/sim-stub.json scenarios/smoke-test.json 1

# Individual agents
.venv/bin/python -m engine.turn_engine config/sim-retailer-only.json scenarios/smoke-test.json 1
.venv/bin/python -m engine.turn_engine config/sim-manufacturer-only.json scenarios/smoke-test.json 1
.venv/bin/python -m engine.turn_engine config/sim-provider-only.json scenarios/smoke-test.json 1

# All together
.venv/bin/python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 1
```

---

## Questions & Answers

**Q: Why not just use a faster model?**  
A: Haiku IS the fastest Claude model. Switching to Sonnet would be 2-3× slower, not faster. The bottleneck is skill complexity, not model speed.

**Q: Why can't you parallelize agents?**  
A: We *could* run retailer + provider in parallel, but:
- Turn engine drives day advances in order (retailer → manufacturer → providers)
- Manufacturer depends on sales orders from retailer
- Adds complexity without huge speedup (Retailer + Provider = 73s, still < Manufacturer's 101s)
- Low-latency mode is simpler solution

**Q: Will fast mode break simulation accuracy?**  
A: Fast mode makes simpler decisions (e.g., restock at fixed threshold instead of analyzing demand). Results will differ but simulation remains valid. Use normal mode for final scenarios, fast mode for testing/demos.

**Q: Can I switch modes mid-run?**  
A: No, mode is set at run start. Each day uses the same mode throughout the run.

**Q: What about longer scenarios (30+ days)?**  
A: Low-latency: 30 days ≈ 12 minutes. Normal: 30 days ≈ 86 minutes. Low-latency makes big scenarios practical.

---

## Next Steps

1. **Review this summary** with stakeholders
2. **Approve the 4-phase plan** (LATENCY_FIX_PLAN.md)
3. **Assign implementation** (2-4 hours estimated)
4. **Test both modes** with real scenarios
5. **Update docs** with latency mode guidance
