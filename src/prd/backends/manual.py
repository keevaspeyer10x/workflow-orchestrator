"""
Manual worker backend - generates prompts for Claude Web users.

This backend doesn't actually execute anything. Instead, it generates
prompts that users can copy/paste into Claude Web sessions.
"""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .base import WorkerBackendBase, WorkerHandle, WorkerStatus
from ..schema import JobMessage, WorkerBackend, TaskResult

logger = logging.getLogger(__name__)


class ManualBackend(WorkerBackendBase):
    """
    Manual worker backend for Claude Web users.

    This backend generates detailed prompts that users can copy
    into Claude Web sessions. It tracks which prompts have been
    generated and allows users to report completion.
    """

    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize the manual backend.

        Args:
            output_dir: Directory to write prompt files
        """
        self._output_dir = output_dir or Path(".claude/manual_prompts")
        self._pending_handles: dict[str, WorkerHandle] = {}

    def spawn(self, job: JobMessage) -> WorkerHandle:
        """
        Generate a prompt for manual execution.

        Creates a detailed prompt file and returns a handle.
        The user must manually execute and report completion.
        """
        worker_id = f"manual-{uuid.uuid4().hex[:8]}"

        # Generate the prompt
        instructions = self._generate_prompt(job, worker_id)

        # Write to file
        self._output_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = self._output_dir / f"{job.job_id}.md"
        with open(prompt_file, "w") as f:
            f.write(instructions)

        handle = WorkerHandle(
            worker_id=worker_id,
            backend=WorkerBackend.MANUAL,
            job_id=job.job_id,
            status=WorkerStatus.STARTING,
            manual_instructions=instructions,
            metadata={"prompt_file": str(prompt_file)},
        )

        self._pending_handles[worker_id] = handle

        logger.info(f"Generated manual prompt for job {job.job_id}: {prompt_file}")
        print(f"\n{'='*60}")
        print(f"MANUAL TASK: {job.task_id}")
        print(f"{'='*60}")
        print(f"Prompt saved to: {prompt_file}")
        print(f"\nCopy the contents of that file into a Claude Web session.")
        print(f"When complete, run: orchestrator prd report-complete {worker_id}")
        print(f"{'='*60}\n")

        return handle

    def _generate_prompt(self, job: JobMessage, worker_id: str) -> str:
        """Generate a detailed prompt for manual execution."""
        return f"""# PRD Task: {job.task_id}

## Worker ID: {worker_id}
## Job ID: {job.job_id}
## PRD: {job.prd_id}

---

## Your Task

{job.prompt}

---

## Instructions

1. **Create a new branch** for this work:
   ```bash
   git checkout -b claude/{job.task_id}-{worker_id[:8]}
   ```

2. **Implement the task** following the requirements above.

3. **Run tests** to verify your changes:
   ```bash
   # Run appropriate tests for your changes
   ```

4. **Commit your changes** with a clear message:
   ```bash
   git add .
   git commit -m "feat({job.task_id}): <description of changes>"
   ```

5. **Report completion** by providing:
   - Branch name: `claude/{job.task_id}-{worker_id[:8]}`
   - Commit SHA: (output of `git rev-parse HEAD`)

---

## When Complete

After finishing this task, report completion to the orchestrator:

```bash
orchestrator prd report-complete {worker_id} --branch <branch-name> --commit <commit-sha>
```

Or if the task failed:

```bash
orchestrator prd report-failed {worker_id} --error "Description of what went wrong"
```

---

## Context

This task is part of a larger PRD being executed with multiple agents.
Other tasks may depend on this one, so please complete it promptly.
"""

    def get_status(self, handle: WorkerHandle) -> WorkerStatus:
        """Get the status of a manual task."""
        if handle.worker_id in self._pending_handles:
            return self._pending_handles[handle.worker_id].status
        return handle.status

    def get_result(self, handle: WorkerHandle) -> Optional[TaskResult]:
        """Get the result of a manual task."""
        if handle.worker_id in self._pending_handles:
            h = self._pending_handles[handle.worker_id]
            if h.status == WorkerStatus.COMPLETED:
                return h.result
        return handle.result

    def cancel(self, handle: WorkerHandle) -> bool:
        """Cancel a manual task (just marks it as cancelled)."""
        if handle.worker_id in self._pending_handles:
            self._pending_handles[handle.worker_id].status = WorkerStatus.CANCELLED
            return True
        return False

    def is_available(self) -> bool:
        """Manual backend is always available."""
        return True

    def max_parallel(self) -> int:
        """Manual backend supports one task at a time (user is the bottleneck)."""
        return 1

    def backend_type(self) -> WorkerBackend:
        """Return MANUAL backend type."""
        return WorkerBackend.MANUAL

    def report_complete(
        self,
        worker_id: str,
        branch: Optional[str] = None,
        commit_sha: Optional[str] = None,
    ) -> bool:
        """
        Report that a manual task has been completed.

        Called by the user when they finish executing a task.
        """
        if worker_id not in self._pending_handles:
            logger.warning(f"Unknown worker ID: {worker_id}")
            return False

        handle = self._pending_handles[worker_id]
        handle.status = WorkerStatus.COMPLETED
        handle.completed_at = datetime.now(timezone.utc)
        handle.result = TaskResult(
            task_id=handle.job_id or "",
            success=True,
            branch=branch,
            commit_sha=commit_sha,
        )

        logger.info(f"Manual task {worker_id} reported as complete")
        return True

    def report_failed(self, worker_id: str, error: str) -> bool:
        """
        Report that a manual task has failed.

        Called by the user when a task fails.
        """
        if worker_id not in self._pending_handles:
            logger.warning(f"Unknown worker ID: {worker_id}")
            return False

        handle = self._pending_handles[worker_id]
        handle.status = WorkerStatus.FAILED
        handle.completed_at = datetime.now(timezone.utc)
        handle.error = error
        handle.result = TaskResult(
            task_id=handle.job_id or "",
            success=False,
            error=error,
        )

        logger.info(f"Manual task {worker_id} reported as failed: {error}")
        return True

    def list_pending(self) -> list[WorkerHandle]:
        """List all pending manual tasks."""
        return [
            h for h in self._pending_handles.values()
            if h.status in (WorkerStatus.STARTING, WorkerStatus.RUNNING)
        ]
