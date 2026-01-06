# Test Cases: Roadmap Items CORE-007, CORE-008, ARCH-001, WF-004

## CORE-007: Deprecate Legacy Claude Integration

### TC-DEP-001: Deprecation Warning on Import
**Component:** `src/claude_integration.py`
**Description:** Importing module shows deprecation warning
**Input:** `import src.claude_integration`
**Expected:** `DeprecationWarning` raised pointing to caller
**Priority:** High

### TC-DEP-002: Functionality Still Works
**Component:** `src/claude_integration.py`
**Description:** Module still functions after deprecation warning
**Input:** `from src.claude_integration import ClaudeCodeIntegration`
**Expected:** Can instantiate and use class
**Priority:** High

### TC-DEP-003: Warning Points to Correct File
**Component:** `src/claude_integration.py`
**Description:** Stacklevel correctly points to importing code
**Input:** Import from test file
**Expected:** Warning shows test file as source, not claude_integration.py
**Priority:** Medium

---

## CORE-008: Input Length Limits

### TC-VAL-001: Valid Constraint Under Limit
**Component:** `src/validation.py`
**Description:** Constraints under 1000 chars accepted
**Input:** `validate_constraint("short constraint")`
**Expected:** Returns input unchanged
**Priority:** High

### TC-VAL-002: Valid Constraint At Limit
**Component:** `src/validation.py`
**Description:** Constraint exactly 1000 chars accepted
**Input:** `validate_constraint("a" * 1000)`
**Expected:** Returns input unchanged
**Priority:** High

### TC-VAL-003: Constraint Over Limit Rejected
**Component:** `src/validation.py`
**Description:** Constraint over 1000 chars rejected
**Input:** `validate_constraint("a" * 1001)`
**Expected:** Raises `ValueError` with clear message
**Priority:** High

### TC-VAL-004: Valid Note Under Limit
**Component:** `src/validation.py`
**Description:** Notes under 500 chars accepted
**Input:** `validate_note("short note")`
**Expected:** Returns input unchanged
**Priority:** High

### TC-VAL-005: Note At Limit
**Component:** `src/validation.py`
**Description:** Note exactly 500 chars accepted
**Input:** `validate_note("a" * 500)`
**Expected:** Returns input unchanged
**Priority:** High

### TC-VAL-006: Note Over Limit Rejected
**Component:** `src/validation.py`
**Description:** Note over 500 chars rejected
**Input:** `validate_note("a" * 501)`
**Expected:** Raises `ValueError` with clear message
**Priority:** High

### TC-VAL-007: None Note Accepted
**Component:** `src/validation.py`
**Description:** None/empty notes pass validation
**Input:** `validate_note(None)`, `validate_note("")`
**Expected:** Returns input unchanged
**Priority:** Medium

### TC-VAL-008: CLI Start Validates Constraints
**Component:** `src/cli.py`
**Description:** Start command validates constraint length
**Input:** `orchestrator start "task" --constraints "a"*1001`
**Expected:** Error message about constraint length
**Priority:** High

### TC-VAL-009: CLI Complete Validates Notes
**Component:** `src/cli.py`
**Description:** Complete command validates note length
**Input:** `orchestrator complete item_id --notes "a"*501`
**Expected:** Error message about note length
**Priority:** High

---

## ARCH-001: Extract Retry Logic

### TC-RTY-001: Successful First Attempt
**Component:** `src/utils.py`
**Description:** No retry when function succeeds
**Input:** Function that succeeds immediately
**Expected:** Returns result, no retries
**Priority:** High

### TC-RTY-002: Success After Retries
**Component:** `src/utils.py`
**Description:** Retries until success within limit
**Input:** Function that fails twice then succeeds
**Expected:** Returns result after 3rd attempt
**Priority:** High

### TC-RTY-003: All Retries Exhausted
**Component:** `src/utils.py`
**Description:** Raises last error after max retries
**Input:** Function that always fails, max_retries=3
**Expected:** Raises exception after 3 attempts
**Priority:** High

### TC-RTY-004: Exponential Backoff Timing
**Component:** `src/utils.py`
**Description:** Delays follow exponential pattern
**Input:** Function that fails, base_delay=1.0
**Expected:** Delays are ~1s, ~2s, ~4s (approx)
**Priority:** Medium

### TC-RTY-005: Max Delay Respected
**Component:** `src/utils.py`
**Description:** Delay never exceeds max_delay
**Input:** base_delay=10, max_delay=15, many retries
**Expected:** Delays capped at 15s
**Priority:** Medium

### TC-RTY-006: Specific Exception Types
**Component:** `src/utils.py`
**Description:** Only catches specified exceptions
**Input:** exceptions=(ValueError,), raise TypeError
**Expected:** TypeError propagates immediately
**Priority:** High

### TC-RTY-007: Function Signature Preserved
**Component:** `src/utils.py`
**Description:** Decorated function keeps name/docstring
**Input:** Decorated function
**Expected:** `__name__` and `__doc__` preserved
**Priority:** Low

### TC-RTY-008: Visual Verification Uses Utility
**Component:** `src/visual_verification.py`
**Description:** Refactored code uses retry utility
**Input:** Call verify() method
**Expected:** Retry behavior unchanged from before
**Priority:** High

---

## WF-004: Auto-Archive Workflow Documents

### TC-ARC-001: Archive Existing Plan
**Component:** `src/engine.py`
**Description:** Archives docs/plan.md when starting workflow
**Setup:** Create docs/plan.md with content
**Input:** `orchestrator start "New task"`
**Expected:** plan.md moved to docs/archive/{date}_{slug}_plan.md
**Priority:** High

### TC-ARC-002: Archive Risk Analysis
**Component:** `src/engine.py`
**Description:** Archives docs/risk_analysis.md
**Setup:** Create docs/risk_analysis.md
**Input:** `orchestrator start "New task"`
**Expected:** File moved to archive
**Priority:** High

### TC-ARC-003: Archive Test Cases
**Component:** `src/engine.py`
**Description:** Archives tests/test_cases.md
**Setup:** Create tests/test_cases.md
**Input:** `orchestrator start "New task"`
**Expected:** File moved to archive
**Priority:** High

### TC-ARC-004: Skip Missing Files
**Component:** `src/engine.py`
**Description:** No error if files don't exist
**Setup:** Empty docs/ directory
**Input:** `orchestrator start "New task"`
**Expected:** Workflow starts normally
**Priority:** High

### TC-ARC-005: Create Archive Directory
**Component:** `src/engine.py`
**Description:** Creates docs/archive/ if missing
**Setup:** No archive directory
**Input:** `orchestrator start "New task"` with existing docs
**Expected:** Archive directory created
**Priority:** High

### TC-ARC-006: Handle Duplicate Names
**Component:** `src/engine.py`
**Description:** Adds counter suffix for duplicates
**Setup:** Archive file with same date/slug already exists
**Input:** Start second workflow same day
**Expected:** File named with _1 suffix
**Priority:** Medium

### TC-ARC-007: No-Archive Flag
**Component:** `src/cli.py`
**Description:** --no-archive skips archiving
**Setup:** docs/plan.md exists
**Input:** `orchestrator start "Task" --no-archive`
**Expected:** plan.md not moved
**Priority:** High

### TC-ARC-008: Archive Logged
**Component:** `src/engine.py`
**Description:** Log event for archived files
**Input:** Start workflow with docs to archive
**Expected:** Log entry shows archived files
**Priority:** Low

### TC-ARC-009: Archived Content Intact
**Component:** `src/engine.py`
**Description:** Archived files have same content
**Setup:** plan.md with specific content
**Input:** Start workflow
**Expected:** Archived file content matches original
**Priority:** High

---

## Integration Tests

### TC-INT-001: Full Workflow With All Features
**Description:** Start workflow exercising all 4 features
**Steps:**
1. Import claude_integration (see warning)
2. Start workflow with long constraint (rejected)
3. Start workflow with valid constraint
4. Verify docs archived
5. Complete item with long note (rejected)
6. Complete item with valid note
**Expected:** All behaviors work together
**Priority:** High

### TC-INT-002: Existing Tests Still Pass
**Description:** No regressions from changes
**Input:** `pytest tests/`
**Expected:** All existing tests pass
**Priority:** High

---

## Coverage Requirements

- 100% coverage for `src/validation.py`
- 100% coverage for `src/utils.py`
- 90%+ coverage for archive logic in `src/engine.py`
- All error paths tested
