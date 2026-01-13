"""Git worktree management for isolated workflow execution - CORE-025 Phase 4

This module provides WorktreeManager for creating, listing, and cleaning up
git worktrees that enable parallel Claude Code sessions without file conflicts.

Each isolated workflow gets its own worktree with:
    - Human-readable name (YYYYMMDD-adjective-noun-sessionid)
    - Unique branch (wf-<session-id>)
    - Copy of .env* files
    - Independent working directory
"""

import random
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Word lists for human-readable names (like Happy's worktree naming)
ADJECTIVES = [
    "brave", "calm", "eager", "fair", "gentle", "happy", "jolly", "keen",
    "lively", "merry", "noble", "proud", "quick", "rapid", "silent", "swift",
    "tender", "vivid", "warm", "zesty", "bright", "clever", "daring", "fierce"
]

NOUNS = [
    "falcon", "tiger", "eagle", "lion", "wolf", "bear", "hawk", "fox",
    "deer", "owl", "raven", "swan", "crane", "heron", "otter", "lynx",
    "puma", "cobra", "viper", "shark", "whale", "dolphin", "seal", "orca"
]


def generate_worktree_name(session_id: str) -> str:
    """Generate a human-readable worktree name.

    Format: YYYYMMDD-adjective-noun-sessionid
    This format ensures chronological ordering when sorted alphabetically.

    Args:
        session_id: 8-character session ID

    Returns:
        Human-readable name like "20260113-brave-falcon-abc12345"
    """
    date_prefix = datetime.now().strftime("%Y%m%d")
    adjective = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    return f"{date_prefix}-{adjective}-{noun}-{session_id}"


class WorktreeError(Exception):
    """Base exception for worktree operations"""
    pass


class DirtyWorkingDirectoryError(WorktreeError):
    """Raised when trying to create worktree with uncommitted changes"""
    pass


class BranchExistsError(WorktreeError):
    """Raised when worktree branch already exists"""
    pass


class MergeConflictError(WorktreeError):
    """Raised when merge has conflicts"""
    pass


class WorktreeNotFoundError(WorktreeError):
    """Raised when worktree doesn't exist"""
    pass


@dataclass
class WorktreeInfo:
    """Information about a worktree"""
    session_id: str
    path: Path
    branch: str
    name: str = ""  # Human-readable name (directory name)
    created_at: Optional[datetime] = None  # Creation time from directory name


@dataclass
class MergeResult:
    """Result of a merge operation"""
    success: bool
    merged_commits: int = 0
    message: str = ""


class WorktreeManager:
    """Manage git worktrees for isolated workflow execution"""

    def __init__(self, repo_root: Path):
        """Initialize WorktreeManager.

        Args:
            repo_root: Path to the git repository root
        """
        self.repo_root = Path(repo_root)
        self.worktrees_dir = self.repo_root / ".orchestrator" / "worktrees"

    def _run_git(self, args: List[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command.

        Args:
            args: Git command arguments (without 'git')
            cwd: Working directory (defaults to repo_root)
            check: Whether to raise on non-zero exit

        Returns:
            CompletedProcess result
        """
        cwd = cwd or self.repo_root
        return subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check
        )

    def _is_dirty(self) -> bool:
        """Check if working directory has uncommitted changes.

        Returns:
            True if there are uncommitted changes
        """
        result = self._run_git(["status", "--porcelain"])
        return bool(result.stdout.strip())

    def _get_current_branch(self) -> str:
        """Get the current branch name.

        Returns:
            Current branch name
        """
        result = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip()

    def _branch_exists(self, branch_name: str) -> bool:
        """Check if a branch exists.

        Args:
            branch_name: Branch name to check

        Returns:
            True if branch exists
        """
        result = self._run_git(["branch", "--list", branch_name], check=False)
        return bool(result.stdout.strip())

    def create(self, session_id: str) -> Path:
        """Create a new worktree for a session.

        Creates a worktree at .orchestrator/worktrees/<human-readable-name> with
        a new branch wf-<session_id>.

        The human-readable name format is: YYYYMMDD-adjective-noun-sessionid
        This ensures chronological ordering when sorted alphabetically.

        Args:
            session_id: Unique session identifier

        Returns:
            Path to the created worktree

        Raises:
            DirtyWorkingDirectoryError: If there are uncommitted changes
            BranchExistsError: If the branch already exists
        """
        # Check for uncommitted changes
        if self._is_dirty():
            raise DirtyWorkingDirectoryError(
                "Cannot create isolated worktree with uncommitted changes. "
                "Commit or stash your changes first."
            )

        branch_name = f"wf-{session_id}"
        worktree_name = generate_worktree_name(session_id)
        worktree_path = self.worktrees_dir / worktree_name

        # Check if branch already exists
        if self._branch_exists(branch_name):
            raise BranchExistsError(f"Branch '{branch_name}' already exists")

        # Create worktrees directory if needed
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)

        # Create worktree with new branch
        self._run_git([
            "worktree", "add",
            "-b", branch_name,
            str(worktree_path)
        ])

        # Copy .env* files
        self._copy_env_files(worktree_path)

        return worktree_path

    def _copy_env_files(self, worktree_path: Path) -> None:
        """Copy .env* files from repo root to worktree.

        Only copies files matching .env or .env.* pattern (not .envrc, etc.)

        Args:
            worktree_path: Path to the worktree
        """
        import re
        # Match .env or .env.something (not .envrc, .envoy, etc.)
        env_pattern = re.compile(r'^\.env(\..+)?$')

        for env_file in self.repo_root.glob(".env*"):
            if env_file.is_file() and env_pattern.match(env_file.name):
                dest = worktree_path / env_file.name
                shutil.copy2(env_file, dest)

    def _parse_worktree_name(self, name: str) -> tuple[str, Optional[datetime]]:
        """Parse a worktree directory name to extract session_id and created_at.

        Supports both formats:
        - New format: YYYYMMDD-adjective-noun-sessionid (e.g., 20260113-brave-falcon-abc12345)
        - Legacy format: just session_id (e.g., abc12345)

        Args:
            name: Directory name of the worktree

        Returns:
            Tuple of (session_id, created_at) where created_at may be None for legacy format
        """
        import re

        # Try new format: YYYYMMDD-adjective-noun-sessionid
        # Session ID can be alphanumeric (not just hex)
        new_format = re.match(r'^(\d{8})-[a-z]+-[a-z]+-(.+)$', name)
        if new_format:
            date_str = new_format.group(1)
            session_id = new_format.group(2)
            try:
                created_at = datetime.strptime(date_str, "%Y%m%d")
                return session_id, created_at
            except ValueError:
                pass

        # Legacy format: just the session_id
        return name, None

    def list(self) -> List[WorktreeInfo]:
        """List all orchestrator-managed worktrees.

        Returns:
            List of WorktreeInfo objects for each worktree, sorted by creation date (newest first)
        """
        if not self.worktrees_dir.exists():
            return []

        result = self._run_git(["worktree", "list", "--porcelain"])
        worktrees = []

        # Parse porcelain output
        current_worktree = {}
        for line in result.stdout.split("\n"):
            if line.startswith("worktree "):
                if current_worktree:
                    worktrees.append(current_worktree)
                current_worktree = {"path": line[9:]}
            elif line.startswith("branch "):
                current_worktree["branch"] = line[7:].replace("refs/heads/", "")
            elif line == "":
                if current_worktree:
                    worktrees.append(current_worktree)
                    current_worktree = {}

        # Filter to only orchestrator-managed worktrees
        managed = []
        for wt in worktrees:
            wt_path = Path(wt.get("path", ""))
            if self.worktrees_dir in wt_path.parents or wt_path.parent == self.worktrees_dir:
                dir_name = wt_path.name
                session_id, created_at = self._parse_worktree_name(dir_name)
                managed.append(WorktreeInfo(
                    session_id=session_id,
                    path=wt_path,
                    branch=wt.get("branch", ""),
                    name=dir_name,
                    created_at=created_at
                ))

        # Sort by created_at (newest first), with None values at the end
        managed.sort(key=lambda x: (x.created_at is None, x.created_at), reverse=True)

        return managed

    def _find_worktree_by_session(self, session_id: str) -> Optional[WorktreeInfo]:
        """Find a worktree by session_id.

        Searches through all managed worktrees to find one matching the session_id.
        This supports both legacy format (session_id as directory name) and new
        human-readable format (YYYYMMDD-adjective-noun-sessionid).

        Args:
            session_id: Session ID to find

        Returns:
            WorktreeInfo if found, None otherwise
        """
        for wt in self.list():
            if wt.session_id == session_id:
                return wt
        return None

    def cleanup(self, session_id: str) -> bool:
        """Remove a worktree and optionally delete its branch.

        Args:
            session_id: Session ID of the worktree to remove

        Returns:
            True if worktree was removed, False if not found
        """
        branch_name = f"wf-{session_id}"

        # Find the worktree (supports both legacy and new naming)
        wt = self._find_worktree_by_session(session_id)
        if not wt:
            # Also check legacy path directly for backward compatibility
            legacy_path = self.worktrees_dir / session_id
            if not legacy_path.exists():
                return False
            worktree_path = legacy_path
        else:
            worktree_path = wt.path

        # Remove worktree
        self._run_git(["worktree", "remove", str(worktree_path), "--force"], check=False)

        # Delete branch if it exists
        if self._branch_exists(branch_name):
            self._run_git(["branch", "-D", branch_name], check=False)

        return True

    def get_worktree_path(self, session_id: str) -> Optional[Path]:
        """Get the path to a worktree for a session.

        Args:
            session_id: Session ID

        Returns:
            Path to worktree if it exists, None otherwise
        """
        wt = self._find_worktree_by_session(session_id)
        if wt:
            return wt.path

        # Check legacy path directly for backward compatibility
        legacy_path = self.worktrees_dir / session_id
        if legacy_path.exists():
            return legacy_path

        return None

    def merge_and_cleanup(self, session_id: str, target_branch: str) -> MergeResult:
        """Merge worktree branch to target branch and cleanup.

        Args:
            session_id: Session ID of the worktree
            target_branch: Branch to merge into

        Returns:
            MergeResult with merge outcome

        Raises:
            WorktreeNotFoundError: If worktree doesn't exist
            MergeConflictError: If merge has conflicts
        """
        worktree_path = self.get_worktree_path(session_id)
        branch_name = f"wf-{session_id}"

        if not worktree_path:
            raise WorktreeNotFoundError(f"Worktree not found: {session_id}")

        # Get commit count before merge
        count_result = self._run_git([
            "rev-list", "--count",
            f"{target_branch}..{branch_name}"
        ], check=False)
        commit_count = int(count_result.stdout.strip()) if count_result.returncode == 0 else 0

        # Checkout target branch in main repo
        self._run_git(["checkout", target_branch])

        # Attempt merge
        merge_result = self._run_git([
            "merge", branch_name,
            "-m", f"Merge isolated workflow {session_id}"
        ], check=False)

        if merge_result.returncode != 0:
            # Check if it's a conflict
            if "CONFLICT" in merge_result.stdout or "conflict" in merge_result.stderr.lower():
                # Abort merge
                self._run_git(["merge", "--abort"], check=False)
                raise MergeConflictError(
                    f"Merge conflict when merging {branch_name} into {target_branch}. "
                    f"Worktree preserved at {worktree_path} for manual resolution."
                )
            # Some other error
            raise WorktreeError(f"Merge failed: {merge_result.stderr}")

        # Cleanup worktree and branch
        self.cleanup(session_id)

        return MergeResult(
            success=True,
            merged_commits=commit_count,
            message=f"Merged {commit_count} commits from {branch_name}"
        )

    def is_in_worktree(self) -> bool:
        """Check if current directory is inside a worktree.

        Returns:
            True if in a worktree (not the main working tree)
        """
        result = self._run_git(["rev-parse", "--is-inside-work-tree"], check=False)
        if result.returncode != 0:
            return False

        # Check if this is a worktree (not the main working tree)
        result = self._run_git(["rev-parse", "--git-common-dir"], check=False)
        common_dir = result.stdout.strip()

        result = self._run_git(["rev-parse", "--git-dir"], check=False)
        git_dir = result.stdout.strip()

        # If git-dir != git-common-dir, we're in a worktree
        return common_dir != git_dir

    def get_original_branch(self) -> Optional[str]:
        """Get the original branch when in a worktree.

        This reads from session metadata stored when worktree was created.

        Returns:
            Original branch name or None if not in worktree
        """
        # This would need to read from session metadata
        # For now, return None if not in worktree
        if not self.is_in_worktree():
            return None
        return None  # Needs session metadata integration
