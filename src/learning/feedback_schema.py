"""
Agent Feedback Schema Definitions

Data models for agent feedback and proactive guidance:
- FeedbackType: Types of feedback an agent can provide
- AgentFeedback: Feedback from an agent about a resolution
- GuidanceMessage: Proactive guidance sent to agents
- ConflictHint: Hint about potential conflicts
- PatternSuggestion: Suggested code patterns
"""

from dataclasses import dataclass, field
from typing import Optional, Literal
from datetime import datetime, timezone
from enum import Enum


# ============================================================================
# Feedback Types
# ============================================================================

class FeedbackType(str, Enum):
    """Types of feedback an agent can provide about a resolution."""
    # Resolution feedback
    CONFLICT_HINT = "conflict_hint"           # Hint about potential conflict
    PATTERN_SUGGESTION = "pattern_suggestion"  # Suggested code pattern
    RESOLUTION_OUTCOME = "resolution_outcome"  # Result of a resolution attempt

    # Work feedback
    APPROACH_WORKED = "approach_worked"        # An approach that worked well
    APPROACH_FAILED = "approach_failed"        # An approach that didn't work

    # Context feedback
    MISSING_CONTEXT = "missing_context"        # Agent needed info not available
    UNCLEAR_INTENT = "unclear_intent"          # Task intent was ambiguous

    # System feedback
    TOOLING_ISSUE = "tooling_issue"           # Issue with tools/infrastructure
    TIMING_ISSUE = "timing_issue"             # Timing or coordination problem


class FeedbackSeverity(str, Enum):
    """Severity level for feedback items."""
    INFO = "info"           # Informational, for learning
    WARNING = "warning"     # Worth noting, may cause issues
    CRITICAL = "critical"   # Significant issue that affected outcome


# ============================================================================
# Agent Feedback
# ============================================================================

@dataclass
class ConflictHint:
    """Hint about a potential or actual conflict."""
    files: list[str]                         # Files involved
    description: str                          # Description of the conflict
    other_agent_id: Optional[str] = None     # ID of other agent involved
    conflict_type: Literal["textual", "semantic", "interface", "behavioral"] = "textual"
    evidence: str = ""                        # Code/diff showing the conflict
    suggested_resolution: str = ""            # How this could be resolved


@dataclass
class PatternSuggestion:
    """Suggested code pattern based on learnings."""
    pattern_name: str                         # Short name for the pattern
    description: str                          # Detailed description
    context: str                              # When to apply this pattern
    example_code: str = ""                    # Example implementation
    source_files: list[str] = field(default_factory=list)  # Where pattern was derived from
    confidence: Literal["high", "medium", "low"] = "medium"


@dataclass
class AgentFeedback:
    """
    Feedback from an agent about a resolution or task.

    Agents provide feedback to help the learning system understand:
    - What worked or didn't work during resolution
    - Suggested improvements for similar future situations
    - Context about conflicts and their resolution

    This feedback is used to:
    - Improve future conflict detection
    - Generate proactive guidance for agents
    - Build a knowledge base of patterns and anti-patterns
    """
    feedback_id: str
    agent_id: str

    # Core feedback
    feedback_type: FeedbackType
    severity: FeedbackSeverity = FeedbackSeverity.INFO

    # What worked / didn't work
    what_worked: list[str] = field(default_factory=list)
    what_didnt_work: list[str] = field(default_factory=list)

    # Suggested improvements
    suggested_improvements: list[str] = field(default_factory=list)

    # Context about the conflict (if applicable)
    conflict_hint: Optional[ConflictHint] = None
    pattern_suggestion: Optional[PatternSuggestion] = None

    # Related artifacts
    resolution_id: Optional[str] = None
    workflow_id: Optional[str] = None
    task_description: Optional[str] = None
    files_involved: list[str] = field(default_factory=list)

    # Metrics
    resolution_time_seconds: Optional[int] = None
    retry_count: int = 0

    # Raw context
    raw_context: dict = field(default_factory=dict)

    # Timestamp
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def has_actionable_insights(self) -> bool:
        """Check if this feedback has actionable insights."""
        return (
            len(self.suggested_improvements) > 0 or
            self.conflict_hint is not None or
            self.pattern_suggestion is not None
        )

    @property
    def is_success_feedback(self) -> bool:
        """Check if this is feedback about a successful outcome."""
        return (
            self.feedback_type in (FeedbackType.APPROACH_WORKED, FeedbackType.RESOLUTION_OUTCOME) and
            len(self.what_worked) > 0 and
            len(self.what_didnt_work) == 0
        )

    def summary(self) -> str:
        """Generate a summary of this feedback."""
        parts = [f"[{self.feedback_type.value}] {self.severity.value}"]

        if self.what_worked:
            parts.append(f"Worked: {', '.join(self.what_worked[:2])}")
        if self.what_didnt_work:
            parts.append(f"Failed: {', '.join(self.what_didnt_work[:2])}")
        if self.suggested_improvements:
            parts.append(f"Suggestions: {len(self.suggested_improvements)}")

        return " | ".join(parts)


# ============================================================================
# Guidance Types
# ============================================================================

class GuidanceType(str, Enum):
    """Types of proactive guidance that can be sent to agents."""
    # Conflict prevention
    CONFLICT_WARNING = "conflict_warning"     # Warn about potential conflict
    FILE_LOCK_HINT = "file_lock_hint"        # Suggest file locking
    COORDINATION_HINT = "coordination_hint"   # Suggest coordination with other agent

    # Pattern guidance
    USE_PATTERN = "use_pattern"              # Recommend using a pattern
    AVOID_PATTERN = "avoid_pattern"          # Recommend avoiding a pattern

    # Context sharing
    CONTEXT_UPDATE = "context_update"        # Share relevant context
    TASK_CLARIFICATION = "task_clarification"  # Clarify task requirements

    # Priority/scheduling
    PRIORITY_UPDATE = "priority_update"      # Task priority changed
    SEQUENCE_HINT = "sequence_hint"          # Suggest task sequence


class GuidanceUrgency(str, Enum):
    """Urgency level for guidance messages."""
    LOW = "low"             # Apply when convenient
    MEDIUM = "medium"       # Should apply soon
    HIGH = "high"           # Apply immediately
    BLOCKING = "blocking"   # Must apply before proceeding


# ============================================================================
# Guidance Message
# ============================================================================

@dataclass
class GuidanceMessage:
    """
    Proactive guidance sent to agents.

    The learning system generates guidance messages to help agents:
    - Avoid conflicts before they occur
    - Apply patterns that worked in similar situations
    - Coordinate with other agents effectively

    Guidance is generated based on:
    - Historical feedback from agents
    - Current workflow state
    - Detected patterns in agent work
    """
    # Required fields (no defaults)
    guidance_id: str
    target_agent_id: str
    guidance_type: GuidanceType
    title: str
    message: str

    # Optional fields (with defaults)
    urgency: GuidanceUrgency = GuidanceUrgency.MEDIUM
    reason: str = ""                          # Why this guidance is being given
    evidence: list[str] = field(default_factory=list)  # Supporting evidence

    # Related feedback (if derived from feedback)
    source_feedback_ids: list[str] = field(default_factory=list)

    # Conflict-specific guidance
    conflict_hint: Optional[ConflictHint] = None
    files_to_avoid: list[str] = field(default_factory=list)
    agents_to_coordinate: list[str] = field(default_factory=list)

    # Pattern-specific guidance
    pattern_suggestion: Optional[PatternSuggestion] = None
    anti_patterns: list[str] = field(default_factory=list)

    # Context
    workflow_id: Optional[str] = None
    related_task: Optional[str] = None

    # Acknowledgment tracking
    acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    applied: bool = False
    applied_at: Optional[datetime] = None
    ignored_reason: Optional[str] = None

    # Timing
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None

    @property
    def is_active(self) -> bool:
        """Check if this guidance is still active."""
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        return not self.applied

    @property
    def is_conflict_related(self) -> bool:
        """Check if this guidance is related to conflict prevention."""
        return self.guidance_type in (
            GuidanceType.CONFLICT_WARNING,
            GuidanceType.FILE_LOCK_HINT,
            GuidanceType.COORDINATION_HINT,
        )

    def acknowledge(self) -> None:
        """Mark this guidance as acknowledged."""
        self.acknowledged = True
        self.acknowledged_at = datetime.now(timezone.utc)

    def mark_applied(self) -> None:
        """Mark this guidance as applied."""
        self.applied = True
        self.applied_at = datetime.now(timezone.utc)

    def mark_ignored(self, reason: str) -> None:
        """Mark this guidance as ignored with a reason."""
        self.applied = False
        self.ignored_reason = reason


# ============================================================================
# Feedback Collection
# ============================================================================

@dataclass
class FeedbackBatch:
    """A batch of feedback items for processing."""
    batch_id: str
    feedback_items: list[AgentFeedback] = field(default_factory=list)

    # Metadata
    workflow_id: Optional[str] = None
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def by_type(self) -> dict[FeedbackType, list[AgentFeedback]]:
        """Group feedback items by type."""
        result: dict[FeedbackType, list[AgentFeedback]] = {}
        for item in self.feedback_items:
            if item.feedback_type not in result:
                result[item.feedback_type] = []
            result[item.feedback_type].append(item)
        return result

    @property
    def by_agent(self) -> dict[str, list[AgentFeedback]]:
        """Group feedback items by agent."""
        result: dict[str, list[AgentFeedback]] = {}
        for item in self.feedback_items:
            if item.agent_id not in result:
                result[item.agent_id] = []
            result[item.agent_id].append(item)
        return result

    @property
    def actionable_items(self) -> list[AgentFeedback]:
        """Get feedback items with actionable insights."""
        return [f for f in self.feedback_items if f.has_actionable_insights]


@dataclass
class GuidanceBatch:
    """A batch of guidance messages to send."""
    batch_id: str
    guidance_messages: list[GuidanceMessage] = field(default_factory=list)

    # Metadata
    workflow_id: Optional[str] = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def by_agent(self) -> dict[str, list[GuidanceMessage]]:
        """Group guidance messages by target agent."""
        result: dict[str, list[GuidanceMessage]] = {}
        for msg in self.guidance_messages:
            if msg.target_agent_id not in result:
                result[msg.target_agent_id] = []
            result[msg.target_agent_id].append(msg)
        return result

    @property
    def urgent_messages(self) -> list[GuidanceMessage]:
        """Get high-urgency or blocking messages."""
        return [
            m for m in self.guidance_messages
            if m.urgency in (GuidanceUrgency.HIGH, GuidanceUrgency.BLOCKING)
        ]

    @property
    def conflict_related(self) -> list[GuidanceMessage]:
        """Get conflict-related guidance messages."""
        return [m for m in self.guidance_messages if m.is_conflict_related]
