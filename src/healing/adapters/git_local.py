"""Local git CLI adapter."""

import asyncio
import subprocess
from pathlib import Path
from typing import Optional

from .base import GitAdapter


class GitBranchExistsError(Exception):
    """Raised when trying to create a branch that already exists."""


class GitMergeConflictError(Exception):
    """Raised when a merge results in conflicts."""


class LocalGitAdapter(GitAdapter):
    """Git CLI implementation of GitAdapter."""

    def __init__(self, repo_path: Optional[Path] = None):
        """Initialize local git adapter.

        Args:
            repo_path: Path to git repository. Defaults to cwd.
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()

    async def _run_git(self, *args: str) -> tuple[int, str, str]:
        """Run a git command.

        Returns:
            Tuple of (exit_code, stdout, stderr).
        """
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=self.repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode(), stderr.decode()

    async def create_branch(self, name: str, base: str = "HEAD") -> None:
        """Create a new branch using git CLI."""
        # Check if branch exists
        exit_code, stdout, _ = await self._run_git("branch", "--list", name)
        if name in stdout:
            raise GitBranchExistsError(f"Branch '{name}' already exists")

        exit_code, stdout, stderr = await self._run_git("checkout", "-b", name, base)
        if exit_code != 0:
            raise RuntimeError(f"Failed to create branch: {stderr}")

    async def apply_diff(self, diff: str, message: str) -> str:
        """Apply changes and commit using git CLI."""
        # Stage all changes
        await self._run_git("add", "-A")

        # Commit
        exit_code, stdout, stderr = await self._run_git("commit", "-m", message)
        if exit_code != 0:
            # Check if nothing to commit
            if "nothing to commit" in stderr or "nothing to commit" in stdout:
                # Return current HEAD
                _, sha, _ = await self._run_git("rev-parse", "HEAD")
                return sha.strip()
            raise RuntimeError(f"Failed to commit: {stderr}")

        # Get commit SHA
        _, sha, _ = await self._run_git("rev-parse", "HEAD")
        return sha.strip()

    async def create_pr(
        self, title: str, body: str, head: str, base: str
    ) -> str:
        """Create PR - not applicable for local git, raises NotImplementedError."""
        raise NotImplementedError(
            "create_pr is not supported in local git adapter. "
            "Use GitHubAPIAdapter for PR creation."
        )

    async def merge_branch(self, branch: str, into: str) -> None:
        """Merge branch using git CLI."""
        # First, make sure we're on the target branch
        if into != "HEAD":
            exit_code, _, stderr = await self._run_git("checkout", into)
            if exit_code != 0:
                raise RuntimeError(f"Failed to checkout {into}: {stderr}")

        exit_code, stdout, stderr = await self._run_git("merge", branch)
        if exit_code != 0:
            if "CONFLICT" in stdout or "CONFLICT" in stderr:
                raise GitMergeConflictError(f"Merge conflict: {stderr}")
            raise RuntimeError(f"Failed to merge: {stderr}")

    async def delete_branch(self, name: str) -> None:
        """Delete branch using git CLI."""
        exit_code, stdout, stderr = await self._run_git("branch", "-d", name)
        if exit_code != 0:
            # Try force delete
            exit_code, stdout, stderr = await self._run_git("branch", "-D", name)
            if exit_code != 0:
                raise RuntimeError(f"Failed to delete branch: {stderr}")

    async def get_recent_commits(self, count: int = 10) -> list[dict]:
        """Get recent commits using git CLI."""
        exit_code, stdout, stderr = await self._run_git(
            "log",
            f"-{count}",
            "--format=%H|%s|%an|%aI",
        )
        if exit_code != 0:
            raise RuntimeError(f"Failed to get commits: {stderr}")

        commits = []
        for line in stdout.strip().split("\n"):
            if line:
                parts = line.split("|")
                if len(parts) >= 4:
                    commits.append({
                        "sha": parts[0],
                        "message": parts[1],
                        "author": parts[2],
                        "date": parts[3],
                    })
        return commits
