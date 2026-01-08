"""
PRD Mode - Full PRD execution with multiple concurrent agents.

This module provides:
- PRD decomposition into tasks
- Wave-based conflict resolution
- Claude Squad integration for interactive sessions (PRD-001)
- Backend selection (interactive/batch/manual)
- Integration branch management
- Checkpoint PRs
- Rollback capability

Usage:
    from src.prd import PRDExecutor, PRDDocument, PRDConfig

    config = PRDConfig(enabled=True, worker_backend="auto")
    executor = PRDExecutor(config)
    result = await executor.execute_prd(prd_document)

    # Or use Claude Squad for interactive sessions
    from src.prd import ClaudeSquadAdapter, BackendSelector
    adapter = ClaudeSquadAdapter(working_dir)
    sessions = adapter.spawn_batch(tasks)
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

# Claude Squad Integration (PRD-001)
from .session_registry import SessionRegistry, SessionRecord
from .squad_capabilities import CapabilityDetector, SquadCapabilities
from .squad_adapter import (
    ClaudeSquadAdapter,
    SquadConfig,
    ClaudeSquadError,
    CapabilityError,
    SessionError,
)
from .backend_selector import BackendSelector, ExecutionMode

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
    # Worker pool (deprecated - use BackendSelector)
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
    # Claude Squad Integration (PRD-001)
    "SessionRegistry",
    "SessionRecord",
    "CapabilityDetector",
    "SquadCapabilities",
    "ClaudeSquadAdapter",
    "SquadConfig",
    "ClaudeSquadError",
    "CapabilityError",
    "SessionError",
    "BackendSelector",
    "ExecutionMode",
]
