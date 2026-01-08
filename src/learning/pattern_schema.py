"""
Pattern memory schema models for conflict pattern learning.

This module defines the data models for recording and retrieving
conflict resolution patterns. The system learns from past resolutions
to suggest strategies for similar conflicts.

Pattern Lifecycle:
- ACTIVE: High confidence, used frequently
- SUGGESTING: Medium confidence, suggested but not auto-applied
- DORMANT: Low confidence, not matched recently
- DEPRECATED: Failed validation, kept for reference only
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class PatternState(Enum):
    """State of a conflict pattern in its lifecycle."""

    ACTIVE = "active"  # High confidence, auto-apply
    SUGGESTING = "suggesting"  # Medium confidence, suggest only
    DORMANT = "dormant"  # Low confidence, not used
    DEPRECATED = "deprecated"  # Failed repeatedly, reference only


class ValidationResult(Enum):
    """Result of validating a resolution."""

    PASSED = "passed"  # All validations passed
    FAILED = "failed"  # Validation failed
    PARTIAL = "partial"  # Some validations passed
    SKIPPED = "skipped"  # Validation was skipped


# Confidence thresholds for state transitions
ACTIVE_THRESHOLD = 0.5  # Above this = ACTIVE
SUGGESTING_THRESHOLD = 0.2  # Above this = SUGGESTING
# Below SUGGESTING_THRESHOLD = DORMANT

# Number of consecutive failures before deprecation
DEPRECATION_FAILURE_COUNT = 3


@dataclass
class ConflictPattern:
    """
    Records a conflict pattern with its characteristics and resolution history.

    This is the core data model for pattern memory. Each pattern represents
    a type of conflict that can be recognized and resolved similarly.
    """

    # Required fields
    pattern_hash: str  # Computed from conflict characteristics
    conflict_type: str  # textual, semantic, dependency, etc.
    resolution_strategy: str  # agent1_primary, merge, etc.

    # Optional fields with defaults
    files_involved: list[str] = field(default_factory=list)
    intent_categories: list[str] = field(default_factory=list)
    success_rate: float = 0.0
    last_used: Optional[datetime] = None
    use_count: int = 0
    created_at: Optional[datetime] = None
    confidence: float = 1.0  # Starts high, decays over time
    state: PatternState = PatternState.ACTIVE

    # Internal tracking
    _consecutive_failures: int = field(default=0, repr=False)

    def __post_init__(self):
        """Set defaults for timestamps if not provided."""
        now = datetime.now(timezone.utc)
        if self.created_at is None:
            self.created_at = now
        if self.last_used is None:
            self.last_used = now

    def record_outcome(self, success: bool) -> None:
        """
        Record the outcome of applying this pattern.

        Updates success rate, use count, and state based on outcome.
        Consecutive failures may lead to deprecation.

        Args:
            success: Whether the resolution succeeded
        """
        # Update use count and success rate
        old_total = self.use_count * self.success_rate
        self.use_count += 1
        new_total = old_total + (1.0 if success else 0.0)
        self.success_rate = new_total / self.use_count

        # Update timestamp
        self.last_used = datetime.now(timezone.utc)

        # Track consecutive failures
        if success:
            self._consecutive_failures = 0
            # Boost confidence on success
            self.confidence = min(1.0, self.confidence + 0.1)
        else:
            self._consecutive_failures += 1
            # Decrease confidence on failure
            self.confidence = max(0.0, self.confidence - 0.15)

        # Check for deprecation
        if self._consecutive_failures >= DEPRECATION_FAILURE_COUNT:
            self.state = PatternState.DEPRECATED
            return

        # Update state based on confidence
        self._update_state_from_confidence()

    def decay_confidence(self, amount: float) -> None:
        """
        Decay confidence by a given amount.

        Called periodically for patterns that haven't been used recently.

        Args:
            amount: How much to decay (0.0 to 1.0)
        """
        self.confidence = max(0.0, self.confidence - amount)
        self._update_state_from_confidence()

    def _update_state_from_confidence(self) -> None:
        """Update state based on current confidence level."""
        if self.state == PatternState.DEPRECATED:
            return  # Don't resurrect deprecated patterns

        if self.confidence >= ACTIVE_THRESHOLD:
            self.state = PatternState.ACTIVE
        elif self.confidence >= SUGGESTING_THRESHOLD:
            self.state = PatternState.SUGGESTING
        else:
            self.state = PatternState.DORMANT

    def to_dict(self) -> dict:
        """Serialize pattern to dictionary for storage."""
        return {
            "pattern_hash": self.pattern_hash,
            "conflict_type": self.conflict_type,
            "resolution_strategy": self.resolution_strategy,
            "files_involved": self.files_involved,
            "intent_categories": self.intent_categories,
            "success_rate": self.success_rate,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "use_count": self.use_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "confidence": self.confidence,
            "state": self.state.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConflictPattern":
        """Deserialize pattern from dictionary."""
        # Parse datetime fields
        last_used = None
        if data.get("last_used"):
            last_used = datetime.fromisoformat(data["last_used"])

        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        # Parse state enum
        state = PatternState(data.get("state", "active"))

        return cls(
            pattern_hash=data["pattern_hash"],
            conflict_type=data["conflict_type"],
            resolution_strategy=data["resolution_strategy"],
            files_involved=data.get("files_involved", []),
            intent_categories=data.get("intent_categories", []),
            success_rate=data.get("success_rate", 0.0),
            last_used=last_used,
            use_count=data.get("use_count", 0),
            created_at=created_at,
            confidence=data.get("confidence", 1.0),
            state=state,
        )


@dataclass
class PatternMatch:
    """
    Result of matching a conflict to known patterns.

    When a new conflict is analyzed, the system finds similar patterns
    and returns PatternMatch objects with similarity scores.
    """

    pattern: ConflictPattern  # The matched pattern
    similarity_score: float  # 0.0 to 1.0, how closely it matches
    matched_on: list[str]  # Factors that contributed to match
    suggested_strategy: str  # Strategy to try based on pattern

    # Threshold for considering a match "strong"
    STRONG_MATCH_THRESHOLD = 0.7

    def is_strong_match(self) -> bool:
        """Check if this is a strong enough match to auto-apply."""
        return self.similarity_score >= self.STRONG_MATCH_THRESHOLD

    def to_dict(self) -> dict:
        """Serialize match to dictionary."""
        return {
            "pattern": self.pattern.to_dict(),
            "similarity_score": self.similarity_score,
            "matched_on": self.matched_on,
            "suggested_strategy": self.suggested_strategy,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PatternMatch":
        """Deserialize match from dictionary."""
        return cls(
            pattern=ConflictPattern.from_dict(data["pattern"]),
            similarity_score=data["similarity_score"],
            matched_on=data["matched_on"],
            suggested_strategy=data["suggested_strategy"],
        )


@dataclass
class ResolutionOutcome:
    """
    Success/failure record for a pattern application.

    Records the result of applying a pattern to resolve a conflict.
    Used to update pattern success rates and detect problematic patterns.
    """

    pattern_hash: str  # Pattern that was applied
    conflict_id: str  # Unique ID of the conflict
    success: bool  # Whether resolution succeeded
    strategy_used: str  # Actual strategy applied
    validation_result: ValidationResult  # PASSED, FAILED, PARTIAL, SKIPPED

    # Optional fields
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """Serialize outcome to dictionary."""
        return {
            "pattern_hash": self.pattern_hash,
            "conflict_id": self.conflict_id,
            "success": self.success,
            "strategy_used": self.strategy_used,
            "validation_result": self.validation_result.value,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ResolutionOutcome":
        """Deserialize outcome from dictionary."""
        # Parse timestamp
        timestamp = datetime.now(timezone.utc)
        if data.get("timestamp"):
            timestamp = datetime.fromisoformat(data["timestamp"])

        # Parse validation result
        validation_result = ValidationResult(data.get("validation_result", "passed"))

        return cls(
            pattern_hash=data["pattern_hash"],
            conflict_id=data["conflict_id"],
            success=data["success"],
            strategy_used=data["strategy_used"],
            validation_result=validation_result,
            duration_seconds=data.get("duration_seconds", 0.0),
            error_message=data.get("error_message"),
            timestamp=timestamp,
        )
