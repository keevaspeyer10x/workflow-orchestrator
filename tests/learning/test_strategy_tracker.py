"""
Tests for StrategyTracker class.

Tests cover:
- Recording strategy attempts
- Getting stats for strategies
- Context-aware recommendations
- Persistence to disk
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime


class TestStrategyTrackerBasics:
    """Basic tests for StrategyTracker."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "strategy_stats.json"

    @pytest.fixture
    def tracker(self, temp_storage):
        """Create a StrategyTracker with temp storage."""
        from src.learning.strategy_tracker import StrategyTracker
        return StrategyTracker(storage_path=temp_storage)

    def test_create_tracker(self, tracker):
        """Can create a tracker."""
        assert tracker is not None
        assert tracker.get_all_stats() == {}

    def test_record_attempt_creates_stats(self, tracker):
        """Recording an attempt creates stats."""
        tracker.record_attempt("merge", {}, success=True)

        stats = tracker.get_stats("merge")
        assert stats is not None
        assert stats.total_uses == 1
        assert stats.successful_uses == 1

    def test_record_multiple_attempts(self, tracker):
        """Records multiple attempts correctly."""
        tracker.record_attempt("merge", {}, success=True, duration=5.0)
        tracker.record_attempt("merge", {}, success=True, duration=3.0)
        tracker.record_attempt("merge", {}, success=False, duration=2.0)

        stats = tracker.get_stats("merge")
        assert stats.total_uses == 3
        assert stats.successful_uses == 2
        assert stats.win_rate == pytest.approx(2/3)

    def test_get_stats_returns_none_for_unknown(self, tracker):
        """Returns None for unknown strategy."""
        stats = tracker.get_stats("unknown")
        assert stats is None

    def test_get_all_stats(self, tracker):
        """Gets all strategy stats."""
        tracker.record_attempt("merge", {}, success=True)
        tracker.record_attempt("agent1_primary", {}, success=False)

        all_stats = tracker.get_all_stats()
        assert "merge" in all_stats
        assert "agent1_primary" in all_stats
        assert len(all_stats) == 2


class TestStrategyTrackerContext:
    """Tests for context-aware tracking."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "strategy_stats.json"

    @pytest.fixture
    def tracker(self, temp_storage):
        """Create a StrategyTracker with temp storage."""
        from src.learning.strategy_tracker import StrategyTracker
        return StrategyTracker(storage_path=temp_storage)

    def test_record_with_context(self, tracker):
        """Records context with attempt."""
        tracker.record_attempt(
            "merge",
            {"language": "python", "framework": "django"},
            success=True,
        )

        # Should have global stats
        stats = tracker.get_stats("merge")
        assert stats.total_uses == 1

    def test_recommend_uses_context(self, tracker):
        """Recommendations consider context."""
        # Python context: merge works well
        for _ in range(5):
            tracker.record_attempt(
                "merge",
                {"language": "python"},
                success=True,
            )

        # Python context: agent1_primary works poorly
        for _ in range(5):
            tracker.record_attempt(
                "agent1_primary",
                {"language": "python"},
                success=False,
            )

        # Recommendation for Python should prefer merge
        rec = tracker.recommend({"language": "python"})
        from src.learning.strategy_schema import ResolutionStrategy
        assert rec.strategy == ResolutionStrategy.MERGE
        assert "language:python" in rec.matching_contexts


class TestStrategyTrackerRecommendations:
    """Tests for strategy recommendations."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "strategy_stats.json"

    @pytest.fixture
    def tracker(self, temp_storage):
        """Create a StrategyTracker with temp storage."""
        from src.learning.strategy_tracker import StrategyTracker
        return StrategyTracker(storage_path=temp_storage)

    def test_recommend_without_data(self, tracker):
        """Returns default recommendation without data."""
        rec = tracker.recommend()

        from src.learning.strategy_schema import ResolutionStrategy
        assert rec.strategy == ResolutionStrategy.MERGE  # Default
        assert rec.confidence < 0.5  # Low confidence
        assert "no historical data" in rec.reasoning.lower()

    def test_recommend_with_data(self, tracker):
        """Returns data-driven recommendation with data."""
        # Record successful merge attempts
        for _ in range(10):
            tracker.record_attempt("merge", {}, success=True)

        rec = tracker.recommend()

        from src.learning.strategy_schema import ResolutionStrategy
        assert rec.strategy == ResolutionStrategy.MERGE
        assert rec.confidence > 0.5
        assert rec.sample_size == 10

    def test_recommend_selects_best_strategy(self, tracker):
        """Selects strategy with best win rate."""
        # Merge: 3 successes
        for _ in range(3):
            tracker.record_attempt("merge", {}, success=True)

        # Agent1: 3 failures
        for _ in range(3):
            tracker.record_attempt("agent1_primary", {}, success=False)

        # Agent2: 3 successes, 1 failure
        for _ in range(3):
            tracker.record_attempt("agent2_primary", {}, success=True)
        tracker.record_attempt("agent2_primary", {}, success=False)

        rec = tracker.recommend()

        from src.learning.strategy_schema import ResolutionStrategy
        assert rec.strategy == ResolutionStrategy.MERGE  # 100% win rate

    def test_recommend_respects_min_sample_size(self, tracker):
        """Respects minimum sample size."""
        # Only 1 use - below min sample
        tracker.record_attempt("merge", {}, success=True)

        rec = tracker.recommend(min_sample_size=3)

        # Should return default with low confidence
        assert rec.confidence < 0.5

    def test_recommend_includes_alternatives(self, tracker):
        """Includes alternative strategies."""
        for _ in range(5):
            tracker.record_attempt("merge", {}, success=True)
        for _ in range(4):
            tracker.record_attempt("agent1_primary", {}, success=True)
        for _ in range(3):
            tracker.record_attempt("agent2_primary", {}, success=True)

        rec = tracker.recommend()

        assert len(rec.alternatives) > 0


class TestStrategyTrackerPersistence:
    """Tests for persistence."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "strategy_stats.json"

    def test_persists_to_disk(self, temp_storage):
        """Tracker persists data to disk."""
        from src.learning.strategy_tracker import StrategyTracker

        tracker1 = StrategyTracker(storage_path=temp_storage)
        tracker1.record_attempt("merge", {}, success=True)

        # Create new tracker with same path
        tracker2 = StrategyTracker(storage_path=temp_storage)
        stats = tracker2.get_stats("merge")

        assert stats is not None
        assert stats.total_uses == 1

    def test_handles_missing_file(self, temp_storage):
        """Handles missing storage file gracefully."""
        from src.learning.strategy_tracker import StrategyTracker

        tracker = StrategyTracker(storage_path=temp_storage)
        stats = tracker.get_all_stats()

        assert stats == {}

    def test_handles_corrupt_file(self, temp_storage):
        """Handles corrupt storage file gracefully."""
        from src.learning.strategy_tracker import StrategyTracker

        # Write corrupt data
        temp_storage.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_storage, 'w') as f:
            f.write("not valid json")

        tracker = StrategyTracker(storage_path=temp_storage)
        stats = tracker.get_all_stats()

        # Should recover with empty state
        assert stats == {}

    def test_clear_removes_data(self, temp_storage):
        """Clear removes all tracked data."""
        from src.learning.strategy_tracker import StrategyTracker

        tracker = StrategyTracker(storage_path=temp_storage)
        tracker.record_attempt("merge", {}, success=True)
        tracker.clear()

        assert tracker.get_all_stats() == {}
        assert not temp_storage.exists()


class TestStrategyTrackerDuration:
    """Tests for duration tracking."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "strategy_stats.json"

    @pytest.fixture
    def tracker(self, temp_storage):
        """Create a StrategyTracker with temp storage."""
        from src.learning.strategy_tracker import StrategyTracker
        return StrategyTracker(storage_path=temp_storage)

    def test_tracks_duration(self, tracker):
        """Tracks duration of attempts."""
        tracker.record_attempt("merge", {}, success=True, duration=5.0)
        tracker.record_attempt("merge", {}, success=True, duration=3.0)

        stats = tracker.get_stats("merge")
        assert stats.avg_duration == pytest.approx(4.0)
        assert stats.min_duration == pytest.approx(3.0)
        assert stats.max_duration == pytest.approx(5.0)


class TestStrategyTrackerInvalidInput:
    """Tests for handling invalid input."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "strategy_stats.json"

    @pytest.fixture
    def tracker(self, temp_storage):
        """Create a StrategyTracker with temp storage."""
        from src.learning.strategy_tracker import StrategyTracker
        return StrategyTracker(storage_path=temp_storage)

    def test_ignores_unknown_strategy(self, tracker):
        """Ignores unknown strategy names."""
        tracker.record_attempt("not_a_real_strategy", {}, success=True)

        # Should not create stats
        stats = tracker.get_all_stats()
        assert len(stats) == 0

    def test_ignores_unknown_context_type(self, tracker):
        """Ignores unknown context types."""
        tracker.record_attempt(
            "merge",
            {"not_a_context": "value"},
            success=True,
        )

        # Should still record global stats
        stats = tracker.get_stats("merge")
        assert stats.total_uses == 1
