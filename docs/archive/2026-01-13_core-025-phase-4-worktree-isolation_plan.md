# CORE-025 Phase 4: Git Worktree Isolation MVP

## Implementation Plan

### Overview
Add git worktree isolation to enable truly parallel Claude Code sessions. Each `orchestrator start --isolated` creates a new worktree with its own branch, allowing multiple workflows to run simultaneously without file conflicts.

### User Decisions
- **Merge on finish**: Auto-merge worktree changes back to original branch
- **Dirty state**: Error and refuse if uncommitted changes present

### Implementation Steps

#### Step 1: Create WorktreeManager Class
**File**: `src/worktree_manager.py`

```python
class WorktreeManager:
    """Manage git worktrees for isolated workflow execution"""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.worktrees_dir = repo_root / ".orchestrator" / "worktrees"

    def create(self, session_id: str, branch_name: str) -> Path:
        """Create new worktree for session"""
        # 1. Check for uncommitted changes (error if dirty)
        # 2. Create worktree branch from current HEAD
        # 3. Create worktree at .orchestrator/worktrees/<session_id>
        # 4. Copy .env* files to worktree
        # 5. Return worktree path

    def list(self) -> List[WorktreeInfo]:
        """List all orchestrator-managed worktrees"""
        # Parse `git worktree list --porcelain`

    def cleanup(self, session_id: str) -> bool:
        """Remove worktree and optionally delete branch"""
        # 1. git worktree remove <path>
        # 2. Delete branch if merged

    def get_worktree_path(self, session_id: str) -> Optional[Path]:
        """Get worktree path for session"""

    def merge_and_cleanup(self, session_id: str, target_branch: str) -> MergeResult:
        """Merge worktree branch to target and cleanup"""
        # 1. Checkout target branch in main repo
        # 2. git merge <worktree-branch>
        # 3. Cleanup worktree
        # 4. Delete worktree branch
```

#### Step 2: Modify cmd_start with --isolated Flag
**File**: `src/cli.py` (cmd_start function)

Changes:
- Add `--isolated` flag to argument parser
- When flag is set:
  1. Create WorktreeManager
  2. Check for uncommitted changes (error if dirty)
  3. Create worktree for session
  4. Print worktree path (user cds manually or opens new terminal)
  5. Store original branch in session metadata

#### Step 3: Modify cmd_finish for Worktree Merge
**File**: `src/cli.py` (cmd_finish function)

Changes:
- Detect if current session is in a worktree
- On finish (not abandon):
  1. Get original branch from session metadata
  2. Merge worktree branch to original branch
  3. Cleanup worktree
  4. Print success message with merge info

#### Step 4: Add orchestrator doctor Command
**File**: `src/cli.py` (new cmd_doctor function)

Features:
- `orchestrator doctor` - Show worktree health status
- `orchestrator doctor --cleanup` - Remove orphaned worktrees
- `orchestrator doctor --fix` - Attempt automatic repairs

Doctor checks:
- Orphaned worktrees (no matching session)
- Sessions with missing worktrees
- Stale worktree branches
- Unmerged changes in worktrees

#### Step 5: Update Session Metadata
**File**: `src/session_manager.py`

Add to session meta.json:
```json
{
  "session_id": "abc12345",
  "isolated": true,
  "worktree_path": "/path/to/.orchestrator/worktrees/abc12345",
  "original_branch": "main",
  "worktree_branch": "wf-abc12345"
}
```

#### Step 6: Document Port Conflict Strategy
**File**: `CLAUDE.md` (update)

Add documentation for:
- Running parallel sessions with different ports
- Environment variable overrides per worktree
- Common port conflict scenarios

### File Changes Summary

| File | Change |
|------|--------|
| `src/worktree_manager.py` | NEW - WorktreeManager class |
| `src/cli.py` | Modify cmd_start, cmd_finish, add cmd_doctor |
| `src/session_manager.py` | Add worktree metadata support |
| `tests/test_worktree_manager.py` | NEW - Unit tests |
| `tests/test_cli_isolated.py` | NEW - Integration tests |
| `CLAUDE.md` | Add worktree documentation |

### Dependencies
- Git (worktree support - requires git 2.5+)
- No new Python dependencies

### Not In MVP (Deferred)
- Human-readable worktree naming (task-slug-sessionid)
- Auto-cleanup timers
- Max concurrent worktrees limit
- Pre-warmed worktree templates
- Symlinked node_modules/venv
