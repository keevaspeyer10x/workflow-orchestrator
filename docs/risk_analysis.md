# Risk Analysis: Roadmap Items CORE-007, CORE-008, ARCH-001, WF-004

## Overall Risk Assessment: LOW

All four items are low-complexity changes with minimal risk. The changes are isolated and backwards-compatible.

---

## Risk Assessment by Item

### CORE-007: Deprecate Legacy Claude Integration

**Risk Level:** Very Low

**Potential Issues:**
1. **Breaking existing code that imports claude_integration**
   - Impact: Low - deprecation warning doesn't break functionality
   - Mitigation: Warning only, no removal until v3.0

2. **Noisy warnings in logs/output**
   - Impact: Low - cosmetic issue
   - Mitigation: Use `stacklevel=2` to point to correct caller

**Testing Required:**
- Verify warning appears when module imported
- Verify existing functionality still works

---

### CORE-008: Input Length Limits

**Risk Level:** Low

**Potential Issues:**
1. **Rejecting valid user input that happens to be long**
   - Impact: Medium - user frustration
   - Mitigation: 1000 chars for constraints, 500 chars for notes are generous limits
   - Mitigation: Clear error messages explaining the limit

2. **Breaking existing workflows with long constraints**
   - Impact: Low - validation only applies to new input, not stored data
   - Mitigation: Only validate on input, not when reading state

**Testing Required:**
- Verify inputs under limit work normally
- Verify inputs at limit work
- Verify inputs over limit rejected with clear error
- Verify existing state with long notes still readable

---

### ARCH-001: Extract Retry Logic

**Risk Level:** Low

**Potential Issues:**
1. **Changing retry behavior in visual_verification.py**
   - Impact: Medium - could affect network resilience
   - Mitigation: Match existing behavior exactly (base 2^n backoff)
   - Mitigation: Keep same defaults (3 retries, exponential backoff)

2. **Decorator complexity with class methods**
   - Impact: Low - decorators work well with methods
   - Mitigation: Use `functools.wraps` to preserve method signatures

**Testing Required:**
- Unit test retry decorator with mock functions
- Test exponential backoff timing
- Test exception propagation after max retries
- Verify visual_verification.py still works

---

### WF-004: Auto-Archive Workflow Documents

**Risk Level:** Low-Medium

**Potential Issues:**
1. **Accidentally archiving important files**
   - Impact: Medium - user loses access to current plan
   - Mitigation: Only archive specific known files (plan.md, risk_analysis.md, test_cases.md)
   - Mitigation: Add `--no-archive` flag to skip

2. **Archive directory clutter**
   - Impact: Low - cosmetic
   - Mitigation: Use dated naming for easy cleanup

3. **File permission issues**
   - Impact: Medium - could fail silently
   - Mitigation: Check permissions, report errors clearly

4. **Race condition with duplicate names**
   - Impact: Low - unlikely
   - Mitigation: Counter suffix for duplicate names

**Testing Required:**
- Test archiving when files exist
- Test skipping when files don't exist
- Test --no-archive flag
- Test duplicate name handling
- Verify archived files are intact

---

## Security Considerations

### CORE-008: Input Validation (Security Improvement)
This change **improves** security by preventing:
- Memory exhaustion from extremely long strings
- Potential log injection with very long inputs
- DoS via oversized state files

### No New Attack Surface
None of these changes introduce:
- New network access
- New file system access (archive only moves existing files)
- External dependencies
- User input that reaches shell commands

---

## Backward Compatibility

All changes are backward compatible:
- CORE-007: Warning only, no functional change
- CORE-008: Existing data unaffected, only new input validated
- ARCH-001: Same retry behavior, just refactored
- WF-004: Opt-out available with `--no-archive`

---

## Rollback Plan

If issues occur:

1. **CORE-007:** Remove deprecation warning (one-line change)
2. **CORE-008:** Remove validation calls, delete validation.py
3. **ARCH-001:** Revert visual_verification.py to inline retry logic
4. **WF-004:** Remove archive call from start_workflow, delete method

All changes are isolated and can be reverted independently.

---

## Testing Checklist

Before merge:
- [ ] All existing tests pass
- [ ] New unit tests for retry decorator
- [ ] New unit tests for input validation
- [ ] Integration test for auto-archive
- [ ] Manual test of deprecation warning
- [ ] Manual test of input limits
