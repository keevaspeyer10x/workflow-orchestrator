"""
Agent Discovery

Finds agent branches (claude/*) in the repository and extracts
basic information about each agent's work.

Branch naming convention:
    claude/{task-slug}-{session-id}
    Examples:
    - claude/add-authentication-abc123
    - claude/fix-login-bug-def456
    - claude/refactor-api-ghi789
"""

import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .schema import (
    AgentInfo,
    AgentType,
    AgentStatus,
    GitInfo,
    DerivedManifest,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class DiscoveredBranch:
    """A discovered agent branch with basic info."""
    branch_name: str
    agent_id: str
    session_id: str
    base_sha: str
    head_sha: str
    last_commit_time: datetime
    commit_count: int
    is_ahead_of_base: bool


# ============================================================================
# Agent Discovery
# ============================================================================

class AgentDiscovery:
    """
    Discovers agent branches in the repository.

    Looks for branches matching the pattern:
    - claude/*
    - agent/*
    - Optional custom patterns
    """

    DEFAULT_PATTERNS = [
        r"^claude/.*",
        r"^agent/.*",
    ]

    def __init__(
        self,
        base_branch: str = "main",
        patterns: Optional[list[str]] = None,
        remote: str = "origin"
    ):
        self.base_branch = base_branch
        self.patterns = patterns or self.DEFAULT_PATTERNS
        self.remote = remote
        self._compiled_patterns = [re.compile(p) for p in self.patterns]

    def discover_branches(self, include_remote: bool = True) -> list[DiscoveredBranch]:
        """
        Find all agent branches.

        Args:
            include_remote: Whether to include remote branches

        Returns:
            List of discovered branches with metadata
        """
        branches = []

        # Get local branches
        local_branches = self._get_local_branches()
        for branch in local_branches:
            if self._matches_pattern(branch):
                try:
                    info = self._get_branch_info(branch, is_remote=False)
                    if info:
                        branches.append(info)
                except Exception as e:
                    logger.warning(f"Failed to get info for local branch {branch}: {e}")

        # Get remote branches
        if include_remote:
            remote_branches = self._get_remote_branches()
            for branch in remote_branches:
                # Strip remote prefix for pattern matching
                short_name = branch.replace(f"{self.remote}/", "")
                if self._matches_pattern(short_name):
                    # Skip if we already have this as a local branch
                    if short_name in [b.branch_name for b in branches]:
                        continue
                    try:
                        info = self._get_branch_info(branch, is_remote=True)
                        if info:
                            branches.append(info)
                    except Exception as e:
                        logger.warning(f"Failed to get info for remote branch {branch}: {e}")

        logger.info(f"Discovered {len(branches)} agent branches")
        return branches

    def _matches_pattern(self, branch_name: str) -> bool:
        """Check if branch name matches any agent pattern."""
        return any(p.match(branch_name) for p in self._compiled_patterns)

    def _get_local_branches(self) -> list[str]:
        """Get list of local branch names."""
        result = subprocess.run(
            ["git", "branch", "--format=%(refname:short)"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.error(f"Failed to list local branches: {result.stderr}")
            return []
        return [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]

    def _get_remote_branches(self) -> list[str]:
        """Get list of remote branch names."""
        # Fetch first to ensure we have latest
        subprocess.run(
            ["git", "fetch", self.remote, "--prune"],
            capture_output=True
        )

        result = subprocess.run(
            ["git", "branch", "-r", "--format=%(refname:short)"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.error(f"Failed to list remote branches: {result.stderr}")
            return []
        return [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]

    def _get_branch_info(self, branch: str, is_remote: bool) -> Optional[DiscoveredBranch]:
        """Get detailed info about a branch."""
        # Get the short name (without remote prefix)
        short_name = branch.replace(f"{self.remote}/", "") if is_remote else branch

        # Extract session ID from branch name (last segment after final dash)
        parts = short_name.split("/", 1)
        if len(parts) < 2:
            return None

        branch_suffix = parts[1]  # e.g., "add-auth-abc123"
        # Session ID is typically the last segment
        session_match = re.search(r"-([a-zA-Z0-9]+)$", branch_suffix)
        session_id = session_match.group(1) if session_match else branch_suffix[:8]

        # Generate agent ID
        agent_id = f"claude-{session_id}"

        # Get base SHA (merge-base with main)
        base_sha = self._get_merge_base(branch)
        if not base_sha:
            return None

        # Get head SHA
        head_sha = self._get_head_sha(branch)
        if not head_sha:
            return None

        # Get last commit time
        last_commit_time = self._get_last_commit_time(branch)

        # Get commit count ahead of base
        commit_count = self._get_commits_ahead(branch, base_sha)

        return DiscoveredBranch(
            branch_name=short_name,
            agent_id=agent_id,
            session_id=session_id,
            base_sha=base_sha,
            head_sha=head_sha,
            last_commit_time=last_commit_time,
            commit_count=commit_count,
            is_ahead_of_base=commit_count > 0,
        )

    def _get_merge_base(self, branch: str) -> Optional[str]:
        """Get the merge base between branch and base branch."""
        result = subprocess.run(
            ["git", "merge-base", self.base_branch, branch],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def _get_head_sha(self, branch: str) -> Optional[str]:
        """Get the HEAD SHA of a branch."""
        result = subprocess.run(
            ["git", "rev-parse", branch],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def _get_last_commit_time(self, branch: str) -> datetime:
        """Get the timestamp of the last commit on a branch."""
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", branch],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return datetime.now(timezone.utc)

        try:
            return datetime.fromisoformat(result.stdout.strip())
        except ValueError:
            return datetime.now(timezone.utc)

    def _get_commits_ahead(self, branch: str, base_sha: str) -> int:
        """Count commits on branch ahead of base."""
        result = subprocess.run(
            ["git", "rev-list", "--count", f"{base_sha}..{branch}"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return 0
        try:
            return int(result.stdout.strip())
        except ValueError:
            return 0

    def derive_manifest(self, branch: DiscoveredBranch) -> DerivedManifest:
        """
        Derive a manifest from actual git diff.

        CRITICAL: Don't trust agent-provided manifest blindly.
        Always derive actual changes from git diff.
        """
        # Get files changed
        files_modified, files_added, files_deleted = self._get_changed_files(
            branch.base_sha,
            branch.head_sha
        )

        return DerivedManifest(
            agent_id=branch.agent_id,
            branch=branch.branch_name,
            base_sha=branch.base_sha,
            head_sha=branch.head_sha,
            files_modified=files_modified,
            files_added=files_added,
            files_deleted=files_deleted,
        )

    def _get_changed_files(
        self,
        base_sha: str,
        head_sha: str
    ) -> tuple[list[str], list[str], list[str]]:
        """Get lists of modified, added, and deleted files."""
        result = subprocess.run(
            ["git", "diff", "--name-status", base_sha, head_sha],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return [], [], []

        modified = []
        added = []
        deleted = []

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue

            status, file_path = parts
            if status.startswith("M"):
                modified.append(file_path)
            elif status.startswith("A"):
                added.append(file_path)
            elif status.startswith("D"):
                deleted.append(file_path)
            elif status.startswith("R"):
                # Rename: old -> new
                if "\t" in file_path:
                    old, new = file_path.split("\t")
                    deleted.append(old)
                    added.append(new)
                else:
                    modified.append(file_path)

        return modified, added, deleted


# ============================================================================
# Convenience Functions
# ============================================================================

def discover_agent_branches(
    base_branch: str = "main",
    include_remote: bool = True
) -> list[DiscoveredBranch]:
    """
    Convenience function to discover agent branches.

    Returns list of DiscoveredBranch objects with metadata.
    """
    discovery = AgentDiscovery(base_branch=base_branch)
    return discovery.discover_branches(include_remote=include_remote)
