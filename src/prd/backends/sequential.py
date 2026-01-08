"""
Sequential execution backend for running inside Claude Code.

When already inside Claude Code, we can't spawn subprocess Claude instances.
Instead, this backend queues tasks for sequential execution by the current session.
"""

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .base import WorkerBackendBase, WorkerHandle, WorkerStatus
from ..schema import JobMessage, WorkerBackend, TaskResult

logger = logging.getLogger(__name__)


def is_inside_claude_code() -> bool:
    """
    Detect if we're running inside Claude Code.

    Returns:
        True if running inside Claude Code, False otherwise
    """
    # Check explicit environment variables (both CLAUDECODE and CLAUDE_CODE)
    if os.environ.get('CLAUDECODE') == '1':
        return True
    if os.environ.get('CLAUDE_CODE') == '1':
        return True

    # Check Claude Code specific entrypoint
    if os.environ.get('CLAUDE_CODE_ENTRYPOINT'):
        return True

    # Check if claude is in the command path
    cmd = os.environ.get('_', '')
    if 'claude' in cmd.lower():
        return True

    return False


@dataclass
class PendingTask:
    """A task pending execution by the current session."""

    task_id: str
    job_id: str
    prd_id: str
    prompt: str
    worker_id: str
    created_at: datetime


class SequentialBackend(WorkerBackendBase):
    """
    Sequential execution backend for Claude Code environment.

    Instead of spawning processes, this backend:
    1. Queues tasks with their prompts
    2. Returns prompts for the current session to execute
    3. Tracks completion via explicit mark_complete calls

    This enables PRD execution when already inside Claude Code.
    """

    def __init__(self):
        """Initialize the sequential backend."""
        self._pending_tasks: dict[str, PendingTask] = {}
        self._handles: dict[str, WorkerHandle] = {}
        self._results: dict[str, TaskResult] = {}

    def spawn(self, job: JobMessage) -> WorkerHandle:
        """
        Queue a task for sequential execution.

        Does not actually spawn a process - just queues the task
        with its prompt for the current session to execute.
        """
        worker_id = f"seq-{uuid.uuid4().hex[:8]}"

        # Generate the execution prompt
        prompt = self._generate_execution_prompt(job, worker_id)

        # Create pending task
        task = PendingTask(
            task_id=job.task_id,
            job_id=job.job_id,
            prd_id=job.prd_id,
            prompt=prompt,
            worker_id=worker_id,
            created_at=datetime.now(timezone.utc),
        )
        self._pending_tasks[worker_id] = task

        # Create handle
        handle = WorkerHandle(
            worker_id=worker_id,
            backend=WorkerBackend.LOCAL,  # Report as local for compatibility
            job_id=job.job_id,
            status=WorkerStatus.STARTING,  # Use STARTING since PENDING doesn't exist
            manual_instructions=prompt,
            metadata={"task_id": job.task_id, "sequential": True},
        )
        self._handles[worker_id] = handle

        logger.info(f"Queued task {job.task_id} for sequential execution")
        return handle

    def _generate_execution_prompt(self, job: JobMessage, worker_id: str) -> str:
        """Generate the prompt for executing this task."""
        return f"""# Task: {job.task_id}

## Instructions
{job.prompt}

## Branch
Create your work on branch: `claude/{job.task_id}-{worker_id[:8]}`

## When Complete
After completing this task, the orchestrator will continue to the next task.

Commit your changes with a clear message describing what was done.
"""

    def get_status(self, handle: WorkerHandle) -> WorkerStatus:
        """Get the status of a task."""
        if handle.worker_id in self._handles:
            return self._handles[handle.worker_id].status
        return handle.status

    def get_result(self, handle: WorkerHandle) -> Optional[TaskResult]:
        """Get the result of a completed task."""
        return self._results.get(handle.worker_id)

    def cancel(self, handle: WorkerHandle) -> bool:
        """Cancel a pending task."""
        if handle.worker_id in self._pending_tasks:
            del self._pending_tasks[handle.worker_id]
            if handle.worker_id in self._handles:
                self._handles[handle.worker_id].status = WorkerStatus.CANCELLED
            return True
        return False

    def is_available(self) -> bool:
        """Sequential backend is always available."""
        return True

    def max_parallel(self) -> int:
        """Sequential execution = 1 task at a time."""
        return 1

    def backend_type(self) -> WorkerBackend:
        """Return LOCAL type for compatibility."""
        return WorkerBackend.LOCAL

    # Sequential-specific methods

    def get_pending_tasks(self) -> list[PendingTask]:
        """Get all pending tasks."""
        return list(self._pending_tasks.values())

    def get_next_task(self) -> Optional[PendingTask]:
        """Get the next pending task to execute."""
        if not self._pending_tasks:
            return None
        # Return first task (FIFO)
        worker_id = next(iter(self._pending_tasks))
        return self._pending_tasks[worker_id]

    def mark_complete(
        self,
        worker_id: str,
        branch: Optional[str] = None,
        commit_sha: Optional[str] = None,
    ) -> bool:
        """
        Mark a task as complete.

        Called by the current session after executing a task.
        """
        if worker_id not in self._handles:
            logger.warning(f"Unknown worker ID: {worker_id}")
            return False

        handle = self._handles[worker_id]
        handle.status = WorkerStatus.COMPLETED
        handle.completed_at = datetime.now(timezone.utc)

        # Store result
        task = self._pending_tasks.get(worker_id)
        self._results[worker_id] = TaskResult(
            task_id=task.task_id if task else "",
            success=True,
            branch=branch,
            commit_sha=commit_sha,
        )

        # Remove from pending
        if worker_id in self._pending_tasks:
            del self._pending_tasks[worker_id]

        logger.info(f"Task {worker_id} marked complete")
        return True

    def mark_failed(self, worker_id: str, error: str) -> bool:
        """
        Mark a task as failed.

        Called by the current session if a task fails.
        """
        if worker_id not in self._handles:
            logger.warning(f"Unknown worker ID: {worker_id}")
            return False

        handle = self._handles[worker_id]
        handle.status = WorkerStatus.FAILED
        handle.error = error
        handle.completed_at = datetime.now(timezone.utc)

        # Store result
        task = self._pending_tasks.get(worker_id)
        self._results[worker_id] = TaskResult(
            task_id=task.task_id if task else "",
            success=False,
            error=error,
        )

        # Remove from pending
        if worker_id in self._pending_tasks:
            del self._pending_tasks[worker_id]

        logger.warning(f"Task {worker_id} marked failed: {error}")
        return True

    def active_count(self) -> int:
        """Get count of pending tasks."""
        return len(self._pending_tasks)
