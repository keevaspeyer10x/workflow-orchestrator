# Issues #63 and #64: Test Cases

## Issue #64: Default task_provider to 'github'

### TC-64-1: Auto-detect GitHub when Available
**Setup**: In a git repo with gh CLI installed and authenticated
**Input**: `orchestrator task list` (no --provider flag)
**Expected**: Uses GitHub provider (lists issues from repo)
**Verification**: Output shows GitHub issues, not local JSON

### TC-64-2: Fallback to Local when gh Unavailable
**Setup**: gh CLI not installed OR not authenticated
**Input**: `orchestrator task list` (no --provider flag)
**Expected**: Falls back to local provider
**Verification**: Output shows tasks from ~/.config/orchestrator/tasks.json

### TC-64-3: Explicit --provider Overrides Auto-detect
**Setup**: In a git repo with gh CLI available
**Input**: `orchestrator task list --provider local`
**Expected**: Uses local provider despite GitHub being available
**Verification**: Output shows local JSON tasks

### TC-64-4: Task Add Uses Auto-detect
**Setup**: In a git repo with gh CLI available
**Input**: `orchestrator task add "Test task"`
**Expected**: Creates GitHub issue (not local task)
**Verification**: `gh issue list` shows new issue

### TC-64-5: Task Add Fallback to Local
**Setup**: gh CLI not authenticated
**Input**: `orchestrator task add "Test task"`
**Expected**: Creates local task
**Verification**: ~/.config/orchestrator/tasks.json contains new task

---

## Issue #63: commit_and_sync UX in zero_human Mode

### TC-63-1: commit_and_sync Marked Completed After Auto-sync
**Setup**:
- Workflow in LEARN phase with commit_and_sync item "skipped"
- Zero_human mode enabled
- Uncommitted changes exist
**Input**: `orchestrator finish`
**Expected**:
- Auto-sync pushes changes
- commit_and_sync status changes from "skipped" to "completed"
- Notes show "Auto-completed via CORE-031 sync"
**Verification**: `orchestrator status` shows item as completed

### TC-63-2: commit_and_sync Stays Skipped if Sync Fails
**Setup**:
- Workflow with commit_and_sync "skipped"
- Network unavailable or push rejected
**Input**: `orchestrator finish`
**Expected**:
- Sync fails with error
- commit_and_sync remains "skipped"
**Verification**: Status shows "Skipped" (not incorrectly completed)

### TC-63-3: commit_and_sync Stays Skipped with --no-push
**Setup**:
- Workflow with commit_and_sync "skipped"
**Input**: `orchestrator finish --no-push`
**Expected**:
- No sync attempted
- commit_and_sync remains "skipped" (correct - no sync happened)
**Verification**: Status shows "Skipped"

### TC-63-4: Already Completed commit_and_sync Unchanged
**Setup**:
- Workflow with commit_and_sync already "completed" (not skipped)
**Input**: `orchestrator finish`
**Expected**:
- Item remains "completed"
- No duplicate completion or status change
**Verification**: Status unchanged, no errors

### TC-63-5: commit_and_sync Not in Workflow (Edge Case)
**Setup**: Custom workflow.yaml without commit_and_sync item
**Input**: `orchestrator finish`
**Expected**:
- No errors (graceful handling)
- Finish completes normally
**Verification**: Command succeeds, no exceptions

---

## Regression Tests

### RT-1: Existing task list Works
**Input**: `orchestrator task list --provider local`
**Expected**: Lists tasks from local JSON file (existing behavior)

### RT-2: Existing task list --provider github Works
**Input**: `orchestrator task list --provider github`
**Expected**: Lists GitHub issues (existing behavior)

### RT-3: orchestrator finish Without Changes
**Setup**: No uncommitted changes
**Input**: `orchestrator finish`
**Expected**: "Already in sync" message, no errors

### RT-4: Full Workflow Lifecycle
**Input**: Start workflow → complete items → finish
**Expected**: All phases complete correctly, summary accurate

---

## Automated Test Coverage

### Unit Tests to Add

```python
# test_task_provider_autodetect.py
def test_task_list_auto_detects_github():
    """When gh CLI available, task list uses GitHub by default."""
    pass

def test_task_list_falls_back_to_local():
    """When gh CLI unavailable, task list uses local."""
    pass

def test_task_add_respects_auto_detect():
    """Task add uses auto-detected provider."""
    pass

# test_finish_commit_sync_ux.py
def test_finish_updates_skipped_commit_sync_on_success():
    """commit_and_sync marked completed after successful auto-sync."""
    pass

def test_finish_keeps_skipped_on_sync_failure():
    """commit_and_sync stays skipped if auto-sync fails."""
    pass

def test_finish_no_push_keeps_skipped():
    """--no-push keeps commit_and_sync as skipped."""
    pass
```

---

## Manual Verification Checklist

- [ ] `orchestrator task list` auto-detects GitHub in this repo
- [ ] `orchestrator task add "Test" --provider local` uses local
- [ ] `orchestrator finish` shows "Completed" for commit_and_sync after push
- [ ] `orchestrator finish --no-push` shows "Skipped" for commit_and_sync
- [ ] All existing tests pass (`pytest tests/`)
