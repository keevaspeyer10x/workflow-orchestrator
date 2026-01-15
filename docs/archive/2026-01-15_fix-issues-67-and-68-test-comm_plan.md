# Issues #63 and #64: Quick Fix Implementation Plan

## Overview

Two UX quick fixes for the workflow orchestrator:
1. **#64**: Default task_provider to 'github' when gh CLI available
2. **#63**: Fix commit_and_sync showing "Skipped" when auto-sync actually pushes

## Issue #64: Default task_provider to 'github'

### Problem
- `orchestrator task add` stores tasks locally by default (~/.config/orchestrator/tasks.json)
- Users expect GitHub Issues when working in a GitHub repo
- Current explicit `--provider local` default causes task confusion

### Solution
Change the default provider resolution in CLI task commands from hardcoded `'local'` to use `get_task_provider()` auto-detection, which already tries GitHub first.

### Files to Modify
- `src/cli.py` - Lines 5886, 5910, 5946, 5965 in task command handlers

### Implementation Steps
1. In `cmd_task_list()`, `cmd_task_add()`, `cmd_task_next()`, `cmd_task_close()`, `cmd_task_show()`:
   - Change from: `provider_name = getattr(args, 'provider', None) or 'local'`
   - To: `provider_name = getattr(args, 'provider', None)` (let get_task_provider auto-detect)
2. The existing `get_task_provider(None)` already:
   - Tries GitHub first (checks gh CLI + authentication + git remote)
   - Falls back to local if GitHub unavailable
3. Update help text to indicate auto-detection

---

## Issue #63: commit_and_sync UX in zero_human mode

### Problem
- In zero_human mode, `commit_and_sync` manual gate is auto-skipped
- Shows "Skipped: Auto-skipped (zero_human mode)" in summary
- But `orchestrator finish` still pushes via CORE-031 auto-sync
- Users think their work wasn't committed/pushed

### Solution
**Option B (recommended)**: Mark `commit_and_sync` as "completed" (not "skipped") when auto-sync succeeds in zero_human mode.

### Files to Modify
- `src/cli.py` - `cmd_finish()` function (lines ~1511-1552)

### Implementation Steps
1. After successful auto-sync in `cmd_finish()`:
   - Load the workflow engine
   - Find the `commit_and_sync` item
   - If status is "skipped" and auto-sync succeeded:
     - Update status to "completed"
     - Set notes to "Auto-completed via CORE-031 sync"
   - Save state
2. The finish summary will now show "Completed" instead of "Skipped"

---

## Parallel Execution Decision

**Will use SEQUENTIAL execution** because:
- Both fixes are small (~10-20 lines each)
- They're in the same file (src/cli.py)
- Changes don't conflict but testing is easier sequentially
- Total implementation time is minimal

---

## Implementation Order

1. **#64 first** - Simpler, isolated change to task commands
2. **#63 second** - Requires understanding of engine state updates
3. **Tests** - Run existing test suite + manual verification
4. **Commit** - Single commit for both fixes
