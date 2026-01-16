# Test Cases: V3 Concurrency Fixes

## Issue #73: TOCTOU in Stale Lock Cleanup

### TC-73-1: Remove stale lock with dead process
**Preconditions**: Lock file exists with PID of non-existent process
**Steps**:
1. Create lock file with content "99999" (non-existent PID)
2. Call `_clean_stale_lock(lock_path)`
3. Verify lock file is removed
4. Verify no `.removing` temp file remains

**Expected**: Lock file removed, no temp files

### TC-73-2: Preserve lock with live process
**Preconditions**: Lock file exists with PID of current process
**Steps**:
1. Create lock file with content `str(os.getpid())`
2. Call `_clean_stale_lock(lock_path)`
3. Verify lock file still exists

**Expected**: Lock file preserved

### TC-73-3: Handle concurrent removal
**Preconditions**: Lock file exists with dead PID
**Steps**:
1. Create lock file
2. Remove file externally (simulating race)
3. Call `_clean_stale_lock(lock_path)`

**Expected**: No exception raised, graceful handling

### TC-73-4: Symlink attack prevention (existing)
**Preconditions**: Symlink pointing outside lock_dir
**Steps**:
1. Create symlink in lock_dir pointing to /tmp/target
2. Call `_clean_stale_lock(symlink_path)`

**Expected**: Symlink ignored (security check passes)

## Issue #80: Directory fsync

### TC-80-1: fsync called after rename
**Preconditions**: None
**Steps**:
1. Mock `os.open`, `os.fsync`, `os.close`
2. Call `save_state_with_integrity(path, data)`
3. Verify `os.open` called with directory path
4. Verify `os.fsync` called with directory fd
5. Verify `os.close` called

**Expected**: Directory fsync sequence complete

### TC-80-2: fsync handles missing O_DIRECTORY
**Preconditions**: Platform without O_DIRECTORY
**Steps**:
1. Temporarily remove `os.O_DIRECTORY` if present
2. Call `save_state_with_integrity(path, data)`
3. Verify function completes without error

**Expected**: Graceful fallback, no exception

### TC-80-3: State file integrity preserved
**Preconditions**: None
**Steps**:
1. Call `save_state_with_integrity(path, data)`
2. Call `load_state_with_verification(path)`
3. Verify data matches

**Expected**: Round-trip successful, checksum valid

### TC-80-4: fsync error handling
**Preconditions**: None
**Steps**:
1. Mock `os.fsync` to raise OSError
2. Call `save_state_with_integrity(path, data)`

**Expected**: State still saved (fsync failure is non-fatal on most platforms)
