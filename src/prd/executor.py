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
from ._deprecated.worker_pool import WorkerPool  # Deprecated - kept for async execute_prd()
from .integration import IntegrationBranchManager, CheckpointPR
from .wave_resolver import WaveResolver, WaveResolutionResult
from .spawn_scheduler import SpawnScheduler, SpawnWave, ScheduleResult
from .backend_selector import BackendSelector, ExecutionMode

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


@dataclass
class SpawnResult:
    """Result of spawning tasks."""
    spawned_count: int
    wave_number: int
    task_ids: list[str] = field(default_factory=list)
    session_ids: list[str] = field(default_factory=list)
    explanation: Optional[str] = None
    error: Optional[str] = None
    dry_run: bool = False


@dataclass
class MergeResult:
    """Result of merging a task."""
    success: bool
    task_id: str
    branch: Optional[str] = None
    commit_sha: Optional[str] = None
    conflicts_resolved: int = 0
    explanation: Optional[str] = None
    error: Optional[str] = None
    dry_run: bool = False


@dataclass
class SyncResult:
    """Result of sync operation."""
    merged_count: int
    spawned_count: int
    merge_results: list[MergeResult] = field(default_factory=list)
    spawn_result: Optional[SpawnResult] = None
    dry_run: bool = False


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

## IMPORTANT: Use the Orchestrator Workflow

You MUST use the orchestrator workflow system for this task. This ensures proper planning,
external AI code reviews, verification, and learning documentation.

```bash
# Start the workflow
orchestrator start "{task.description}"

# Follow all 5 phases:
# 1. PLAN - Define approach, get approval
# 2. EXECUTE - Implement code and tests
# 3. REVIEW - Run external AI reviews (security, quality, consistency)
# 4. VERIFY - Final testing
# 5. LEARN - Document learnings

# Use orchestrator commands throughout:
orchestrator status          # Check current phase
orchestrator complete <id>   # Complete items
orchestrator advance         # Move to next phase
orchestrator finish          # Complete workflow
```

## Branch
Create your work on branch: `claude/{task.id}`

## Requirements
1. Use `orchestrator start` FIRST before any implementation
2. Follow all orchestrator phases - do not skip REVIEW or LEARN
3. Ensure external AI reviews pass (REVIEW phase)
4. Write tests for your changes
5. Ensure all tests pass
6. Commit with clear messages

## When Complete
- Ensure orchestrator workflow is finished (`orchestrator finish`)
- Commit all changes
- Push your branch
- The parent PRD executor will handle merging

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

    # =========================================================================
    # CLI-Driven Methods (PRD-001 Phase 2)
    # =========================================================================

    def spawn(
        self,
        prd: PRDDocument,
        explain: bool = False,
        dry_run: bool = False,
        force_tasks: Optional[list[str]] = None,
        inject_approval_gate: bool = True,
    ) -> SpawnResult:
        """
        Spawn the next wave of tasks via Claude Squad.

        This is the CLI-driven spawn method that:
        1. Uses SpawnScheduler to find non-conflicting tasks
        2. Spawns them via ClaudeSquadAdapter as tmux sessions
        3. Returns information about what was spawned

        Args:
            prd: The PRD document
            explain: If True, show wave groupings without spawning
            dry_run: If True, show what would happen without actually spawning
            force_tasks: If provided, force spawn these specific tasks (bypasses scheduler)
            inject_approval_gate: If True, inject approval gate instructions into prompts (PRD-006)

        Returns:
            SpawnResult with details about spawned tasks
        """
        scheduler = SpawnScheduler()

        # Track what's already spawned and merged
        spawned_ids = [t.id for t in prd.tasks if t.status != TaskStatus.PENDING]
        merged_ids = [t.id for t in prd.tasks if t.status == TaskStatus.COMPLETED]

        # Determine what to spawn
        if force_tasks:
            # Force mode: bypass scheduler
            wave = scheduler.force_spawn(prd.tasks, force_tasks, merged_ids)
            explanation = "Forced spawn (bypassing scheduler)"
        else:
            # Normal mode: get next wave from scheduler
            wave = scheduler.get_next_wave(prd.tasks, spawned_ids, merged_ids)
            if not wave:
                return SpawnResult(
                    spawned_count=0,
                    wave_number=0,
                    task_ids=[],
                    explanation="No tasks ready to spawn (all spawned or dependencies not met)",
                )
            explanation = None
            if explain:
                result = scheduler.schedule_waves([t for t in prd.tasks if t.id not in spawned_ids], explain=True)
                explanation = result.explanation

        if dry_run:
            return SpawnResult(
                spawned_count=len(wave.tasks),
                wave_number=wave.wave_number,
                task_ids=wave.task_ids,
                explanation=explanation or f"Would spawn {len(wave.tasks)} tasks in wave {wave.wave_number}",
                dry_run=True,
            )

        # Actually spawn via TmuxAdapter (or SubprocessAdapter fallback)
        backend_selector = BackendSelector.detect(self.working_dir)
        adapter = backend_selector.get_adapter(inject_approval_gate=inject_approval_gate)

        if adapter is None:
            return SpawnResult(
                spawned_count=0,
                wave_number=wave.wave_number,
                task_ids=wave.task_ids,
                explanation="No execution backend available. Install tmux for interactive sessions.",
                error="No backend available for spawn",
            )

        session_ids = []
        for task in wave.tasks:
            try:
                prompt = self._generate_task_prompt(task, prd.id)
                branch = f"claude/{task.id}"
                session = adapter.spawn_agent(
                    task_id=task.id,
                    prompt=prompt,
                    working_dir=self.working_dir,
                    branch=branch,
                )
                session_ids.append(session.session_id)
                task.status = TaskStatus.RUNNING
                task.agent_id = session.session_id
                task.branch = branch
                task.started_at = datetime.now(timezone.utc)
                logger.info(f"Spawned session for task {task.id}: {session.session_name}")
            except Exception as e:
                logger.error(f"Failed to spawn session for task {task.id}: {e}")
                task.status = TaskStatus.FAILED
                task.error = str(e)

        return SpawnResult(
            spawned_count=len(session_ids),
            wave_number=wave.wave_number,
            task_ids=[t.id for t in wave.tasks if t.status == TaskStatus.RUNNING],
            session_ids=session_ids,
            explanation=explanation,
        )

    def merge(
        self,
        prd: PRDDocument,
        task_id: str,
        dry_run: bool = False,
    ) -> MergeResult:
        """
        Merge a single completed task into the integration branch.

        This is the CLI-driven merge method that:
        1. Validates the task is complete
        2. Merges its branch into the integration branch
        3. Auto-resolves any conflicts using the resolution pipeline

        Args:
            prd: The PRD document
            task_id: ID of the task to merge
            dry_run: If True, show what would happen without actually merging

        Returns:
            MergeResult with details about the merge
        """
        task = prd.get_task(task_id)
        if not task:
            return MergeResult(
                success=False,
                task_id=task_id,
                error=f"Task not found: {task_id}",
            )

        if task.status != TaskStatus.RUNNING:
            return MergeResult(
                success=False,
                task_id=task_id,
                error=f"Task {task_id} is not running (status={task.status.value})",
            )

        if not task.branch:
            return MergeResult(
                success=False,
                task_id=task_id,
                error=f"Task {task_id} has no branch",
            )

        if dry_run:
            return MergeResult(
                success=True,
                task_id=task_id,
                branch=task.branch,
                explanation=f"Would merge branch {task.branch} into {prd.integration_branch}",
                dry_run=True,
            )

        # Ensure integration branch exists
        try:
            self._integration_manager.create_integration_branch(prd.id)
        except Exception:
            pass  # Branch may already exist

        # Merge using integration manager
        try:
            merge_record = self._integration_manager.merge_branch(
                branch=task.branch,
                prd_id=prd.id,
            )

            task.status = TaskStatus.COMPLETED
            task.commit_sha = merge_record.commit_sha if hasattr(merge_record, 'commit_sha') else None
            task.completed_at = datetime.now(timezone.utc)

            return MergeResult(
                success=True,
                task_id=task_id,
                branch=task.branch,
                commit_sha=task.commit_sha,
                conflicts_resolved=merge_record.conflicts_resolved if hasattr(merge_record, 'conflicts_resolved') else 0,
            )
        except Exception as e:
            logger.error(f"Merge failed for task {task_id}: {e}")
            return MergeResult(
                success=False,
                task_id=task_id,
                branch=task.branch,
                error=str(e),
            )

    def sync(
        self,
        prd: PRDDocument,
        dry_run: bool = False,
    ) -> SyncResult:
        """
        Sync: merge all completed tasks and spawn the next wave.

        This is a convenience method that combines merge + spawn:
        1. Find all tasks marked as "done" in Claude Squad sessions
        2. Merge each one sequentially
        3. Spawn the next wave of tasks

        Args:
            prd: The PRD document
            dry_run: If True, show what would happen without acting

        Returns:
            SyncResult with details about merges and spawns
        """
        merge_results = []
        spawn_result = None

        # Find tasks that are running but have completed sessions
        # In CLI-driven mode, we rely on the user marking tasks done
        # For now, we just spawn the next wave

        if dry_run:
            # Show what would be spawned
            spawn_result = self.spawn(prd, dry_run=True)
            return SyncResult(
                merged_count=0,
                spawned_count=spawn_result.spawned_count,
                merge_results=[],
                spawn_result=spawn_result,
                dry_run=True,
            )

        # Spawn next wave
        spawn_result = self.spawn(prd)

        return SyncResult(
            merged_count=0,
            spawned_count=spawn_result.spawned_count,
            merge_results=merge_results,
            spawn_result=spawn_result,
        )

    def get_sessions_status(self, prd: PRDDocument) -> list[dict]:
        """
        Get status of all active sessions for this PRD.

        Returns list of session info dicts with:
        - task_id
        - session_id
        - status (running/done/failed)
        - idle_time (seconds since last activity)
        """
        backend_selector = BackendSelector.detect(self.working_dir)
        adapter = backend_selector.get_adapter()

        if adapter is None:
            return []

        # Get all active sessions from the adapter
        active_sessions = adapter.list_agents()
        session_map = {s.task_id: s for s in active_sessions}

        sessions = []
        for task in prd.tasks:
            if task.status == TaskStatus.RUNNING and task.agent_id:
                session = session_map.get(task.id)
                idle_time = None
                if task.started_at:
                    idle_time = (datetime.now(timezone.utc) - task.started_at).total_seconds()

                sessions.append({
                    "task_id": task.id,
                    "session_id": task.agent_id,
                    "status": session.status if session else "unknown",
                    "idle_time": idle_time,
                    "branch": task.branch,
                })

        return sessions
