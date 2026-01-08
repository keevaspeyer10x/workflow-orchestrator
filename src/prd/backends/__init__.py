"""
Worker backends for PRD execution.

Available backends:
- LocalBackend: Runs Claude Code CLI locally
- ModalBackend: Runs on Modal serverless
- RenderBackend: Runs on Render containers
- GitHubActionsBackend: Runs via GitHub Actions
- ManualBackend: Generates prompts for manual execution (Claude Web)
"""

from .base import WorkerBackendBase, WorkerHandle, WorkerStatus
from .local import LocalBackend
from .manual import ManualBackend

# Cloud backends are imported conditionally to avoid dependency issues
__all__ = [
    "WorkerBackendBase",
    "WorkerHandle",
    "WorkerStatus",
    "LocalBackend",
    "ManualBackend",
]
