"""
Worker pool for dynamic backend selection and auto-scaling.

The WorkerPool manages multiple worker backends and automatically
selects the best backend based on:
- Task count (small tasks → local, large → cloud)
- Available credentials (Modal, Render, etc.)
- Current load
"""

import logging
import os
from typing import Optional

from .schema import PRDConfig, WorkerBackend, JobMessage
from .backends.base import WorkerBackendBase, WorkerHandle, WorkerStatus
from .backends.local import LocalBackend
from .backends.manual import ManualBackend
from .backends.modal_worker import ModalBackend
from .backends.render import RenderBackend
from .backends.github_actions import GitHubActionsBackend
from .backends.sequential import SequentialBackend, is_inside_claude_code

logger = logging.getLogger(__name__)


class WorkerPool:
    """
    Manages worker backends and automatically selects the best one.

    Features:
    - Auto-detection of available backends
    - Dynamic backend selection based on workload
    - Auto-scaling across backends
    - Fallback handling
    """

    def __init__(self, config: PRDConfig):
        """
        Initialize the worker pool.

        Args:
            config: PRD configuration
        """
        self.config = config
        self._backends: dict[WorkerBackend, WorkerBackendBase] = {}
        self._available_backends: set[WorkerBackend] = set()
        self._active_handles: dict[str, WorkerHandle] = {}

        # Initialize backends
        self._init_backends()

    def _init_backends(self) -> None:
        """Initialize all configured backends."""
        # Check if inside Claude Code - use Sequential instead of Local
        self._inside_claude_code = is_inside_claude_code()
        if self._inside_claude_code:
            logger.info("Detected Claude Code environment - using SequentialBackend")
            self._sequential_backend = SequentialBackend()
            # Map LOCAL to use Sequential when inside Claude Code
            self._backends[WorkerBackend.LOCAL] = self._sequential_backend
            self._available_backends.add(WorkerBackend.LOCAL)
        else:
            self._sequential_backend = None
            # Local backend (always available)
            self._backends[WorkerBackend.LOCAL] = LocalBackend(
                max_parallel=self.config.backends.local.max_parallel,
                timeout_minutes=self.config.backends.local.timeout_minutes,
            )
            self._available_backends.add(WorkerBackend.LOCAL)

        # Manual backend (always available)
        self._backends[WorkerBackend.MANUAL] = ManualBackend()
        self._available_backends.add(WorkerBackend.MANUAL)

        # Modal backend (if configured)
        if self.config.backends.modal.enabled:
            modal = ModalBackend(
                max_parallel=self.config.backends.modal.max_parallel,
                timeout_minutes=self.config.backends.modal.timeout_minutes,
            )
            self._backends[WorkerBackend.MODAL] = modal
            if modal.is_available():
                self._available_backends.add(WorkerBackend.MODAL)

        # Render backend (if configured)
        if self.config.backends.render.enabled:
            render = RenderBackend(
                max_parallel=self.config.backends.render.max_parallel,
                instance_type=self.config.backends.render.instance_type,
                region=self.config.backends.render.region,
            )
            self._backends[WorkerBackend.RENDER] = render
            if render.is_available():
                self._available_backends.add(WorkerBackend.RENDER)

        # GitHub Actions backend (if configured)
        if self.config.backends.github_actions.enabled:
            gha = GitHubActionsBackend(
                max_parallel=self.config.backends.github_actions.max_parallel,
                workflow_file=self.config.backends.github_actions.workflow_file,
            )
            self._backends[WorkerBackend.GITHUB_ACTIONS] = gha
            if gha.is_available():
                self._available_backends.add(WorkerBackend.GITHUB_ACTIONS)

        logger.info(f"Available backends: {[b.value for b in self._available_backends]}")

    def _check_backend_availability(self) -> None:
        """Refresh backend availability (e.g., after env vars change)."""
        for backend_type, backend in self._backends.items():
            if backend.is_available():
                self._available_backends.add(backend_type)
            else:
                self._available_backends.discard(backend_type)

    def select_backend(self, task_count: int) -> WorkerBackend:
        """
        Select the best backend for the given task count.

        Selection priority:
        1. If task_count <= local.max_parallel → LOCAL
        2. If Modal available → MODAL (fastest scaling)
        3. If Render available → RENDER (persistent workers)
        4. If GitHub Actions available → GITHUB_ACTIONS
        5. If task_count > local.max_parallel → MANUAL (prompt user)
        6. Else → LOCAL (batch locally)

        Args:
            task_count: Number of tasks to execute

        Returns:
            Selected backend type
        """
        # Refresh availability
        self._check_backend_availability()

        local_capacity = self.config.backends.local.max_parallel

        # Small workload - use local
        if task_count <= local_capacity:
            return WorkerBackend.LOCAL

        # Large workload - prefer cloud
        if WorkerBackend.MODAL in self._available_backends:
            return WorkerBackend.MODAL

        if WorkerBackend.RENDER in self._available_backends:
            return WorkerBackend.RENDER

        if WorkerBackend.GITHUB_ACTIONS in self._available_backends:
            return WorkerBackend.GITHUB_ACTIONS

        # No cloud available
        if task_count > local_capacity:
            # Suggest manual or batch locally
            logger.warning(
                f"Task count ({task_count}) exceeds local capacity ({local_capacity}). "
                f"Consider setting up Modal or Render for cloud execution."
            )
            # Fall back to local (will batch)
            return WorkerBackend.LOCAL

        return WorkerBackend.LOCAL

    def _get_backend(self, backend_type: WorkerBackend) -> WorkerBackendBase:
        """Get a backend by type."""
        if backend_type not in self._backends:
            raise ValueError(f"Backend {backend_type} not configured")
        return self._backends[backend_type]

    def get_available_backends(self) -> list[WorkerBackend]:
        """Get list of available backends."""
        return list(self._available_backends)

    def spawn(self, job: JobMessage, backend: Optional[WorkerBackend] = None) -> WorkerHandle:
        """
        Spawn a worker for a job.

        Args:
            job: The job to execute
            backend: Specific backend to use (None for auto-select)

        Returns:
            Handle to the spawned worker
        """
        if backend is None:
            backend = self.select_backend(task_count=1)

        backend_impl = self._get_backend(backend)
        handle = backend_impl.spawn(job)

        self._active_handles[handle.worker_id] = handle
        return handle

    def get_status(self, handle: WorkerHandle) -> WorkerStatus:
        """Get the status of a worker."""
        backend = self._get_backend(handle.backend)
        return backend.get_status(handle)

    def active_worker_count(self) -> int:
        """Get count of active workers."""
        # Clean up completed workers
        active = {}
        for worker_id, handle in self._active_handles.items():
            status = self.get_status(handle)
            if status in (WorkerStatus.STARTING, WorkerStatus.RUNNING):
                active[worker_id] = handle

        self._active_handles = active
        return len(active)

    def auto_scale(self, queue_depth: int) -> None:
        """
        Scale workers based on queue depth.

        If queue has items and we have capacity, spawn more workers.
        If queue is empty, let workers finish naturally.

        Args:
            queue_depth: Number of items in the queue
        """
        if queue_depth == 0:
            return

        # Determine backend and capacity
        backend_type = self.select_backend(queue_depth)
        backend = self._get_backend(backend_type)
        max_workers = backend.max_parallel()

        current = self.active_worker_count()
        available = max_workers - current

        if available <= 0:
            logger.debug(f"At capacity ({current}/{max_workers}), waiting for slots")
            return

        # Log scaling action
        logger.info(
            f"Auto-scaling: queue_depth={queue_depth}, "
            f"current={current}, available={available}"
        )

    def get_backend_stats(self) -> dict[str, dict]:
        """Get statistics for all backends."""
        stats = {}
        for backend_type, backend in self._backends.items():
            stats[backend_type.value] = {
                "available": backend.is_available(),
                "max_parallel": backend.max_parallel(),
                "active": sum(
                    1 for h in self._active_handles.values()
                    if h.backend == backend_type
                    and self.get_status(h) in (WorkerStatus.STARTING, WorkerStatus.RUNNING)
                ),
            }
        return stats

    # Sequential mode helpers
    def is_sequential_mode(self) -> bool:
        """Check if running in sequential mode (inside Claude Code)."""
        return self._inside_claude_code

    def get_sequential_backend(self) -> Optional[SequentialBackend]:
        """Get the sequential backend if in sequential mode."""
        return self._sequential_backend
