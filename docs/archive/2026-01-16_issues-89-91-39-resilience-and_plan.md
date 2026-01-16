# V3 Concurrency Fixes Plan

**Task**: Fix issues #72, #73, #80 - V3 concurrency and reliability improvements
**Date**: 2026-01-16

## Summary

Address two valid concurrency/reliability issues identified in multi-model code review:
- **Issue #73**: TOCTOU vulnerability in stale lock cleanup
- **Issue #80**: Missing directory fsync after atomic rename

Issue #72 is obsolete (references non-existent `StateVersionManager` class).

## Scope

### In Scope
1. Fix TOCTOU vulnerability in `checkpoint.py:_clean_stale_lock()`
2. Add directory fsync in `state_version.py:save_state_with_integrity()`
3. Add unit tests for both fixes
4. Close issue #72 as obsolete

### Out of Scope
- Creating new StateVersionManager class
- Platform-specific fsync behavior (will fsync on all platforms)

## Implementation Plan

### Fix 1: TOCTOU in Stale Lock Cleanup (Issue #73)

**File**: `src/checkpoint.py`
**Method**: `LockManager._clean_stale_lock()`
**Current line**: 336-359

**Current vulnerable pattern**:
```python
def _clean_stale_lock(self, lock_path: Path) -> None:
    if not lock_path.exists():
        return
    # ... check PID ...
    if not _process_exists(pid):
        lock_path.unlink()  # RACE: another process could acquire between check and unlink
```

**Fixed pattern** (atomic rename before delete):
```python
def _clean_stale_lock(self, lock_path: Path) -> None:
    if not lock_path.exists():
        return
    # ... security checks ...
    try:
        content = lock_path.read_text().strip()
        if content:
            pid = int(content)
            if not _process_exists(pid):
                # Atomic: rename to temp, then delete
                # If rename succeeds, we own the file
                temp_path = lock_path.with_suffix('.removing')
                try:
                    lock_path.rename(temp_path)
                    temp_path.unlink()
                except FileNotFoundError:
                    pass  # Another process already removed it
                except OSError:
                    pass  # Lock was acquired (no longer stale)
    except (ValueError, FileNotFoundError):
        pass
```

### Fix 2: Directory fsync (Issue #80)

**File**: `src/state_version.py`
**Function**: `save_state_with_integrity()`
**Current line**: 71

**Current code**:
```python
temp_path.rename(state_path)
# Missing directory fsync!
```

**Fixed code**:
```python
temp_path.rename(state_path)

# Sync directory to ensure rename is durable (prevents data loss on crash)
dir_fd = os.open(str(state_path.parent), os.O_RDONLY | os.O_DIRECTORY)
try:
    os.fsync(dir_fd)
finally:
    os.close(dir_fd)
```

**Note**: `O_DIRECTORY` may not be available on all platforms. Will use try/except with fallback.

## Test Cases

### Test 1: Atomic stale lock removal
- Create a lock file with dead PID
- Call `_clean_stale_lock()`
- Verify lock is removed
- Verify no `.removing` temp files left behind

### Test 2: Directory fsync called
- Mock `os.open` and `os.fsync`
- Call `save_state_with_integrity()`
- Verify directory fd opened and fsynced

## Execution Mode

**Sequential execution** - These are small, focused changes in the same codebase area. No benefit to parallelization; easier to review and test sequentially.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| fsync slows writes | Low | Low | fsync is fast; correctness > speed |
| Platform compatibility | Medium | Medium | Use try/except for O_DIRECTORY |
| Breaking existing tests | Low | Low | Changes are additive |

## Acceptance Criteria

- [ ] TOCTOU vulnerability fixed with atomic rename pattern
- [ ] Directory fsync added after atomic rename
- [ ] Unit tests pass
- [ ] Existing tests pass
- [ ] Issues #73 and #80 can be closed
- [ ] Issue #72 closed as obsolete
