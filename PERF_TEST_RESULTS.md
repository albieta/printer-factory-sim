# Performance Test Results — Single Day Simulation

## Test Summary

**Date**: 2026-05-22  
**Model Used**: Confirmed `claude-haiku-4-5-20251001` (via `--model` flag)  
**Thinking Mode**: Off (no `--thinking` or budget-tokens flags)  
**Baseline**: 2.3 seconds (stub agents, pure HTTP/API overhead)

## Per-Agent Breakdown

| Agent | Time | % of Total | Tool Calls | Complexity |
|-------|------|-----------|-----------|-----------|
| **Retailer** | 41.6s | 24% | ~10 | Low (basic stock checks) |
| **Manufacturer** | 101.3s | 58% | ~30 | High (capacity, production, orders) |
| **Provider** | 31.6s | 18% | ~8 | Low (stock, orders) |
| **API/Turn Overhead** | 2.3s | – | – | (baseline) |
| **TOTAL** | **173.4s** | 100% | **~48** | Mixed |

**Key Insight**: Manufacturer agent accounts for 58% of total time (101 seconds), 3x slower than Retailer.

## Why is Manufacturer Slow?

### 1. **Complex Skill File** (112 lines)
   - Long decision framework with 6 steps
   - Many conditional branches (scaling, pricing, ordering)
   - Requires understanding of financial constraints

### 2. **Many Tool Calls** (~30 per day)
   - Repeated state checks: `capacity` called 4 times, `inventory` 3 times
   - Sequential commands due to error handling (e.g., `financial summary` not found caused retries)
   - Agent must reason about each tool result before proceeding

### 3. **Tool Call Latency**
   - Each bash call spawns a subprocess
   - CLI parsing and database queries add ~50-200ms per call
   - 30 calls × 100ms average = ~3 seconds in tool overhead alone
   - Plus time for Haiku to reason about results between calls

### 4. **CLI Command Issues**
   - Skill file references `bin/manufacturer-cli financial summary` → does NOT exist
   - This causes tool cancellation and agent must retry logic
   - Adds unnecessary tokens and delay

## Response Model Confirmation

All responses confirmed to be from **Haiku**:

```bash
[DEBUG] Day 1 - Factory: claude --print --verbose --output-format stream-json \
  --permission-mode bypassPermissions --allowedTools Bash \
  --model claude-haiku-4-5-20251001 \
  --add-dir /workspaces/printer-factory-sim -- <prompt>
```

No thinking, no caching, no budget parameters. Pure streaming JSON output.

## Logs Generated

- `logs/day-001-Factory.log` — 601 lines (full flow: prompt → 30 tool calls → response)
- `logs/day-001-PrinterWorld.log` — 210 lines  
- `logs/day-001-ChipSupply Co.log` — 195 lines  
- `logs/day-001-bash-calls.jsonl` — 47 entries (individual bash commands)

**File sizes reflect agent complexity:**
- Manufacturer log is 2.8× larger than Retail (due to tool calls)
- Tool calls logged: all commands + stdout/stderr for audit trail

## Theoretical vs. Actual

| Metric | Haiku Expectation | Actual | Gap |
|--------|---|---|---|
| Output tokens/call | 200-500 | ~300-600 | ✓ Expected range |
| Tool call overhead | ~100ms | ~100-200ms | ✓ Expected |
| Total time for 3 agents | 60-90s | 173s | ⚠ 2× slower |

The 2× gap is due to:
1. Complex reasoning (decision frameworks, capacity calculations)
2. Sequential tool dependency (can't parallelize, each call needs previous result)
3. Error handling (retries due to missing commands)
4. Deliberation time between tool calls

## Conclusions

1. **Haiku IS being used** — confirmed at subprocess level
2. **Thinking mode is OFF** — no extended thinking flags
3. **Bottleneck is Manufacturer agent** — 101s = 58% of total time
   - Not a model issue; it's skill file complexity + tool call overhead
   - Decision framework has 6 steps with conditional branching
4. **Root causes of latency**:
   - ❌ Missing `financial summary` command (causes retries)
   - ⚠ Repeated state checks (could be cached)
   - ⚠ Sequential tool dependency (can't parallelize)
   - ✓ Model choice is correct (Haiku appropriate for CLI tool calls)

## Recommendations for Low-Latency Mode

### Quick Wins (No Code Changes)
1. **Fix missing `financial summary` command** — remove from skill file or implement CLI command
2. **Reduce tool call redundancy** — skill should cache state instead of re-checking

### Low-Latency Mode Features (New)
1. **Faster skill variant** — simplified decision framework for 2-3 second agent runs
2. **Batch tool calls** — combine checks into single commands (e.g., `status --all`)
3. **Optional parallelization** — run retailer + provider in parallel (manufacturer is sequential-heavy)
4. **Skip optional steps** — disable pricing/scaling decisions for lower latency

See `LATENCY_FIX_PLAN.md` for detailed implementation.
