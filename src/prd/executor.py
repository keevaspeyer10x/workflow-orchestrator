"""
PRD Executor - orchestrates full PRD execution with multiple agents.

This is the main entry point for executing a PRD with:
- Task decomposition and dependency tracking
- Multi-backend worker pool
- Wave-based conflict resolution
- Checkpoint PRs at intervals
- Final PR when complete
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable

from .schema import (
    PRDConfig,
    PRDDocument,
    PRDTask,
    TaskStatus,
    TaskResult,
    JobMessage,
    WorkerBackend,
)
from .queue import FileJobQueue
from .worker_pool import WorkerPool
from .integration import IntegrationBranchManager, CheckpointPR
from .wave_resolver import WaveResolver, WaveResolutionResult

logger = logging.getLogger(__name__)


@dataclass
class PRDExecutionResult:
    """Result of PRD execution."""

    prd_id: str
    success: bool
    tasks_completed: int
    tasks_failed: int
    waves_executed: int
    checkpoint_prs: list[CheckpointPR] = field(default_factory=list)
    final_pr_url: Optional[str] = None
    duration_seconds: float = 0.0
    error: Optional[str] = None


class PRDExecutor:
    """
    Executes a full PRD with automatic coordination.

    Flow:
    1. Load/validate PRD
    2. Create integration branch
    3. Spawn agents for ready tasks
    4. Monitor progress, resolve conflicts
    5. Create checkpoint PRs at intervals
    6. Final PR when complete
    """

    def __init__(
        self,
        config: PRDConfig,
        working_dir: Optional[Path] = None,
        on_task_complete: Optional[Callable[[PRDTask, TaskResult], None]] = None,
        on_checkpoint: Optional[Callable[[CheckpointPR], None]] = None,
    ):
        """
        Initialize the PRD executor.

        Args:
            config: PRD configuration
            working_dir: Working directory
            on_task_complete: Callback when a task completes
            on_checkpoint: Callback when a checkpoint PR is created
        """
        self.config = config
        self.working_dir = working_dir or Path.cwd()
        self.on_task_complete = on_task_complete
        self.on_checkpoint = on_checkpoint

        # Initialize components
        self._queue = FileJobQueue(self.working_dir / ".claude" / "job_queue")
        self._worker_pool = WorkerPool(config)
        self._integration_manager = IntegrationBranchManager(self.working_dir)
        self._wave_resolver = WaveResolver(self._integration_manager)

        # Execution state
        self._active_prd: Optional[PRDDocument] = None
        self._completed_tasks: list[tuple[PRDTask, TaskResult]] = []
        self._tasks_since_checkpoint: int = 0

    async def execute_prd(self, prd: PRDDocument) -> PRDExecutionResult:
        """
        Execute a PRD with automatic coordination.

        Args:
            prd: PRD document to execute

        Returns:
            PRDExecutionResult with execution details
        """
        start_time = datetime.now(timezone.utc)
        self._active_prd = prd
        self._completed_tasks = []
        self._tasks_since_checkpoint = 0
        checkpoint_prs: list[CheckpointPR] = []

        try:
            # 1. Create integration branch
            logger.info(f"Starting PRD execution: {prd.id}")
            self._integration_manager.create_integration_branch(prd.id)

            # 2. Execute in waves
            while not prd.all_complete():
                # Get ready tasks
                ready_tasks = prd.get_ready_tasks()

                if not ready_tasks:
                    # Check if we're stuck (tasks pending but none ready)
                    pending = [t for t in prd.tasks if t.status == TaskStatus.PENDING]
                    running = [t for t in prd.tasks if t.status == TaskStatus.RUNNING]

                    if pending and not running:
                        # Dependency deadlock or all tasks failed
                        logger.error("No tasks ready and none running - possible deadlock")
                        break

                    # Wait for running tasks to complete
                    await asyncio.sleep(5)
                    continue

                # Spawn workers for ready tasks
                for task in ready_tasks[:self.config.max_concurrent_agents]:
                    if task.status != TaskStatus.PENDING:
                        continue

                    self._spawn_task(task, prd.id)

                # Wait for some completions
                await self._wait_for_completions(prd)

                # Resolve conflicts and merge completed work
                if self._completed_tasks:
                    wave_result = self._wave_resolver.resolve_in_waves(
                        self._completed_tasks,
                        prd.id,
                    )

                    # Clear completed tasks that were merged
                    self._completed_tasks = [
                        (task, result) for task, result in self._completed_tasks
                        if task.id in wave_result.failed_tasks
                    ]

                    self._tasks_since_checkpoint += wave_result.total_conflicts_resolved

                # Checkpoint if needed
                if self._should_checkpoint():
                    checkpoint = await self._create_checkpoint(prd)
                    if checkpoint:
                        checkpoint_prs.append(checkpoint)
                        if self.on_checkpoint:
                            self.on_checkpoint(checkpoint)

            # 3. Final PR if everything completed
            completed_count = len(prd.get_completed_tasks())
            failed_count = len(prd.get_failed_tasks())

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Create final PR if there's work to merge
            final_pr_url = None
            if completed_count > 0 and failed_count == 0:
                try:
                    final_checkpoint = await self._create_checkpoint(
                        prd,
                        description="Final PR - all tasks complete",
                        is_final=True,
                    )
                    if final_checkpoint:
                        final_pr_url = final_checkpoint.pr_url
                except Exception as e:
                    logger.error(f"Failed to create final PR: {e}")

            return PRDExecutionResult(
                prd_id=prd.id,
                success=failed_count == 0,
                tasks_completed=completed_count,
                tasks_failed=failed_count,
                waves_executed=0,  # TODO: Track wave count
                checkpoint_prs=checkpoint_prs,
                final_pr_url=final_pr_url,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.exception(f"PRD execution failed: {e}")
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return PRDExecutionResult(
                prd_id=prd.id,
                success=False,
                tasks_completed=len(prd.get_completed_tasks()),
                tasks_failed=len(prd.get_failed_tasks()) + len([
                    t for t in prd.tasks
                    if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
                ]),
                waves_executed=0,
                checkpoint_prs=checkpoint_prs,
                duration_seconds=duration,
                error=str(e),
            )

    def _spawn_task(self, task: PRDTask, prd_id: str) -> None:
        """Spawn a worker for a task."""
        # Generate prompt for the task
        prompt = self._generate_task_prompt(task, prd_id)

        # Create job
        job = JobMessage(
            job_id=f"job-{uuid.uuid4().hex[:8]}",
            task_id=task.id,
            prd_id=prd_id,
            prompt=prompt,
        )

        # Enqueue
        self._queue.enqueue(job)

        # Spawn worker
        handle = self._worker_pool.spawn(job)

        # Update task status
        task.mark_running(
            agent_id=handle.worker_id,
            branch=f"claude/{task.id}-{handle.worker_id[:8]}",
        )

        logger.info(f"Spawned task {task.id} with worker {handle.worker_id}")

    def _generate_task_prompt(self, task: PRDTask, prd_id: str) -> str:
        """Generate the prompt for a task."""
        return f"""# PRD Task: {task.id}

## Description
{task.description}

## Branch
Create your work on branch: `claude/{task.id}-{{worker_id}}`

## Requirements
1. Implement the feature/fix described above
2. Write tests for your changes
3. Ensure all tests pass
4. Commit with clear messages

## When Complete
- Commit all changes
- Push your branch
- The orchestrator will handle merging

## PRD Context
This task is part of PRD: {prd_id}
Dependencies: {task.dependencies if task.dependencies else 'None'}
"""

    async def _wait_for_completions(self, prd: PRDDocument) -> None:
        """Wait for at least one task to complete."""
        # Check for completed jobs in queue
        while True:
            # Check processing jobs
            processing_jobs = self._queue.list_processing()

            if not processing_jobs:
                # No jobs processing, check if any running tasks
                running = [t for t in prd.tasks if t.status == TaskStatus.RUNNING]
                if not running:
                    return

            # Poll for completions (simplified - real impl would use callbacks)
            for job in self._queue.list_completed():
                task = prd.get_task(job.task_id)
                if task and task.status == TaskStatus.RUNNING:
                    result = TaskResult(
                        task_id=task.id,
                        success=True,
                        branch=task.branch,
                        commit_sha=job.result.get("commit_sha") if job.result else None,
                    )
                    task.mark_completed(result.commit_sha or "")
                    self._completed_tasks.append((task, result))

                    if self.on_task_complete:
                        self.on_task_complete(task, result)

                    logger.info(f"Task {task.id} completed")

            # Check for failed jobs
            for job in self._queue.list_failed():
                task = prd.get_task(job.task_id)
                if task and task.status == TaskStatus.RUNNING:
                    task.mark_failed(job.error or "Unknown error")
                    logger.warning(f"Task {task.id} failed: {job.error}")

            # If we got completions, return
            if self._completed_tasks:
                return

            # Wait a bit before checking again
            await asyncio.sleep(2)

    def _should_checkpoint(self) -> bool:
        """Check if we should create a checkpoint PR."""
        return self._tasks_since_checkpoint >= self.config.checkpoint_interval

    async def _create_checkpoint(
        self,
        prd: PRDDocument,
        description: Optional[str] = None,
        is_final: bool = False,
    ) -> Optional[CheckpointPR]:
        """Create a checkpoint PR."""
        completed = prd.get_completed_tasks()
        if not completed:
            return None

        desc = description or f"Checkpoint: {len(completed)} tasks complete"

        try:
            checkpoint = self._integration_manager.create_checkpoint_pr(
                prd_id=prd.id,
                description=desc,
                tasks_included=[t.id for t in completed],
            )
            self._tasks_since_checkpoint = 0
            return checkpoint
        except Exception as e:
            logger.error(f"Failed to create checkpoint PR: {e}")
            return None

    def get_status(self) -> dict:
        """Get current execution status."""
        if not self._active_prd:
            return {"status": "idle"}

        prd = self._active_prd
        return {
            "status": "running",
            "prd_id": prd.id,
            "progress": prd.progress_summary(),
            "queue": self._queue.get_stats(),
            "workers": self._worker_pool.get_backend_stats(),
        }

    def cancel(self) -> bool:
        """Cancel the current PRD execution."""
        if not self._active_prd:
            return False

        # Cancel all pending/running tasks
        for task in self._active_prd.tasks:
            if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                task.status = TaskStatus.CANCELLED

        self._active_prd = None
        logger.info("PRD execution cancelled")
        return True
