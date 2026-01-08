"""
Job queue for PRD task distribution.

Provides a file-based queue by default (works everywhere),
with support for other backends (Redis, etc.) in the future.
"""

import json
import logging
import shutil
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Protocol

from .schema import JobMessage, JobStatus

logger = logging.getLogger(__name__)


class JobQueue(Protocol):
    """Protocol for job queue implementations."""

    def enqueue(self, job: JobMessage) -> None:
        """Add a job to the queue."""
        ...

    def dequeue(self) -> Optional[JobMessage]:
        """Get and claim the next pending job."""
        ...

    def complete(self, job_id: str, success: bool, result: Optional[dict] = None) -> None:
        """Mark a job as completed."""
        ...

    def fail(self, job_id: str, error: str) -> None:
        """Mark a job as failed."""
        ...

    def pending_count(self) -> int:
        """Get count of pending jobs."""
        ...

    def processing_count(self) -> int:
        """Get count of processing jobs."""
        ...

    def is_empty(self) -> bool:
        """Check if queue has no pending jobs."""
        ...

    def get_job(self, job_id: str) -> Optional[JobMessage]:
        """Get a job by ID."""
        ...


class FileJobQueue:
    """
    File-based job queue implementation.

    Uses a directory structure:
    - pending/   - Jobs waiting to be picked up
    - processing/ - Jobs currently being worked on
    - completed/  - Successfully completed jobs
    - failed/     - Failed jobs

    This is simple, portable, and works everywhere without
    external dependencies.
    """

    def __init__(self, queue_dir: Optional[Path] = None):
        """
        Initialize the file queue.

        Args:
            queue_dir: Directory for queue files. Defaults to .claude/job_queue/
        """
        self.queue_dir = queue_dir or Path(".claude/job_queue")
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Create queue directories if they don't exist."""
        for subdir in ["pending", "processing", "completed", "failed"]:
            (self.queue_dir / subdir).mkdir(parents=True, exist_ok=True)

    def _job_path(self, job_id: str, status: str) -> Path:
        """Get the path for a job file."""
        return self.queue_dir / status / f"{job_id}.json"

    def _write_job(self, job: JobMessage, status: str) -> None:
        """Write a job to disk."""
        path = self._job_path(job.job_id, status)
        with open(path, "w") as f:
            json.dump(job.to_dict(), f, indent=2, default=str)

    def _read_job(self, path: Path) -> Optional[JobMessage]:
        """Read a job from disk."""
        try:
            with open(path) as f:
                data = json.load(f)
                return JobMessage.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to read job from {path}: {e}")
            return None

    def _move_job(self, job_id: str, from_status: str, to_status: str) -> Optional[Path]:
        """Move a job from one status directory to another."""
        from_path = self._job_path(job_id, from_status)
        to_path = self._job_path(job_id, to_status)

        if not from_path.exists():
            return None

        shutil.move(str(from_path), str(to_path))
        return to_path

    def enqueue(self, job: JobMessage) -> None:
        """Add a job to the queue."""
        job.status = JobStatus.PENDING
        self._write_job(job, "pending")
        logger.info(f"Enqueued job {job.job_id} for task {job.task_id}")

    def dequeue(self) -> Optional[JobMessage]:
        """Get and claim the next pending job (FIFO)."""
        pending_dir = self.queue_dir / "pending"

        # Get oldest pending job (sorted by filename/creation time)
        pending_files = sorted(pending_dir.glob("*.json"))

        if not pending_files:
            return None

        # Read and move to processing
        job = self._read_job(pending_files[0])
        if job is None:
            return None

        job.status = JobStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)

        # Move to processing
        self._move_job(job.job_id, "pending", "processing")
        self._write_job(job, "processing")

        logger.info(f"Dequeued job {job.job_id}")
        return job

    def complete(self, job_id: str, success: bool = True, result: Optional[dict] = None) -> None:
        """Mark a job as completed."""
        path = self._job_path(job_id, "processing")
        job = self._read_job(path)

        if job is None:
            logger.warning(f"Job {job_id} not found in processing")
            return

        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        job.result = result

        # Move to completed
        self._move_job(job_id, "processing", "completed")
        self._write_job(job, "completed")

        logger.info(f"Completed job {job_id}")

    def fail(self, job_id: str, error: str) -> None:
        """Mark a job as failed."""
        path = self._job_path(job_id, "processing")
        job = self._read_job(path)

        if job is None:
            logger.warning(f"Job {job_id} not found in processing")
            return

        job.status = JobStatus.FAILED
        job.completed_at = datetime.now(timezone.utc)
        job.error = error

        # Move to failed
        self._move_job(job_id, "processing", "failed")
        self._write_job(job, "failed")

        logger.info(f"Failed job {job_id}: {error}")

    def pending_count(self) -> int:
        """Get count of pending jobs."""
        return len(list((self.queue_dir / "pending").glob("*.json")))

    def processing_count(self) -> int:
        """Get count of processing jobs."""
        return len(list((self.queue_dir / "processing").glob("*.json")))

    def is_empty(self) -> bool:
        """Check if queue has no pending jobs."""
        return self.pending_count() == 0

    def get_job(self, job_id: str) -> Optional[JobMessage]:
        """Get a job by ID from any status."""
        for status in ["pending", "processing", "completed", "failed"]:
            path = self._job_path(job_id, status)
            if path.exists():
                return self._read_job(path)
        return None

    def list_pending(self) -> list[JobMessage]:
        """List all pending jobs."""
        jobs = []
        for path in sorted((self.queue_dir / "pending").glob("*.json")):
            job = self._read_job(path)
            if job:
                jobs.append(job)
        return jobs

    def list_processing(self) -> list[JobMessage]:
        """List all processing jobs."""
        jobs = []
        for path in (self.queue_dir / "processing").glob("*.json"):
            job = self._read_job(path)
            if job:
                jobs.append(job)
        return jobs

    def list_completed(self) -> list[JobMessage]:
        """List all completed jobs."""
        jobs = []
        for path in (self.queue_dir / "completed").glob("*.json"):
            job = self._read_job(path)
            if job:
                jobs.append(job)
        return jobs

    def list_failed(self) -> list[JobMessage]:
        """List all failed jobs."""
        jobs = []
        for path in (self.queue_dir / "failed").glob("*.json"):
            job = self._read_job(path)
            if job:
                jobs.append(job)
        return jobs

    def clear_completed(self) -> int:
        """Remove all completed jobs. Returns count removed."""
        completed_dir = self.queue_dir / "completed"
        count = 0
        for path in completed_dir.glob("*.json"):
            path.unlink()
            count += 1
        return count

    def clear_failed(self) -> int:
        """Remove all failed jobs. Returns count removed."""
        failed_dir = self.queue_dir / "failed"
        count = 0
        for path in failed_dir.glob("*.json"):
            path.unlink()
            count += 1
        return count

    def retry_failed(self, job_id: str) -> bool:
        """Move a failed job back to pending for retry."""
        path = self._job_path(job_id, "failed")
        job = self._read_job(path)

        if job is None:
            return False

        job.status = JobStatus.PENDING
        job.error = None
        job.started_at = None
        job.completed_at = None

        self._move_job(job_id, "failed", "pending")
        self._write_job(job, "pending")

        logger.info(f"Retrying job {job_id}")
        return True

    def get_stats(self) -> dict[str, int]:
        """Get queue statistics."""
        return {
            "pending": self.pending_count(),
            "processing": self.processing_count(),
            "completed": len(list((self.queue_dir / "completed").glob("*.json"))),
            "failed": len(list((self.queue_dir / "failed").glob("*.json"))),
        }
