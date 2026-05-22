# Comprehensive Testing Strategy

## Overview
This document outlines a multi-layered testing approach to ensure the Week 8 simulation system (financial tracking, scenarios, resets, and configuration) works reliably under all conditions.

## 1. Test Pyramid Architecture

### Layer 1: Unit Tests (Fast, Isolated)
Test individual functions in isolation with mocked dependencies.

**Coverage Areas:**
- Financial calculations (cost accumulation, profit)
- Configuration updates (single field changes)
- Inventory calculations (capacity, usage %)
- Reset logic (each reset type independently)

**Expected Count:** 30-40 tests
**Speed:** < 100ms each
**Tools:** pytest with in-memory database

### Layer 2: Integration Tests (Medium, Real Database)
Test interactions between services with real SQLAlchemy sessions.

**Coverage Areas:**
- Reset workflows (reset → verify → reset again)
- Financial workflows (open line → hire → sell → verify totals)
- Configuration propagation (change config → verify impact on production)
- Inventory state transitions (consume → deliver → consume)

**Expected Count:** 20-30 tests
**Speed:** 100ms - 1s each
**Tools:** pytest with test transactions

### Layer 3: End-to-End Tests (Slow, Full System)
Test complete user workflows from UI to database.

**Coverage Areas:**
- Full simulation day (orders → production → delivery → reset)
- Scenario selection → recommendation display → apply → verify
- User editing config → starting simulation → verifying impact
- Multiple resets during active simulation

**Expected Count:** 10-15 tests
**Speed:** 1s - 10s each
**Tools:** pytest with temporary databases, FastAPI TestClient

## 2. Bug-Specific Test Cases

### The Duplicate Inventory Bug (FIXED)
**What happened:** `reset_to_default_config()` called `reset_simulation()` which created inventory, then tried to create it again.

**Test Strategy:**
1. Reset to default → count inventory items (should be 6)
2. Reset to default again → count inventory items (should still be 6, not 12)
3. Verify no product has > 1 inventory entry
4. Repeat 5 times → verify no accumulation

### Negative Inventory Bug (PREVENTION)
**What we prevent:** Production consuming materials faster than arrival creates negative quantities.

**Test Strategy:**
1. Check no inventory starts negative
2. Create orders for max capacity
3. Run production
4. Verify all inventory ≥ 0 after production
5. Test with 0 starting inventory
6. Test with minimal starting inventory

### Warehouse Capacity Exceeded (EDGE CASE)
**What we handle:** Warehouse can temporarily exceed capacity when materials arrive.

**Test Strategy:**
1. Fill warehouse to capacity
2. Deliver large order
3. Verify capacity usage calculated correctly
4. Check available_capacity shows negative correctly
5. Verify UI displays capacity state accurately

### Financial Tracking Gaps (VALIDATION)
**What we track:** Costs for operations, revenue for sales, profit calculation.

**Test Strategy:**
1. Track assembly line opening → verify cost recorded
2. Track worker hiring → verify salary cost recorded
3. Track material purchases → verify cost recorded
4. Track product sold → verify revenue recorded
5. Verify profit = revenue - costs always
6. Check no transaction type missing
7. Verify transaction history complete

## 3. Test Categories by System Area

### Configuration System
```
✓ Default values correct
✓ Update single field preserves others
✓ Update multiple fields atomically
✓ Constraints enforced (max_workers, shift_hours range)
✓ Reset to defaults works
✓ Reset preserves financial config
✓ Reset clears custom values
✓ Reset multiple times is idempotent
```

### Financial System
```
✓ Assembly line costs recorded
✓ Worker hiring costs recorded
✓ Material purchase costs recorded
✓ Product sale revenue recorded
✓ Transaction list complete and accurate
✓ Summary calculations correct
✓ Profit = Revenue - Costs always
✓ No negative costs allowed
✓ No missing transaction types
✓ Large transactions handled correctly
```

### Inventory System
```
✓ No negative inventory
✓ Capacity tracking accurate
✓ Available capacity calculated correctly
✓ Warehouse can exceed capacity (temporarily)
✓ No duplicate inventory items
✓ Material consumption tracked
✓ Material delivery tracked
✓ Inventory persists across resets
```

### Scenario System
```
✓ Recommendations load from JSON
✓ Recommendations display in UI
✓ Apply assembly button disabled when already applied
✓ Apply costs button disabled when already applied
✓ Apply assembly actually updates config
✓ Apply costs actually updates config
✓ Partial recommendations don't overwrite other fields
✓ Disabled buttons show visually disabled state
✓ Recommendations persist across scenario switches
```

### Reset System
```
✓ reset_simulation clears orders and events
✓ reset_simulation preserves products
✓ reset_to_empty removes everything except config
✓ reset_to_default_config recreates starter data
✓ No duplicates after multiple resets
✓ Config values reset properly
✓ Financial tracking reset
✓ Inventory reset properly
✓ No data corruption during resets
✓ Reset is transactional (all or nothing)
```

## 4. Failure Scenario Tests

### Stress Tests
- 1000 inventory items (normal: ~6)
- 100 concurrent orders
- Multiple rapid resets
- Large financial transactions ($1M+)
- Zero inventory starting point
- Maxed out assembly capacity

### Edge Case Combinations
- Reset while simulation running
- Apply scenario while running
- Change config during day advance
- Zero inventory + high demand
- Max workers + max assembly lines
- Decimal precision in shift hours

### Data Corruption Prevention
- Transaction rollback on error
- Inventory consistency after failed production
- Financial totals correct after failed orders
- Config integrity after interruption

## 5. Test Execution Strategy

### Phase 1: Core Unit Tests (Week 1)
- 40 unit tests covering basic functionality
- Target: 100% coverage of business logic
- Run: On every commit

### Phase 2: Integration Tests (Week 2)
- 30 integration tests covering workflows
- Target: All service interactions tested
- Run: Before merge to main

### Phase 3: End-to-End Tests (Week 3)
- 15 E2E tests covering full user journeys
- Target: Critical user paths verified
- Run: Before releases

### Phase 4: Ongoing Regression
- Add test for every bug found
- Maintain 90%+ code coverage
- Run full suite nightly

## 6. Test Quality Metrics

### Target Metrics
- **Code Coverage:** 85%+ for business logic
- **Test Pass Rate:** 100% (no flaky tests)
- **Test Execution Time:** < 5 minutes full suite
- **Bug Detection:** Catches all bugs pre-production

### Coverage by Area
- Configuration: 95%
- Financial: 90%
- Inventory: 90%
- Scenarios: 85%
- Resets: 95%

## 7. Continuous Improvement

### Bug → Test Workflow
1. Bug reported/found
2. Write failing test that reproduces bug
3. Fix code
4. Verify test passes
5. Keep test in suite forever

### Test Review Criteria
- Does it test one thing clearly?
- Would it catch the bug it's named for?
- Is it maintainable?
- Does it run fast?
- Is it deterministic?

## 8. Tools & Infrastructure

### Testing Stack
- pytest: Test framework
- SQLAlchemy: ORM with test transactions
- httpx.MockTransport: API mocking
- Fixtures: Reusable test data

### CI/CD Integration
- Run tests on every commit
- Fail PR if tests don't pass
- Generate coverage reports
- Track metrics over time

## Success Criteria

✓ All unit tests pass
✓ All integration tests pass
✓ All E2E tests pass
✓ Zero known bugs
✓ No regressions in related systems
✓ Code coverage ≥ 85%
✓ New features have tests before merge
