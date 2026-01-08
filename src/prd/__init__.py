"""
PRD Mode - Full PRD execution with multiple concurrent agents.

This module provides:
- PRD decomposition into tasks
- Wave-based conflict resolution
- Multi-backend worker pool (local, Modal, Render, GitHub Actions, manual)
- Integration branch management
- Checkpoint PRs
- Rollback capability

Usage:
    from src.prd import PRDExecutor, PRDDocument, PRDConfig

    config = PRDConfig(enabled=True, worker_backend="auto")
    executor = PRDExecutor(config)
    result = await executor.execute_prd(prd_document)
"""

from .schema import (
    # Enums
    TaskStatus,
    WorkerBackend,
    JobStatus,
    # Config
    PRDConfig,
    BackendConfig,
    LocalBackendConfig,
    ModalBackendConfig,
    RenderBackendConfig,
    # Task models
    PRDTask,
    PRDDocument,
    TaskResult,
    # Queue models
    JobMessage,
)

from .queue import FileJobQueue
from .worker_pool import WorkerPool
from .integration import IntegrationBranchManager, MergeRecord, CheckpointPR
from .wave_resolver import WaveResolver, WaveResolutionResult
from .executor import PRDExecutor, PRDExecutionResult

__all__ = [
    # Enums
    "TaskStatus",
    "WorkerBackend",
    "JobStatus",
    # Config
    "PRDConfig",
    "BackendConfig",
    "LocalBackendConfig",
    "ModalBackendConfig",
    "RenderBackendConfig",
    # Task models
    "PRDTask",
    "PRDDocument",
    "TaskResult",
    # Queue models
    "JobMessage",
    # Queue
    "FileJobQueue",
    # Worker pool
    "WorkerPool",
    # Integration
    "IntegrationBranchManager",
    "MergeRecord",
    "CheckpointPR",
    # Wave resolution
    "WaveResolver",
    "WaveResolutionResult",
    # Executor
    "PRDExecutor",
    "PRDExecutionResult",
]
