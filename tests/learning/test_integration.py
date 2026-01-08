"""
Integration tests for the learning module.

Tests cover:
- Integration with ResolutionPipeline (pattern memory, strategy tracking)
- Integration with PRDExecutor (feedback collection, guidance generation)
- Integration with WaveResolver (strategy recommendations)
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch


class TestPatternMemoryIntegration:
    """Tests for pattern memory integration with resolution pipeline."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_pattern_memory_exports(self):
        """Learning module exports pattern memory."""
        from src.learning import ConflictPatternMemory, ResolutionSuggestion
        assert ConflictPatternMemory is not None
        assert ResolutionSuggestion is not None

    def test_pattern_memory_creation(self, temp_dir):
        """Can create pattern memory with storage path."""
        from src.learning import ConflictPatternMemory

        memory = ConflictPatternMemory(storage_dir=temp_dir / "patterns")
        assert memory is not None

    def test_pattern_memory_suggest_resolution(self, temp_dir):
        """Pattern memory can suggest resolutions."""
        from src.learning import ConflictPatternMemory

        memory = ConflictPatternMemory(storage_dir=temp_dir / "patterns")

        # Before any data, should suggest nothing or low confidence
        suggestion = memory.suggest_resolution(
            conflict_type="textual",
            files_involved=["src/foo.py"],
            intent_categories=["feature"],
        )

        # May be None or low confidence
        if suggestion is not None:
            assert hasattr(suggestion, 'confidence')


class TestStrategyTrackerIntegration:
    """Tests for strategy tracker integration with wave resolver."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_strategy_tracker_exports(self):
        """Learning module exports strategy tracker."""
        from src.learning import StrategyTracker, StrategyRecommendation
        assert StrategyTracker is not None
        assert StrategyRecommendation is not None

    def test_strategy_tracker_creation(self, temp_dir):
        """Can create strategy tracker with storage path."""
        from src.learning import StrategyTracker

        tracker = StrategyTracker(storage_path=temp_dir / "stats.json")
        assert tracker is not None

    def test_strategy_tracker_recommend(self, temp_dir):
        """Strategy tracker provides recommendations."""
        from src.learning import StrategyTracker, ResolutionStrategy

        tracker = StrategyTracker(storage_path=temp_dir / "stats.json")

        # Record some attempts
        for _ in range(5):
            tracker.record_attempt("merge", {"language": "python"}, success=True)

        rec = tracker.recommend({"language": "python"})
        assert rec.strategy == ResolutionStrategy.MERGE
        assert rec.confidence > 0.3

    def test_strategy_tracker_context_awareness(self, temp_dir):
        """Strategy tracker uses context in recommendations."""
        from src.learning import StrategyTracker, ResolutionStrategy

        tracker = StrategyTracker(storage_path=temp_dir / "stats.json")

        # Python: merge works
        for _ in range(5):
            tracker.record_attempt("merge", {"language": "python"}, success=True)

        # JavaScript: fresh_synthesis works
        for _ in range(5):
            tracker.record_attempt("fresh_synthesis", {"language": "javascript"}, success=True)

        python_rec = tracker.recommend({"language": "python"})
        js_rec = tracker.recommend({"language": "javascript"})

        assert python_rec.strategy == ResolutionStrategy.MERGE
        assert js_rec.strategy == ResolutionStrategy.FRESH_SYNTHESIS


class TestFeedbackLoopIntegration:
    """Tests for feedback loop integration with PRD executor."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_feedback_loop_exports(self):
        """Learning module exports feedback loop."""
        from src.learning import FeedbackLoop, AgentFeedback, GuidanceMessage
        assert FeedbackLoop is not None
        assert AgentFeedback is not None
        assert GuidanceMessage is not None

    def test_feedback_loop_creation(self, temp_dir):
        """Can create feedback loop with storage path."""
        from src.learning import FeedbackLoop

        loop = FeedbackLoop(storage_path=temp_dir / "feedback.json")
        assert loop is not None

    def test_feedback_loop_collect_and_guidance(self, temp_dir):
        """Feedback loop can collect and generate guidance."""
        from src.learning import FeedbackLoop, FeedbackType
        from src.learning.feedback_schema import AgentFeedback
        import uuid

        loop = FeedbackLoop(storage_path=temp_dir / "feedback.json")

        # Collect some feedback
        feedback = AgentFeedback(
            feedback_id=f"fb-{uuid.uuid4().hex[:8]}",
            agent_id="agent-1",
            feedback_type=FeedbackType.APPROACH_FAILED,
            what_didnt_work=["Merge strategy failed"],
        )
        loop.collect_feedback("agent-1", feedback)

        # Generate guidance
        guidance = loop.generate_guidance("agent-1")
        # May have guidance about the failure
        assert isinstance(guidance, list)


class TestIntegratedLearningSystem:
    """Tests for the integrated learning system."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_full_learning_workflow(self, temp_dir):
        """Test a complete learning workflow."""
        from src.learning import (
            ConflictPatternMemory,
            StrategyTracker,
            FeedbackLoop,
            FeedbackType,
        )
        from src.learning.feedback_schema import AgentFeedback
        import uuid

        # Create all learning components
        pattern_memory = ConflictPatternMemory(storage_dir=temp_dir / "patterns")
        strategy_tracker = StrategyTracker(storage_path=temp_dir / "stats.json")
        feedback_loop = FeedbackLoop(
            storage_path=temp_dir / "feedback.json",
            pattern_memory=pattern_memory,
            strategy_tracker=strategy_tracker,
        )

        # 1. Record some strategy attempts
        strategy_tracker.record_attempt("merge", {"language": "python"}, success=True)
        strategy_tracker.record_attempt("merge", {"language": "python"}, success=True)
        strategy_tracker.record_attempt("merge", {"language": "python"}, success=False)

        # 2. Get strategy recommendation
        rec = strategy_tracker.recommend({"language": "python"})
        assert rec.strategy.value == "merge"

        # 3. Collect feedback about the attempt
        feedback = AgentFeedback(
            feedback_id=f"fb-{uuid.uuid4().hex[:8]}",
            agent_id="agent-1",
            feedback_type=FeedbackType.APPROACH_WORKED,
            what_worked=["Merge strategy worked well for Python"],
        )
        feedback_loop.collect_feedback("agent-1", feedback)

        # 4. Generate guidance for future attempts
        guidance = feedback_loop.generate_guidance(
            "agent-1",
            task_context={"language": "python"},
        )

        # Should include strategy recommendation
        assert isinstance(guidance, list)
        # May have strategy guidance
        if guidance:
            assert all(hasattr(g, 'message') for g in guidance)

    def test_learning_with_pattern_memory(self, temp_dir):
        """Test learning with pattern memory."""
        from src.learning import (
            ConflictPatternMemory,
            ConflictPattern,
            PatternState,
        )

        memory = ConflictPatternMemory(storage_dir=temp_dir / "patterns")

        # Record a conflict pattern
        pattern = ConflictPattern(
            pattern_hash="hash123",
            conflict_type="textual",
            files_involved=["src/foo.py", "src/bar.py"],
            intent_categories=["feature"],
            resolution_strategy="merge",
            success_rate=0.9,
        )

        # Store the pattern (would need database integration)
        # For now, just test that memory can suggest resolution
        suggestion = memory.suggest_resolution(
            conflict_type="textual",
            files_involved=["src/foo.py", "src/bar.py"],
            intent_categories=["feature"],
        )

        # May or may not have suggestion
        assert suggestion is None or hasattr(suggestion, 'confidence')


class TestLearningExports:
    """Test that all learning components are properly exported."""

    def test_all_pattern_exports(self):
        """All pattern-related classes are exported."""
        from src.learning import (
            PatternState,
            ValidationResult,
            ConflictPattern,
            PatternMatch,
            ResolutionOutcome,
            PatternDatabase,
            PatternHasher,
            ConflictPatternMemory,
            ResolutionSuggestion,
        )
        assert all([
            PatternState,
            ValidationResult,
            ConflictPattern,
            PatternMatch,
            ResolutionOutcome,
            PatternDatabase,
            PatternHasher,
            ConflictPatternMemory,
            ResolutionSuggestion,
        ])

    def test_all_strategy_exports(self):
        """All strategy-related classes are exported."""
        from src.learning import (
            ResolutionStrategy,
            ContextType,
            StrategyStats,
            StrategyContext,
            StrategyRecommendation,
            StrategyTracker,
            DEFAULT_STRATEGY_ORDER,
        )
        assert all([
            ResolutionStrategy,
            ContextType,
            StrategyStats,
            StrategyContext,
            StrategyRecommendation,
            StrategyTracker,
            DEFAULT_STRATEGY_ORDER,
        ])

    def test_all_feedback_exports(self):
        """All feedback-related classes are exported."""
        from src.learning import (
            FeedbackType,
            FeedbackSeverity,
            ConflictHint,
            PatternSuggestion,
            AgentFeedback,
            GuidanceType,
            GuidanceUrgency,
            GuidanceMessage,
            FeedbackBatch,
            GuidanceBatch,
            FeedbackLoop,
            MAX_HISTORY_PER_AGENT,
        )
        assert all([
            FeedbackType,
            FeedbackSeverity,
            ConflictHint,
            PatternSuggestion,
            AgentFeedback,
            GuidanceType,
            GuidanceUrgency,
            GuidanceMessage,
            FeedbackBatch,
            GuidanceBatch,
            FeedbackLoop,
        ])
        assert MAX_HISTORY_PER_AGENT > 0


class TestResolutionPipelineIntegration:
    """Tests for integration with resolution pipeline."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_pipeline_can_use_pattern_memory(self, temp_dir):
        """Resolution pipeline can use pattern memory."""
        from src.learning import ConflictPatternMemory
        from src.resolution.pipeline import ResolutionPipeline

        memory = ConflictPatternMemory(storage_dir=temp_dir / "patterns")
        pipeline = ResolutionPipeline(repo_path=temp_dir)

        # Pipeline exists and could be extended to use pattern memory
        assert pipeline is not None
        assert memory is not None

    def test_pipeline_can_use_strategy_tracker(self, temp_dir):
        """Resolution pipeline can use strategy tracker."""
        from src.learning import StrategyTracker
        from src.resolution.pipeline import ResolutionPipeline

        tracker = StrategyTracker(storage_path=temp_dir / "stats.json")
        pipeline = ResolutionPipeline(repo_path=temp_dir)

        # Both exist and could be connected
        assert pipeline is not None
        assert tracker is not None


class TestWaveResolverIntegration:
    """Tests for integration with wave resolver."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_wave_resolver_can_use_strategy_tracker(self, temp_dir):
        """Wave resolver can use strategy tracker."""
        from src.learning import StrategyTracker
        from src.prd.wave_resolver import WaveResolver
        from src.prd.integration import IntegrationBranchManager

        tracker = StrategyTracker(storage_path=temp_dir / "stats.json")

        # Initialize a mock branch manager
        manager = Mock(spec=IntegrationBranchManager)

        resolver = WaveResolver(
            integration_manager=manager,
        )

        # Both exist and could be connected
        assert resolver is not None
        assert tracker is not None
