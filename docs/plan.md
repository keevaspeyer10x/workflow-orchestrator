# CORE-031: Auto-Sync on Workflow Finish

## Overview
Make `orchestrator finish` automatically sync with remote - fetch before finish, handle conflicts via existing `orchestrator resolve` / `GitConflictResolver`, and push after success.

## User Decisions
- **Default behavior:** Auto-push ON (use `--no-push` to skip)
- **Conflict handling:** Integrate with existing `GitConflictResolver`
- **Isolated workflows:** Push merged result to remote

## Parallel Execution Assessment
**Decision: SEQUENTIAL**

Tasks are interdependent:
1. CLI flags must exist before sync logic uses them
2. Divergence detection needed before conflict handling
3. Conflict resolution integration depends on divergence detection
4. Tests should follow TDD (write as we implement each feature)

No opportunities for parallel agents - this is a single coherent feature in one command.

## Implementation Steps

### Step 1: Add CLI flags to `finish` command
**File:** `src/cli.py:5644-5651`

Add:
- `--no-push` - Skip auto-sync to remote (escape hatch)
- `--continue` - Resume finish after manual conflict resolution

### Step 2: Create `SyncManager` class
**File:** `src/sync_manager.py` (new)

Encapsulates all sync logic:
```python
@dataclass
class DivergenceInfo:
    diverged: bool
    local_ahead: int
    remote_ahead: int
    remote_branch: str

@dataclass
class SyncResult:
    success: bool
    pushed_commits: int
    message: str
    conflicts: list[str] = field(default_factory=list)

class SyncManager:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def get_remote_tracking_branch(self) -> Optional[str]:
        """Get the upstream branch for current branch."""

    def fetch(self) -> bool:
        """Fetch from remote."""

    def check_divergence(self) -> DivergenceInfo:
        """Check if local and remote have diverged."""

    def attempt_rebase(self, remote_branch: str) -> bool:
        """Try to rebase onto remote. Returns False if conflicts."""

    def push(self) -> SyncResult:
        """Push to remote tracking branch."""

    def sync(self) -> SyncResult:
        """Full sync: fetch, handle divergence, push."""
```

### Step 3: Integrate with `cmd_finish`
**File:** `src/cli.py:1321+`

Insert sync logic after review validation, before summary generation:

```python
def cmd_finish(args):
    # ... existing validation ...

    if not args.no_push:
        sync_mgr = SyncManager(working_dir)

        # Check if we have a remote
        if sync_mgr.get_remote_tracking_branch():
            sync_result = sync_mgr.sync()

            if not sync_result.success and sync_result.conflicts:
                # Conflicts detected - save state and prompt user
                save_sync_state(working_dir, 'pending_resolution')
                print("=" * 60)
                print("CONFLICTS WITH REMOTE")
                print("=" * 60)
                print("Remote has changes that conflict with yours.")
                print("Run: orchestrator resolve --apply")
                print("Then: orchestrator finish --continue")
                print("=" * 60)
                sys.exit(1)

            if sync_result.success:
                print(f"Pushed {sync_result.pushed_commits} commits to {sync_result.remote_branch}")

    # ... existing summary generation ...
```

### Step 4: Update isolated worktree flow
**File:** `src/cli.py:1375-1415`

After `merge_and_cleanup()` succeeds, push the merged result:

```python
if worktree_merged and worktree_merge_info:
    # Push merged result to remote
    if not args.no_push:
        sync_mgr = SyncManager(working_dir)
        if sync_mgr.get_remote_tracking_branch():
            sync_result = sync_mgr.push()
            if sync_result.success:
                worktree_merge_info['pushed'] = True
                worktree_merge_info['pushed_commits'] = sync_result.pushed_commits
```

### Step 5: Handle `--continue` flag
For interrupted syncs (conflicts requiring manual resolution):

1. Save sync state to `.orchestrator/sync_state.json`:
   ```json
   {
     "status": "pending_resolution",
     "workflow_id": "wf_xxx",
     "original_branch": "main",
     "saved_at": "2026-01-13T..."
   }
   ```

2. `finish --continue` checks for saved state and resumes:
   - Verify conflicts are resolved
   - Complete push
   - Clean up state file

### Step 6: Write tests
**File:** `tests/test_sync_manager.py`

Test cases:
1. `test_sync_no_remote` - Works when no remote configured
2. `test_sync_already_up_to_date` - No-op when in sync
3. `test_sync_local_ahead` - Push local commits
4. `test_sync_remote_ahead_no_conflicts` - Rebase and push
5. `test_sync_diverged_with_conflicts` - Detect conflicts, return error
6. `test_no_push_flag` - Skip sync entirely
7. `test_continue_after_resolution` - Resume interrupted sync
8. `test_isolated_worktree_push` - Push after merge

## Files Modified
- `src/cli.py` - Add flags, integrate sync flow
- `src/sync_manager.py` (new) - Sync logic
- `tests/test_sync_manager.py` (new) - Tests
- `CLAUDE.md` - Document new flags and behavior

## Dependencies
- Existing: `GitConflictResolver` from `src/git_conflict_resolver.py`
- Existing: `WorktreeManager` from `src/worktree_manager.py`
