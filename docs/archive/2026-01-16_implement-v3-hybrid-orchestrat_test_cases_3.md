# V3 Hybrid Orchestration - Phase 3 Test Cases

**Task:** Implement v3 hybrid orchestration Phase 3: Checkpointing
**Date:** 2026-01-16

## Test Categories

### Checkpoint Chaining Tests

| ID | Test | Expected |
|----|------|----------|
| CC-01 | Create checkpoint with parent | parent_checkpoint_id set |
| CC-02 | Get checkpoint chain | Returns full lineage |
| CC-03 | Chain with missing parent | Handles gracefully |

### File Locking Tests

| ID | Test | Expected |
|----|------|----------|
| FL-01 | Acquire exclusive lock | Lock acquired |
| FL-02 | Acquire shared lock | Multiple readers allowed |
| FL-03 | Lock timeout | Raises after timeout |
| FL-04 | Lock released on exit | Auto-cleanup works |

### Lock Manager Tests

| ID | Test | Expected |
|----|------|----------|
| LM-01 | Context manager usage | Lock released after block |
| LM-02 | Nested locks same file | No deadlock |
| LM-03 | Stale lock detection | Old locks cleaned up |
