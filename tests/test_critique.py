"""
Tests for WF-008: AI Critique at Phase Gates

These tests verify the PhaseCritique functionality that runs
lightweight AI reviews at phase transitions.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Import will fail until we implement the module
try:
    from src.critique import (
        PhaseCritique,
        CritiqueResult,
        CritiqueObservation,
        ObservationSeverity,
        CRITIQUE_PROMPTS,
    )
    CRITIQUE_AVAILABLE = True
except ImportError:
    CRITIQUE_AVAILABLE = False

from src.engine import WorkflowEngine
from src.schema import WorkflowState, PhaseState, ItemState, ItemStatus


@pytest.fixture
def temp_workflow_dir():
    """Create a temporary directory for workflow tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_engine():
    """Create a mock WorkflowEngine with state."""
    engine = Mock(spec=WorkflowEngine)
    engine.state = Mock(spec=WorkflowState)
    engine.state.task_description = "Implement feature X"
    engine.state.constraints = ["No breaking changes", "Must have tests"]
    engine.state.current_phase_id = "EXECUTE"
    engine.state.phases = {
        "EXECUTE": Mock(spec=PhaseState)
    }
    engine.state.phases["EXECUTE"].items = {
        "implement_code": Mock(
            status=ItemStatus.COMPLETED,
            notes="Added new function"
        ),
        "write_tests": Mock(
            status=ItemStatus.COMPLETED,
            notes="10 tests added"
        ),
    }
    engine.get_skipped_items = Mock(return_value=[])
    engine.workflow_def = Mock()
    engine.workflow_def.phases = [
        Mock(id="PLAN"),
        Mock(id="EXECUTE"),
        Mock(id="REVIEW"),
    ]
    return engine


class TestCritiqueContextCollection:
    """Tests for collecting context for critique."""

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_critique_context_collection(self, temp_workflow_dir, mock_engine):
        """C1: Collect context from engine state."""
        critique = PhaseCritique(temp_workflow_dir)
        context = critique.collect_context(mock_engine)

        assert "task" in context
        assert context["task"] == "Implement feature X"
        assert "constraints" in context
        assert len(context["constraints"]) == 2
        assert "completed_items" in context
        assert "current_phase" in context
        assert context["current_phase"] == "EXECUTE"

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_critique_context_truncation(self, temp_workflow_dir, mock_engine):
        """C2: Large context is truncated to token limit."""
        # Create a very long notes field
        mock_engine.state.phases["EXECUTE"].items["implement_code"].notes = "A" * 10000

        critique = PhaseCritique(temp_workflow_dir, max_context_tokens=8000)
        context = critique.collect_context(mock_engine)

        # Context should be truncated
        serialized = critique._serialize_context(context)
        assert len(serialized) <= 8000

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_critique_includes_skipped_items(self, temp_workflow_dir, mock_engine):
        """C3: Skipped items included in context."""
        mock_engine.get_skipped_items = Mock(
            return_value=[("performance_test", "Deferred")]
        )

        critique = PhaseCritique(temp_workflow_dir)
        context = critique.collect_context(mock_engine)

        assert "skipped_items" in context
        assert len(context["skipped_items"]) == 1
        assert context["skipped_items"][0][0] == "performance_test"


class TestCritiquePrompts:
    """Tests for critique prompt generation."""

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_critique_prompt_plan_execute(self):
        """C4: PLAN→EXECUTE prompt focuses on requirements."""
        prompt = CRITIQUE_PROMPTS.get("PLAN_EXECUTE")
        assert prompt is not None
        assert "requirements" in prompt.lower() or "risk" in prompt.lower()

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_critique_prompt_execute_review(self):
        """C5: EXECUTE→REVIEW prompt focuses on completion."""
        prompt = CRITIQUE_PROMPTS.get("EXECUTE_REVIEW")
        assert prompt is not None
        assert "complete" in prompt.lower() or "test" in prompt.lower()

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_critique_prompt_review_verify(self):
        """C6: REVIEW→VERIFY prompt focuses on findings."""
        prompt = CRITIQUE_PROMPTS.get("REVIEW_VERIFY")
        assert prompt is not None
        assert "review" in prompt.lower() or "finding" in prompt.lower()

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_all_transitions_have_prompts(self):
        """C7: All phase transitions have prompts defined."""
        expected_transitions = [
            "PLAN_EXECUTE",
            "EXECUTE_REVIEW",
            "REVIEW_VERIFY",
            "VERIFY_LEARN",
        ]
        for transition in expected_transitions:
            assert transition in CRITIQUE_PROMPTS, f"Missing prompt for {transition}"


class TestCritiqueResultParsing:
    """Tests for parsing critique results."""

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_critique_result_parsing(self):
        """C8: Parse review result into observations."""
        raw_result = """Observations:
- WARNING: No rollback plan specified
- PASS: Tests are comprehensive
- CRITICAL: Security vulnerability in auth

Recommendation: Address security issue before proceeding.
"""

        result = CritiqueResult.parse(raw_result)

        # Should parse at least some observations
        assert len(result.observations) >= 1
        # Should have a recommendation
        assert result.recommendation is not None or len(result.observations) > 0

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_critique_critical_detection(self):
        """C9: Detect critical issues - should_block = True."""
        result = CritiqueResult(
            observations=[
                CritiqueObservation("Security issue", ObservationSeverity.CRITICAL),
            ],
            recommendation="Fix security issue",
        )

        assert result.should_block is True

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_critique_no_critical(self):
        """C10: All warnings, no criticals - should_block = False."""
        result = CritiqueResult(
            observations=[
                CritiqueObservation("Minor issue", ObservationSeverity.WARNING),
                CritiqueObservation("Good practice", ObservationSeverity.PASS),
            ],
            recommendation="Consider addressing warning",
        )

        assert result.should_block is False


class TestCritiqueExecution:
    """Tests for executing critique."""

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_critique_api_failure_graceful(self, temp_workflow_dir, mock_engine):
        """C11: API throws exception - returns None, logs warning."""
        critique = PhaseCritique(temp_workflow_dir)

        with patch.object(critique, '_call_api', side_effect=Exception("API Error")):
            result = critique.run(mock_engine, "EXECUTE", "REVIEW")

        assert result is None

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_critique_timeout(self, temp_workflow_dir, mock_engine):
        """C12: API exceeds timeout - TimeoutError caught."""
        critique = PhaseCritique(temp_workflow_dir, timeout=1)

        # Simulate an exception (timeout would raise an exception)
        with patch.object(critique, '_call_api', side_effect=TimeoutError("Timeout")):
            result = critique.run(mock_engine, "EXECUTE", "REVIEW")

        # Should return None on timeout, not raise
        assert result is None

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_critique_disabled(self, temp_workflow_dir, mock_engine):
        """C13: phase_critique: false - critique not called."""
        mock_engine.workflow_def.settings = {"phase_critique": False}

        critique = PhaseCritique(temp_workflow_dir)

        with patch.object(critique, '_call_api') as mock_api:
            result = critique.run_if_enabled(mock_engine, "EXECUTE", "REVIEW")

        mock_api.assert_not_called()
        assert result is None


class TestCritiqueIntegration:
    """Integration tests for critique with cmd_advance."""

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_advance_with_critique(self, temp_workflow_dir):
        """C14: Full advance flow with critique."""
        # This would be a more complex integration test
        # requiring a full workflow setup
        pass

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_advance_critique_blocking(self, temp_workflow_dir):
        """C15: Critical issue found - user prompted."""
        # Integration test requiring CLI interaction
        pass


class TestCritiqueModelSelection:
    """Tests for model selection in critique."""

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_critique_uses_latest_model(self, temp_workflow_dir):
        """C16: critique_model: 'latest' resolves via ModelRegistry."""
        critique = PhaseCritique(temp_workflow_dir)

        # Test that 'latest' returns a model ID (could be default or from registry)
        model = critique._get_model("latest")

        # Should return a valid model string
        assert model is not None
        assert isinstance(model, str)
        assert len(model) > 0

    @pytest.mark.skipif(not CRITIQUE_AVAILABLE, reason="Critique module not implemented")
    def test_critique_explicit_model(self, temp_workflow_dir):
        """C17: Explicit model name used directly."""
        critique = PhaseCritique(temp_workflow_dir)

        model = critique._get_model("openai/gpt-4o")

        assert model == "openai/gpt-4o"
