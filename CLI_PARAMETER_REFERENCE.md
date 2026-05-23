# CLI Parameters Reference — Low-Latency Mode

## Current Subprocess Call (Normal Mode)

```bash
claude --print \
  --verbose \
  --output-format stream-json \
  --permission-mode bypassPermissions \
  --allowedTools Bash \
  --model claude-haiku-4-5-20251001 \
  --add-dir /workspaces/printer-factory-sim \
  -- \
  <PROMPT_WITH_SKILL_FILE>
```

**Model**: Haiku 4.5  
**Thinking**: Off  
**Result**: Full skill file (112 lines) → 30 tool calls → 101 seconds for manufacturer

---

## Proposed Low-Latency Subprocess Call

```bash
claude --print \
  --verbose \
  --output-format stream-json \
  --permission-mode bypassPermissions \
  --allowedTools Bash \
  --model claude-haiku-4-5-20251001 \
  --add-dir /workspaces/printer-factory-sim \
  -- \
  <PROMPT_WITH_SKILL_FILE_FAST>
```

**Model**: Haiku 4.5 (same)  
**Thinking**: Off (same)  
**Skill file**: `manufacturer-manager-fast.md` (40 lines instead of 112)  
**Tool calls**: ~10 instead of ~30  
**Result**: 10-15 seconds for manufacturer (7× faster)

---

## How the Parameter Flows Through the System

### 1. User Selects in UI

```
┌─ Scenarios Page (React) ─────────────────────────┐
│                                                   │
│  Config:    [sim.json]                          │
│  Scenario:  [smoke-test]                        │
│  Days:      [5]                                 │
│  Model:     [claude-haiku-4-5-20251001]         │
│  Thinking:  [OFF]                               │
│  Mode:      [Fast] ✓ ← NEW SELECTOR             │
│                                                   │
│  [Start Run]                                    │
└─────────────────────────────────────────────────┘
         │
         ▼
```

### 2. POST Request to Backend API

```json
POST /api/scenarios/start
{
  "config": "sim.json",
  "scenario": "smoke-test.json",
  "days": 5,
  "model": "claude-haiku-4-5-20251001",
  "thinking_enabled": false,
  "low_latency": true,
  "assembly_lines": 1,
  "workers_per_line": 1,
  "shift_hours": 8.0
}
```

### 3. ScenarioRunner Subprocess

```python
env = os.environ.copy()
env["CLAUDE_MODEL"] = "claude-haiku-4-5-20251001"
env["CLAUDE_THINKING_ENABLED"] = "false"
env["CLAUDE_LOW_LATENCY"] = "true"  # ← NEW ENV VAR
env["ASSEMBLY_LINES"] = "1"
env["WORKERS_PER_LINE"] = "1"
env["SHIFT_HOURS"] = "8.0"

subprocess.Popen(
    [python, "-m", "engine.turn_engine", "config/sim.json", "scenarios/smoke-test.json", "5"],
    env=env,  # ← Passes CLAUDE_LOW_LATENCY=true
    # ...
)
```

### 4. Turn Engine Reads Environment

```python
# In run_role_agent()
low_latency = os.environ.get("CLAUDE_LOW_LATENCY", "").lower() == "true"

if low_latency and skill_file:
    fast_variant = skill_file.replace(".md", "-fast.md")
    if Path(fast_variant).exists():
        skill_file = fast_variant
        # Now: "skills/manufacturer-manager-fast.md" instead of "skills/manufacturer-manager.md"
```

### 5. Skill File Used in Prompt

```
**Normal Mode Prompt** (118 lines total):
  Skill file: skills/manufacturer-manager.md (112 lines)
  Framework: 6-step decision process
  Result: ~30 tool calls, 101 seconds

**Low-Latency Mode Prompt** (48 lines total):
  Skill file: skills/manufacturer-manager-fast.md (40 lines)
  Framework: 2-3 step simplified process
  Result: ~10 tool calls, 15 seconds
```

### 6. Subprocess Call (Step 1 in code)

Same exact Claude CLI call, but with different prompt content:

```bash
# Normal mode (step 1 in agent_runner.py line 81)
--model claude-haiku-4-5-20251001
# ↓ prompt = load("skills/manufacturer-manager.md") + framework

# Low-latency mode (same line, but skill_file switched)
--model claude-haiku-4-5-20251001
# ↓ prompt = load("skills/manufacturer-manager-fast.md") + framework
```

---

## Environment Variable Flow

```
User clicks "Fast" in UI
        ↓
POST /api/scenarios/start with low_latency=true
        ↓
ScenarioRunner.start(low_latency=True)
        ↓
env["CLAUDE_LOW_LATENCY"] = "true"
        ↓
subprocess.Popen(..., env=env)
        ↓
Turn engine reads: os.environ.get("CLAUDE_LOW_LATENCY")
        ↓
run_role_agent() switches skill file:
  "skills/manufacturer-manager.md" → "skills/manufacturer-manager-fast.md"
        ↓
run_agent() reads new skill file and builds prompt
        ↓
Claude CLI sees only the new prompt (no new flags needed)
        ↓
Agent responds in ~15s instead of ~101s
        ↓
Response logged to logs/day-001-Factory.log
```

---

## Testing the Parameter

### Test 1: Via Environment Variable (CLI)

```bash
# Normal mode (baseline)
time CLAUDE_LOW_LATENCY=false .venv/bin/python -m engine.turn_engine \
  config/sim.json scenarios/smoke-test.json 1
# Expected: ~173s

# Fast mode
time CLAUDE_LOW_LATENCY=true .venv/bin/python -m engine.turn_engine \
  config/sim.json scenarios/smoke-test.json 1
# Expected: ~25s
```

### Test 2: Via Scenario Runner (what UI uses)

```python
runner = ScenarioRunner()

# Normal mode
runner.start("sim.json", "smoke-test.json", 1, low_latency=False)
# Expected: ~173s

# Fast mode
runner.start("sim.json", "smoke-test.json", 1, low_latency=True)
# Expected: ~25s
```

### Test 3: Check Which Skill File Was Used

```bash
# After run completes, check the logs
head -50 logs/day-001-Factory.log

# Look for the skill file content in the prompt:
# "# Manufacturer Manager Skill" (normal)
# or
# "# Manufacturer Manager — Fast Mode" (fast)
```

---

## API Contract

### Request

```json
POST /api/scenarios/start
Content-Type: application/json

{
  "config": "sim.json",
  "scenario": "smoke-test.json",
  "days": 5,
  "model": "claude-haiku-4-5-20251001",
  "thinking_enabled": false,
  "low_latency": false,
  "assembly_lines": 1,
  "workers_per_line": 1,
  "shift_hours": 8.0
}
```

### Response

```json
{
  "run_id": "run-20260522-180620",
  "config": "config/sim.json",
  "scenario": "scenarios/smoke-test.json",
  "days": 5,
  "started_at": "2026-05-22T18:06:20+00:00",
  "status": "running",
  "finished_at": null,
  "exit_code": null,
  "log_file": "logs/run-20260522-180620.log"
}
```

**Note**: The `low_latency` field is NOT echoed back in response; it's internal to the run.

---

## Backward Compatibility

✅ **Fully backward compatible**:

1. **Existing API calls without `low_latency` field**: Defaults to `false` (normal mode)
2. **CLI without `CLAUDE_LOW_LATENCY` env var**: Defaults to `false` (normal mode)
3. **No new CLI flags needed**: Uses environment variables
4. **Skill files don't change**: `-fast.md` variants are *new* files, existing ones untouched

---

## Quick Reference Table

| Aspect | Value |
|--------|-------|
| **New Parameter Name** | `low_latency` (bool) |
| **API Field** | `low_latency: boolean` in `ScenarioStartRequest` |
| **Env Variable** | `CLAUDE_LOW_LATENCY=true\|false` |
| **Default** | `false` (normal mode) |
| **Location in Code** | `turn_engine.py:run_role_agent()` (switching logic) |
| **Impact on Claude CLI** | None (same command, different prompt) |
| **Skill Files to Create** | 3 (`*-fast.md` variants) |
| **Test Expected Times** | Normal: ~173s/day; Fast: ~25s/day |

---

## No New CLI Flags Needed

**Important**: This implementation does NOT add any new flags to the `claude` CLI call itself.

The speedup comes entirely from:
1. Switching to simpler skill files
2. Agent making fewer/simpler decisions
3. Fewer tool calls needed

The subprocess call remains:
```bash
claude --print --model claude-haiku-4-5-20251001 ...
```

Same model, same flags. Just different prompt content.
