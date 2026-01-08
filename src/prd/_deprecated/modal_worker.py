"""
Modal serverless worker backend.

Uses Modal (modal.com) for serverless Python execution.
Ideal for variable workloads - pay only for compute time.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from ..backends.base import WorkerBackendBase, WorkerHandle, WorkerStatus
from ..schema import JobMessage, WorkerBackend, TaskResult

logger = logging.getLogger(__name__)


class ModalBackend(WorkerBackendBase):
    """
    Modal serverless worker backend.

    Executes PRD tasks using Modal's serverless infrastructure.
    Requires MODAL_TOKEN_ID and MODAL_TOKEN_SECRET environment variables.

    Modal provides:
    - Fast cold starts (~1s)
    - Pay-per-use pricing
    - Easy scaling to 100+ concurrent workers
    - GPU support for ML workloads
    """

    def __init__(self, max_parallel: int = 50, timeout_minutes: int = 30):
        """
        Initialize the Modal backend.

        Args:
            max_parallel: Maximum concurrent workers
            timeout_minutes: Timeout for each worker
        """
        self._max_parallel = max_parallel
        self._timeout_minutes = timeout_minutes
        self._active_handles: dict[str, WorkerHandle] = {}

        # Check for Modal
        self._modal_available = self._check_modal()

    def _check_modal(self) -> bool:
        """Check if Modal is available and configured."""
        token_id = os.environ.get("MODAL_TOKEN_ID")
        token_secret = os.environ.get("MODAL_TOKEN_SECRET")

        if not token_id or not token_secret:
            return False

        # Try importing modal
        try:
            import modal  # noqa: F401
            return True
        except ImportError:
            logger.warning("Modal package not installed. Install with: pip install modal")
            return False

    def spawn(self, job: JobMessage) -> WorkerHandle:
        """Spawn a Modal function to execute the job."""
        if not self._modal_available:
            return WorkerHandle(
                worker_id=f"modal-{uuid.uuid4().hex[:8]}",
                backend=WorkerBackend.MODAL,
                job_id=job.job_id,
                status=WorkerStatus.FAILED,
                error="Modal not available. Set MODAL_TOKEN_ID and MODAL_TOKEN_SECRET, and pip install modal",
            )

        worker_id = f"modal-{uuid.uuid4().hex[:8]}"

        try:
            # Import modal here to avoid issues when not installed
            import modal

            # Create a stub for the function
            # In production, this would be a pre-defined Modal app
            # For now, we create a simple function

            # TODO: Implement actual Modal function execution
            # This requires setting up a Modal app with Claude Code installed
            # For now, return a placeholder

            handle = WorkerHandle(
                worker_id=worker_id,
                backend=WorkerBackend.MODAL,
                job_id=job.job_id,
                status=WorkerStatus.STARTING,
                metadata={"modal_stub": "prd-worker"},
            )

            self._active_handles[worker_id] = handle

            logger.info(f"Spawned Modal worker {worker_id} for job {job.job_id}")
            return handle

        except Exception as e:
            logger.error(f"Failed to spawn Modal worker: {e}")
            return WorkerHandle(
                worker_id=worker_id,
                backend=WorkerBackend.MODAL,
                job_id=job.job_id,
                status=WorkerStatus.FAILED,
                error=str(e),
            )

    def get_status(self, handle: WorkerHandle) -> WorkerStatus:
        """Get the status of a Modal worker."""
        if handle.worker_id not in self._active_handles:
            return handle.status

        # TODO: Query Modal for actual status
        return self._active_handles[handle.worker_id].status

    def get_result(self, handle: WorkerHandle) -> Optional[TaskResult]:
        """Get the result from a Modal worker."""
        if handle.worker_id not in self._active_handles:
            return handle.result

        h = self._active_handles[handle.worker_id]
        if h.status == WorkerStatus.COMPLETED:
            return h.result
        return None

    def cancel(self, handle: WorkerHandle) -> bool:
        """Cancel a Modal worker."""
        if handle.worker_id not in self._active_handles:
            return False

        # TODO: Implement Modal cancellation
        self._active_handles[handle.worker_id].status = WorkerStatus.CANCELLED
        return True

    def is_available(self) -> bool:
        """Check if Modal is available."""
        return self._modal_available

    def max_parallel(self) -> int:
        """Return max parallel workers."""
        return self._max_parallel

    def backend_type(self) -> WorkerBackend:
        """Return MODAL backend type."""
        return WorkerBackend.MODAL
