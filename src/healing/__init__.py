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

Phase 2: Pattern Memory, Lookup & Security (complete)
- SecurityScrubber: Remove secrets/PII before storage
- EmbeddingService: OpenAI embeddings for RAG
- HealingSupabaseClient: Supabase client for pattern storage
- PatternGenerator: LLM-based pattern generation
- HealingClient: Unified client with three-tier lookup
- PRESEEDED_PATTERNS: ~30 pre-built patterns for common errors

Phase 3a: Validation Logic (complete)
- SafetyCategorizer: Categorize fix safety based on diff analysis
- MultiModelJudge: Multi-model consensus for fix approval
- ValidationPipeline: 3-phase validation (preflight, verification, approval)
- CostTracker: API cost tracking and limits
- CascadeDetector: Detect fix ping-pong cascades

Phase 3b: Fix Application (complete)
- ContextRetriever: Get file context for fixes
- FixApplicator: Environment-aware fix application

Phase 4: CLI & Workflow Integration (complete)
- cli_heal: CLI commands for healing system
- cli_issues: CLI commands for issue management
- hooks: Workflow engine integration hooks

Phase 5: Observability & Hardening (complete)
- metrics: Dashboard metrics collection
- circuit_breaker: Prevent runaway auto-fixing
- flakiness: Detect intermittent errors
- cache_optimizer: Local cache optimization
- backfill: Historical log processing
"""

from .environment import Environment, detect_environment, ENVIRONMENT, get_environment
from .config import HealingConfig, get_config, reset_config
from .models import ErrorEvent, FixAction, PatternContext
from .fingerprint import Fingerprinter, FingerprintConfig
from .context_extraction import (
    extract_context,
    detect_language,
    detect_error_category,
    wilson_score,
    calculate_relevance_score,
    is_eligible_for_cross_project,
)
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
from .client import HealingClient, LookupResult, SAME_PROJECT_THRESHOLD, CROSS_PROJECT_THRESHOLD
from .preseeded_patterns import PRESEEDED_PATTERNS, seed_patterns, match_preseeded

# Phase 3a imports
from .safety import SafetyCategory, SafetyCategorizer, SafetyAnalysis
from .costs import CostTracker, CostStatus, get_cost_tracker, reset_cost_tracker
from .cascade import CascadeDetector, AppliedFix, CascadeStatus, get_cascade_detector, reset_cascade_detector
from .judges import MultiModelJudge, JudgeModel, JudgeVote, JudgeResult, SuggestedFix
from .validation import (
    ValidationPipeline,
    ValidationPhase,
    ValidationResult,
    VerificationOutput,
    validate_fix,
)

# Phase 3b imports
from .context import ContextRetriever, FileContext, ContextBundle
from .applicator import FixApplicator, ApplyResult, VerifyResult

# Phase 4 imports
from .hooks import HealingHooks, get_hooks, reset_hooks, init_hooks

# Phase 5 imports
from .circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerConfig, get_circuit_breaker, reset_circuit_breaker
from .metrics import HealingMetrics, DashboardMetrics
from .flakiness import FlakinessDetector, FlakinessResult
from .cache_optimizer import CacheOptimizer
from .backfill import HistoricalBackfill

# Phase 7 - Scanner
from .scanner import PatternScanner, ScanState, ScanResult, ScanSummary
from .github_parser import GitHubIssueParser

__all__ = [
    # Phase 0
    "Environment",
    "detect_environment",
    "get_environment",
    "ENVIRONMENT",
    # Phase 1 - Config
    "HealingConfig",
    "get_config",
    "reset_config",
    # Phase 1 - Models
    "ErrorEvent",
    "FixAction",
    "PatternContext",
    # Phase 1 - Fingerprinting
    "Fingerprinter",
    "FingerprintConfig",
    # Phase 6 - Context Extraction
    "extract_context",
    "detect_language",
    "detect_error_category",
    "wilson_score",
    "calculate_relevance_score",
    "is_eligible_for_cross_project",
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
    "SAME_PROJECT_THRESHOLD",
    "CROSS_PROJECT_THRESHOLD",
    # Phase 2 - Pre-seeded Patterns
    "PRESEEDED_PATTERNS",
    "seed_patterns",
    "match_preseeded",
    # Phase 3a - Safety
    "SafetyCategory",
    "SafetyCategorizer",
    "SafetyAnalysis",
    # Phase 3a - Costs
    "CostTracker",
    "CostStatus",
    "get_cost_tracker",
    "reset_cost_tracker",
    # Phase 3a - Cascade Detection
    "CascadeDetector",
    "AppliedFix",
    "CascadeStatus",
    "get_cascade_detector",
    "reset_cascade_detector",
    # Phase 3a - Multi-Model Judges
    "MultiModelJudge",
    "JudgeModel",
    "JudgeVote",
    "JudgeResult",
    "SuggestedFix",
    # Phase 3a - Validation Pipeline
    "ValidationPipeline",
    "ValidationPhase",
    "ValidationResult",
    "VerificationOutput",
    "validate_fix",
    # Phase 3b - Context Retrieval
    "ContextRetriever",
    "FileContext",
    "ContextBundle",
    # Phase 3b - Fix Application
    "FixApplicator",
    "ApplyResult",
    "VerifyResult",
    # Phase 4 - Hooks
    "HealingHooks",
    "get_hooks",
    "reset_hooks",
    "init_hooks",
    # Phase 5 - Circuit Breaker
    "CircuitBreaker",
    "CircuitState",
    "CircuitBreakerConfig",
    "get_circuit_breaker",
    "reset_circuit_breaker",
    # Phase 5 - Metrics
    "HealingMetrics",
    "DashboardMetrics",
    # Phase 5 - Flakiness Detection
    "FlakinessDetector",
    "FlakinessResult",
    # Phase 5 - Cache Optimizer
    "CacheOptimizer",
    # Phase 5 - Backfill
    "HistoricalBackfill",
    # Phase 7 - Scanner
    "PatternScanner",
    "ScanState",
    "ScanResult",
    "ScanSummary",
    "GitHubIssueParser",
]
