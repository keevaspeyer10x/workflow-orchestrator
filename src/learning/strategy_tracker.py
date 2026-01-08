"""
Strategy tracker for monitoring resolution strategy performance.

This module provides the StrategyTracker class which records strategy
attempts and provides recommendations based on historical data.

Usage:
    tracker = StrategyTracker()
    tracker.record_attempt("merge", {"language": "python"}, success=True, duration=5.0)
    recommendation = tracker.recommend({"language": "python"})
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .strategy_schema import (
    ResolutionStrategy,
    ContextType,
    StrategyStats,
    StrategyContext,
    StrategyRecommendation,
    DEFAULT_STRATEGY_ORDER,
)

logger = logging.getLogger(__name__)


# Default storage path
DEFAULT_STATS_PATH = Path(".claude/strategy_stats.json")

# Minimum sample size for confident recommendations
MIN_SAMPLE_SIZE = 3


@dataclass
class TrackerState:
    """Persistent state for the strategy tracker."""

    # Global stats per strategy
    global_stats: dict[str, StrategyStats] = field(default_factory=dict)

    # Per-context stats
    contexts: dict[str, StrategyContext] = field(default_factory=dict)

    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Serialize state to dictionary."""
        return {
            "global_stats": {
                key: stats.to_dict()
                for key, stats in self.global_stats.items()
            },
            "contexts": {
                key: ctx.to_dict()
                for key, ctx in self.contexts.items()
            },
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TrackerState":
        """Deserialize state from dictionary."""
        global_stats = {}
        for key, stats_data in data.get("global_stats", {}).items():
            global_stats[key] = StrategyStats.from_dict(stats_data)

        contexts = {}
        for key, ctx_data in data.get("contexts", {}).items():
            contexts[key] = StrategyContext.from_dict(ctx_data)

        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        updated_at = None
        if data.get("updated_at"):
            updated_at = datetime.fromisoformat(data["updated_at"])

        return cls(
            global_stats=global_stats,
            contexts=contexts,
            created_at=created_at,
            updated_at=updated_at,
        )


class StrategyTracker:
    """
    Tracks resolution strategy performance over time.

    Records which strategies succeed/fail in different contexts,
    and provides recommendations based on historical performance.

    Storage: JSON file at .claude/strategy_stats.json (by default)
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize the strategy tracker.

        Args:
            storage_path: Path to storage file (default: .claude/strategy_stats.json)
        """
        self.storage_path = storage_path or DEFAULT_STATS_PATH
        self._state: Optional[TrackerState] = None

    def _load_state(self) -> TrackerState:
        """Load state from disk or create new."""
        if self._state is not None:
            return self._state

        if self.storage_path.exists():
            try:
                with open(self.storage_path) as f:
                    data = json.load(f)
                self._state = TrackerState.from_dict(data)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load strategy stats: {e}")
                self._state = TrackerState(created_at=datetime.now(timezone.utc))
        else:
            self._state = TrackerState(created_at=datetime.now(timezone.utc))

        return self._state

    def _save_state(self) -> None:
        """Save state to disk."""
        if self._state is None:
            return

        self._state.updated_at = datetime.now(timezone.utc)

        # Ensure parent directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.storage_path, 'w') as f:
            json.dump(self._state.to_dict(), f, indent=2)

    def record_attempt(
        self,
        strategy: str,
        context: dict[str, str],
        success: bool,
        duration: float = 0.0,
    ) -> None:
        """
        Record a strategy attempt.

        Args:
            strategy: Strategy name (e.g., "merge", "agent1_primary")
            context: Context dictionary (e.g., {"language": "python"})
            success: Whether the resolution succeeded
            duration: Time taken in seconds
        """
        state = self._load_state()

        # Parse strategy enum
        try:
            strategy_enum = ResolutionStrategy(strategy)
        except ValueError:
            logger.warning(f"Unknown strategy: {strategy}")
            return

        # Update global stats
        if strategy not in state.global_stats:
            state.global_stats[strategy] = StrategyStats(strategy=strategy_enum)
        state.global_stats[strategy].record_use(success, duration)

        # Update per-context stats
        for key, value in context.items():
            try:
                ctx_type = ContextType(key)
            except ValueError:
                logger.debug(f"Unknown context type: {key}")
                continue

            ctx_key = f"{key}:{value}"
            if ctx_key not in state.contexts:
                state.contexts[ctx_key] = StrategyContext(
                    context_type=ctx_type,
                    context_value=value,
                )
            state.contexts[ctx_key].record_use(strategy_enum, success, duration)

        self._save_state()

    def get_stats(self, strategy: str) -> Optional[StrategyStats]:
        """
        Get statistics for a specific strategy.

        Args:
            strategy: Strategy name

        Returns:
            StrategyStats or None if not found
        """
        state = self._load_state()
        return state.global_stats.get(strategy)

    def get_all_stats(self) -> dict[str, StrategyStats]:
        """
        Get statistics for all strategies.

        Returns:
            Dictionary mapping strategy names to stats
        """
        state = self._load_state()
        return dict(state.global_stats)

    def recommend(
        self,
        context: Optional[dict[str, str]] = None,
        min_sample_size: int = MIN_SAMPLE_SIZE,
    ) -> StrategyRecommendation:
        """
        Recommend a strategy based on historical performance.

        Args:
            context: Context dictionary for context-aware recommendation
            min_sample_size: Minimum uses required to consider a strategy

        Returns:
            StrategyRecommendation with confidence score
        """
        state = self._load_state()

        # Collect candidate strategies with scores
        candidates: list[tuple[ResolutionStrategy, float, int, str]] = []

        # Check context-specific performance first
        matching_contexts = []
        if context:
            for key, value in context.items():
                ctx_key = f"{key}:{value}"
                if ctx_key in state.contexts:
                    ctx = state.contexts[ctx_key]
                    matching_contexts.append(ctx_key)

                    best = ctx.get_best_strategy(min_uses=min_sample_size)
                    if best:
                        stats = ctx.get_stats(best)
                        # Weight context-specific higher
                        score = stats.win_rate * 1.2
                        candidates.append((best, score, stats.total_uses, ctx_key))

        # Add global stats
        for strategy_name, stats in state.global_stats.items():
            if stats.total_uses >= min_sample_size:
                try:
                    strategy_enum = ResolutionStrategy(strategy_name)
                    # Check if already added from context
                    if not any(c[0] == strategy_enum for c in candidates):
                        candidates.append((
                            strategy_enum,
                            stats.win_rate,
                            stats.total_uses,
                            "global",
                        ))
                except ValueError:
                    continue

        # Sort by score (descending)
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Build recommendation
        if candidates:
            best = candidates[0]
            strategy, score, sample_size, source = best

            # Calculate confidence based on sample size and win rate
            confidence = min(0.95, score * (1 - 1 / (sample_size + 1)))

            # Build alternatives
            alternatives = [
                (c[0], min(0.95, c[1] * (1 - 1 / (c[2] + 1))))
                for c in candidates[1:4]  # Top 3 alternatives
            ]

            return StrategyRecommendation(
                strategy=strategy,
                confidence=confidence,
                reasoning=f"Based on {sample_size} uses with {score*100:.1f}% success rate",
                historical_win_rate=score,
                sample_size=sample_size,
                matching_contexts=matching_contexts,
                alternatives=alternatives,
            )

        # No data - return default with low confidence
        return StrategyRecommendation(
            strategy=DEFAULT_STRATEGY_ORDER[0],
            confidence=0.3,
            reasoning="Default strategy (no historical data available)",
            historical_win_rate=0.0,
            sample_size=0,
            matching_contexts=[],
            alternatives=[
                (s, 0.2) for s in DEFAULT_STRATEGY_ORDER[1:4]
            ],
        )

    def clear(self) -> None:
        """Clear all tracked data."""
        self._state = TrackerState(created_at=datetime.now(timezone.utc))
        if self.storage_path.exists():
            self.storage_path.unlink()
