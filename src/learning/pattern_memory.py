"""
Conflict pattern memory - the main interface for pattern-based resolution.

This is like git rerere for multi-agent conflicts:
- Records how conflicts were resolved
- Suggests resolutions for similar conflicts
- Tracks success rates to improve suggestions
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .pattern_schema import (
    ConflictPattern,
    PatternMatch,
    ResolutionOutcome,
    ValidationResult,
)
from .pattern_database import PatternDatabase
from .pattern_hasher import PatternHasher

logger = logging.getLogger(__name__)


@dataclass
class ResolutionSuggestion:
    """A suggested resolution strategy based on past patterns."""

    strategy: str  # Suggested resolution strategy
    confidence: float  # Confidence in the suggestion (0.0 to 1.0)
    based_on_pattern: str  # Hash of the pattern this is based on
    success_rate: float  # Historical success rate
    use_count: int  # How many times this pattern has been used


class ConflictPatternMemory:
    """
    The main interface for pattern-based conflict resolution.

    Like git rerere (reuse recorded resolution) for multi-agent conflicts:
    - Remembers how conflicts were resolved
    - Suggests strategies for similar conflicts
    - Learns from success/failure outcomes
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize pattern memory.

        Args:
            storage_dir: Directory for pattern storage (default: .claude/patterns)
        """
        self._storage_dir = storage_dir or Path(".claude/patterns")
        self._database = PatternDatabase(storage_dir=self._storage_dir)
        self._hasher = PatternHasher()

    def record_resolution(
        self,
        conflict_type: str,
        files_involved: list[str],
        intent_categories: list[str],
        resolution_strategy: str,
        success: bool,
        validation_result: ValidationResult,
        duration_seconds: float = 0.0,
        error_message: Optional[str] = None,
    ) -> str:
        """
        Record a conflict resolution outcome.

        Called by ResolutionPipeline after a resolution attempt.

        Args:
            conflict_type: Type of conflict (textual, semantic, etc.)
            files_involved: Files involved in the conflict
            intent_categories: Categories of intent
            resolution_strategy: Strategy that was used
            success: Whether the resolution succeeded
            validation_result: Result of validation
            duration_seconds: Time taken to resolve
            error_message: Error message if failed

        Returns:
            Pattern hash for the recorded resolution
        """
        # Compute pattern hash
        pattern_hash = self._compute_hash(
            conflict_type, files_involved, intent_categories
        )

        # Check if pattern already exists
        existing = self._database.lookup(pattern_hash)

        if existing:
            # Update existing pattern
            existing.record_outcome(success)
            self._database.store(existing)
            logger.debug(f"Updated existing pattern: {pattern_hash}")
        else:
            # Create new pattern
            pattern = ConflictPattern(
                pattern_hash=pattern_hash,
                conflict_type=conflict_type,
                resolution_strategy=resolution_strategy,
                files_involved=files_involved,
                intent_categories=intent_categories,
                success_rate=1.0 if success else 0.0,
                use_count=1,
            )
            self._database.store(pattern)
            logger.debug(f"Created new pattern: {pattern_hash}")

        # Record the outcome
        outcome = ResolutionOutcome(
            pattern_hash=pattern_hash,
            conflict_id=f"conflict-{datetime.now(timezone.utc).isoformat()}",
            success=success,
            strategy_used=resolution_strategy,
            validation_result=validation_result,
            duration_seconds=duration_seconds,
            error_message=error_message,
        )

        # Log outcome (could be stored separately for analytics)
        logger.info(
            f"Recorded resolution: pattern={pattern_hash[:8]}, "
            f"strategy={resolution_strategy}, success={success}"
        )

        return pattern_hash

    def suggest_resolution(
        self,
        conflict_type: str,
        files_involved: list[str],
        intent_categories: list[str],
        min_confidence: float = 0.3,
    ) -> Optional[ResolutionSuggestion]:
        """
        Suggest a resolution strategy based on past patterns.

        Consulted before generating new resolution candidates.

        Args:
            conflict_type: Type of conflict
            files_involved: Files in the conflict
            intent_categories: Intent categories
            min_confidence: Minimum confidence threshold

        Returns:
            ResolutionSuggestion if a good match is found, None otherwise
        """
        # Find similar patterns
        matches = self._database.find_similar(
            conflict_type=conflict_type,
            files_involved=files_involved,
            threshold=min_confidence,
        )

        if not matches:
            logger.debug("No matching patterns found for suggestion")
            return None

        # Find the best match (highest similarity with good success rate)
        best_match: Optional[PatternMatch] = None
        best_score = 0.0

        for match in matches:
            # Combine similarity with success rate for overall score
            combined_score = (
                match.similarity_score * 0.4 + match.pattern.success_rate * 0.6
            )
            if combined_score > best_score:
                best_score = combined_score
                best_match = match

        if best_match is None:
            return None

        pattern = best_match.pattern
        confidence = min(1.0, best_match.similarity_score * pattern.success_rate * 1.2)

        if confidence < min_confidence:
            return None

        logger.debug(
            f"Suggesting strategy '{pattern.resolution_strategy}' "
            f"based on pattern {pattern.pattern_hash[:8]} "
            f"(confidence={confidence:.2f})"
        )

        return ResolutionSuggestion(
            strategy=pattern.resolution_strategy,
            confidence=confidence,
            based_on_pattern=pattern.pattern_hash,
            success_rate=pattern.success_rate,
            use_count=pattern.use_count,
        )

    def get_success_rate(self, pattern_hash: str) -> float:
        """
        Get the success rate for a specific pattern.

        Args:
            pattern_hash: The pattern hash

        Returns:
            Success rate (0.0 to 1.0), or 0.0 if pattern not found
        """
        pattern = self._database.lookup(pattern_hash)
        if pattern is None:
            return 0.0
        return pattern.success_rate

    def count_patterns(self) -> int:
        """Get the total number of stored patterns."""
        return self._database.count()

    def prune_old_patterns(self, days: int = 90) -> int:
        """
        Remove patterns that haven't been used recently.

        Args:
            days: Remove patterns not used in this many days

        Returns:
            Number of patterns removed
        """
        return self._database.prune_stale(days)

    def _compute_hash(
        self,
        conflict_type: str,
        files_involved: list[str],
        intent_categories: list[str],
    ) -> str:
        """Compute hash for a conflict."""
        return self._hasher.compute_hash(
            conflict_type=conflict_type,
            files_involved=files_involved,
            intent_categories=intent_categories,
        )
