"""
Fast-Path Merge

Handles the happy path: when branches have no conflicts,
create a PR directly without resolution steps.

This is the MVP path that handles non-conflicting agent work.
"""

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .schema import AgentManifest, DerivedManifest
from .discovery import DiscoveredBranch

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class PRInfo:
    """Information about a created pull request."""
    number: int
    url: str
    title: str
    branch: str
    base_branch: str
    created_at: datetime
    agent_ids: list[str]


@dataclass
class MergeResult:
    """Result of a merge attempt."""
    success: bool
    pr_info: Optional[PRInfo] = None
    error: Optional[str] = None
    merged_sha: Optional[str] = None


# ============================================================================
# Fast-Path Merger
# ============================================================================

class FastPathMerger:
    """
    Creates PRs for non-conflicting agent branches.

    Prerequisites:
    - Branch has no conflicts with base (checked by ConflictDetector)
    - Branch has completed work (checked by CompletionDetector)

    Uses GitHub CLI (gh) for PR creation.
    """

    def __init__(self, base_branch: str = "main"):
        self.base_branch = base_branch

    def create_pr(
        self,
        branch: DiscoveredBranch,
        manifest: Optional[AgentManifest] = None,
        derived: Optional[DerivedManifest] = None,
        draft: bool = False,
    ) -> MergeResult:
        """
        Create a pull request for a branch.

        Args:
            branch: The discovered branch to create a PR for
            manifest: Agent-provided manifest (optional)
            derived: Git-derived manifest (optional)
            draft: Whether to create as draft PR

        Returns:
            MergeResult with PR info or error
        """
        # Generate PR title and body
        title = self._generate_title(branch, manifest)
        body = self._generate_body(branch, manifest, derived)

        # Create the PR using gh CLI
        try:
            result = self._run_gh_pr_create(
                branch=branch.branch_name,
                title=title,
                body=body,
                draft=draft,
            )

            if result.returncode != 0:
                return MergeResult(
                    success=False,
                    error=f"Failed to create PR: {result.stderr}"
                )

            # Parse PR URL from output
            pr_url = result.stdout.strip()
            pr_number = self._extract_pr_number(pr_url)

            return MergeResult(
                success=True,
                pr_info=PRInfo(
                    number=pr_number,
                    url=pr_url,
                    title=title,
                    branch=branch.branch_name,
                    base_branch=self.base_branch,
                    created_at=datetime.now(timezone.utc),
                    agent_ids=[branch.agent_id],
                ),
            )

        except Exception as e:
            logger.error(f"Error creating PR: {e}")
            return MergeResult(success=False, error=str(e))

    def create_combined_pr(
        self,
        branches: list[DiscoveredBranch],
        manifests: Optional[dict[str, AgentManifest]] = None,
        draft: bool = False,
    ) -> MergeResult:
        """
        Create a PR that combines multiple non-conflicting branches.

        This merges all branches into a temporary integration branch,
        then creates a single PR from that branch.

        Args:
            branches: List of branches to combine
            manifests: Dict of agent_id -> manifest
            draft: Whether to create as draft PR

        Returns:
            MergeResult with PR info or error
        """
        if not branches:
            return MergeResult(success=False, error="No branches provided")

        if len(branches) == 1:
            return self.create_pr(branches[0], draft=draft)

        # Create integration branch name
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        integration_branch = f"integrate/{timestamp}"

        # Create and merge
        try:
            # Create integration branch from base
            subprocess.run(
                ["git", "checkout", "-b", integration_branch, self.base_branch],
                capture_output=True,
                check=True,
            )

            # Merge each branch
            merged_agents = []
            for branch in branches:
                result = subprocess.run(
                    ["git", "merge", "--no-edit", branch.branch_name],
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0:
                    # Cleanup and return error
                    subprocess.run(["git", "merge", "--abort"], capture_output=True)
                    subprocess.run(["git", "checkout", self.base_branch], capture_output=True)
                    subprocess.run(["git", "branch", "-D", integration_branch], capture_output=True)

                    return MergeResult(
                        success=False,
                        error=f"Failed to merge {branch.branch_name}: {result.stderr}"
                    )

                merged_agents.append(branch.agent_id)

            # Push integration branch
            subprocess.run(
                ["git", "push", "-u", "origin", integration_branch],
                capture_output=True,
                check=True,
            )

            # Generate combined title and body
            title = self._generate_combined_title(branches)
            body = self._generate_combined_body(branches, manifests)

            # Create PR
            result = self._run_gh_pr_create(
                branch=integration_branch,
                title=title,
                body=body,
                draft=draft,
            )

            # Get merged SHA
            merged_sha_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
            )
            merged_sha = merged_sha_result.stdout.strip()

            # Switch back to base branch
            subprocess.run(["git", "checkout", self.base_branch], capture_output=True)

            if result.returncode != 0:
                return MergeResult(
                    success=False,
                    error=f"Failed to create PR: {result.stderr}"
                )

            pr_url = result.stdout.strip()
            pr_number = self._extract_pr_number(pr_url)

            return MergeResult(
                success=True,
                merged_sha=merged_sha,
                pr_info=PRInfo(
                    number=pr_number,
                    url=pr_url,
                    title=title,
                    branch=integration_branch,
                    base_branch=self.base_branch,
                    created_at=datetime.now(timezone.utc),
                    agent_ids=merged_agents,
                ),
            )

        except Exception as e:
            # Cleanup on error
            subprocess.run(["git", "checkout", self.base_branch], capture_output=True)
            subprocess.run(["git", "branch", "-D", integration_branch], capture_output=True)
            logger.error(f"Error creating combined PR: {e}")
            return MergeResult(success=False, error=str(e))

    def _run_gh_pr_create(
        self,
        branch: str,
        title: str,
        body: str,
        draft: bool = False,
    ) -> subprocess.CompletedProcess:
        """Run gh pr create command."""
        cmd = [
            "gh", "pr", "create",
            "--base", self.base_branch,
            "--head", branch,
            "--title", title,
            "--body", body,
        ]

        if draft:
            cmd.append("--draft")

        return subprocess.run(cmd, capture_output=True, text=True)

    def _generate_title(
        self,
        branch: DiscoveredBranch,
        manifest: Optional[AgentManifest] = None,
    ) -> str:
        """Generate PR title from branch/manifest info."""
        if manifest and manifest.task.description:
            return manifest.task.description

        # Extract from branch name: claude/add-feature-abc123 -> Add feature
        branch_suffix = branch.branch_name.split("/", 1)[-1]
        # Remove session ID suffix
        parts = branch_suffix.rsplit("-", 1)
        if len(parts) == 2 and len(parts[1]) <= 10:
            branch_suffix = parts[0]

        # Convert kebab-case to title case
        title = branch_suffix.replace("-", " ").replace("_", " ").title()
        return f"[Agent] {title}"

    def _generate_body(
        self,
        branch: DiscoveredBranch,
        manifest: Optional[AgentManifest] = None,
        derived: Optional[DerivedManifest] = None,
    ) -> str:
        """Generate PR body with agent work details."""
        lines = ["## Agent Work Summary\n"]

        # Agent info
        lines.append(f"**Agent ID:** `{branch.agent_id}`")
        lines.append(f"**Branch:** `{branch.branch_name}`")
        lines.append(f"**Commits:** {branch.commit_count}")
        lines.append("")

        # Task description
        if manifest and manifest.task.description:
            lines.append("### Task")
            lines.append(manifest.task.description)
            lines.append("")

        # Files changed
        files_changed = []
        if derived:
            files_changed = derived.all_files_touched
        elif manifest:
            files_changed = manifest.all_files_touched

        if files_changed:
            lines.append("### Files Changed")
            for f in files_changed[:20]:  # Limit to 20 files
                lines.append(f"- `{f}`")
            if len(files_changed) > 20:
                lines.append(f"- ... and {len(files_changed) - 20} more")
            lines.append("")

        # Risk flags
        if manifest and manifest.risk_flags:
            lines.append("### Risk Flags")
            for flag in manifest.risk_flags:
                lines.append(f"- {flag.value}")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append("*Created by Multi-Agent Coordinator*")

        return "\n".join(lines)

    def _generate_combined_title(self, branches: list[DiscoveredBranch]) -> str:
        """Generate title for combined PR."""
        count = len(branches)
        return f"[Integration] Combine {count} agent branches"

    def _generate_combined_body(
        self,
        branches: list[DiscoveredBranch],
        manifests: Optional[dict[str, AgentManifest]] = None,
    ) -> str:
        """Generate body for combined PR."""
        lines = ["## Combined Agent Work\n"]
        lines.append(f"This PR combines work from {len(branches)} agent branches.\n")

        lines.append("### Included Branches")
        for branch in branches:
            manifest = manifests.get(branch.agent_id) if manifests else None
            desc = manifest.task.description if manifest else "No description"
            lines.append(f"- `{branch.branch_name}`: {desc}")

        lines.append("")
        lines.append("### Agent IDs")
        for branch in branches:
            lines.append(f"- `{branch.agent_id}`")

        lines.append("")
        lines.append("---")
        lines.append("*Created by Multi-Agent Coordinator*")

        return "\n".join(lines)

    def _extract_pr_number(self, pr_url: str) -> int:
        """Extract PR number from URL."""
        try:
            return int(pr_url.rstrip("/").split("/")[-1])
        except (ValueError, IndexError):
            return 0


# ============================================================================
# Convenience Functions
# ============================================================================

def create_fast_path_pr(
    branch: DiscoveredBranch,
    manifest: Optional[AgentManifest] = None,
    base_branch: str = "main",
    draft: bool = False,
) -> MergeResult:
    """
    Convenience function to create a PR for a non-conflicting branch.

    Args:
        branch: The branch to create a PR for
        manifest: Optional agent manifest
        base_branch: The target branch (default: main)
        draft: Whether to create as draft PR

    Returns:
        MergeResult with PR info or error
    """
    merger = FastPathMerger(base_branch=base_branch)
    return merger.create_pr(branch, manifest=manifest, draft=draft)
