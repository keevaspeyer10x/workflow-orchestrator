# CORE-031: Risk Analysis

## Risk Assessment

### Risk 1: Accidental Push to Wrong Branch
**Severity:** HIGH
**Likelihood:** LOW

**Description:** Auto-push could push to wrong remote branch if tracking is misconfigured.

**Mitigation:**
- Always use `git rev-parse --abbrev-ref --symbolic-full-name @{u}` to get actual upstream
- Refuse to push if no upstream is configured (require explicit `git push -u`)
- Log which branch we're pushing to before pushing

### Risk 2: Force Push / Destructive Operations
**Severity:** CRITICAL
**Likelihood:** VERY LOW

**Description:** Sync logic must NEVER do force push or rewrite history.

**Mitigation:**
- Never use `--force` flag
- Only use `git push` (not `git push -f`)
- Fail gracefully if push rejected - let user handle

### Risk 3: Conflict Resolution Fails Mid-Sync
**Severity:** MEDIUM
**Likelihood:** MEDIUM

**Description:** If sync starts, detects conflicts, but then conflict resolution fails, user could be in an awkward state.

**Mitigation:**
- Use `--continue` flag to resume from interrupted state
- Save state before starting any destructive operations
- Provide clear instructions for manual recovery
- Don't abort workflow completion - just skip sync

### Risk 4: No Network / Remote Unreachable
**Severity:** LOW
**Likelihood:** MEDIUM

**Description:** Network issues during fetch/push could cause confusing errors.

**Mitigation:**
- Set reasonable timeout (30s for fetch, 60s for push)
- Clear error message: "Remote unreachable - use --no-push to skip"
- Non-fatal: workflow still completes, just warns about sync failure

### Risk 5: Large Push Takes Too Long
**Severity:** LOW
**Likelihood:** LOW

**Description:** Very large commits could timeout during push.

**Mitigation:**
- Configurable timeout (default 60s)
- Progress indication where possible
- Warn but don't fail workflow on timeout

### Risk 6: Isolated Worktree + Remote Conflicts
**Severity:** MEDIUM
**Likelihood:** LOW

**Description:** For `--isolated` workflows, merge to original branch succeeds but push to remote fails.

**Mitigation:**
- Merge happens locally first (already working)
- Push failure is non-fatal - warn user
- User can manually push if needed

## Impact Assessment

### Affected Components
1. `src/cli.py` - cmd_finish function (existing, well-tested)
2. `src/sync_manager.py` - New module (isolated, testable)
3. `src/worktree_manager.py` - Minor addition (push after merge)

### Breaking Changes
- **None** - All new flags are additive
- Existing workflows continue to work (just gain auto-push)
- `--no-push` provides escape hatch for old behavior

### Backwards Compatibility
- Default behavior changes from "no sync" to "auto sync"
- Users who relied on manual push will now have auto push
- This is intentional and desired per user feedback
- `--no-push` flag preserves old behavior if needed

## Rollback Plan
If issues discovered:
1. `--no-push` flag allows immediate workaround
2. Can revert to previous behavior by making `--no-push` the default
3. `SyncManager` is isolated - can be disabled without affecting rest of finish
