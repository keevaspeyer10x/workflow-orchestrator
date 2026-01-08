"""
Local worker backend - runs Claude Code CLI locally.
"""

import logging
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .base import WorkerBackendBase, WorkerHandle, WorkerStatus
from ..schema import JobMessage, WorkerBackend, TaskResult

logger = logging.getLogger(__name__)


class LocalBackend(WorkerBackendBase):
    """
    Local worker backend that runs Claude Code CLI.

    This backend spawns local processes running Claude Code
    to execute PRD tasks. Good for development and small PRDs.
    """

    def __init__(
        self,
        max_parallel: int = 4,
        timeout_minutes: int = 30,
        working_dir: Optional[Path] = None,
    ):
        """
        Initialize the local backend.

        Args:
            max_parallel: Maximum concurrent workers
            timeout_minutes: Timeout for each worker
            working_dir: Working directory for workers
        """
        self._max_parallel = max_parallel
        self._timeout_minutes = timeout_minutes
        self._working_dir = working_dir or Path.cwd()
        self._active_workers: dict[str, subprocess.Popen] = {}

    def spawn(self, job: JobMessage) -> WorkerHandle:
        """Spawn a local Claude Code process."""
        worker_id = f"local-{uuid.uuid4().hex[:8]}"

        # Create a prompt file for the worker
        prompt_file = self._working_dir / ".claude" / "prd_prompts" / f"{job.job_id}.md"
        prompt_file.parent.mkdir(parents=True, exist_ok=True)

        # Write the prompt
        prompt_content = f"""# PRD Task: {job.task_id}

## Instructions
{job.prompt}

## Important
- Create a new branch for this work: `claude/{job.task_id}-{worker_id}`
- Commit your changes with clear messages
- Run tests before completing
- Output the branch name and commit SHA when done
"""
        with open(prompt_file, "w") as f:
            f.write(prompt_content)

        # Check if claude CLI is available
        claude_path = shutil.which("claude")
        if not claude_path:
            logger.warning("Claude CLI not found, creating handle for manual execution")
            return WorkerHandle(
                worker_id=worker_id,
                backend=WorkerBackend.LOCAL,
                job_id=job.job_id,
                status=WorkerStatus.FAILED,
                error="Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code",
                manual_instructions=prompt_content,
            )

        # Spawn the Claude process
        try:
            # Use claude with the prompt file
            process = subprocess.Popen(
                [
                    claude_path,
                    "--print",  # Non-interactive mode
                    "-p", prompt_content,
                ],
                cwd=self._working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self._active_workers[worker_id] = process

            return WorkerHandle(
                worker_id=worker_id,
                backend=WorkerBackend.LOCAL,
                job_id=job.job_id,
                status=WorkerStatus.RUNNING,
                metadata={"pid": process.pid, "prompt_file": str(prompt_file)},
            )

        except Exception as e:
            logger.error(f"Failed to spawn local worker: {e}")
            return WorkerHandle(
                worker_id=worker_id,
                backend=WorkerBackend.LOCAL,
                job_id=job.job_id,
                status=WorkerStatus.FAILED,
                error=str(e),
            )

    def get_status(self, handle: WorkerHandle) -> WorkerStatus:
        """Check if the local process is still running."""
        if handle.worker_id not in self._active_workers:
            return handle.status

        process = self._active_workers[handle.worker_id]
        poll_result = process.poll()

        if poll_result is None:
            return WorkerStatus.RUNNING
        elif poll_result == 0:
            return WorkerStatus.COMPLETED
        else:
            return WorkerStatus.FAILED

    def get_result(self, handle: WorkerHandle) -> Optional[TaskResult]:
        """Get the result from a completed local worker."""
        if handle.worker_id not in self._active_workers:
            if handle.result:
                return handle.result
            return None

        process = self._active_workers[handle.worker_id]
        poll_result = process.poll()

        if poll_result is None:
            # Still running
            return None

        # Get output
        stdout, stderr = process.communicate(timeout=5)

        # Clean up
        del self._active_workers[handle.worker_id]

        if poll_result == 0:
            # Try to extract branch and commit from output
            branch = None
            commit_sha = None

            # Look for branch name in output
            for line in stdout.split("\n"):
                if "branch:" in line.lower():
                    branch = line.split(":")[-1].strip()
                if "commit:" in line.lower() or "sha:" in line.lower():
                    commit_sha = line.split(":")[-1].strip()

            return TaskResult(
                task_id=handle.job_id or "",
                success=True,
                branch=branch,
                commit_sha=commit_sha,
                output=stdout,
            )
        else:
            return TaskResult(
                task_id=handle.job_id or "",
                success=False,
                error=stderr or f"Process exited with code {poll_result}",
                output=stdout,
            )

    def cancel(self, handle: WorkerHandle) -> bool:
        """Cancel a running local worker."""
        if handle.worker_id not in self._active_workers:
            return False

        process = self._active_workers[handle.worker_id]
        try:
            process.terminate()
            process.wait(timeout=5)
            del self._active_workers[handle.worker_id]
            return True
        except Exception as e:
            logger.error(f"Failed to cancel worker {handle.worker_id}: {e}")
            return False

    def is_available(self) -> bool:
        """Local backend is always available."""
        return True

    def max_parallel(self) -> int:
        """Return configured max parallel workers."""
        return self._max_parallel

    def backend_type(self) -> WorkerBackend:
        """Return LOCAL backend type."""
        return WorkerBackend.LOCAL

    def active_count(self) -> int:
        """Get count of active workers."""
        # Clean up finished workers
        finished = []
        for worker_id, process in self._active_workers.items():
            if process.poll() is not None:
                finished.append(worker_id)

        for worker_id in finished:
            del self._active_workers[worker_id]

        return len(self._active_workers)
