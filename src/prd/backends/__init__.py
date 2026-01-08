"""
Worker backends for PRD execution.

Active backends:
- ManualBackend: Generates prompts for manual execution (Claude Web)

Deprecated backends (moved to _deprecated/):
- LocalBackend, ModalBackend, RenderBackend, GitHubActionsBackend, SequentialBackend
- WorkerPool

See ClaudeSquadAdapter for the new parallel execution model.
"""

from .base import WorkerBackendBase, WorkerHandle, WorkerStatus
from .manual import ManualBackend

__all__ = [
    "WorkerBackendBase",
    "WorkerHandle",
    "WorkerStatus",
    "ManualBackend",
]
