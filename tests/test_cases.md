# V3 Pre-Rollout Fixes - Test Cases

## Issue #71: hmac.compare_digest for timing attack prevention

### TC-71-1: Verify hmac.compare_digest is used
- **Description:** Verify that hash comparison uses constant-time comparison
- **Steps:**
  1. Mock `hmac.compare_digest`
  2. Call `verify_integrity()` with valid audit log
  3. Assert `hmac.compare_digest` was called
- **Expected:** hmac.compare_digest called for each hash comparison

### TC-71-2: Verify integrity check still works
- **Description:** Verify tamper detection still functions correctly
- **Steps:**
  1. Create valid audit log
  2. Tamper with one hash
  3. Call `verify_integrity()`
- **Expected:** AuditTamperError raised

---

## Issue #79: Audit log DoS fix

### TC-79-1: Empty file handling
- **Description:** Verify empty audit log doesn't cause errors
- **Steps:**
  1. Create empty audit.jsonl file
  2. Initialize AuditLogger
- **Expected:** No error, _last_hash is None

### TC-79-2: Small file handling
- **Description:** Verify files smaller than chunk size work
- **Steps:**
  1. Create audit log with single entry
  2. Initialize AuditLogger
- **Expected:** _last_hash correctly loaded

### TC-79-3: Large file memory efficiency
- **Description:** Verify memory usage stays constant for large files
- **Steps:**
  1. Create/mock large audit log (100MB+)
  2. Initialize AuditLogger
  3. Monitor memory usage
- **Expected:** Memory usage < 10MB (only reads last 4KB)

### TC-79-4: Multiple lines in chunk
- **Description:** Verify correct last line is found
- **Steps:**
  1. Create audit log with multiple entries
  2. Initialize AuditLogger
- **Expected:** _last_hash matches last entry's hash

---

## Issue #74: Audit integrity check in health.py

### TC-74-1: Valid audit log
- **Description:** Verify valid audit log passes integrity check
- **Steps:**
  1. Create valid audit log with chained hashes
  2. Run check_audit_integrity()
- **Expected:** ComponentHealth with status="ok"

### TC-74-2: Broken hash chain
- **Description:** Verify broken chain is detected
- **Steps:**
  1. Create audit log
  2. Modify prev_hash of middle entry
  3. Run check_audit_integrity()
- **Expected:** ComponentHealth with status="error", message contains "chain broken"

### TC-74-3: Invalid JSON in log
- **Description:** Verify invalid JSON is detected
- **Steps:**
  1. Create audit log with invalid JSON line
  2. Run check_audit_integrity()
- **Expected:** ComponentHealth with status="error", message contains "Invalid JSON"

### TC-74-4: Missing audit log
- **Description:** Verify missing file is handled gracefully
- **Steps:**
  1. Ensure audit.jsonl doesn't exist
  2. Run check_audit_integrity()
- **Expected:** ComponentHealth with status="ok", message indicates no log present

### TC-74-5: Full check includes audit integrity
- **Description:** Verify full_check() includes audit integrity
- **Steps:**
  1. Run full_check()
  2. Check components list
- **Expected:** Component named "audit_log" in results

---

## Issue #87: Optimize _auto_detect_important_files

### TC-87-1: Git-based detection works
- **Description:** Verify git ls-files is used when available
- **Steps:**
  1. Initialize CheckpointManager in git repo with modified files
  2. Call _auto_detect_important_files()
- **Expected:** Returns modified/untracked files from git

### TC-87-2: Fallback when git unavailable
- **Description:** Verify rglob fallback works
- **Steps:**
  1. Mock subprocess.run to raise exception
  2. Call _auto_detect_important_files()
- **Expected:** Falls back to rglob, returns recently modified files

### TC-87-3: Timeout handling
- **Description:** Verify git command timeout is handled
- **Steps:**
  1. Mock subprocess.run to raise TimeoutExpired
  2. Call _auto_detect_important_files()
- **Expected:** Falls back to rglob without error

---

## Issue #82: Design Validation Review

### TC-82-1: Workflow YAML valid
- **Description:** Verify updated workflow.yaml is valid YAML
- **Steps:**
  1. Load src/default_workflow.yaml
  2. Parse with yaml.safe_load()
- **Expected:** No parse errors

### TC-82-2: Design validation item exists
- **Description:** Verify design_validation item in REVIEW phase
- **Steps:**
  1. Load workflow definition
  2. Find REVIEW phase
  3. Find design_validation item
- **Expected:** Item exists with correct fields

### TC-82-3: Skip conditions defined
- **Description:** Verify skip conditions are set
- **Steps:**
  1. Load design_validation item
  2. Check skip_conditions field
- **Expected:** Contains "no_plan_exists", "simple_bug_fix", "trivial_change"

---

## Integration Tests

### TC-INT-1: Full workflow with all fixes
- **Description:** Verify all fixes work together
- **Steps:**
  1. Create audit log
  2. Run health check (tests #74)
  3. Verify integrity (tests #71, #79)
  4. Run workflow with design validation (tests #82)
- **Expected:** All checks pass

### TC-INT-2: Existing test suite passes
- **Description:** All existing tests still pass
- **Steps:**
  1. Run `pytest`
- **Expected:** 2141+ tests pass
