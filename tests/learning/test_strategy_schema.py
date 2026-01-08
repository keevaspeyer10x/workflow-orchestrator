"""
Tests for strategy tracking schema models.

Tests cover:
- StrategyStats performance tracking
- StrategyContext per-context statistics
- StrategyRecommendation with confidence scoring
- Serialization/deserialization for all models
"""

import pytest
from datetime import datetime, timezone


class TestResolutionStrategy:
    """Tests for ResolutionStrategy enum."""

    def test_all_strategies_exist(self):
        """All expected strategies are defined."""
        from src.learning.strategy_schema import ResolutionStrategy

        assert ResolutionStrategy.AGENT1_PRIMARY.value == "agent1_primary"
        assert ResolutionStrategy.AGENT2_PRIMARY.value == "agent2_primary"
        assert ResolutionStrategy.MERGE.value == "merge"
        assert ResolutionStrategy.FRESH_SYNTHESIS.value == "fresh_synthesis"


class TestContextType:
    """Tests for ContextType enum."""

    def test_all_context_types_exist(self):
        """All expected context types are defined."""
        from src.learning.strategy_schema import ContextType

        assert ContextType.LANGUAGE.value == "language"
        assert ContextType.FRAMEWORK.value == "framework"
        assert ContextType.FILE_TYPE.value == "file_type"
        assert ContextType.CONFLICT_TYPE.value == "conflict_type"
        assert ContextType.FILE_PATTERN.value == "file_pattern"


class TestStrategyStats:
    """Tests for StrategyStats model."""

    def test_create_empty_stats(self):
        """Creates stats with defaults."""
        from src.learning.strategy_schema import ResolutionStrategy, StrategyStats

        stats = StrategyStats(strategy=ResolutionStrategy.MERGE)

        assert stats.strategy == ResolutionStrategy.MERGE
        assert stats.total_uses == 0
        assert stats.successful_uses == 0
        assert stats.failed_uses == 0
        assert stats.win_rate == 0.0
        assert stats.avg_duration == 0.0

    def test_record_successful_use(self):
        """Records a successful strategy use."""
        from src.learning.strategy_schema import ResolutionStrategy, StrategyStats

        stats = StrategyStats(strategy=ResolutionStrategy.MERGE)
        stats.record_use(success=True, duration=5.0)

        assert stats.total_uses == 1
        assert stats.successful_uses == 1
        assert stats.failed_uses == 0
        assert stats.win_rate == 1.0
        assert stats.total_duration == 5.0
        assert stats.first_used is not None
        assert stats.last_used is not None

    def test_record_failed_use(self):
        """Records a failed strategy use."""
        from src.learning.strategy_schema import ResolutionStrategy, StrategyStats

        stats = StrategyStats(strategy=ResolutionStrategy.AGENT1_PRIMARY)
        stats.record_use(success=False, duration=3.0)

        assert stats.total_uses == 1
        assert stats.successful_uses == 0
        assert stats.failed_uses == 1
        assert stats.win_rate == 0.0

    def test_win_rate_calculation(self):
        """Win rate is correctly calculated."""
        from src.learning.strategy_schema import ResolutionStrategy, StrategyStats

        stats = StrategyStats(strategy=ResolutionStrategy.MERGE)
        stats.record_use(success=True)
        stats.record_use(success=True)
        stats.record_use(success=False)
        stats.record_use(success=True)

        assert stats.total_uses == 4
        assert stats.successful_uses == 3
        assert stats.win_rate == pytest.approx(0.75)

    def test_avg_duration_calculation(self):
        """Average duration is correctly calculated."""
        from src.learning.strategy_schema import ResolutionStrategy, StrategyStats

        stats = StrategyStats(strategy=ResolutionStrategy.MERGE)
        stats.record_use(success=True, duration=2.0)
        stats.record_use(success=True, duration=4.0)
        stats.record_use(success=True, duration=6.0)

        assert stats.avg_duration == pytest.approx(4.0)

    def test_min_max_duration(self):
        """Tracks min and max duration."""
        from src.learning.strategy_schema import ResolutionStrategy, StrategyStats

        stats = StrategyStats(strategy=ResolutionStrategy.MERGE)
        stats.record_use(success=True, duration=5.0)
        stats.record_use(success=True, duration=2.0)
        stats.record_use(success=True, duration=8.0)

        assert stats.min_duration == pytest.approx(2.0)
        assert stats.max_duration == pytest.approx(8.0)

    def test_serialization(self):
        """Stats can be serialized and deserialized."""
        from src.learning.strategy_schema import ResolutionStrategy, StrategyStats

        stats = StrategyStats(strategy=ResolutionStrategy.MERGE)
        stats.record_use(success=True, duration=5.0)
        stats.record_use(success=False, duration=3.0)

        data = stats.to_dict()
        restored = StrategyStats.from_dict(data)

        assert restored.strategy == stats.strategy
        assert restored.total_uses == stats.total_uses
        assert restored.successful_uses == stats.successful_uses
        assert restored.win_rate == pytest.approx(stats.win_rate)


class TestStrategyContext:
    """Tests for StrategyContext model."""

    def test_create_context(self):
        """Creates a strategy context."""
        from src.learning.strategy_schema import ContextType, StrategyContext

        ctx = StrategyContext(
            context_type=ContextType.LANGUAGE,
            context_value="python",
        )

        assert ctx.context_type == ContextType.LANGUAGE
        assert ctx.context_value == "python"
        assert len(ctx.stats_by_strategy) == 0

    def test_get_or_create_stats(self):
        """Gets or creates stats for a strategy."""
        from src.learning.strategy_schema import (
            ContextType, StrategyContext, ResolutionStrategy
        )

        ctx = StrategyContext(
            context_type=ContextType.LANGUAGE,
            context_value="python",
        )

        stats = ctx.get_stats(ResolutionStrategy.MERGE)
        assert stats.strategy == ResolutionStrategy.MERGE
        assert stats.total_uses == 0

        # Same instance returned on second call
        stats2 = ctx.get_stats(ResolutionStrategy.MERGE)
        assert stats is stats2

    def test_record_use(self):
        """Records a strategy use in context."""
        from src.learning.strategy_schema import (
            ContextType, StrategyContext, ResolutionStrategy
        )

        ctx = StrategyContext(
            context_type=ContextType.LANGUAGE,
            context_value="python",
        )

        ctx.record_use(ResolutionStrategy.MERGE, success=True, duration=5.0)
        ctx.record_use(ResolutionStrategy.MERGE, success=True, duration=3.0)
        ctx.record_use(ResolutionStrategy.AGENT1_PRIMARY, success=False, duration=2.0)

        merge_stats = ctx.get_stats(ResolutionStrategy.MERGE)
        assert merge_stats.total_uses == 2
        assert merge_stats.win_rate == 1.0

        agent1_stats = ctx.get_stats(ResolutionStrategy.AGENT1_PRIMARY)
        assert agent1_stats.total_uses == 1
        assert agent1_stats.win_rate == 0.0

    def test_get_best_strategy(self):
        """Gets the best performing strategy."""
        from src.learning.strategy_schema import (
            ContextType, StrategyContext, ResolutionStrategy
        )

        ctx = StrategyContext(
            context_type=ContextType.LANGUAGE,
            context_value="python",
        )

        # Add uses for different strategies
        for _ in range(5):
            ctx.record_use(ResolutionStrategy.MERGE, success=True)
        for _ in range(5):
            ctx.record_use(ResolutionStrategy.AGENT1_PRIMARY, success=False)
        for _ in range(3):
            ctx.record_use(ResolutionStrategy.AGENT2_PRIMARY, success=True)

        best = ctx.get_best_strategy(min_uses=3)
        assert best == ResolutionStrategy.MERGE  # 100% win rate

    def test_get_best_strategy_respects_min_uses(self):
        """Best strategy requires minimum uses."""
        from src.learning.strategy_schema import (
            ContextType, StrategyContext, ResolutionStrategy
        )

        ctx = StrategyContext(
            context_type=ContextType.LANGUAGE,
            context_value="python",
        )

        # Only 1 use - below min_uses threshold
        ctx.record_use(ResolutionStrategy.MERGE, success=True)

        best = ctx.get_best_strategy(min_uses=3)
        assert best is None

    def test_serialization(self):
        """Context can be serialized and deserialized."""
        from src.learning.strategy_schema import (
            ContextType, StrategyContext, ResolutionStrategy
        )

        ctx = StrategyContext(
            context_type=ContextType.LANGUAGE,
            context_value="python",
        )
        ctx.record_use(ResolutionStrategy.MERGE, success=True, duration=5.0)
        ctx.record_use(ResolutionStrategy.AGENT1_PRIMARY, success=False, duration=3.0)

        data = ctx.to_dict()
        restored = StrategyContext.from_dict(data)

        assert restored.context_type == ctx.context_type
        assert restored.context_value == ctx.context_value
        assert len(restored.stats_by_strategy) == 2


class TestStrategyRecommendation:
    """Tests for StrategyRecommendation model."""

    def test_create_recommendation(self):
        """Creates a strategy recommendation."""
        from src.learning.strategy_schema import ResolutionStrategy, StrategyRecommendation

        rec = StrategyRecommendation(
            strategy=ResolutionStrategy.MERGE,
            confidence=0.85,
            reasoning="High success rate in similar contexts",
            historical_win_rate=0.92,
            sample_size=25,
        )

        assert rec.strategy == ResolutionStrategy.MERGE
        assert rec.confidence == 0.85
        assert rec.is_high_confidence
        assert rec.is_medium_confidence

    def test_confidence_thresholds(self):
        """Confidence thresholds work correctly."""
        from src.learning.strategy_schema import ResolutionStrategy, StrategyRecommendation

        high = StrategyRecommendation(
            strategy=ResolutionStrategy.MERGE,
            confidence=0.9,
        )
        assert high.is_high_confidence
        assert high.is_medium_confidence

        medium = StrategyRecommendation(
            strategy=ResolutionStrategy.MERGE,
            confidence=0.6,
        )
        assert not medium.is_high_confidence
        assert medium.is_medium_confidence

        low = StrategyRecommendation(
            strategy=ResolutionStrategy.MERGE,
            confidence=0.3,
        )
        assert not low.is_high_confidence
        assert not low.is_medium_confidence

    def test_with_alternatives(self):
        """Recommendations can include alternatives."""
        from src.learning.strategy_schema import ResolutionStrategy, StrategyRecommendation

        rec = StrategyRecommendation(
            strategy=ResolutionStrategy.MERGE,
            confidence=0.85,
            alternatives=[
                (ResolutionStrategy.AGENT1_PRIMARY, 0.6),
                (ResolutionStrategy.FRESH_SYNTHESIS, 0.3),
            ],
        )

        assert len(rec.alternatives) == 2
        assert rec.alternatives[0][0] == ResolutionStrategy.AGENT1_PRIMARY
        assert rec.alternatives[0][1] == 0.6

    def test_with_matching_contexts(self):
        """Recommendations can list matching contexts."""
        from src.learning.strategy_schema import ResolutionStrategy, StrategyRecommendation

        rec = StrategyRecommendation(
            strategy=ResolutionStrategy.MERGE,
            confidence=0.85,
            matching_contexts=["language:python", "framework:django"],
        )

        assert "language:python" in rec.matching_contexts
        assert "framework:django" in rec.matching_contexts

    def test_serialization(self):
        """Recommendation can be serialized and deserialized."""
        from src.learning.strategy_schema import ResolutionStrategy, StrategyRecommendation

        rec = StrategyRecommendation(
            strategy=ResolutionStrategy.MERGE,
            confidence=0.85,
            reasoning="High success rate",
            historical_win_rate=0.92,
            sample_size=25,
            matching_contexts=["language:python"],
            alternatives=[
                (ResolutionStrategy.AGENT1_PRIMARY, 0.6),
            ],
        )

        data = rec.to_dict()
        restored = StrategyRecommendation.from_dict(data)

        assert restored.strategy == rec.strategy
        assert restored.confidence == rec.confidence
        assert restored.reasoning == rec.reasoning
        assert restored.historical_win_rate == rec.historical_win_rate
        assert restored.sample_size == rec.sample_size
        assert len(restored.alternatives) == 1


class TestDefaultStrategyOrder:
    """Tests for default strategy order."""

    def test_default_order(self):
        """Default strategy order is sensible."""
        from src.learning.strategy_schema import (
            DEFAULT_STRATEGY_ORDER, ResolutionStrategy
        )

        # MERGE should be preferred by default
        assert DEFAULT_STRATEGY_ORDER[0] == ResolutionStrategy.MERGE

        # FRESH_SYNTHESIS should be last resort
        assert DEFAULT_STRATEGY_ORDER[-1] == ResolutionStrategy.FRESH_SYNTHESIS

        # All strategies should be in the order
        assert len(DEFAULT_STRATEGY_ORDER) == 4
