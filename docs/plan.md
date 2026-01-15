# V3 Hybrid Orchestration - Phase 3 Implementation Plan

**Task:** Implement v3 hybrid orchestration Phase 3: Checkpointing
**Date:** 2026-01-16

## Overview

Phase 3 extends the existing checkpoint system with chaining, concurrent access handling, and lock management.

## Files to Modify

### 1. `src/checkpoint.py` (MODIFY)

**New Features:**

1. **Checkpoint Chaining**
   - Add `parent_checkpoint_id` field to CheckpointData
   - Track lineage for checkpoint history
   - Method to get checkpoint chain

2. **File Locking**
   - Add `FileLock` class for cross-process locking
   - Lock checkpoints during read/write operations
   - Use `fcntl.flock()` for UNIX/Linux, fallback for Windows

3. **Lock Management**
   - Add `LockManager` class
   - Timeout support for lock acquisition
   - Automatic lock cleanup on process exit

### 2. `tests/test_checkpoint_v3.py` (NEW)

Test classes:
- `TestCheckpointChaining` - parent chain, lineage
- `TestFileLocking` - concurrent access, deadlock prevention
- `TestLockManager` - acquire/release, timeouts

## Execution Strategy

**Sequential execution** - Features are interdependent:
- Locking depends on FileLock class
- Chaining extends CheckpointData
- Tests verify all features together

## Implementation Order

1. Add FileLock class to src/checkpoint.py
2. Add LockManager class
3. Extend CheckpointData with parent_checkpoint_id
4. Add checkpoint chain methods
5. Create tests/test_checkpoint_v3.py
6. Run tests and verify
7. Tag v3-phase3-complete
