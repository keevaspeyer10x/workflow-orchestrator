"""
PRD Mode - Full PRD execution with multiple concurrent agents.

This module provides:
- PRD decomposition into tasks
- Wave-based conflict resolution
- Tmux-based interactive sessions (PRD-004)
- Backend selection (interactive/batch/manual)
- Integration branch management
- Checkpoint PRs
- Rollback capability

Usage:
    from src.prd import PRDExecutor, PRDDocument, PRDConfig

    config = PRDConfig(enabled=True, worker_backend="auto")
    executor = PRDExecutor(config)
    result = await executor.execute_prd(prd_document)

    # Or use BackendSelector for interactive sessions
    from src.prd import BackendSelector
    selector = BackendSelector.detect(working_dir)
    adapter = selector.get_adapter()  # TmuxAdapter or SubprocessAdapter
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
from ._deprecated.worker_pool import WorkerPool  # Deprecated - use ClaudeSquadAdapter
from .integration import IntegrationBranchManager, MergeRecord, CheckpointPR
from .wave_resolver import WaveResolver, WaveResolutionResult
from .spawn_scheduler import SpawnScheduler, SpawnWave, ScheduleResult, TaskOverlapPrediction
from .executor import PRDExecutor, PRDExecutionResult, SpawnResult, MergeResult, SyncResult

# Session management (PRD-004)
from .session_registry import SessionRegistry, SessionRecord
from .tmux_adapter import TmuxAdapter
from .subprocess_adapter import SubprocessAdapter
from .backend_selector import BackendSelector, ExecutionMode

# Deprecated Claude Squad Integration (PRD-001) - kept for backwards compatibility
from ._deprecated.squad_capabilities import CapabilityDetector, SquadCapabilities
from ._deprecated.squad_adapter import (
    ClaudeSquadAdapter,
    SquadConfig,
    ClaudeSquadError,
    CapabilityError,
    SessionError,
)

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
    # Spawn scheduling (PRD-001 Phase 2)
    "SpawnScheduler",
    "SpawnWave",
    "ScheduleResult",
    "TaskOverlapPrediction",
    # Executor
    "PRDExecutor",
    "PRDExecutionResult",
    "SpawnResult",
    "MergeResult",
    "SyncResult",
    # Session management (PRD-004)
    "SessionRegistry",
    "SessionRecord",
    "TmuxAdapter",
    "SubprocessAdapter",
    "BackendSelector",
    "ExecutionMode",
    # Deprecated Claude Squad Integration (PRD-001)
    "CapabilityDetector",
    "SquadCapabilities",
    "ClaudeSquadAdapter",
    "SquadConfig",
    "ClaudeSquadError",
    "CapabilityError",
    "SessionError",
]
