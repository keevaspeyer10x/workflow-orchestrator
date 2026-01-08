"""
Base interface for worker backends.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any

from ..schema import JobMessage, WorkerBackend, TaskResult


class WorkerStatus(str, Enum):
    """Status of a worker."""

    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkerHandle:
    """Handle to a running worker."""

    worker_id: str
    backend: WorkerBackend
    job_id: Optional[str] = None
    status: WorkerStatus = WorkerStatus.STARTING
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    result: Optional[TaskResult] = None
    error: Optional[str] = None

    # For manual backend
    manual_instructions: Optional[str] = None

    # Backend-specific metadata
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkerBackendBase(ABC):
    """
    Abstract base class for worker backends.

    Each backend implementation must provide methods to:
    - spawn: Start a worker for a job
    - get_status: Check worker status
    - get_result: Get the result when complete
    - cancel: Cancel a running worker
    - is_available: Check if backend can be used
    - max_parallel: Maximum concurrent workers
    """

    @abstractmethod
    def spawn(self, job: JobMessage) -> WorkerHandle:
        """
        Spawn a worker to execute a job.

        Args:
            job: The job to execute

        Returns:
            Handle to the spawned worker
        """
        pass

    @abstractmethod
    def get_status(self, handle: WorkerHandle) -> WorkerStatus:
        """
        Get the current status of a worker.

        Args:
            handle: Handle to the worker

        Returns:
            Current status
        """
        pass

    @abstractmethod
    def get_result(self, handle: WorkerHandle) -> Optional[TaskResult]:
        """
        Get the result of a completed worker.

        Args:
            handle: Handle to the worker

        Returns:
            TaskResult if complete, None if still running
        """
        pass

    @abstractmethod
    def cancel(self, handle: WorkerHandle) -> bool:
        """
        Cancel a running worker.

        Args:
            handle: Handle to the worker

        Returns:
            True if successfully cancelled
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this backend is available for use.

        Returns:
            True if the backend can be used
        """
        pass

    @abstractmethod
    def max_parallel(self) -> int:
        """
        Get the maximum number of parallel workers this backend supports.

        Returns:
            Maximum concurrent workers
        """
        pass

    def backend_type(self) -> WorkerBackend:
        """Get the backend type. Override in subclasses."""
        raise NotImplementedError
