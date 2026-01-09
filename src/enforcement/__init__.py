"""
Step Enforcement Module

Provides enforcement mechanisms for workflow steps:
- Hard gates: Commands run by orchestrator, cannot be skipped
- Evidence requirements: Structured output proving engagement
- Skip reasoning validation: Substantive justification for skips
"""

from .evidence import (
    CodeAnalysisEvidence,
    EdgeCaseEvidence,
    SpecReviewEvidence,
    TestPlanEvidence,
    EVIDENCE_SCHEMAS,
    get_evidence_schema,
    validate_evidence_depth,
)
from .skip import (
    SkipDecision,
    validate_skip_reasoning,
    SHALLOW_PATTERNS,
    MIN_SKIP_REASON_LENGTH,
)
from .gates import (
    GateResult,
    HardGateExecutor,
)

__all__ = [
    # Evidence
    "CodeAnalysisEvidence",
    "EdgeCaseEvidence",
    "SpecReviewEvidence",
    "TestPlanEvidence",
    "EVIDENCE_SCHEMAS",
    "get_evidence_schema",
    "validate_evidence_depth",
    # Skip
    "SkipDecision",
    "validate_skip_reasoning",
    "SHALLOW_PATTERNS",
    "MIN_SKIP_REASON_LENGTH",
    # Gates
    "GateResult",
    "HardGateExecutor",
]
