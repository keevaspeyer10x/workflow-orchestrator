# CORE-031: Test Cases

## Unit Tests: SyncManager (`tests/test_sync_manager.py`)

### Test 1: `test_get_remote_tracking_branch`
**Input:** Branch with upstream configured
**Expected:** Returns `origin/main` (or equivalent)
**Edge case:** Returns `None` if no upstream

### Test 2: `test_fetch_success`
**Input:** Valid remote
**Expected:** Returns `True`, fetches refs
**Mock:** `git fetch` subprocess

### Test 3: `test_fetch_network_error`
**Input:** Unreachable remote
**Expected:** Returns `False`, no exception
**Mock:** `git fetch` returns non-zero exit code

### Test 4: `test_check_divergence_in_sync`
**Input:** Local and remote at same commit
**Expected:** `DivergenceInfo(diverged=False, local_ahead=0, remote_ahead=0)`

### Test 5: `test_check_divergence_local_ahead`
**Input:** Local has 3 commits not on remote
**Expected:** `DivergenceInfo(diverged=False, local_ahead=3, remote_ahead=0)`

### Test 6: `test_check_divergence_remote_ahead`
**Input:** Remote has 2 commits not on local
**Expected:** `DivergenceInfo(diverged=True, local_ahead=0, remote_ahead=2)`

### Test 7: `test_check_divergence_both`
**Input:** Both local and remote have diverged commits
**Expected:** `DivergenceInfo(diverged=True, local_ahead=2, remote_ahead=1)`

### Test 8: `test_attempt_rebase_success`
**Input:** Remote ahead, no conflicts
**Expected:** Returns `True`, local rebased

### Test 9: `test_attempt_rebase_conflicts`
**Input:** Remote ahead with conflicts
**Expected:** Returns `False`, rebase aborted

### Test 10: `test_push_success`
**Input:** Local ahead, remote reachable
**Expected:** `SyncResult(success=True, pushed_commits=3)`

### Test 11: `test_push_rejected`
**Input:** Remote has changes (non-fast-forward)
**Expected:** `SyncResult(success=False)`, no force push

### Test 12: `test_sync_full_flow`
**Input:** Local ahead by 2 commits
**Expected:** Fetch -> check -> push, returns success

## Integration Tests: cmd_finish (`tests/test_cli_finish.py`)

### Test 13: `test_finish_with_auto_push`
**Setup:** Active workflow, local commits
**Command:** `orchestrator finish`
**Expected:** Workflow completes AND commits pushed

### Test 14: `test_finish_with_no_push_flag`
**Setup:** Active workflow, local commits
**Command:** `orchestrator finish --no-push`
**Expected:** Workflow completes, NO push happens

### Test 15: `test_finish_no_remote`
**Setup:** Active workflow, no remote configured
**Command:** `orchestrator finish`
**Expected:** Workflow completes, sync skipped gracefully

### Test 16: `test_finish_conflict_detection`
**Setup:** Active workflow, remote diverged with conflicts
**Command:** `orchestrator finish`
**Expected:** Workflow paused, message about conflicts, suggests `--continue`

### Test 17: `test_finish_continue_after_resolve`
**Setup:** Conflict state resolved manually
**Command:** `orchestrator finish --continue`
**Expected:** Completes push, cleans up state

### Test 18: `test_finish_isolated_worktree_push`
**Setup:** Isolated worktree workflow completed
**Command:** `orchestrator finish`
**Expected:** Merges to original branch AND pushes

### Test 19: `test_finish_isolated_no_push`
**Setup:** Isolated worktree workflow
**Command:** `orchestrator finish --no-push`
**Expected:** Merges locally, no push

## Edge Case Tests

### Test 20: `test_sync_timeout`
**Setup:** Very slow remote
**Expected:** Timeout after configured duration, warns but doesn't fail

### Test 21: `test_sync_empty_push`
**Setup:** Already in sync with remote
**Expected:** "Nothing to push" message, success

### Test 22: `test_sync_detached_head`
**Setup:** Detached HEAD state
**Expected:** Skip sync gracefully (no tracking branch)

## Test Fixtures Needed

```python
@pytest.fixture
def mock_git_repo(tmp_path):
    """Create a mock git repo with remote."""

@pytest.fixture
def active_workflow(mock_git_repo):
    """Create an active workflow in the mock repo."""

@pytest.fixture
def diverged_remote(mock_git_repo):
    """Setup remote with diverged commits."""
```

## TDD Order
1. Write `test_get_remote_tracking_branch` first
2. Implement `get_remote_tracking_branch()`
3. Write `test_check_divergence_*` tests
4. Implement `check_divergence()`
5. Write `test_push_*` tests
6. Implement `push()`
7. Write integration tests
8. Wire everything together in `cmd_finish`
