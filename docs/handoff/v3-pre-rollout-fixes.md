# V3 Pre-Rollout Fixes - Handoff Prompt

## Task

Fix 5 issues before V3 rollout using the orchestrator workflow.

```bash
orchestrator start "V3 Pre-Rollout: Fix issues #71, #79, #74, #87, #82"
```

## Branch

Continue on `v3-hybrid-orchestration` branch (already checked out).

## Issues to Fix

### Issue #71: Add hmac.compare_digest for timing attack prevention
**Priority:** P0 Security | **Effort:** 5 min

**Problem:** Audit log verification uses standard string comparison which is vulnerable to timing attacks.

**File:** `src/audit.py`

**Current code (line ~225):**
```python
if entry['hash'] != expected_hash:
```

**Fix:**
```python
import hmac
# ... in verify_integrity method:
if not hmac.compare_digest(entry['hash'], expected_hash):
```

Also update state_version.py if it has string comparisons for checksums.

**Test:** Add test verifying hmac is used (can mock hmac.compare_digest to verify it's called).

---

### Issue #79: Audit log DoS - reads entire file into memory
**Priority:** P1 Performance/Security | **Effort:** 15 min

**Problem:** `_load_last_hash()` reads entire audit log into memory with `f.read().strip().split('\n')`. For long-running systems, this could be gigabytes.

**File:** `src/audit.py`

**Current code:**
```python
def _load_last_hash(self) -> None:
    try:
        with open(self.log_file, 'r') as f:
            lines = f.read().strip().split('\n')  # READS ENTIRE FILE!
            if lines and lines[-1]:
                last_entry = json.loads(lines[-1])
                self._last_hash = last_entry.get('hash')
```

**Fix:** Read only the last line efficiently:
```python
def _load_last_hash(self) -> None:
    """Load the hash of the last entry for chain continuation."""
    if not self.log_file.exists():
        return

    try:
        with open(self.log_file, 'rb') as f:
            # Seek to end
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return

            # Read backwards to find last newline
            chunk_size = min(4096, size)
            f.seek(-chunk_size, 2)
            chunk = f.read()

            # Find last complete line
            lines = chunk.split(b'\n')
            for line in reversed(lines):
                if line.strip():
                    last_entry = json.loads(line.decode('utf-8'))
                    self._last_hash = last_entry.get('hash')
                    return
    except Exception as e:
        logger.warning(f"Could not load last audit hash: {e}")
```

**Test:** Create large audit log file and verify memory usage stays constant.

---

### Issue #74: Add real audit integrity verification in health.py
**Priority:** P2 Defense in Depth | **Effort:** 20 min

**Problem:** Health check only verifies audit log file exists, doesn't verify hash chain integrity.

**File:** `src/health.py`

**Add new method:**
```python
def check_audit_integrity(self) -> ComponentHealth:
    """Verify audit log hash chain integrity."""
    import hmac

    audit_file = self.orchestrator_dir / "audit.jsonl"

    if not audit_file.exists():
        return ComponentHealth(
            name="audit_log",
            status="ok",
            message="No audit log present"
        )

    try:
        prev_hash = None
        line_num = 0

        with open(audit_file, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                line_num += 1

                entry = json.loads(line)

                # Verify chain link
                if entry.get('prev_hash') != prev_hash:
                    return ComponentHealth(
                        name="audit_log",
                        status="error",
                        message=f"Audit chain broken at line {line_num}",
                        details={"expected_prev": prev_hash, "actual_prev": entry.get('prev_hash')}
                    )

                prev_hash = entry['hash']

        return ComponentHealth(
            name="audit_log",
            status="ok",
            message=f"Audit chain verified ({line_num} entries)"
        )

    except json.JSONDecodeError as e:
        return ComponentHealth(
            name="audit_log",
            status="error",
            message=f"Invalid JSON in audit log: {e}"
        )
    except Exception as e:
        return ComponentHealth(
            name="audit_log",
            status="error",
            message=f"Error checking audit log: {e}"
        )
```

**Update `full_check()`** to include audit integrity:
```python
def full_check(self) -> HealthReport:
    components = [
        self.check_state(),
        self.check_locks(),
        self.check_checkpoints(),
        self.check_audit_integrity(),  # ADD THIS
    ]
```

**Test:** Add tests for corrupted audit log detection.

---

### Issue #87: Optimize _auto_detect_important_files performance
**Priority:** Low | **Effort:** 15 min

**Problem:** Uses `rglob('*')` which can be slow on large projects despite exclusions.

**File:** `src/checkpoint.py`

**Optimization options:**
1. Use `git ls-files -m` for git repos (much faster)
2. Add depth limit to recursion
3. Use more efficient pattern matching

**Suggested fix:**
```python
def _auto_detect_important_files(self, max_files: int = 10) -> List[str]:
    """Auto-detect important files based on recent modifications."""
    import time
    import subprocess

    one_hour_ago = time.time() - 3600
    important_files = []

    # Try git first (much faster for git repos)
    try:
        result = subprocess.run(
            ['git', 'ls-files', '-m', '--others', '--exclude-standard'],
            cwd=self.working_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            for filepath in result.stdout.strip().split('\n')[:max_files]:
                if filepath and self._is_important_file(filepath):
                    important_files.append(filepath)
            if important_files:
                return important_files
    except Exception:
        pass  # Fall back to rglob

    # Fallback: use rglob with depth limit
    # ... existing implementation with max_depth parameter
```

---

### Issue #82: Design Validation Review (6th Review Type)
**Priority:** Feature | **Effort:** 45 min

**Goal:** Add a 6th review type that validates implementation against design goals.

**Files to modify:**
- `src/default_workflow.yaml` - Add design_validation item to REVIEW phase
- `workflow.yaml` template - Same

**Implementation:**

1. **Add to REVIEW phase in workflow:**
```yaml
- id: "design_validation"
  name: "Design Validation Review"
  description: |
    Validate that all design goals from plan.md are fully implemented.
    Use minds review with design-focused prompt to verify:
    - All stated goals are complete (not partial)
    - Implementation will work in production
    - No gaps between design and code
    - Parameter choices are appropriate

    Run: minds ask "Review implementation against design goals in docs/plan.md.
    Check: 1) All goals fully implemented, 2) Will work in production,
    3) No gaps, 4) Parameters appropriate" --file docs/plan.md
  required: true
  skippable: true
  skip_conditions: ["simple_bug_fix", "no_plan_exists", "trivial_change"]
```

2. **Add skip logic** - Only run when `docs/plan.md` exists

3. **Document in CLAUDE.md** - Add section explaining when/how design validation is used

**Acceptance criteria:**
- [ ] Design validation review item added to default workflow
- [ ] Skippable when no plan.md exists
- [ ] Clear guidance in workflow description
- [ ] Documented in CLAUDE.md

---

## Workflow Execution

1. **PLAN**: Create plan.md with implementation approach for all 5 issues
2. **EXECUTE**: Implement fixes, write tests
3. **REVIEW**: Run multi-model review on changes
4. **VERIFY**: Run full test suite
5. **LEARN**: Document any learnings

## Success Criteria

- [ ] All 5 issues fixed
- [ ] Tests pass (2141+ tests)
- [ ] Multi-model review passes
- [ ] Issues closed with commit references
- [ ] Ready for merge to main

## Notes

- These are the final fixes before V3 rollout
- After this, V3 branch should be merged to main
- All local repos will then use V3 automatically (backward compatible)
