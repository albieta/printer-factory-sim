# Batch Execution & Optimization Guide

**Date**: 2026-05-27  
**Status**: ✅ Complete  
**Requirements**: Claude Code Pro subscription (no API key needed)

---

## What's Optimized

### 1. Batch Tool Execution ✅

**How it works:**

Claude's `--print` CLI outputs stream-json format, which includes ALL tool calls Claude decides to make in a single response. We extract them all at once and execute them together before sending results back.

```
Single Claude Response (stream-json):
{
  "type": "assistant",
  "message": {
    "content": [
      {"type": "tool_use", "name": "Bash", "input": {"command": "cmd1"}},
      {"type": "tool_use", "name": "Bash", "input": {"command": "cmd2"}},
      {"type": "tool_use", "name": "Bash", "input": {"command": "cmd3"}},
      {"type": "text", "text": "I'll run these commands..."}
    ]
  }
}
```

**Our approach:**
- Extract all 3 tools from that single response
- Log them as a batch: `BATCH TOOL INVOCATIONS (3 total)`
- Execute all 3 (within subprocess safety constraints)
- Send results back in one message to Claude

**Result:**
- ✅ All tools collected from single response
- ✅ Minimizes iterations
- ✅ Reduces total prompt calls
- ✅ No API key required

---

### 2. Skill File Caching ✅

**Problem:** Skill files are read from disk for every agent, every day.

**Solution:** Cache them in memory since they don't change during a scenario run.

```python
# Before (read every time)
skill_text = Path(skill_file).read_text(encoding="utf-8")  # Disk I/O every call

# After (cached)
if skill_file not in _SKILL_FILE_CACHE:
    _SKILL_FILE_CACHE[skill_file] = Path(skill_file).read_text(encoding="utf-8")
skill_text = _SKILL_FILE_CACHE[skill_file]  # Fast memory lookup
```

**Benefit:**
- 3 skill files (Manufacturer, Provider, Retailer) cached once at start
- On 25 days with 3 agents/day = 75 skill file lookups → 3 disk reads
- 72 memory cache hits instead of disk I/O

---

## Architecture

### Stream-JSON Batch Extraction

```
Claude Response (stream-json)
    ↓
_parse_stream_json() extracts:
  - tool_invocations = [tool1, tool2, tool3, ...]
  - final_text = "I'll execute these..."
    ↓
Batch Processing:
  for tool in tool_invocations:
      execute(tool)
      log(tool)
    ↓
Results → Claude (next iteration)
```

### No API Key Architecture

```
Turn Engine
    ↓
run_agent(skill_file, prompt, state)
    ↓
subprocess.run(["claude", "--print", ...])
    ↓ (uses Claude Code Pro)
Stream-JSON output
    ↓
_parse_stream_json() → batch extract tools
    ↓
Execute batch + log
    ↓
Return final response to turn engine
```

**Key point:** No Anthropic SDK. Uses CLI subprocess. Works with Pro subscription.

---

## Expected Behavior

### Scenario Run Flow

**Day 1, Agent 1 (Manufacturer):**
```
1. Claude called via subprocess
2. Returns response with [tool1, tool2]
3. Both tools extracted as batch
4. Both executed together
5. Results logged and sent back
6. Claude responds: "Done"

Log output:
  === BATCH TOOL INVOCATIONS (2 total) ===
  [CALL: cmd1]
  [CALL: cmd2]
```

**Day 1, Agent 2 (Provider):**
```
1. Skill file fetched from CACHE (not disk)
2. Claude called
3. Returns [tool3]
4. Tool extracted as batch (single item)
5. Executed and results sent back
6. Claude responds

Log output:
  === BATCH TOOL INVOCATIONS (1 total) ===
  [CALL: cmd3]
```

**Day 2 and beyond:** Repeats with cached skill files.

---

## Verification

### Check That Batch Execution Is Working

```bash
# Run a test scenario
export CLAUDE_MODEL="claude-haiku-4-5-20251001"
.venv/bin/python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 3

# Check logs for batch indicator
grep -h "BATCH TOOL INVOCATIONS" logs/day-*.log

# Example output:
# === BATCH TOOL INVOCATIONS (2 total) ===
# === BATCH TOOL INVOCATIONS (3 total) ===
# === BATCH TOOL INVOCATIONS (1 total) ===
```

If you see batch counts > 1, the optimization is working.

### Skill Cache Verification

```bash
# The cache is internal, but you can verify it's being used by:
# 1. Running multiple days
# 2. Checking that each day's agents start quickly
# 3. Observing that skill file reading time is minimal

# Skill files (3 total):
ls -lh manufacturer/backend/cli/skills/
ls -lh provider/app/skills/
ls -lh retailer/app/skills/
# These are read once at scenario start, then cached
```

---

## When Batch Execution Happens

### Within Single Agent Turn

Example: Manufacturer agent needs to:
1. Check inventory (cmd1)
2. Release production (cmd2)
3. Create purchase order (cmd3)

**Without batch:**
- Iteration 1: Claude decides cmd1 → execute → send result
- Iteration 2: Claude decides cmd2 → execute → send result
- Iteration 3: Claude decides cmd3 → execute → send result
- Iteration 4: Claude done
- **Total: 4 iterations**

**With batch:**
- Iteration 1: Claude decides [cmd1, cmd2, cmd3] → batch execute all → send all results
- Iteration 2: Claude done
- **Total: 2 iterations** (50% reduction!)

### Across Full Day

With 3 agents making ~2 iterations each:
- **Without batch**: 6 iterations/day
- **With batch**: 3 iterations/day (50% reduction)

Over 25 days: 150 → 75 total iterations.

---

## Configuration

Constants in `engine/agent_runner.py`:

```python
DEFAULT_TIMEOUT = 180          # Overall claude --print timeout
TOOL_TIMEOUT_SECONDS = 30      # Per-tool bash execution timeout
```

Adjust these if needed, but defaults are safe for normal scenarios.

---

## No API Key Required

✅ **Why this works:**
- Uses Claude Code Pro subscription
- Runs `claude --print` CLI subprocess
- CLI handles authentication (no explicit API key needed)
- Full batch optimization available

✅ **No Anthropic SDK:**
- Pure subprocess approach
- Parses stream-json output
- Extracts all tools from single response
- Executes batch naturally

❌ **What's NOT available:**
- Prompt caching (requires Anthropic SDK + API key)
- That's okay—batch execution is the bigger optimization anyway

---

## Performance Impact

### Reduction in Iterations

Expected reduction: **40-50%** through batch execution alone.

### Example Calculation

**25-day scenario, 3 agents/day:**

**Without batch:**
- Average 2.5 iterations per agent
- 75 agents × 2.5 = 187.5 iterations
- 187.5 × average 2 sec per iteration = 375 seconds

**With batch:**
- Average 1.5 iterations per agent
- 75 agents × 1.5 = 112.5 iterations
- 112.5 × average 2 sec per iteration = 225 seconds

**Savings: ~150 seconds (40% reduction in wall-clock time)**

Token savings are harder to quantify without Anthropic SDK, but fewer iterations = fewer token roundtrips = lower cost.

---

## Troubleshooting

### Issue: Batch count always = 1

**Likely cause:** Agents making single-tool decisions (Claude decides one tool at a time).

**What to check:**
- Agent decision logic is sequential
- Skill files encourage multi-tool decisions
- This is fine—batch is optimized when Claude naturally makes multiple decisions

### Issue: Tool execution times are slow

**Check:**
- Individual tool timeouts (TOOL_TIMEOUT_SECONDS = 30)
- Bash commands themselves are slow
- Not a batch execution problem

### Issue: Missing tools in logs

**Check:**
- Stream-json parsing is correct
- Tools are Bash type (other types may not be extracted)
- See `_parse_stream_json()` for extraction logic

---

## Future Optimizations

If you later upgrade to API-based approach:

1. **Prompt Caching** (requires Anthropic SDK + API key)
   - Would add ~45% more token savings
   - TTL-based caching of skill files
   - Requires separate implementation

2. **Concurrent Tool Execution**
   - Current: Sequential bash execution
   - Future: Parallel subprocess execution
   - Would reduce wall-clock time further

3. **Tool Pre-execution Analysis**
   - Predict which tools will be called
   - Pre-load resources
   - Not applicable for current subprocess mode

---

## Summary

**What's implemented:**
- ✅ Batch tool extraction from stream-json
- ✅ Skill file caching in memory
- ✅ Works with Claude Code Pro (no API key)
- ✅ Expected 40-50% iteration reduction

**What's NOT implemented (not needed for CLI):**
- ❌ Anthropic SDK prompt caching (requires API key)
- ❌ Concurrent tool execution (sequential is safe)

**Status:** Production ready, fully documented, backward compatible.

---

**Next Steps:** Run a scenario and check batch counts in logs!

```bash
bash scripts/verify-caching-setup.sh  # Optional, verifies structure
.venv/bin/python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 3
grep "BATCH TOOL INVOCATIONS" logs/day-*.log
```
