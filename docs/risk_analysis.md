# CORE-025 Risk Analysis

## High Risk

### R1: Concurrent Access Corruption
**Risk**: Multiple Claude sessions writing to same state file
**Mitigation**: File locking with `filelock` package, session isolation via directories
**Residual**: Lock timeout could still cause issues under heavy load

### R2: Partial Migration State
**Risk**: Crash mid-migration leaves inconsistent state
**Mitigation**: Atomic operations (temp-file-and-rename), all-or-nothing with marker file
**Residual**: Filesystem-level failures still possible

### R3: Breaking Existing Workflows
**Risk**: Legacy workflows stop working after update
**Mitigation**: Dual-read pattern - always check legacy path as fallback
**Residual**: Edge cases in path resolution

## Medium Risk

### R4: Windows Compatibility
**Risk**: Path handling differs on Windows (symlinks, long paths)
**Mitigation**: Use file for `current` pointer instead of symlink, test on Windows
**Residual**: Untested edge cases

### R5: Cross-Filesystem Migration
**Risk**: `shutil.move` becomes copy+delete across filesystems
**Mitigation**: Use `shutil.copy2` + explicit delete, handle failures gracefully
**Residual**: Performance impact

### R6: Session Directory Growth
**Risk**: Many sessions accumulate over time
**Mitigation**: Document cleanup, defer session pruning to Phase 2
**Residual**: Disk usage

## Low Risk

### R7: Git Remote Detection Failure
**Risk**: Cannot detect git remote for meta.json
**Mitigation**: Make git_remote optional, graceful fallback
**Residual**: None significant

### R8: Repo Root Detection Edge Cases
**Risk**: Nested repos or no .git directory
**Mitigation**: Fall back to cwd, document behavior
**Residual**: User confusion in edge cases

## Mitigations Summary

| Risk | Severity | Mitigation Strategy |
|------|----------|---------------------|
| Concurrent access | High | File locking + session isolation |
| Partial migration | High | Atomic operations |
| Breaking workflows | High | Dual-read fallback |
| Windows compat | Medium | File-based current pointer |
| Cross-filesystem | Medium | Explicit copy+delete |
| Session growth | Medium | Defer cleanup to Phase 2 |
