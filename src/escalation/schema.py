"""
Escalation Schema Definitions

Data models for the human escalation system:
- EscalationTrigger: Reasons for escalation
- EscalationOption: A choice presented to the user
- Escalation: Full escalation request
- EscalationResult: Outcome of escalation
- TimeoutPolicy: SLA configuration
"""

from dataclasses import dataclass, field
from typing import Optional, Literal
from datetime import datetime, timezone
from enum import Enum

from ..resolution.schema import ResolutionCandidate, IntentAnalysis
from ..conflict.pipeline import PipelineResult


# ============================================================================
# Escalation Triggers
# ============================================================================

class EscalationTrigger(str, Enum):
    """Reasons why an escalation was triggered."""
    # Risk flags (always escalate)
    SECURITY_SENSITIVE = "security_sensitive_files"
    AUTH_CHANGES = "auth_changes"
    DB_MIGRATIONS = "db_migrations"
    PUBLIC_API_CHANGES = "public_api_changes"
    PAYMENT_PROCESSING = "payment_processing"

    # Confidence issues
    LOW_INTENT_CONFIDENCE = "low_intent_confidence"
    CONFLICTING_INTENTS = "conflicting_intents"
    NO_PASSING_CANDIDATES = "no_passing_candidates"
    NO_VIABLE_CANDIDATES = "no_viable_candidates"

    # Quality issues
    TESTS_REMOVED = "tests_removed"
    TESTS_WEAKENED = "tests_weakened"
    COVERAGE_DECREASED = "coverage_decreased"

    # Multiple good options
    CANDIDATES_TOO_SIMILAR = "candidates_too_similar_in_score"
    DIFFERENT_TRADEOFFS = "different_tradeoffs"

    # Complexity
    MANY_FILES_CHANGED = "many_files_changed"
    ARCHITECTURAL_CHANGES = "architectural_changes"


# Always escalate these triggers (never auto-resolve)
ALWAYS_ESCALATE_TRIGGERS = {
    EscalationTrigger.SECURITY_SENSITIVE,
    EscalationTrigger.AUTH_CHANGES,
    EscalationTrigger.DB_MIGRATIONS,
    EscalationTrigger.PUBLIC_API_CHANGES,
    EscalationTrigger.PAYMENT_PROCESSING,
    EscalationTrigger.LOW_INTENT_CONFIDENCE,
    EscalationTrigger.CONFLICTING_INTENTS,
    EscalationTrigger.NO_PASSING_CANDIDATES,
    EscalationTrigger.TESTS_REMOVED,
    EscalationTrigger.TESTS_WEAKENED,
    EscalationTrigger.COVERAGE_DECREASED,
}


# ============================================================================
# Escalation Priority
# ============================================================================

class EscalationPriority(str, Enum):
    """Priority level for escalations."""
    CRITICAL = "critical"  # Security, payment - immediate attention
    HIGH = "high"          # Auth, DB migrations
    STANDARD = "standard"  # Normal conflicts
    LOW = "low"            # Minor decisions


# ============================================================================
# Escalation Status
# ============================================================================

class EscalationStatus(str, Enum):
    """Current status of an escalation."""
    PENDING = "pending"           # Awaiting user response
    AWAITING_INFO = "awaiting_info"  # User asked for more info
    RESOLVED = "resolved"         # User responded with selection
    AUTO_SELECTED = "auto_selected"  # Timed out, auto-selected
    TIMEOUT = "timeout"           # Timed out, no auto-select allowed
    CANCELLED = "cancelled"       # Escalation no longer needed


# ============================================================================
# Timeout Policy
# ============================================================================

@dataclass
class TimeoutPolicy:
    """Timeout policy for an escalation priority level."""
    reminder_hours: int
    timeout_hours: int
    auto_select: bool  # Can auto-select on timeout?
    notify_channels: list[str] = field(default_factory=lambda: ["github"])


# Default timeout policies
TIMEOUT_POLICIES = {
    EscalationPriority.CRITICAL: TimeoutPolicy(
        reminder_hours=4,
        timeout_hours=24,
        auto_select=False,  # Never auto-select critical
        notify_channels=["github", "slack", "email"],
    ),
    EscalationPriority.HIGH: TimeoutPolicy(
        reminder_hours=12,
        timeout_hours=48,
        auto_select=False,
        notify_channels=["github", "slack"],
    ),
    EscalationPriority.STANDARD: TimeoutPolicy(
        reminder_hours=24,
        timeout_hours=72,
        auto_select=True,
        notify_channels=["github"],
    ),
    EscalationPriority.LOW: TimeoutPolicy(
        reminder_hours=48,
        timeout_hours=168,  # 1 week
        auto_select=True,
        notify_channels=["github"],
    ),
}


# ============================================================================
# Escalation Option
# ============================================================================

@dataclass
class EscalationOption:
    """A choice presented to the user in an escalation."""
    option_id: str  # "A", "B", "C", etc.
    title: str
    description: str  # Plain English explanation
    tradeoffs: list[str] = field(default_factory=list)
    risk_level: Literal["low", "medium", "high"] = "medium"
    is_recommended: bool = False

    # Link to resolution candidate
    candidate_id: Optional[str] = None
    candidate: Optional[ResolutionCandidate] = None

    # For custom options
    requires_input: bool = False


@dataclass
class TechnicalDetails:
    """Technical details for users who want more info."""
    files_involved: list[str] = field(default_factory=list)
    code_diff: str = ""
    test_results: str = ""
    architectural_impact: str = ""


# ============================================================================
# Escalation
# ============================================================================

@dataclass
class Escalation:
    """
    A complete escalation request.

    Created when auto-resolution fails and human input is needed.
    """
    escalation_id: str

    # What triggered this escalation
    triggers: list[EscalationTrigger] = field(default_factory=list)
    trigger_reason: str = ""

    # Priority and status
    priority: EscalationPriority = EscalationPriority.STANDARD
    status: EscalationStatus = EscalationStatus.PENDING

    # Context from resolution attempt
    detection_result: Optional[PipelineResult] = None
    intent_analysis: Optional[IntentAnalysis] = None
    candidates: list[ResolutionCandidate] = field(default_factory=list)

    # Options presented to user
    options: list[EscalationOption] = field(default_factory=list)

    # Recommendation
    recommendation: Optional[str] = None  # "A", "B", etc.
    recommendation_reason: str = ""
    confidence: float = 0.0

    # Technical details (available on request)
    technical_details: Optional[TechnicalDetails] = None

    # Timing
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reminder_sent_at: Optional[datetime] = None
    reminder_count: int = 0
    resolved_at: Optional[datetime] = None

    # User response
    response: Optional[str] = None
    response_at: Optional[datetime] = None

    # GitHub references
    issue_number: Optional[int] = None
    issue_url: Optional[str] = None
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None

    @property
    def age_in_hours(self) -> float:
        """Get age of escalation in hours."""
        now = datetime.now(timezone.utc)
        delta = now - self.created_at
        return delta.total_seconds() / 3600

    @property
    def timeout_policy(self) -> TimeoutPolicy:
        """Get timeout policy for this escalation."""
        return TIMEOUT_POLICIES.get(
            self.priority,
            TIMEOUT_POLICIES[EscalationPriority.STANDARD]
        )

    def has_risk_flag(self, flag: str) -> bool:
        """Check if escalation has a specific risk flag."""
        trigger_values = [t.value for t in self.triggers]
        return flag in trigger_values or any(flag in t for t in trigger_values)


# ============================================================================
# Escalation Result
# ============================================================================

@dataclass
class EscalationResult:
    """Result of processing an escalation response."""
    resolved: bool
    awaiting_response: bool = False

    # Winner (if resolved)
    winner: Optional[EscalationOption] = None
    winning_candidate: Optional[ResolutionCandidate] = None

    # Ported features from losing options
    ported_features: list[str] = field(default_factory=list)

    # For custom response
    custom: bool = False
    custom_preference: str = ""

    # PR created
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None

    # Auto-selection info
    auto_selected: bool = False
    auto_select_reason: str = ""


# ============================================================================
# Feature Port
# ============================================================================

@dataclass
class FeaturePort:
    """A feature ported from a losing option to the winning one."""
    from_option: str
    to_option: str
    feature_description: str
    files_modified: list[str] = field(default_factory=list)
    success: bool = False
    error: Optional[str] = None
