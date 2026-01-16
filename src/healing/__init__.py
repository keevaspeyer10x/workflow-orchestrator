"""Self-healing infrastructure for the workflow orchestrator.

This module provides automatic error detection, pattern matching, and fix application
to reduce manual intervention in workflow execution.

Phase 0: Abstraction Layer (complete)
- Environment detection
- Adapters (storage, git, cache, execution)

Phase 1: Detection, Fingerprinting & Config (complete)
- HealingConfig: Configuration from environment variables
- ErrorEvent: Unified error model
- Fingerprinter: Error deduplication via fingerprinting
- Detectors: WorkflowLog, Subprocess, Transcript, Hook
- ErrorAccumulator: Session-level error accumulation

Phase 2: Pattern Memory, Lookup & Security (current)
- SecurityScrubber: Remove secrets/PII before storage
- EmbeddingService: OpenAI embeddings for RAG
- HealingSupabaseClient: Supabase client for pattern storage
- PatternGenerator: LLM-based pattern generation
- HealingClient: Unified client with three-tier lookup
- PRESEEDED_PATTERNS: ~30 pre-built patterns for common errors
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

# Phase 2 imports
from .security import SecurityScrubber
from .embeddings import EmbeddingService
from .supabase_client import HealingSupabaseClient
from .pattern_generator import PatternGenerator
from .client import HealingClient, LookupResult
from .preseeded_patterns import PRESEEDED_PATTERNS, seed_patterns, match_preseeded

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
    # Phase 2 - Security
    "SecurityScrubber",
    # Phase 2 - Embeddings
    "EmbeddingService",
    # Phase 2 - Supabase Client
    "HealingSupabaseClient",
    # Phase 2 - Pattern Generator
    "PatternGenerator",
    # Phase 2 - Healing Client
    "HealingClient",
    "LookupResult",
    # Phase 2 - Pre-seeded Patterns
    "PRESEEDED_PATTERNS",
    "seed_patterns",
    "match_preseeded",
]
