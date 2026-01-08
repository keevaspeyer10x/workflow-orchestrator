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
    VerificationType
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

__version__ = "1.1.0"
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

    # Review
    "ReviewOrchestrator",
    "ReviewTier",
    "ReviewConfig",
    "ChangeContext",
    "SynthesizedReview",
    "review_changes",
    "get_review_tier",
    "get_default_review_config",
]
