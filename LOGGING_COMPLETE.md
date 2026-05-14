# Complete Logging System: Phase 2 Integration

## Overview

The simulation now provides **complete visibility** into all three systems communicating via APIs and all Claude agent decisions via bash command invocations. Three complementary log files per day track the entire flow.

## The Three Log Files

### 1. `logs/day-NNN-bash-calls.jsonl`
**What**: Every bash command Claude executes, with full input and output.  
**Format**: JSONL (one JSON object per line)  
**Content per line**:
```json
{
  "ts": "2026-05-14T18:15:15.687135",
  "day": 1,
  "command": "bin/manufacturer-cli sales orders --status PENDING",
  "exit_code": 0,
  "stdout": "ref | retailer | model | qty | status | day\n...",
  "stderr": null
}
```

**How it works**:
- Claude Code is invoked with `--print --verbose --output-format stream-json`
- Stream-json output includes structured "tool_use" objects describing each Bash invocation
- `agent_runner.py` parses this to extract all Bash commands and their results
- Results are written to JSONL using `BashLogger`

**Why it matters**: You can see exactly what state Claude inspected and what decisions it made based on that state.

---

### 2. `logs/day-NNN-api-calls.jsonl`
**What**: Every HTTP call between the three apps (retailer, manufacturer, provider).  
**Format**: JSONL (one JSON object per line)  
**Content per line**:
```json
{
  "ts": "2026-05-14T16:00:01",
  "day": 1,
  "method": "POST",
  "url": "http://localhost:8002/api/sales/orders",
  "request": {"retailer": "PrinterWorld", "model": "Basic300", "quantity": 1},
  "status": 201,
  "response": "{\"order_id\": \"SO-0015-001\", \"status\": \"PENDING\"}"
}
```

**How it works**:
- `turn_engine.py` creates an `ApiLogger` at the start of each day
- Every HTTP call (_get, _post) logs to the JSONL file
- Includes request body and response (truncated to 500 chars)

**Why it matters**: Trace the demand flow: customer orders → retailer → manufacturer → provider. See when orders arrive, when stock changes, when day advances ripple through the system.

---

### 3. `logs/day-NNN-Factory.log`
**What**: Claude's complete decision-making flow for the Factory agent.  
**Format**: Markdown-like human-readable text  
**Content sections**:
1. **=== PROMPT SENT TO CLAUDE ===**: Full prompt including skill file and market signal
2. **=== TOOL INVOCATIONS ===**: All bash commands Claude ran with their stdout/stderr
3. **=== CLAUDE FINAL RESPONSE ===**: Claude's summary and reasoning
4. **=== STDERR / EXIT CODE ===** (if any errors)

**Example**:
```
=== PROMPT SENT TO CLAUDE ===
# Simulation turn — day 1

## Your skill

# Manufacturer Manager Skill
...

## Market signal for day 1
{'base_demand': {'mean': 4, 'variance': 1}, 'demand_modifier': 1.0}

=== TOOL INVOCATIONS ===

[CALL: bin/manufacturer-cli day current]
stdout: 2026-05-22

[CALL: bin/manufacturer-cli sales orders --status PENDING]
stdout: ref | retailer | model | qty | status | day
...

=== CLAUDE FINAL RESPONSE ===
**Day 22 complete.**
- Released 14 sales orders.
- Placed 2 purchase orders.
...
```

**How it works**:
- Prompt and final response are captured from the subprocess
- Tool invocations are extracted from stream-json output
- `agent_runner.py` assembles all three parts in sequence

**Why it matters**: You can read Claude's reasoning, see what state it started with, and verify it made correct decisions.

---

## Understanding the Flow

### Demand Flow (from `logs/day-NNN-api-calls.jsonl`)
```
Turn engine starts day 1
  ↓
Retailer catalog fetched (1 GET /api/catalog)
  ↓
Customer demand generated (14 POST /api/orders at retailer)
  ↓
Orders marked BACKORDERED (no stock to fulfill immediately)
  ↓
Orders forwarded to manufacturer (14 POST /api/sales/orders)
  ↓
Manufacturer agent runs (see Factory.log)
  ↓
Days advance downstream: retailer → manufacturer → provider
  ↓
Each app publishes state change events
```

### Claude's Decision Flow (from `logs/day-NNN-Factory.log` + `logs/day-NNN-bash-calls.jsonl`)
```
Prompt sent: 
  - Skill file with decision framework
  - Market signal (demand_modifier, supply_modifier)
  
Claude's thinking (visible in stream-json):
  Step 1: Assess current state
    - Runs: day current, capacity, inventory, sales orders, production status, purchase list
    - Sees: 14 PENDING orders, capacity available, low materials
    
  Step 2: Fulfil orders
    - Runs: production release SO-0015-001, SO-0015-002, ... SO-0015-014
    - Moves orders from PENDING → CONFIRMED → SHIPPED → DELIVERED
    
  Step 3: Replenish materials
    - Runs: suppliers list, suppliers catalog, purchase create
    - Places POs for materials below 50 units
    
  Step 4: Adjust prices
    - Runs: price list, price set (only if demand_modifier > 1.5 or < 0.5)
    
Claude outputs:
  - Summary of what changed (orders released, materials ordered, prices adjusted)
  - These decisions are visible in downstream order status, inventory, and pricing logs
```

---

## Verification Checklist

To verify the logging system is working:

```bash
# 1. Start all services
bash scripts/dev-start.sh

# 2. Run a simulation
rm -f logs/day-*.log logs/day-*.jsonl
python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 1

# 3. Check bash logs exist and have commands
wc -l logs/day-001-bash-calls.jsonl
jq '.command' logs/day-001-bash-calls.jsonl | sort | uniq

# 4. Check API logs show demand flow
grep "/api/orders" logs/day-001-api-calls.jsonl | wc -l  # Should be 14+ POST orders
grep "/api/sales/orders" logs/day-001-api-calls.jsonl | wc -l  # Should be 14+ POST orders

# 5. Check Factory.log has all three sections
grep "=== PROMPT SENT TO CLAUDE ===" logs/day-001-Factory.log
grep "=== TOOL INVOCATIONS ===" logs/day-001-Factory.log
grep "=== CLAUDE FINAL RESPONSE ===" logs/day-001-Factory.log

# 6. See what Claude actually did
head -30 logs/day-001-Factory.log | tail -20
grep "stdout:" logs/day-001-Factory.log | head -5

# 7. Trace a single order through the system
echo "Order SO-0015-001 was created at retailer, forwarded to manufacturer, and released to CONFIRMED status"
grep "SO-0015-001" logs/day-001-api-calls.jsonl
grep "SO-0015-001" logs/day-001-bash-calls.jsonl
```

---

## Using the Logs for Debugging

### Question: Why did Claude release order X?
**Answer**: Check logs/day-001-Factory.log for the TOOL INVOCATIONS section. See what inventory/capacity Claude checked before deciding.

### Question: Why didn't the order arrive at the manufacturer?
**Answer**: Check logs/day-001-api-calls.jsonl. Trace the POST /api/orders call at retailer, then look for POST /api/sales/orders at manufacturer (should follow within the same day).

### Question: What was the manufacturer's inventory state when deciding to replenish?
**Answer**: Check logs/day-001-bash-calls.jsonl for the "inventory" command. See what on_hand, inbound, and demand values Claude saw.

### Question: Did the demand signal affect prices?
**Answer**: Check Factory.log for demand_modifier value. If > 1.5 or < 0.5, look for "price set" commands in bash-calls.jsonl. Otherwise, no change expected.

---

## Implementation Details

### Changes Made

**`engine/agent_runner.py`**:
- Now invokes Claude with `--output-format stream-json --verbose` to get structured tool invocation data
- Added `_parse_stream_json()` function that extracts tool_use objects and their results from the JSON stream
- Writes logs with three sections: prompt, tool invocations (with outputs), final response
- Calls `BashLogger` to record each Bash command and its result to JSONL

**`engine/bash_logger.py`**:
- Already in place from previous work
- Logs each command with timestamp, day, command text, stdout, stderr, exit code
- Writes to `logs/day-NNN-bash-calls.jsonl`

**`engine/api_logger.py`**:
- Already in place from previous work
- Logs each HTTP call with timestamp, day, method, URL, request body, response status, response body
- Writes to `logs/day-NNN-api-calls.jsonl`

**`engine/turn_engine.py`**:
- Creates ApiLogger at start of each day
- Passes logger through all _get() and _post() calls
- Calls forward_demand_to_manufacturer() to bridge Phase 1 gap

**`skills/manufacturer-manager.md`**:
- Cleaned up: removed instructions to output [CALL: ...] markers (we get them from stream-json now)
- Skill file focuses on decision framework steps, not logging mechanism

---

## Limitations & Notes

1. **Stream-json output is verbose**: The raw stream-json output is extensive. We extract just the tool invocations and final text response for readability in Factory.log.

2. **Command output truncation**: Bash stdout is truncated to ~500 chars in api-calls.jsonl for file size (use bash-calls.jsonl for full output).

3. **Multi-command bash statements**: Claude can chain commands with && on a single line. Each line is logged as one entry, but `wc -l` counts the full count of invocations.

4. **Stderr capture**: Only populated if a command errors. Normal successful commands have stderr=null.

---

## Next Steps

Once the retailer gets a real skill file (Week 8):
- Remove `forward_demand_to_manufacturer()` from turn_engine.py
- Retailer will handle restocking via its own skill (POST /api/purchases)
- Orders will flow through the proper retailer → manufacturer API path
- Logging remains unchanged—API calls will still be visible in api-calls.jsonl
