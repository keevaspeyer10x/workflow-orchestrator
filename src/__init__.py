"""
Workflow Orchestrator - AI Workflow Enforcement System

A framework for enforcing multi-phase workflows with active verification,
analytics, automated learning, and multi-model code review.
"""

from .schema import (
    WorkflowDef,
    WorkflowState,
    WorkflowEvent,
    ItemStatus,
    PhaseStatus,
    WorkflowStatus,
    EventType,
    VerificationType,
    StepType,
)

from .engine import WorkflowEngine
from .analytics import WorkflowAnalytics
from .learning_engine import LearningEngine

# Multi-model review system
from .review import (
    ReviewOrchestrator,
    ReviewTier,
    ReviewConfig,
    ChangeContext,
    SynthesizedReview,
    review_changes,
    get_review_tier,
    get_default_config as get_default_review_config,
)

# Step enforcement system
from .enforcement import (
    SkipDecision,
    CodeAnalysisEvidence,
    EdgeCaseEvidence,
    SpecReviewEvidence,
    TestPlanEvidence,
    GateResult,
    HardGateExecutor,
    validate_skip_reasoning,
    validate_evidence_depth,
    get_evidence_schema,
)

__version__ = "1.2.0"
__all__ = [
    # Workflow
    "WorkflowDef",
    "WorkflowState",
    "WorkflowEvent",
    "WorkflowEngine",
    "WorkflowAnalytics",
    "LearningEngine",
    "ItemStatus",
    "PhaseStatus",
    "WorkflowStatus",
    "EventType",
    "VerificationType",
    "StepType",

    # Review
    "ReviewOrchestrator",
    "ReviewTier",
    "ReviewConfig",
    "ChangeContext",
    "SynthesizedReview",
    "review_changes",
    "get_review_tier",
    "get_default_review_config",

    # Enforcement
    "SkipDecision",
    "CodeAnalysisEvidence",
    "EdgeCaseEvidence",
    "SpecReviewEvidence",
    "TestPlanEvidence",
    "GateResult",
    "HardGateExecutor",
    "validate_skip_reasoning",
    "validate_evidence_depth",
    "get_evidence_schema",
]
