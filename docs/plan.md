# V3 Pre-Rollout Fixes Implementation Plan

## Task
Fix 5 issues (#71, #79, #74, #87, #82) before V3 rollout.

## Branch
`v3-hybrid-orchestration` (already checked out)

## Execution Strategy

**Decision: Sequential execution**

**Rationale:** While there are 5 independent issues, they:
1. Touch related files (audit.py for #71 and #79)
2. Require reading each file once and making targeted edits
3. Are small, focused changes (5-45 min each)
4. Sequential execution avoids merge conflicts in shared files

Parallel execution is less efficient here because:
- #71 and #79 both modify `src/audit.py` - parallel would cause conflicts
- Total estimated time is ~2 hours with minimal parallelization benefit
- Risk of merge conflicts outweighs time savings

---

## Issue #71: Add hmac.compare_digest for Timing Attack Prevention
**Priority:** P0 Security | **Files:** `src/audit.py`

### Problem
Line 229 uses `!=` for hash comparison, which is vulnerable to timing attacks that could reveal hash values through response time analysis.

### Solution
1. Import `hmac` module
2. Replace `entry['hash'] != expected_hash` with `not hmac.compare_digest(entry['hash'], expected_hash)`

### Test Strategy
- Unit test: Mock `hmac.compare_digest` to verify it's called
- Verify timing attack resistance by confirming constant-time comparison is used

---

## Issue #79: Fix Audit Log DoS (Memory Exhaustion)
**Priority:** P1 Performance/Security | **Files:** `src/audit.py`

### Problem
`_load_last_hash()` at line 77 reads entire file with `f.read().strip().split('\n')`, which could consume gigabytes of memory for long-running systems.

### Solution
Use seek-from-end approach:
1. Open file in binary mode
2. Seek to end, get file size
3. Read only last 4KB chunk
4. Find last complete JSON line
5. Parse only that line

### Test Strategy
- Create test with large audit log (simulated via mocking)
- Verify memory usage stays constant
- Verify correct last hash is loaded

---

## Issue #74: Add check_audit_integrity() to health.py
**Priority:** P2 Defense in Depth | **Files:** `src/health.py`

### Problem
Health check only verifies audit log file exists, doesn't verify hash chain integrity.

### Solution
1. Add `check_audit_integrity()` method to `HealthChecker` class
2. Verify hash chain by iterating through entries
3. Use hmac.compare_digest for hash comparisons
4. Add to `full_check()` method

### Test Strategy
- Test with valid audit log (returns ok)
- Test with broken chain (returns error)
- Test with invalid JSON (returns error)
- Test with missing file (returns ok)

---

## Issue #87: Optimize _auto_detect_important_files Performance
**Priority:** Low | **Files:** `src/checkpoint.py`

### Problem
`_auto_detect_important_files()` uses `rglob('*')` which can be slow on large projects.

### Solution
1. Try `git ls-files -m --others --exclude-standard` first (much faster for git repos)
2. Add depth limit to fallback rglob approach
3. Add helper method `_is_important_file()` for extension checking

### Test Strategy
- Test git-based detection (when git available)
- Test fallback to rglob (when git unavailable)
- Test depth limiting works correctly

---

## Issue #82: Add Design Validation Review (6th Review Type)
**Priority:** Feature | **Files:** `src/default_workflow.yaml`, `CLAUDE.md`

### Problem
No review validates that implementation matches design goals in plan.md.

### Solution
1. Add `design_validation` item to REVIEW phase in `src/default_workflow.yaml`
2. Make it skippable with conditions: `no_plan_exists`, `simple_bug_fix`, `trivial_change`
3. Provide clear guidance on running minds review with design-focused prompt
4. Document in CLAUDE.md

### Prompt Design (for minds review)
```
Review implementation against design goals in docs/plan.md.
Check:
1. All stated goals are fully implemented (not partial)
2. Implementation will work in production
3. No gaps between design and code
4. Parameter choices are appropriate
```

### Test Strategy
- Verify workflow YAML is valid
- Verify skip_conditions are respected
- Manual verification of review guidance clarity

---

## Success Criteria
- [ ] All 5 issues fixed with tests
- [ ] All existing tests pass (2141+ tests)
- [ ] Multi-model review passes (`minds review --timeout 120 --verbose`)
- [ ] Ready for merge to main
