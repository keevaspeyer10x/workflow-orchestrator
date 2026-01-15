# Issue #56: Risk Analysis

## Risk Assessment

### 1. gh CLI Dependency (LOW)
**Risk:** GitHub backend requires `gh` CLI to be installed and authenticated.
**Mitigation:**
- Graceful fallback to local backend if gh unavailable
- Check `gh auth status` before operations
- Clear error messages with setup instructions

### 2. File Locking for Local Backend (LOW)
**Risk:** Concurrent writes to tasks.json could cause corruption.
**Mitigation:**
- Single-user use case (orchestrator is single-agent)
- Could add fcntl locking if needed (defer per YAGNI)
- Atomic write using temp file + rename

### 3. Repo Detection Edge Cases (LOW)
**Risk:** `git remote get-url origin` may fail or return unexpected format.
**Mitigation:**
- Support multiple URL formats (HTTPS, SSH, git@)
- Allow explicit `--repo owner/name` override
- Fail fast with clear error message

### 4. Breaking Changes to Existing Code (NONE)
**Risk:** New module, no changes to existing interfaces.
**Mitigation:** N/A - purely additive feature.

### 5. CLI Namespace Collision (NONE)
**Risk:** `task` subcommand conflicts with existing commands.
**Mitigation:** Checked - no existing `task` command.

## Impact Assessment

| Area | Impact | Notes |
|------|--------|-------|
| Existing workflows | None | Additive feature |
| Dependencies | None | Uses stdlib only |
| Config files | None | Optional config integration |
| Tests | Add | New test file needed |
| Documentation | Add | Update CLAUDE.md |

## Rollback Plan
If issues arise:
1. Feature is isolated in `src/task_provider/`
2. CLI commands are additive (no existing behavior changed)
3. Can revert entire module without affecting core orchestrator

## Security Considerations
- Local backend: File permissions follow user defaults
- GitHub backend: Uses `gh` CLI authentication (already trusted)
- No secrets stored in task data
- No remote execution or code evaluation
