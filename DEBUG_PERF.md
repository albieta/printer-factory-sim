# Performance Debugging Guide

## Issue
Single simulated day takes several minutes with Haiku (without thinking enabled).

## How API calls are made

The turn engine calls Claude agents via subprocess:
- **Entry point**: `turn_engine.py:run_role_agent()` (line 180)
- **Subprocess call**: `agent_runner.py:run_agent()` (line 39)
- **CLI invocation**: `claude --print --verbose --output-format stream-json --model <model> -- <prompt>`
- **Number of agents per day**: 3 (retailer, manufacturer, provider)
- **Total subprocess spawns per day**: 3

Each agent:
1. Receives a prompt with their skill file
2. Makes tool calls (bash commands) to check state
3. Processes results and responds

## How to verify what model is actually being used

### Option 1: Check environment variable
```bash
# When running manually
CLAUDE_MODEL=claude-haiku-4-5-20251001 python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 1

# From UI: check the request payload at POST /api/scenarios/start
# Look for the "model" field in the JSON request
```

### Option 2: Check the subprocess command being executed
Add this debug code to `engine/agent_runner.py` line 70 (before `subprocess.run`):
```python
print(f"[DEBUG] Spawning agent: {' '.join(cmd)}", file=sys.stderr)
```

### Option 3: Check the logs
After running, look at `logs/day-001-Factory.log`:
- First line shows the prompt sent
- Look for `=== CLAUDE FINAL RESPONSE ===` to see if model output looks reasonable

## How to verify thinking mode is OFF

Check the subprocess arguments:
1. Open `engine/agent_runner.py`
2. Line 70-92 shows the `subprocess.run()` call
3. **Notice**: There is NO `--thinking` or `--budget-tokens` flag
4. Verify: The `--model` parameter is the ONLY model-related flag being passed

The environment variable `CLAUDE_THINKING_ENABLED` is set in `scenario_runner.py` line 149, but it is **NOT** used by the agent runner. It's only there for future use or for logging context.

## Debugging Steps

### 1. Run a single day with verbose output
```bash
# Terminal: watch subprocess calls in real-time
python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 1 2>&1 | tee /tmp/debug.log

# In another terminal: monitor the logs directory
watch 'ls -lh logs/'
```

### 2. Check where time is spent
After a day finishes, check the log files:
```bash
# Time spent in each agent (tool calls inside each agent)
grep -A5 "=== TOOL INVOCATIONS ===" logs/day-001-*.log

# Check if many bash commands were run
wc -l logs/day-001-bash-calls.jsonl
```

### 3. Check API call latency
```bash
# View all HTTP calls made that day
cat logs/day-001-api-calls.jsonl | jq '.duration_ms'
```

### 4. Check token usage (if using Opus/Sonnet)
The stream-json output shows token counts. Check the logs:
```bash
grep -i "tokens\|usage" logs/day-001-*.log
```

## Potential bottlenecks

### A. Too many tool calls
**Symptom**: Agent is running bash commands repeatedly for state checks

**Check**:
```bash
cat logs/day-001-bash-calls.jsonl | jq '.command' | sort | uniq -c | sort -rn
```

**Fix**: Optimize skill files to reduce redundant state checks

### B. Slow HTTP responses from apps
**Symptom**: Turn engine stuck during `advance_app()` or demand injection

**Check**:
```bash
cat logs/day-001-api-calls.jsonl | jq 'select(.duration_ms > 1000)'
```

**Fix**: 
- Ensure all three apps (retailer, manufacturer, provider) are running
- Check if their databases are large (slow queries)

### C. Subprocess overhead
**Symptom**: Three 3-minute runs = 9 minutes total

**Check**: 
```bash
time python -c "
import subprocess
for i in range(3):
    subprocess.run(['echo', f'agent {i}'], capture_output=True)
"
```

**Note**: Modern `claude` CLI spawns quickly (~200ms startup), so this is unlikely unless the CLI itself is slow

### D. Model is not actually Haiku
**Symptom**: Runs take far longer than expected for Haiku

**Check**:
1. Print the subprocess command (see step 1 above)
2. Look for `--model` flag and verify it says `claude-haiku-4-5-20251001`
3. If the flag is missing, check `CLAUDE_MODEL` env var:
```bash
echo $CLAUDE_MODEL
```

### E. Caching overhead
**Symptom**: First day slow, subsequent days slower

**Note**: Prompt caching via `--cache-mode` is NOT enabled in the current code

**Check**: Look for `cache` in the subprocess call - it shouldn't be there

## Performance expectations

With Haiku and a typical skill file (100 lines):

| Operation | Time | Notes |
|-----------|------|-------|
| Agent subprocess startup | ~200ms | CLI invocation |
| Single agent reasoning + tools | 5-30s | Depends on skill complexity |
| Single `day advance` call | 1-2s per app | Database transaction |
| Total per day (3 agents) | 20-120s | Can vary widely |

**If you're seeing >3 minutes per day with Haiku**, something is unusual.

## How to test model isolation

Run a minimal agent with just Haiku:
```bash
CLAUDE_MODEL=claude-haiku-4-5-20251001 \
python -m engine.turn_engine config/sim-stub.json scenarios/smoke-test.json 1
```

This uses stub agents (no actual Claude calls), just HTTP overhead. Should complete in <5 seconds.

Then try with one real agent (manufacturer only):
```bash
CLAUDE_MODEL=claude-haiku-4-5-20251001 \
python -m engine.turn_engine config/sim-manufacturer-only.json scenarios/smoke-test.json 1
```

This isolates the manufacturer agent. Should complete in 10-30 seconds.

## Quick debugging checklist

- [ ] Verify `--model` flag in subprocess command shows Haiku
- [ ] Verify no `--thinking` or `--budget-tokens` flags present
- [ ] Check `CLAUDE_MODEL` env var is not set to Opus/Sonnet
- [ ] Run stub scenario first to check API overhead baseline
- [ ] Monitor resource usage (CPU, memory) during run
- [ ] Check if skill files are reading state repeatedly (optimize them)
