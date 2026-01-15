# V3 Hybrid Orchestration - Phase 0 Risk Analysis

**Task:** Implement v3 hybrid orchestration Phase 0
**Date:** 2026-01-16

## Risk Assessment Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Mode detection false negative | Low | High | Emergency override escape hatch |
| Mode detection false positive | Medium | Low | ORCHESTRATOR_MODE=human override |
| State file corruption | Low | Medium | Atomic writes + checksums |
| State tampering undetected | Very Low | High | SHA256 checksums |
| Version confusion (v2/v3) | Medium | Medium | Separate state directories |
| Breaking existing CLI | Medium | High | Preserve existing interface |

## Detailed Risk Analysis

### R1: Mode Detection False Negative (LLM detected as human)

**Risk:** LLM gains human-level privileges, bypasses restrictions

**Likelihood:** Low - Multiple detection signals (CLAUDECODE, TTY)

**Impact:** High - Security boundary breached

**Mitigations:**
1. Conservative default (unknown = LLM mode)
2. Multiple detection signals checked in priority order
3. Audit logging of mode detection for debugging

### R2: Mode Detection False Positive (Human detected as LLM)

**Risk:** Human operator blocked from legitimate actions

**Likelihood:** Medium - Non-TTY sessions common (SSH, CI)

**Impact:** Low - Emergency override available

**Mitigations:**
1. Emergency override: `ORCHESTRATOR_EMERGENCY_OVERRIDE=human-override-v3`
2. Explicit mode: `ORCHESTRATOR_MODE=human`
3. Clear error messages with override instructions

### R3: State File Corruption

**Risk:** Workflow state lost or corrupted during write

**Likelihood:** Low - OS-level issues (power loss, disk full)

**Impact:** Medium - Workflow progress lost

**Mitigations:**
1. Atomic writes (temp file + rename)
2. fsync before rename
3. Checksum verification on load

### R4: State Tampering Undetected

**Risk:** Malicious modification of state bypasses controls

**Likelihood:** Very Low - Requires local filesystem access

**Impact:** High - Security controls circumvented

**Mitigations:**
1. SHA256 checksum verification
2. Version field prevents downgrade attacks
3. Audit logging tracks all state changes

### R5: Version Confusion (v2/v3 State)

**Risk:** v3 code reads v2 state or vice versa

**Likelihood:** Medium - During migration period

**Impact:** Medium - Unexpected behavior

**Mitigations:**
1. Separate directories: `.orchestrator/` (v2) vs `.orchestrator/v3/` (v3)
2. Version field in state files
3. Clear error messages for version mismatch

### R6: Breaking Existing CLI

**Risk:** Changes break existing workflows

**Likelihood:** Medium - Significant refactoring

**Impact:** High - User disruption

**Mitigations:**
1. Phase 0 adds new modules, doesn't modify existing heavily
2. `is_llm_mode()` interface preserved (import changes)
3. Comprehensive test suite (2019 existing tests)
4. Rollback point available (`v2.0-stable`)

## Phase 0 Specific Risks

### Integration with Existing Code

**Risk:** New mode_detection.py conflicts with existing is_llm_mode()

**Mitigation:** Replace existing function with import from new module, preserving interface

### Test Coverage Gaps

**Risk:** New code paths untested

**Mitigation:**
- Write tests before implementation (TDD approach)
- Target ~15 new tests covering all detection paths
- Use mocking for environment variables and TTY state

## Rollback Plan

If critical issues discovered:

```bash
git checkout v2.0-stable
pip install -e .
rm -rf .orchestrator/v3/
```

Detailed rollback instructions in `/home/keeva/workflow-orchestrator/ROLLBACK.md`

## Acceptance Criteria

Phase 0 acceptable when:
1. All existing tests pass
2. New tests pass with >90% coverage on new modules
3. Mode detection correctly identifies Claude Code environment
4. Emergency override works
5. State checksums detect tampering
