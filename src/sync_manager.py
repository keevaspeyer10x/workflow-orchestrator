"""
Sync Manager - CORE-031

Handles synchronization with remote repository:
- Fetch from remote
- Check for divergence
- Attempt rebase if needed
- Push to remote

Philosophy:
- Never force push
- Prefer rebase over merge for cleaner history
- Fail gracefully if conflicts detected
"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DivergenceInfo:
    """Information about local/remote divergence."""
    diverged: bool
    local_ahead: int
    remote_ahead: int
    remote_branch: str


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    pushed_commits: int
    message: str
    conflicts: list[str] = field(default_factory=list)


class SyncManager:
    """
    Manages synchronization with remote repository.

    Usage:
        sync_mgr = SyncManager(repo_path)
        result = sync_mgr.sync()
        if result.success:
            print(f"Pushed {result.pushed_commits} commits")
        else:
            print(f"Sync failed: {result.message}")
    """

    def __init__(self, repo_path: Path):
        """
        Initialize the sync manager.

        Args:
            repo_path: Path to git repository
        """
        self.repo_path = Path(repo_path)

    def _run_git(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command."""
        result = subprocess.run(
            ["git"] + args,
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, ["git"] + args, result.stdout, result.stderr
            )
        return result

    def get_remote_tracking_branch(self) -> Optional[str]:
        """
        Get the upstream branch for the current branch.

        Returns:
            Remote tracking branch (e.g., 'origin/main') or None if not configured
        """
        result = self._run_git(
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            check=False
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def get_current_branch(self) -> Optional[str]:
        """Get the current branch name."""
        result = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], check=False)
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def fetch(self) -> bool:
        """
        Fetch from remote.

        Returns:
            True if fetch succeeded, False otherwise
        """
        upstream = self.get_remote_tracking_branch()
        if not upstream:
            return False

        # Extract remote name from upstream (e.g., 'origin/main' -> 'origin')
        remote = upstream.split('/')[0]

        result = self._run_git(["fetch", remote], check=False)
        return result.returncode == 0

    def check_divergence(self) -> DivergenceInfo:
        """
        Check if local and remote have diverged.

        Returns:
            DivergenceInfo with divergence details
        """
        upstream = self.get_remote_tracking_branch()
        if not upstream:
            return DivergenceInfo(
                diverged=False,
                local_ahead=0,
                remote_ahead=0,
                remote_branch=""
            )

        # Count commits local is ahead
        result = self._run_git(
            ["rev-list", "--count", f"{upstream}..HEAD"],
            check=False
        )
        local_ahead = int(result.stdout.strip()) if result.returncode == 0 else 0

        # Count commits remote is ahead
        result = self._run_git(
            ["rev-list", "--count", f"HEAD..{upstream}"],
            check=False
        )
        remote_ahead = int(result.stdout.strip()) if result.returncode == 0 else 0

        # Diverged if remote is ahead (even if local is also ahead)
        diverged = remote_ahead > 0

        return DivergenceInfo(
            diverged=diverged,
            local_ahead=local_ahead,
            remote_ahead=remote_ahead,
            remote_branch=upstream
        )

    def attempt_rebase(self) -> bool:
        """
        Attempt to rebase onto upstream branch.

        Returns:
            True if rebase succeeded, False if there were conflicts
        """
        upstream = self.get_remote_tracking_branch()
        if not upstream:
            return False

        result = self._run_git(["rebase", upstream], check=False)

        if result.returncode != 0:
            # Abort the rebase to leave repo in clean state
            self._run_git(["rebase", "--abort"], check=False)
            return False

        return True

    def push(self) -> SyncResult:
        """
        Push to remote tracking branch.

        Returns:
            SyncResult with push outcome
        """
        upstream = self.get_remote_tracking_branch()
        if not upstream:
            return SyncResult(
                success=False,
                pushed_commits=0,
                message="No upstream branch configured"
            )

        # Check how many commits to push
        result = self._run_git(
            ["rev-list", "--count", f"{upstream}..HEAD"],
            check=False
        )
        commits_to_push = int(result.stdout.strip()) if result.returncode == 0 else 0

        if commits_to_push == 0:
            return SyncResult(
                success=True,
                pushed_commits=0,
                message="Already up to date"
            )

        # Attempt push (never force)
        result = self._run_git(["push"], check=False)

        if result.returncode != 0:
            # Check if it was rejected due to non-fast-forward
            stderr_lower = result.stderr.lower()
            if "rejected" in stderr_lower or "non-fast-forward" in stderr_lower:
                return SyncResult(
                    success=False,
                    pushed_commits=0,
                    message="Push rejected: non-fast-forward (remote has diverged)"
                )
            return SyncResult(
                success=False,
                pushed_commits=0,
                message=f"Push failed: {result.stderr.strip()}"
            )

        return SyncResult(
            success=True,
            pushed_commits=commits_to_push,
            message=f"Pushed {commits_to_push} commit(s) to {upstream}"
        )

    def sync(self) -> SyncResult:
        """
        Full sync: fetch, handle divergence, push.

        Returns:
            SyncResult with sync outcome
        """
        upstream = self.get_remote_tracking_branch()
        if not upstream:
            return SyncResult(
                success=True,
                pushed_commits=0,
                message="No upstream branch - skipping sync"
            )

        # Fetch latest from remote
        if not self.fetch():
            return SyncResult(
                success=False,
                pushed_commits=0,
                message="Failed to fetch from remote"
            )

        # Check divergence
        info = self.check_divergence()

        # If remote is ahead, try to rebase
        if info.remote_ahead > 0:
            if not self.attempt_rebase():
                return SyncResult(
                    success=False,
                    pushed_commits=0,
                    message="Rebase failed due to conflicts. Run 'orchestrator resolve' then 'orchestrator finish --continue'",
                    conflicts=["<check with git status>"]
                )

        # Push
        return self.push()
