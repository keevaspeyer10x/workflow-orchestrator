"""Self-healing infrastructure for the workflow orchestrator.

This module provides automatic error detection, pattern matching, and fix application
to reduce manual intervention in workflow execution.

Phase 0: Abstraction Layer (complete)
- Environment detection
- Adapters (storage, git, cache, execution)

Phase 1: Detection, Fingerprinting & Config (current)
- HealingConfig: Configuration from environment variables
- ErrorEvent: Unified error model
- Fingerprinter: Error deduplication via fingerprinting
- Detectors: WorkflowLog, Subprocess, Transcript, Hook
- ErrorAccumulator: Session-level error accumulation
"""

from .environment import Environment, detect_environment, ENVIRONMENT
from .config import HealingConfig, get_config, reset_config
from .models import ErrorEvent, FixAction
from .fingerprint import Fingerprinter, FingerprintConfig
from .accumulator import ErrorAccumulator
from .detectors import (
    BaseDetector,
    WorkflowLogDetector,
    SubprocessDetector,
    TranscriptDetector,
    HookDetector,
)

__all__ = [
    # Phase 0
    "Environment",
    "detect_environment",
    "ENVIRONMENT",
    # Phase 1 - Config
    "HealingConfig",
    "get_config",
    "reset_config",
    # Phase 1 - Models
    "ErrorEvent",
    "FixAction",
    # Phase 1 - Fingerprinting
    "Fingerprinter",
    "FingerprintConfig",
    # Phase 1 - Detectors
    "BaseDetector",
    "WorkflowLogDetector",
    "SubprocessDetector",
    "TranscriptDetector",
    "HookDetector",
    # Phase 1 - Accumulator
    "ErrorAccumulator",
]
