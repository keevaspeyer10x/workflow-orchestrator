"""
GitHub Actions worker backend.

Uses GitHub Actions for CI/CD integrated execution.
Good when you want PRD execution tied to your CI pipeline.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from ..backends.base import WorkerBackendBase, WorkerHandle, WorkerStatus
from ..schema import JobMessage, WorkerBackend, TaskResult

logger = logging.getLogger(__name__)


class GitHubActionsBackend(WorkerBackendBase):
    """
    GitHub Actions worker backend.

    Executes PRD tasks using GitHub Actions workflows.
    Uses workflow_dispatch to trigger jobs.

    GitHub Actions provides:
    - Free tier (2000 minutes/month)
    - Good CI/CD integration
    - Access to repo context
    - Parallel job execution
    """

    def __init__(
        self,
        max_parallel: int = 10,
        timeout_minutes: int = 30,
        workflow_file: str = ".github/workflows/prd-worker.yml",
    ):
        """
        Initialize the GitHub Actions backend.

        Args:
            max_parallel: Maximum concurrent workers (GitHub's limit)
            timeout_minutes: Timeout for each worker
            workflow_file: Path to the workflow file
        """
        self._max_parallel = max_parallel
        self._timeout_minutes = timeout_minutes
        self._workflow_file = workflow_file
        self._active_handles: dict[str, WorkerHandle] = {}

        # Check if we're in a GitHub repo with Actions enabled
        self._gh_available = self._check_github_actions()

    def _check_github_actions(self) -> bool:
        """Check if GitHub Actions is available."""
        # Check if we're running in GitHub Actions
        if os.environ.get("GITHUB_ACTIONS"):
            return True

        # Check if gh CLI is available and authenticated
        try:
            import subprocess
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def spawn(self, job: JobMessage) -> WorkerHandle:
        """Trigger a GitHub Actions workflow for the job."""
        worker_id = f"gha-{uuid.uuid4().hex[:8]}"

        if not self._gh_available:
            return WorkerHandle(
                worker_id=worker_id,
                backend=WorkerBackend.GITHUB_ACTIONS,
                job_id=job.job_id,
                status=WorkerStatus.FAILED,
                error="GitHub Actions not available. Authenticate with: gh auth login",
            )

        try:
            # TODO: Use gh CLI to trigger workflow_dispatch
            # gh workflow run prd-worker.yml -f task_id=X -f prompt="..."

            handle = WorkerHandle(
                worker_id=worker_id,
                backend=WorkerBackend.GITHUB_ACTIONS,
                job_id=job.job_id,
                status=WorkerStatus.STARTING,
                metadata={"workflow": self._workflow_file},
            )

            self._active_handles[worker_id] = handle

            logger.info(f"Triggered GitHub Actions workflow {worker_id} for job {job.job_id}")
            return handle

        except Exception as e:
            logger.error(f"Failed to trigger GitHub Actions workflow: {e}")
            return WorkerHandle(
                worker_id=worker_id,
                backend=WorkerBackend.GITHUB_ACTIONS,
                job_id=job.job_id,
                status=WorkerStatus.FAILED,
                error=str(e),
            )

    def get_status(self, handle: WorkerHandle) -> WorkerStatus:
        """Get the status of a GitHub Actions run."""
        if handle.worker_id not in self._active_handles:
            return handle.status

        # TODO: Query GitHub API for workflow run status
        return self._active_handles[handle.worker_id].status

    def get_result(self, handle: WorkerHandle) -> Optional[TaskResult]:
        """Get the result from a GitHub Actions run."""
        if handle.worker_id not in self._active_handles:
            return handle.result

        h = self._active_handles[handle.worker_id]
        if h.status == WorkerStatus.COMPLETED:
            return h.result
        return None

    def cancel(self, handle: WorkerHandle) -> bool:
        """Cancel a GitHub Actions run."""
        if handle.worker_id not in self._active_handles:
            return False

        # TODO: Use gh CLI to cancel the workflow run
        self._active_handles[handle.worker_id].status = WorkerStatus.CANCELLED
        return True

    def is_available(self) -> bool:
        """Check if GitHub Actions is available."""
        return self._gh_available

    def max_parallel(self) -> int:
        """Return max parallel workers."""
        return self._max_parallel

    def backend_type(self) -> WorkerBackend:
        """Return GITHUB_ACTIONS backend type."""
        return WorkerBackend.GITHUB_ACTIONS
