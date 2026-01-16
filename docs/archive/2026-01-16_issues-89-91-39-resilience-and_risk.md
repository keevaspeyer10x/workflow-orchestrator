# Risk Analysis: V3 Concurrency Fixes

**Issues**: #73 (TOCTOU), #80 (fsync)
**Date**: 2026-01-16

## Risk Summary

| Risk | Likelihood | Impact | Severity | Mitigation |
|------|------------|--------|----------|------------|
| Platform incompatibility (O_DIRECTORY) | Medium | Low | Low | Try/except fallback |
| Atomic rename fails on cross-device | Low | Medium | Low | Lock files are local |
| Performance degradation from fsync | Low | Low | Low | Single syscall, fast |
| Breaking existing tests | Low | Low | Low | Changes are additive |

## Detailed Analysis

### Risk 1: O_DIRECTORY flag unavailable

**Description**: The `os.O_DIRECTORY` flag may not be available on all platforms (notably Windows).

**Likelihood**: Medium (Windows doesn't support O_DIRECTORY)

**Impact**: Low - fsync still works, just with less strict fd type

**Mitigation**: Use `getattr(os, 'O_DIRECTORY', 0)` pattern:
```python
flags = os.O_RDONLY
if hasattr(os, 'O_DIRECTORY'):
    flags |= os.O_DIRECTORY
```

### Risk 2: Atomic rename fails cross-device

**Description**: `Path.rename()` can fail if source and target are on different filesystems.

**Likelihood**: Low - lock files are always in `.orchestrator/` within the repo

**Impact**: Medium - would leave orphaned `.removing` files

**Mitigation**: Already handled - the fix catches `OSError` and handles gracefully.

### Risk 3: fsync performance

**Description**: Directory fsync adds latency to every state save.

**Likelihood**: Low - fsync is typically fast (< 1ms on SSD)

**Impact**: Low - state saves are infrequent (once per workflow operation)

**Mitigation**: None needed. Correctness > performance for state persistence.

### Risk 4: Concurrent test flakiness

**Description**: Tests for concurrent behavior can be flaky.

**Likelihood**: Medium - race conditions are inherently timing-dependent

**Impact**: Low - test flakiness doesn't affect production

**Mitigation**: Test the pattern (atomic rename succeeds) not the race condition itself.

## Security Considerations

### Positive Security Impact

1. **TOCTOU fix**: Eliminates race condition that could allow lock bypass
2. **fsync fix**: Ensures state durability, preventing data loss/corruption

### No New Security Risks

- No new attack surface
- No new dependencies
- No privilege escalation paths

## Rollback Plan

Both changes are isolated and can be reverted independently:
1. Revert commit for TOCTOU fix
2. Revert commit for fsync fix

No data migration required.
