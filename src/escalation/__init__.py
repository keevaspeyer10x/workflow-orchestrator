"""
Escalation Package

Phase 4: Human escalation system for complex conflicts.

Components:
- IssueCreator: Creates user-friendly GitHub issues
- ResponseHandler: Processes user responses
- TimeoutHandler: Handles SLA-based timeouts
- FeaturePorter: Ports features from losing options
- EscalationManager: Main orchestrator
"""

from .schema import (
    # Enums
    EscalationTrigger,
    EscalationPriority,
    EscalationStatus,
    # Data classes
    TimeoutPolicy,
    EscalationOption,
    TechnicalDetails,
    Escalation,
    EscalationResult,
    FeaturePort,
    # Constants
    TIMEOUT_POLICIES,
    ALWAYS_ESCALATE_TRIGGERS,
)

from .issue_creator import IssueCreator
from .response_handler import ResponseHandler, parse_github_comment
from .timeout_handler import TimeoutHandler
from .feature_porter import FeaturePorter, FeatureIdentifier
from .manager import EscalationManager, create_escalation

__all__ = [
    # Schema
    "EscalationTrigger",
    "EscalationPriority",
    "EscalationStatus",
    "TimeoutPolicy",
    "EscalationOption",
    "TechnicalDetails",
    "Escalation",
    "EscalationResult",
    "FeaturePort",
    "TIMEOUT_POLICIES",
    "ALWAYS_ESCALATE_TRIGGERS",
    # Components
    "IssueCreator",
    "ResponseHandler",
    "parse_github_comment",
    "TimeoutHandler",
    "FeaturePorter",
    "FeatureIdentifier",
    "EscalationManager",
    "create_escalation",
]
