"""
Strategy tracking schema models for resolution strategy optimization.

This module defines models for tracking resolution strategy performance
across different contexts. The system learns which strategies work best
for specific conflict types, file patterns, and languages.

Strategy Types:
- agent1_primary: Agent 1's changes take precedence
- agent2_primary: Agent 2's changes take precedence
- merge: Intelligent merge of both changes
- fresh_synthesis: AI generates new resolution from scratch
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ResolutionStrategy(Enum):
    """Available resolution strategies."""

    AGENT1_PRIMARY = "agent1_primary"
    AGENT2_PRIMARY = "agent2_primary"
    MERGE = "merge"
    FRESH_SYNTHESIS = "fresh_synthesis"


class ContextType(Enum):
    """Types of context that can influence strategy selection."""

    LANGUAGE = "language"  # Python, JavaScript, etc.
    FRAMEWORK = "framework"  # React, Django, etc.
    FILE_TYPE = "file_type"  # Config, test, source, etc.
    CONFLICT_TYPE = "conflict_type"  # Textual, semantic, etc.
    FILE_PATTERN = "file_pattern"  # Path patterns


@dataclass
class StrategyStats:
    """
    Statistics for a resolution strategy's performance.

    Tracks win rate, usage count, and timing data for a specific
    strategy across all or filtered contexts.
    """

    strategy: ResolutionStrategy

    # Performance metrics
    total_uses: int = 0
    successful_uses: int = 0
    failed_uses: int = 0

    # Timing metrics (in seconds)
    total_duration: float = 0.0
    min_duration: float = float('inf')
    max_duration: float = 0.0

    # Timestamps
    first_used: Optional[datetime] = None
    last_used: Optional[datetime] = None

    @property
    def win_rate(self) -> float:
        """Calculate the success rate (0.0 to 1.0)."""
        if self.total_uses == 0:
            return 0.0
        return self.successful_uses / self.total_uses

    @property
    def avg_duration(self) -> float:
        """Calculate average duration in seconds."""
        if self.total_uses == 0:
            return 0.0
        return self.total_duration / self.total_uses

    def record_use(self, success: bool, duration: float = 0.0) -> None:
        """
        Record a strategy use.

        Args:
            success: Whether the resolution succeeded
            duration: Time taken in seconds
        """
        now = datetime.now(timezone.utc)

        self.total_uses += 1
        if success:
            self.successful_uses += 1
        else:
            self.failed_uses += 1

        # Update timing
        self.total_duration += duration
        if duration > 0:
            self.min_duration = min(self.min_duration, duration)
            self.max_duration = max(self.max_duration, duration)

        # Update timestamps
        if self.first_used is None:
            self.first_used = now
        self.last_used = now

    def to_dict(self) -> dict:
        """Serialize stats to dictionary."""
        return {
            "strategy": self.strategy.value,
            "total_uses": self.total_uses,
            "successful_uses": self.successful_uses,
            "failed_uses": self.failed_uses,
            "win_rate": self.win_rate,
            "total_duration": self.total_duration,
            "avg_duration": self.avg_duration,
            "min_duration": self.min_duration if self.min_duration != float('inf') else None,
            "max_duration": self.max_duration,
            "first_used": self.first_used.isoformat() if self.first_used else None,
            "last_used": self.last_used.isoformat() if self.last_used else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyStats":
        """Deserialize stats from dictionary."""
        first_used = None
        if data.get("first_used"):
            first_used = datetime.fromisoformat(data["first_used"])

        last_used = None
        if data.get("last_used"):
            last_used = datetime.fromisoformat(data["last_used"])

        min_duration = data.get("min_duration")
        if min_duration is None:
            min_duration = float('inf')

        return cls(
            strategy=ResolutionStrategy(data["strategy"]),
            total_uses=data.get("total_uses", 0),
            successful_uses=data.get("successful_uses", 0),
            failed_uses=data.get("failed_uses", 0),
            total_duration=data.get("total_duration", 0.0),
            min_duration=min_duration,
            max_duration=data.get("max_duration", 0.0),
            first_used=first_used,
            last_used=last_used,
        )


@dataclass
class StrategyContext:
    """
    Context information for when/where a strategy works best.

    Records the conditions under which a strategy has historically
    performed well, enabling context-aware strategy selection.
    """

    context_type: ContextType
    context_value: str  # e.g., "python", "react", "test_*.py"

    # Strategy-specific stats for this context
    stats_by_strategy: dict[str, StrategyStats] = field(default_factory=dict)

    def get_stats(self, strategy: ResolutionStrategy) -> StrategyStats:
        """Get or create stats for a strategy in this context."""
        key = strategy.value
        if key not in self.stats_by_strategy:
            self.stats_by_strategy[key] = StrategyStats(strategy=strategy)
        return self.stats_by_strategy[key]

    def record_use(
        self,
        strategy: ResolutionStrategy,
        success: bool,
        duration: float = 0.0,
    ) -> None:
        """Record a strategy use in this context."""
        stats = self.get_stats(strategy)
        stats.record_use(success, duration)

    def get_best_strategy(self, min_uses: int = 3) -> Optional[ResolutionStrategy]:
        """
        Get the best performing strategy for this context.

        Args:
            min_uses: Minimum uses required to consider a strategy

        Returns:
            Best strategy or None if no strategies meet criteria
        """
        best_strategy = None
        best_win_rate = 0.0

        for key, stats in self.stats_by_strategy.items():
            if stats.total_uses >= min_uses and stats.win_rate > best_win_rate:
                best_win_rate = stats.win_rate
                best_strategy = stats.strategy

        return best_strategy

    def to_dict(self) -> dict:
        """Serialize context to dictionary."""
        return {
            "context_type": self.context_type.value,
            "context_value": self.context_value,
            "stats_by_strategy": {
                key: stats.to_dict()
                for key, stats in self.stats_by_strategy.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyContext":
        """Deserialize context from dictionary."""
        stats_by_strategy = {}
        for key, stats_data in data.get("stats_by_strategy", {}).items():
            stats_by_strategy[key] = StrategyStats.from_dict(stats_data)

        return cls(
            context_type=ContextType(data["context_type"]),
            context_value=data["context_value"],
            stats_by_strategy=stats_by_strategy,
        )


@dataclass
class StrategyRecommendation:
    """
    Recommended strategy with confidence score.

    Returned by the strategy optimizer when suggesting which
    resolution strategy to use for a given conflict.
    """

    strategy: ResolutionStrategy
    confidence: float  # 0.0 to 1.0

    # Why this strategy is recommended
    reasoning: str = ""

    # Supporting data
    historical_win_rate: float = 0.0
    sample_size: int = 0
    matching_contexts: list[str] = field(default_factory=list)

    # Alternative strategies ranked by preference
    alternatives: list[tuple[ResolutionStrategy, float]] = field(default_factory=list)

    # Confidence thresholds
    HIGH_CONFIDENCE = 0.8
    MEDIUM_CONFIDENCE = 0.5

    @property
    def is_high_confidence(self) -> bool:
        """Check if this is a high-confidence recommendation."""
        return self.confidence >= self.HIGH_CONFIDENCE

    @property
    def is_medium_confidence(self) -> bool:
        """Check if this is at least medium confidence."""
        return self.confidence >= self.MEDIUM_CONFIDENCE

    def to_dict(self) -> dict:
        """Serialize recommendation to dictionary."""
        return {
            "strategy": self.strategy.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "historical_win_rate": self.historical_win_rate,
            "sample_size": self.sample_size,
            "matching_contexts": self.matching_contexts,
            "alternatives": [
                {"strategy": s.value, "confidence": c}
                for s, c in self.alternatives
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyRecommendation":
        """Deserialize recommendation from dictionary."""
        alternatives = []
        for alt in data.get("alternatives", []):
            alternatives.append((
                ResolutionStrategy(alt["strategy"]),
                alt["confidence"],
            ))

        return cls(
            strategy=ResolutionStrategy(data["strategy"]),
            confidence=data["confidence"],
            reasoning=data.get("reasoning", ""),
            historical_win_rate=data.get("historical_win_rate", 0.0),
            sample_size=data.get("sample_size", 0),
            matching_contexts=data.get("matching_contexts", []),
            alternatives=alternatives,
        )


# Default strategy order when no historical data available
DEFAULT_STRATEGY_ORDER = [
    ResolutionStrategy.MERGE,
    ResolutionStrategy.AGENT1_PRIMARY,
    ResolutionStrategy.AGENT2_PRIMARY,
    ResolutionStrategy.FRESH_SYNTHESIS,
]
