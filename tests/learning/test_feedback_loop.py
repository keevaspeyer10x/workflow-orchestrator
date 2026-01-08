"""
Tests for FeedbackLoop class.

Tests cover:
- Collecting feedback from agents
- Retrieving agent history
- Generating guidance based on patterns and strategies
- Persistence to disk
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone
import uuid


def make_feedback(agent_id: str, feedback_type, **kwargs):
    """Helper to create AgentFeedback instances."""
    from src.learning.feedback_schema import AgentFeedback
    return AgentFeedback(
        feedback_id=f"fb-{uuid.uuid4().hex[:8]}",
        agent_id=agent_id,
        feedback_type=feedback_type,
        **kwargs,
    )


class TestFeedbackLoopBasics:
    """Basic tests for FeedbackLoop."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "feedback_history.json"

    @pytest.fixture
    def loop(self, temp_storage):
        """Create a FeedbackLoop with temp storage."""
        from src.learning.feedback_loop import FeedbackLoop
        return FeedbackLoop(storage_path=temp_storage)

    def test_create_loop(self, loop):
        """Can create a feedback loop."""
        assert loop is not None

    def test_collect_feedback(self, loop):
        """Can collect feedback from an agent."""
        from src.learning.feedback_schema import FeedbackType

        feedback = make_feedback(
            "agent-1",
            FeedbackType.APPROACH_WORKED,
            what_worked=["Merge worked well"],
        )

        loop.collect_feedback("agent-1", feedback)

        # Verify it was stored
        history = loop.get_agent_history("agent-1")
        assert len(history) == 1
        assert "Merge worked well" in history[0].what_worked

    def test_collect_multiple_feedbacks(self, loop):
        """Can collect multiple feedbacks from an agent."""
        from src.learning.feedback_schema import FeedbackType

        for i in range(5):
            feedback = make_feedback(
                "agent-1",
                FeedbackType.APPROACH_WORKED,
                what_worked=[f"Feedback {i}"],
            )
            loop.collect_feedback("agent-1", feedback)

        history = loop.get_agent_history("agent-1")
        assert len(history) == 5

    def test_get_history_empty(self, loop):
        """Returns empty list for unknown agent."""
        history = loop.get_agent_history("unknown-agent")
        assert history == []


class TestFeedbackLoopGuidance:
    """Tests for guidance generation."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "feedback_history.json"

    @pytest.fixture
    def loop(self, temp_storage):
        """Create a FeedbackLoop with temp storage."""
        from src.learning.feedback_loop import FeedbackLoop
        return FeedbackLoop(storage_path=temp_storage)

    def test_generate_guidance_empty_history(self, loop):
        """Generates no guidance for new agent."""
        guidance = loop.generate_guidance("new-agent")
        assert guidance == []

    def test_guidance_after_failures(self, loop):
        """Generates warning after multiple failures."""
        from src.learning.feedback_schema import FeedbackType

        # Record several failures
        for i in range(3):
            feedback = make_feedback(
                "agent-1",
                FeedbackType.APPROACH_FAILED,
                what_didnt_work=[f"Failed attempt {i}"],
            )
            loop.collect_feedback("agent-1", feedback)

        guidance = loop.generate_guidance("agent-1")

        # Should have warning about failures
        assert len(guidance) >= 1
        assert any("failure" in g.message.lower() for g in guidance)

    def test_guidance_includes_pattern_suggestions(self, loop):
        """Includes agent's own pattern suggestions in guidance."""
        from src.learning.feedback_schema import (
            FeedbackType, PatternSuggestion
        )

        feedback = make_feedback(
            "agent-1",
            FeedbackType.PATTERN_SUGGESTION,
            pattern_suggestion=PatternSuggestion(
                pattern_name="merge_conflict_pattern",
                description="When files A and B conflict, use merge strategy",
                context="When two agents modify the same function",
            ),
        )
        loop.collect_feedback("agent-1", feedback)

        guidance = loop.generate_guidance("agent-1")

        # Should reference the pattern suggestion
        assert len(guidance) >= 1
        assert any("previously suggested" in g.message.lower() for g in guidance)


class TestFeedbackLoopWithStrategyTracker:
    """Tests for guidance with strategy tracker integration."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_guidance_from_strategy_tracker(self, temp_dir):
        """Generates guidance from strategy tracker."""
        from src.learning.feedback_loop import FeedbackLoop
        from src.learning.strategy_tracker import StrategyTracker

        # Create strategy tracker with some data
        tracker = StrategyTracker(storage_path=temp_dir / "stats.json")
        for _ in range(10):
            tracker.record_attempt("merge", {"language": "python"}, success=True)

        # Create loop with tracker
        loop = FeedbackLoop(
            storage_path=temp_dir / "feedback.json",
            strategy_tracker=tracker,
        )

        guidance = loop.generate_guidance(
            "agent-1",
            task_context={"language": "python"},
        )

        # Should include strategy recommendation (uses USE_PATTERN type)
        assert len(guidance) >= 1
        assert any(
            g.guidance_type.value == "use_pattern"
            for g in guidance
        )


class TestFeedbackLoopPersistence:
    """Tests for persistence."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "feedback_history.json"

    def test_persists_to_disk(self, temp_storage):
        """Loop persists data to disk."""
        from src.learning.feedback_loop import FeedbackLoop
        from src.learning.feedback_schema import FeedbackType

        loop1 = FeedbackLoop(storage_path=temp_storage)
        feedback = make_feedback(
            "agent-1",
            FeedbackType.APPROACH_WORKED,
            what_worked=["Test feedback"],
        )
        loop1.collect_feedback("agent-1", feedback)

        # Create new loop with same path
        loop2 = FeedbackLoop(storage_path=temp_storage)
        history = loop2.get_agent_history("agent-1")

        assert len(history) == 1
        assert "Test feedback" in history[0].what_worked

    def test_handles_missing_file(self, temp_storage):
        """Handles missing storage file gracefully."""
        from src.learning.feedback_loop import FeedbackLoop

        loop = FeedbackLoop(storage_path=temp_storage)
        history = loop.get_agent_history("agent-1")

        assert history == []

    def test_handles_corrupt_file(self, temp_storage):
        """Handles corrupt storage file gracefully."""
        from src.learning.feedback_loop import FeedbackLoop

        # Write corrupt data
        temp_storage.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_storage, 'w') as f:
            f.write("not valid json")

        loop = FeedbackLoop(storage_path=temp_storage)
        history = loop.get_agent_history("agent-1")

        assert history == []

    def test_clear_removes_data(self, temp_storage):
        """Clear removes all feedback history."""
        from src.learning.feedback_loop import FeedbackLoop
        from src.learning.feedback_schema import FeedbackType

        loop = FeedbackLoop(storage_path=temp_storage)
        feedback = make_feedback(
            "agent-1",
            FeedbackType.APPROACH_WORKED,
            what_worked=["Test feedback"],
        )
        loop.collect_feedback("agent-1", feedback)
        loop.clear()

        assert loop.get_agent_history("agent-1") == []
        assert not temp_storage.exists()


class TestFeedbackLoopHistoryLimit:
    """Tests for history size limits."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "feedback_history.json"

    def test_trims_old_history(self, temp_storage):
        """Trims history to max size."""
        from src.learning.feedback_loop import FeedbackLoop, MAX_HISTORY_PER_AGENT
        from src.learning.feedback_schema import FeedbackType

        loop = FeedbackLoop(storage_path=temp_storage)

        # Add more than max entries
        for i in range(MAX_HISTORY_PER_AGENT + 50):
            feedback = make_feedback(
                "agent-1",
                FeedbackType.APPROACH_WORKED,
                what_worked=[f"Feedback {i}"],
            )
            loop.collect_feedback("agent-1", feedback)

        history = loop.get_agent_history("agent-1")
        assert len(history) == MAX_HISTORY_PER_AGENT

        # Should keep most recent
        assert f"Feedback {MAX_HISTORY_PER_AGENT + 49}" in history[-1].what_worked
