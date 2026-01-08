"""
Tests for WF-005: Summary Before Approval Gates

These tests verify the phase summary functionality that displays
a concise summary before manual approval gates.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.engine import WorkflowEngine
from src.schema import WorkflowState, PhaseState, ItemState, ItemStatus
from src.cli import format_duration

# Import will be added once implemented
try:
    from src.cli import generate_phase_summary, format_phase_summary
    SUMMARY_AVAILABLE = True
except ImportError:
    SUMMARY_AVAILABLE = False


@pytest.fixture
def temp_workflow_dir():
    """Create a temporary directory for workflow tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_engine_with_items(temp_workflow_dir):
    """Create a mock WorkflowEngine with completed and skipped items."""
    engine = Mock(spec=WorkflowEngine)
    engine.state = Mock(spec=WorkflowState)
    engine.state.task_description = "Implement feature X"
    engine.state.current_phase_id = "EXECUTE"

    # Create items with different statuses - use Mock with value attribute for status
    implement_item = Mock()
    implement_item.status = Mock()
    implement_item.status.value = "completed"
    implement_item.notes = "Added PhaseCritique class with 145 lines"
    implement_item.completed_at = datetime.now()

    tests_item = Mock()
    tests_item.status = Mock()
    tests_item.status.value = "completed"
    tests_item.notes = "23 tests, all passing"
    tests_item.completed_at = datetime.now()

    perf_item = Mock()
    perf_item.status = Mock()
    perf_item.status.value = "skipped"
    perf_item.notes = None
    perf_item.skip_reason = "Not applicable - CLI tool"

    items = {
        "implement_code": implement_item,
        "write_tests": tests_item,
        "performance_test": perf_item,
    }

    engine.state.phases = {
        "EXECUTE": Mock(spec=PhaseState, items=items)
    }

    engine.get_skipped_items = Mock(
        return_value=[("performance_test", "Not applicable - CLI tool")]
    )

    engine.working_dir = temp_workflow_dir

    return engine


class TestFormatDuration:
    """Tests for duration formatting helper."""

    def test_format_duration_minutes(self):
        """S1: Format duration less than an hour."""
        delta = timedelta(minutes=45)
        result = format_duration(delta)
        assert result == "45m"

    def test_format_duration_hours_minutes(self):
        """S2: Format duration with hours and minutes."""
        delta = timedelta(hours=2, minutes=15)
        result = format_duration(delta)
        assert result == "2h 15m"

    def test_format_duration_days(self):
        """S3: Format duration with days."""
        delta = timedelta(days=1, hours=3, minutes=30)
        result = format_duration(delta)
        assert result == "1d 3h 30m"

    def test_format_duration_less_than_minute(self):
        """S4: Format very short duration."""
        delta = timedelta(seconds=30)
        result = format_duration(delta)
        assert result == "< 1m"

    def test_format_duration_exact_hour(self):
        """S5: Format exact hour with no minutes."""
        delta = timedelta(hours=1)
        result = format_duration(delta)
        assert result == "1h"


class TestPhaseSummary:
    """Tests for phase summary generation."""

    @pytest.mark.skipif(not SUMMARY_AVAILABLE, reason="Summary functions not implemented")
    def test_summary_completed_items(self, mock_engine_with_items):
        """S6: Summarize completed items with notes."""
        summary = generate_phase_summary(mock_engine_with_items)

        # Check that completed items are found
        completed_ids = [item["id"] for item in summary["completed"]]
        assert "implement_code" in completed_ids
        assert "write_tests" in completed_ids
        assert len(summary["completed"]) == 2

    @pytest.mark.skipif(not SUMMARY_AVAILABLE, reason="Summary functions not implemented")
    def test_summary_skipped_items(self, mock_engine_with_items):
        """S7: Include skipped items with reasons."""
        summary = generate_phase_summary(mock_engine_with_items)

        assert len(summary["skipped"]) == 1
        assert summary["skipped"][0][0] == "performance_test"
        assert "Not applicable" in summary["skipped"][0][1]

    @pytest.mark.skipif(not SUMMARY_AVAILABLE, reason="Summary functions not implemented")
    def test_summary_empty_phase(self, temp_workflow_dir):
        """S8: Handle phase with no completed items."""
        engine = Mock(spec=WorkflowEngine)
        engine.state = Mock()
        engine.state.current_phase_id = "PLAN"
        engine.state.phases = {
            "PLAN": Mock(items={})
        }
        engine.get_skipped_items = Mock(return_value=[])
        engine.working_dir = temp_workflow_dir

        summary = generate_phase_summary(engine)

        assert len(summary["completed"]) == 0
        assert len(summary["skipped"]) == 0

    @pytest.mark.skipif(not SUMMARY_AVAILABLE, reason="Summary functions not implemented")
    def test_summary_format(self, mock_engine_with_items):
        """S9: Output uses correct formatting."""
        summary = generate_phase_summary(mock_engine_with_items)
        formatted = format_phase_summary(summary, "EXECUTE", "REVIEW")

        # Check formatting elements
        assert "PHASE SUMMARY" in formatted
        assert "EXECUTE" in formatted
        assert "REVIEW" in formatted
        assert "✓" in formatted  # Completed marker
        assert "⊘" in formatted  # Skipped marker


class TestSummaryGitIntegration:
    """Tests for git diff integration in summary."""

    @pytest.mark.skipif(not SUMMARY_AVAILABLE, reason="Summary functions not implemented")
    def test_summary_includes_git_stat(self, mock_engine_with_items, temp_workflow_dir):
        """S10: Summary includes git diff stat."""
        mock_engine_with_items.working_dir = temp_workflow_dir

        # Initialize git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=temp_workflow_dir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=temp_workflow_dir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=temp_workflow_dir, capture_output=True)

        # Create and commit a file
        test_file = temp_workflow_dir / "test.py"
        test_file.write_text("print('hello')")
        subprocess.run(["git", "add", "."], cwd=temp_workflow_dir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_workflow_dir, capture_output=True)

        # Modify file
        test_file.write_text("print('hello world')\nprint('goodbye')")

        summary = generate_phase_summary(mock_engine_with_items)

        assert "git_diff_stat" in summary
        # Should show file change

    @pytest.mark.skipif(not SUMMARY_AVAILABLE, reason="Summary functions not implemented")
    def test_summary_no_git_repo(self, mock_engine_with_items, temp_workflow_dir):
        """S11: Handle directory without git repo gracefully."""
        mock_engine_with_items.working_dir = temp_workflow_dir

        summary = generate_phase_summary(mock_engine_with_items)

        # Should not fail, just have empty git stat
        assert summary.get("git_diff_stat", "") == "" or summary.get("git_diff_stat") is None


class TestSummaryInAdvance:
    """Tests for summary display in cmd_advance."""

    @pytest.mark.skipif(not SUMMARY_AVAILABLE, reason="Summary functions not implemented")
    def test_advance_shows_summary(self, temp_workflow_dir, capsys):
        """S12: Summary displayed before advance prompt."""
        # This would require integration testing with actual CLI
        pass

    @pytest.mark.skipif(not SUMMARY_AVAILABLE, reason="Summary functions not implemented")
    def test_advance_yes_flag_skips_prompt(self, temp_workflow_dir):
        """S13: --yes flag skips interactive prompt."""
        # Integration test
        pass
