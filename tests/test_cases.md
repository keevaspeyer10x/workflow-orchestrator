# CORE-025 Phase 4: Test Cases

## Unit Tests: WorktreeManager

### test_worktree_manager.py

#### Test: create_worktree_success
- Setup: Clean git repo with no uncommitted changes
- Action: Call `manager.create(session_id="abc12345")`
- Assert:
  - Worktree directory exists at `.orchestrator/worktrees/abc12345`
  - Branch `wf-abc12345` exists
  - Worktree is registered in `git worktree list`

#### Test: create_worktree_copies_env_files
- Setup: Create `.env` and `.env.local` in repo root
- Action: Call `manager.create(session_id="abc12345")`
- Assert:
  - `.env` copied to worktree
  - `.env.local` copied to worktree
  - Other files not copied (e.g., `.envrc`)

#### Test: create_worktree_fails_on_dirty_repo
- Setup: Git repo with uncommitted changes
- Action: Call `manager.create(session_id="abc12345")`
- Assert:
  - Raises `DirtyWorkingDirectoryError`
  - No worktree created
  - No branch created

#### Test: list_worktrees_empty
- Setup: Clean git repo with no worktrees
- Action: Call `manager.list()`
- Assert: Returns empty list

#### Test: list_worktrees_with_entries
- Setup: Create 2 worktrees
- Action: Call `manager.list()`
- Assert:
  - Returns list with 2 WorktreeInfo objects
  - Each has session_id, path, branch

#### Test: cleanup_worktree_success
- Setup: Create worktree
- Action: Call `manager.cleanup(session_id="abc12345")`
- Assert:
  - Worktree directory removed
  - Branch deleted (if merged)
  - Returns True

#### Test: cleanup_worktree_not_found
- Setup: No worktree exists
- Action: Call `manager.cleanup(session_id="nonexistent")`
- Assert: Returns False

#### Test: merge_and_cleanup_success
- Setup: Create worktree, make commits
- Action: Call `manager.merge_and_cleanup(session_id, target_branch)`
- Assert:
  - Changes merged to target branch
  - Worktree removed
  - Worktree branch deleted

#### Test: merge_and_cleanup_conflict
- Setup: Create worktree, make conflicting changes on both branches
- Action: Call `manager.merge_and_cleanup(session_id, target_branch)`
- Assert:
  - Raises `MergeConflictError`
  - Worktree NOT removed (for manual resolution)
  - Error message includes resolution steps

## Integration Tests: CLI

### test_cli_isolated.py

#### Test: start_isolated_creates_worktree
- Action: `orchestrator start "Test task" --isolated`
- Assert:
  - Session created
  - Worktree created
  - Output includes worktree path

#### Test: start_isolated_fails_on_dirty
- Setup: Uncommitted changes
- Action: `orchestrator start "Test task" --isolated`
- Assert:
  - Exit code 1
  - Error message about uncommitted changes
  - No session created

#### Test: finish_isolated_merges_changes
- Setup: Create isolated workflow, make changes, commit
- Action: `orchestrator finish`
- Assert:
  - Changes merged to original branch
  - Worktree cleaned up
  - Success message

#### Test: doctor_shows_worktree_status
- Setup: Create isolated workflow
- Action: `orchestrator doctor`
- Assert:
  - Output shows worktree status
  - Shows session ID and path

#### Test: doctor_cleanup_removes_orphans
- Setup: Create worktree manually (no session)
- Action: `orchestrator doctor --cleanup`
- Assert:
  - Orphaned worktree removed
  - Success message

## Edge Cases

#### Test: git_version_check
- Setup: Mock git version to 2.4
- Action: Try to create worktree
- Assert: Clear error about git version requirement

#### Test: branch_name_collision
- Setup: Branch `wf-abc12345` already exists
- Action: Try to create worktree with session_id `abc12345`
- Assert: Error or use alternative name

#### Test: nested_worktree_detection
- Setup: Run orchestrator from within a worktree
- Action: `orchestrator start --isolated`
- Assert: Error about nested worktrees not supported
