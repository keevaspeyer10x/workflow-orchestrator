# Test Cases: WF-010 Auto-Run Third-Party Reviews

## Unit Tests

### TC-001: Review mapping exists
- **Input:** Check `REVIEW_ITEM_MAPPING` constant
- **Expected:** Contains security_review, quality_review, architecture_review

### TC-002: run_auto_review returns success tuple
- **Input:** Call with valid review type
- **Expected:** Returns (bool, str, str) tuple

### TC-003: run_auto_review handles missing infrastructure
- **Input:** Call when no CLIs available
- **Expected:** Returns (False, "", error_message)

## Integration Tests

### TC-004: Complete security_review runs auto-review
- **Input:** `orchestrator complete security_review`
- **Expected:** Runs codex security review before completing

### TC-005: Complete with --skip-auto-review bypasses
- **Input:** `orchestrator complete security_review --skip-auto-review`
- **Expected:** Completes without running review

### TC-006: Blocking findings prevent completion
- **Input:** Complete review item when blocking issues exist
- **Expected:** Exit code 1, guidance to fix or skip

## Existing Tests
- All 381 existing tests pass (verified)
