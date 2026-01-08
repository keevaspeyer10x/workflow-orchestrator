"""
Integration branch manager for PRD execution.

Manages the integration branch where agent work accumulates:
- Create/manage integration branches
- Merge agent work
- Create checkpoint PRs to main
- Track merge history for rollback
"""

import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MergeRecord:
    """Record of a merge to integration branch."""

    agent_id: str
    branch: str
    commit_sha: str
    merged_at: datetime
    task_id: str
    prd_id: str


@dataclass
class CheckpointPR:
    """Record of a checkpoint PR to main."""

    pr_number: int
    pr_url: str
    created_at: datetime
    commits_included: list[str]
    tasks_included: list[str]


class IntegrationBranchManager:
    """
    Manages the integration branch for PRD execution.

    The integration branch:
    - Is created from main at PRD start
    - Accumulates agent work as they complete
    - Creates checkpoint PRs at intervals
    - Merges to main when PRD completes
    """

    def __init__(self, working_dir: Optional[Path] = None, base_branch: str = "main"):
        """
        Initialize the integration branch manager.

        Args:
            working_dir: Git repository directory
            base_branch: Base branch (usually main)
        """
        self.working_dir = working_dir or Path.cwd()
        self.base_branch = base_branch
        self._merge_history: list[MergeRecord] = []

    def _run_git(self, *args: str) -> tuple[int, str, str]:
        """Run a git command and return (returncode, stdout, stderr)."""
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)

    def create_integration_branch(self, prd_id: str) -> str:
        """
        Create an integration branch for a PRD.

        Creates: integration/{prd_id}

        Args:
            prd_id: PRD identifier

        Returns:
            Branch name
        """
        branch_name = f"integration/{prd_id}"

        # Fetch latest from base
        self._run_git("fetch", "origin", self.base_branch)

        # Create branch from base
        code, out, err = self._run_git(
            "checkout", "-b", branch_name, f"origin/{self.base_branch}"
        )

        if code != 0:
            # Branch might already exist, try switching
            code, out, err = self._run_git("checkout", branch_name)
            if code != 0:
                raise RuntimeError(f"Failed to create/switch to {branch_name}: {err}")

        # Push to origin
        self._run_git("push", "-u", "origin", branch_name)

        logger.info(f"Created integration branch: {branch_name}")
        return branch_name

    def merge_agent_work(
        self,
        agent_branch: str,
        agent_id: str,
        task_id: str,
        prd_id: str,
    ) -> MergeRecord:
        """
        Merge an agent's work branch to the integration branch.

        Args:
            agent_branch: Agent's work branch
            agent_id: Agent identifier
            task_id: Task identifier
            prd_id: PRD identifier

        Returns:
            MergeRecord
        """
        integration_branch = f"integration/{prd_id}"

        # Switch to integration branch
        code, out, err = self._run_git("checkout", integration_branch)
        if code != 0:
            raise RuntimeError(f"Failed to checkout {integration_branch}: {err}")

        # Pull latest
        self._run_git("pull", "origin", integration_branch)

        # Merge agent branch
        code, out, err = self._run_git(
            "merge", agent_branch,
            "--no-ff",
            "-m", f"Merge {agent_branch} (task: {task_id})"
        )

        if code != 0:
            # Merge conflict - need resolution
            raise RuntimeError(f"Merge conflict merging {agent_branch}: {err}")

        # Get commit SHA
        code, commit_sha, _ = self._run_git("rev-parse", "HEAD")

        # Push
        code, out, err = self._run_git("push", "origin", integration_branch)
        if code != 0:
            raise RuntimeError(f"Failed to push: {err}")

        record = MergeRecord(
            agent_id=agent_id,
            branch=agent_branch,
            commit_sha=commit_sha,
            merged_at=datetime.now(timezone.utc),
            task_id=task_id,
            prd_id=prd_id,
        )

        self._merge_history.append(record)
        logger.info(f"Merged {agent_branch} to {integration_branch}: {commit_sha[:8]}")

        return record

    def create_checkpoint_pr(
        self,
        prd_id: str,
        description: str,
        tasks_included: list[str],
    ) -> CheckpointPR:
        """
        Create a checkpoint PR from integration branch to main.

        Args:
            prd_id: PRD identifier
            description: PR description
            tasks_included: List of completed task IDs

        Returns:
            CheckpointPR record
        """
        integration_branch = f"integration/{prd_id}"

        # Get commits since last checkpoint or branch creation
        code, commits, _ = self._run_git(
            "log", f"origin/{self.base_branch}..{integration_branch}",
            "--format=%H", "--reverse"
        )
        commit_list = commits.split("\n") if commits else []

        # Create PR using gh CLI
        title = f"[PRD Checkpoint] {prd_id}: {description}"
        body = f"""## PRD Checkpoint

**PRD:** {prd_id}
**Tasks Completed:** {len(tasks_included)}

### Tasks Included
{chr(10).join(f'- {task}' for task in tasks_included)}

### Commits
{len(commit_list)} commits from integration branch.

---
*This is an automated checkpoint PR from PRD execution.*
"""

        code, out, err = self._run_git(
            "gh", "pr", "create",
            "--base", self.base_branch,
            "--head", integration_branch,
            "--title", title,
            "--body", body,
        )

        # Note: gh is not a git command, use subprocess directly
        try:
            result = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--base", self.base_branch,
                    "--head", integration_branch,
                    "--title", title,
                    "--body", body,
                ],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise RuntimeError(f"Failed to create PR: {result.stderr}")

            pr_url = result.stdout.strip()
            # Extract PR number from URL
            pr_number = int(pr_url.split("/")[-1]) if "/" in pr_url else 0

        except Exception as e:
            logger.error(f"Failed to create checkpoint PR: {e}")
            raise

        checkpoint = CheckpointPR(
            pr_number=pr_number,
            pr_url=pr_url,
            created_at=datetime.now(timezone.utc),
            commits_included=commit_list,
            tasks_included=tasks_included,
        )

        logger.info(f"Created checkpoint PR: {pr_url}")
        return checkpoint

    def get_merge_history(self) -> list[MergeRecord]:
        """Get the merge history for this session."""
        return self._merge_history.copy()

    def get_commits_since_base(self, prd_id: str) -> list[str]:
        """Get all commits on integration branch since diverging from base."""
        integration_branch = f"integration/{prd_id}"
        code, commits, _ = self._run_git(
            "log", f"origin/{self.base_branch}..{integration_branch}",
            "--format=%H"
        )
        return commits.split("\n") if commits else []

    def get_current_sha(self, branch: str) -> str:
        """Get the current commit SHA of a branch."""
        code, sha, _ = self._run_git("rev-parse", branch)
        return sha

    def branch_exists(self, branch: str) -> bool:
        """Check if a branch exists."""
        code, _, _ = self._run_git("rev-parse", "--verify", branch)
        return code == 0

    def delete_integration_branch(self, prd_id: str, force: bool = False) -> bool:
        """
        Delete the integration branch after PRD completion.

        Args:
            prd_id: PRD identifier
            force: Force delete even if not merged

        Returns:
            True if deleted
        """
        branch_name = f"integration/{prd_id}"

        # Switch to base first
        self._run_git("checkout", self.base_branch)

        # Delete locally
        flag = "-D" if force else "-d"
        code, _, err = self._run_git("branch", flag, branch_name)

        if code != 0:
            logger.warning(f"Failed to delete local branch {branch_name}: {err}")
            return False

        # Delete remote
        code, _, err = self._run_git("push", "origin", "--delete", branch_name)
        if code != 0:
            logger.warning(f"Failed to delete remote branch {branch_name}: {err}")

        logger.info(f"Deleted integration branch: {branch_name}")
        return True
