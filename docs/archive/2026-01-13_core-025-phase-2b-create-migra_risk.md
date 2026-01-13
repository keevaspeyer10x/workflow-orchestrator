# CORE-025 Phase 2: Risk Analysis

## Risk Assessment

### Risk 1: Breaking Backward Compatibility
**Severity:** HIGH
**Likelihood:** MEDIUM
**Impact:** Users with existing `.workflow_state.json` lose access to active workflows

**Mitigation:**
- Implement dual-read pattern: check new path first, fall back to legacy
- Never auto-delete legacy files
- Document migration path for users
- Integration test: verify legacy state files load correctly

### Risk 2: Race Conditions with Concurrent Access
**Severity:** MEDIUM
**Likelihood:** LOW
**Impact:** State corruption if multiple processes access same session

**Mitigation:**
- Keep existing fcntl file locking (already in engine.py)
- Sessions are isolated by design (each has own directory)
- Test concurrent access patterns

### Risk 3: Path Resolution Errors
**Severity:** MEDIUM
**Likelihood:** LOW
**Impact:** Files created in wrong location or not found

**Mitigation:**
- OrchestratorPaths already has unit tests (34 passing)
- Add integration tests verifying paths in real workflow
- Use absolute paths internally

### Risk 4: Session Creation Failure
**Severity:** LOW
**Likelihood:** LOW
**Impact:** Workflow can't start if `.orchestrator/` creation fails

**Mitigation:**
- SessionManager.create_session() uses mkdir with exist_ok=True
- Fail early with clear error message
- Test permission scenarios

### Risk 5: CLI Breaking Changes
**Severity:** MEDIUM
**Likelihood:** LOW
**Impact:** Existing scripts using `orchestrator` CLI break

**Mitigation:**
- No changes to CLI command interface
- Only internal implementation changes
- All existing commands work identically

## Impact Analysis

### Files Modified
| File | Risk Level | Rollback Complexity |
|------|------------|---------------------|
| src/engine.py | HIGH | MEDIUM - Core logic changes |
| src/cli.py | MEDIUM | LOW - Initialization changes |
| src/checkpoint.py | LOW | LOW - Path changes only |
| src/learning_engine.py | LOW | LOW - Path changes only |

### Dependencies Affected
- All CLI commands use WorkflowEngine
- Checkpoint and Learning features depend on path resolution
- No external API changes

## Rollback Plan

If issues are discovered:
1. Revert to commit 458d302 (Phase 1 complete)
2. Users with new `.orchestrator/` structure can copy state files back to root
3. Legacy path support means existing workflows continue working

## Testing Requirements

1. **Backward Compatibility Test**
   - Existing `.workflow_state.json` loads correctly
   - Workflow can complete with legacy files

2. **New Path Test**
   - New workflows create files in `.orchestrator/sessions/<id>/`
   - All operations work with new paths

3. **Migration Test**
   - Mixed scenario: legacy state, new checkpoints

4. **Concurrency Test**
   - Multiple sessions in parallel don't conflict
