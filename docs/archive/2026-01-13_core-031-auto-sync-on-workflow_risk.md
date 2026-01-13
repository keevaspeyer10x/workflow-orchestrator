# CORE-025 Phase 4: Risk Analysis

## Risk Assessment

### High Risk

#### R1: Merge Conflicts on Finish
**Risk**: When merging worktree branch back to original, conflicts may occur if the original branch has changed.
**Mitigation**:
- Detect merge conflicts before attempting auto-merge
- Provide clear error message with resolution steps
- Offer `--no-merge` flag to skip auto-merge
- Store unmerged worktree path for manual resolution

#### R2: Orphaned Worktrees
**Risk**: Crash or interruption leaves worktrees without cleanup.
**Mitigation**:
- `orchestrator doctor` command for reconciliation
- Store worktree metadata in session for recovery
- Clear warning when orphans detected

### Medium Risk

#### R3: Disk Space
**Risk**: Each worktree consumes disk space (full working copy).
**Mitigation**:
- Document space requirements
- `orchestrator doctor --cleanup` for manual cleanup
- Future: max concurrent limit (deferred to v2)

#### R4: Git Version Compatibility
**Risk**: Worktrees require Git 2.5+ (released 2015).
**Mitigation**:
- Check git version before worktree operations
- Clear error message if git too old
- Document minimum version requirement

#### R5: Port Conflicts
**Risk**: Multiple worktree sessions may try to use same ports.
**Mitigation**:
- Document port conflict strategy in CLAUDE.md
- Recommend different PORT env vars per worktree
- Future: automatic port allocation (deferred)

### Low Risk

#### R6: .env File Sensitivity
**Risk**: Copying .env files to worktrees duplicates secrets.
**Mitigation**:
- Worktrees are in .orchestrator/ (gitignored)
- .env files are not committed to git
- Cleanup removes worktree and .env copies

#### R7: Branch Naming Collisions
**Risk**: Session ID collision creates duplicate branch names.
**Mitigation**:
- 8-char UUID prefix has extremely low collision probability
- Check branch exists before creating
- Error with clear message if collision occurs

## Impact Assessment

| Area | Impact | Notes |
|------|--------|-------|
| Existing workflows | None | Only affects new `--isolated` workflows |
| CLI interface | Low | Additive changes, no breaking changes |
| Session management | Low | New metadata fields, backward compatible |
| File system | Medium | New .orchestrator/worktrees/ directory |

## Rollback Plan

If issues are discovered:
1. Remove `--isolated` flag from cmd_start (returns to non-isolated behavior)
2. `orchestrator doctor --cleanup` removes all worktrees
3. Session metadata fields are safely ignored by older versions
