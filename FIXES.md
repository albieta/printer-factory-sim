# FIXES.md — Week 7 Conformance Gaps

Reference document for resolving deviations between the Week 7 spec and the
current implementation. Work through these in order; earlier fixes unblock later ones.

---

## FIX-1 · Rename manufacturer CLI sales commands ✓ DONE

**Problem:** The skill file and spec both use `manufacturer-cli sales orders` and
`manufacturer-cli sales order <id>`, but the CLI implements them as `sales list` and
`sales show`. Every LLM agent run calls a non-existent command.

**File:** `manufacturer/cli/__main__.py`

**Changes:**
- Rename `@sales_app.command("list")` → `@sales_app.command("orders")`
- Rename `@sales_app.command("show")` → `@sales_app.command("order")`

**Verification:** `manufacturer-cli sales orders` and `manufacturer-cli sales order 1`
both return output without "No such command" errors.

---

## FIX-2 · Add missing manufacturer CLI commands: `production release`, `production status`, `capacity` ✓ DONE

**Problem:** The spec requires three production-management commands that are entirely
absent from the manufacturer CLI. The skill file reasons about capacity but has no
command to query it.

**File:** `manufacturer/cli/__main__.py`

**Commands to add:**

```
manufacturer-cli production release <order_id>   # release a sales order to production
manufacturer-cli production status               # list in-progress production runs
manufacturer-cli capacity                        # daily capacity + current utilisation
```

**Implementation notes:**
- `production release <order_id>` — calls `SalesService` to transition a sales order
  from `PENDING` → `RELEASED` (or equivalent status); checks BOM parts in stock.
- `production status` — lists sales orders currently `IN_PROGRESS`, with model, qty,
  and expected completion day.
- `capacity` — prints daily capacity baseline (e.g. 5 units/day from config) and
  current utilisation (units in progress / capacity).

**Verification:** Each command returns structured output (JSON or table) without error.

---

## FIX-3 · Fix skill file command references ✓ DONE

**Problem:** `skills/manufacturer-manager.md` references commands that don't match
the actual CLI surface — both the old names (pre FIX-1) and the missing commands
(pre FIX-2).

**File:** `skills/manufacturer-manager.md`

**Changes after FIX-1 and FIX-2 are done:**
- Replace `manufacturer-cli sales orders` with the correct command name (verify it
  matches FIX-1 output).
- Replace `manufacturer-cli sales order <id>` with the correct command name.
- Add `manufacturer-cli production status` and `manufacturer-cli capacity` to the
  "Read state" block under Available Commands.
- Add `manufacturer-cli production release <order_id>` to a "Production" block under
  Available Commands.
- Update Step 2 (Fulfil) of the Decision Framework to use `production release` when
  parts are available, rather than describing fulfilment as fully automatic.

**Verification:** Run the engine in LLM mode for one day and confirm the agent's
output contains no "No such command" or "Error" lines from CLI calls.

---

## FIX-4 · Enforce minimum 15 % markup in retailer price setting ✓ DONE

**Problem:** `catalog_service.py:set_price()` only validates `price > 0`. The spec
requires retail prices to stay above manufacturer wholesale price + 15 % margin.
Any price can currently be set, including below cost.

**File:** `retailer/app/services/catalog_service.py`

**Changes:**
- `set_price()` must accept (or fetch) the current wholesale price for the model
  from the manufacturer (via HTTP or a locally cached value) and reject any price
  below `wholesale_price * 1.15`.
- If the wholesale price cannot be fetched (manufacturer offline), raise `CatalogError`
  with a clear message rather than silently allowing the update.
- The same check should apply in the CLI (`price set`) and REST route (`price set`).

**Verification:** Attempting to set a retail price below wholesale + 15 % returns a
400/422 error (REST) or a printed error message (CLI) without writing to the DB.

---

## FIX-5 · Add `scripts/dev-start-all.sh` ✓ DONE

**Problem:** CLAUDE.md and the spec both reference `scripts/dev-start-all.sh` for
starting all three apps (provider + manufacturer + retailer + frontend) in one command.
Only `scripts/dev-start.sh` (provider + manufacturer + frontend) exists.

**File:** `scripts/dev-start-all.sh` (new file)

**Changes:**
- Copy the structure of `dev-start.sh`.
- Add a third block that starts the retailer: `.venv/bin/python -m retailer.cli serve
  --config retailer.json --port 8003` in a new terminal pane or background process,
  consistent with how the other two apps are started.
- Make the file executable (`chmod +x`).

**Verification:** Running `bash scripts/dev-start-all.sh` brings up all three FastAPI
servers; `curl http://localhost:8003/api/catalog` returns a valid response.

---

## FIX-6 · Align manufacturer REST endpoint paths with CLAUDE.md contract ✓ DONE

**Problem:** CLAUDE.md documents the manufacturer sales endpoints as `POST /api/orders`,
`GET /api/orders/{id}`, `GET /api/prices`, and `PUT /api/prices/{model}`. The
implementation mounts them under `/api/sales/orders` and `/api/sales/prices`. The
retailer already uses the `/api/sales/` paths so the system works, but the documented
contract is wrong.

**Options (pick one and be consistent):**

- **Option A (preferred):** Update CLAUDE.md and `docs/PRD-week7.md` §5.2 to reflect
  the actual `/api/sales/` paths. No code changes needed.
- **Option B:** Add `/api/orders` and `/api/prices` as aliases in the manufacturer's
  router (keep `/api/sales/` too for backward compat).

**Verification:** CLAUDE.md §Architecture and PRD-week7.md §5.2 match what
`curl http://localhost:8002/openapi.json` actually exposes.

---

## FIX-7 · Document scenario file format in CLAUDE.md / PRD ✓ DONE

**Problem:** The spec skeleton uses an `events` array with `start_day`/`end_day`
ranges. The actual implementation uses a `days` array with exact day numbers. This
is a better design but the format is undocumented, making it hard to write new
scenarios.

**File:** `docs/PRD-week7.md` (scenario format section) and optionally `CLAUDE.md`

**Changes:**
- Document the actual `days`-array schema with an annotated example.
- List all recognised signal keys: `demand_modifier`, `supply_modifier`, and any
  others the engine currently reads.
- Remove or strike through the old `events`/`start_day`/`end_day` skeleton if it
  appears in the PRD.

**Verification:** A new contributor can write a valid scenario file from the docs
alone without reading `engine/runner.py`.

---

## Fix order summary

| # | Scope | Blocks |
|---|-------|--------|
| FIX-1 | manufacturer CLI rename | FIX-3 |
| FIX-2 | manufacturer CLI new commands | FIX-3 |
| FIX-3 | skill file update | LLM agent correctness |
| FIX-4 | retailer price floor | standalone |
| FIX-5 | dev-start-all.sh | standalone |
| FIX-6 | docs / endpoint alignment | standalone |
| FIX-7 | scenario format docs | standalone |
