"""
Tests for CLI review integration.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from src.cli import run_auto_review
from src.review.router import ReviewMethod
from src.review.registry import get_all_review_types


class TestCLIReviewChoices:
    """Tests for CLI review type argument choices (Issue #65)."""

    def test_cli_review_choices_include_all_registry_types(self):
        """CLI review choices should include all types from registry plus 'all'."""
        import subprocess
        import sys

        # Get expected choices from registry
        registry_types = set(get_all_review_types())
        expected_choices = registry_types | {'all'}

        # Run orchestrator review --help and check output
        result = subprocess.run(
            [sys.executable, '-m', 'src.cli', 'review', '--help'],
            capture_output=True, text=True, cwd=str(Path(__file__).parent.parent)
        )

        # The help output should mention all review types
        for review_type in expected_choices:
            assert review_type in result.stdout or review_type in result.stderr, (
                f"Review type '{review_type}' not found in CLI help output. "
                f"Make sure CLI uses get_all_review_types() for choices."
            )

    def test_cli_accepts_vibe_coding_review_type(self):
        """CLI should accept 'vibe_coding' as a valid review type (Issue #65 regression test)."""
        import subprocess
        import sys

        # This should NOT fail with "invalid choice" error
        result = subprocess.run(
            [sys.executable, '-m', 'src.cli', 'review', 'vibe_coding', '--help'],
            capture_output=True, text=True, cwd=str(Path(__file__).parent.parent)
        )

        # Check that it's not rejected as an invalid choice
        assert 'invalid choice' not in result.stderr.lower(), (
            f"'vibe_coding' rejected as invalid choice. "
            f"Error: {result.stderr}"
        )

    def test_cli_accepts_all_registry_review_types(self):
        """CLI should accept all review types from the registry."""
        import subprocess
        import sys

        for review_type in get_all_review_types():
            result = subprocess.run(
                [sys.executable, '-m', 'src.cli', 'review', review_type, '--help'],
                capture_output=True, text=True, cwd=str(Path(__file__).parent.parent)
            )
            assert 'invalid choice' not in result.stderr.lower(), (
                f"Review type '{review_type}' rejected as invalid. "
                f"Error: {result.stderr}"
            )

class TestRunAutoReview:
    """Tests for run_auto_review function."""

    @pytest.fixture
    def mock_router_cls(self):
        with patch("src.cli.ReviewRouter") as mock:
            yield mock

    def test_infrastructure_unavailable(self, mock_router_cls):
        """Test handling when review infrastructure raises ValueError."""
        mock_router_cls.side_effect = ValueError("No configuration")
        
        success, notes, error, info = run_auto_review("security")
        
        assert success is False
        assert "not available" in error
        assert info == {}

    def test_method_unavailable(self, mock_router_cls):
        """Test handling when no review method is available."""
        mock_instance = mock_router_cls.return_value
        mock_instance.method = ReviewMethod.UNAVAILABLE
        
        success, notes, error, info = run_auto_review("security")
        
        assert success is False
        assert "No review method" in error
        assert info == {}

    def test_review_execution_error(self, mock_router_cls):
        """Test handling when execution returns an error result."""
        mock_instance = mock_router_cls.return_value
        mock_instance.method = ReviewMethod.CLI
        
        mock_result = MagicMock()
        mock_result.error = "API failure"
        mock_result.model_used = "gpt-4"
        mock_result.blocking_count = 0
        mock_result.findings = []
        
        mock_instance.execute_review.return_value = mock_result
        
        success, notes, error, info = run_auto_review("security")
        
        assert success is False
        assert "Review error" in error
        assert info["error"] == "API failure"
        assert info["success"] is False

    def test_review_with_blocking_issues(self, mock_router_cls):
        """Test handling of blocking issues."""
        mock_instance = mock_router_cls.return_value
        mock_instance.method = ReviewMethod.API
        
        mock_result = MagicMock()
        mock_result.error = None
        mock_result.model_used = "claude-3-opus"
        mock_result.blocking_count = 2
        mock_result.findings = [MagicMock(), MagicMock()] # 2 findings
        mock_result.duration_seconds = 1.5
        
        mock_instance.execute_review.return_value = mock_result
        
        success, notes, error, info = run_auto_review("security")
        
        assert success is False
        assert "blocking issue(s)" in error
        assert info["blocking"] == 2
        assert info["success"] is False
        assert info["issues"] == 2

    def test_review_success_no_issues(self, mock_router_cls):
        """Test successful review with no issues."""
        mock_instance = mock_router_cls.return_value
        mock_instance.method = ReviewMethod.CLI
        
        mock_result = MagicMock()
        mock_result.error = None
        mock_result.model_used = "gemini-pro"
        mock_result.blocking_count = 0
        mock_result.findings = []
        mock_result.duration_seconds = 0.5
        
        mock_instance.execute_review.return_value = mock_result
        
        success, notes, error, info = run_auto_review("quality")
        
        assert success is True
        assert "No issues found" in notes
        assert info["success"] is True
        assert info["blocking"] == 0

    def test_review_success_non_blocking_issues(self, mock_router_cls):
        """Test successful review with only non-blocking issues."""
        mock_instance = mock_router_cls.return_value
        mock_instance.method = ReviewMethod.API
        
        mock_result = MagicMock()
        mock_result.error = None
        mock_result.model_used = "gpt-4"
        mock_result.blocking_count = 0
        mock_result.findings = [MagicMock()]
        mock_result.summary = "Minor nits"
        mock_result.duration_seconds = 1.0
        
        mock_instance.execute_review.return_value = mock_result
        
        success, notes, error, info = run_auto_review("quality")
        
        assert success is True
        assert "non-blocking findings" in notes
        assert info["success"] is True
        assert info["issues"] == 1

    def test_exception_during_execution(self, mock_router_cls):
        """Test unexpected exception during execution."""
        mock_instance = mock_router_cls.return_value
        mock_instance.method = ReviewMethod.CLI
        mock_instance.execute_review.side_effect = Exception("Unexpected crash")
        
        success, notes, error, info = run_auto_review("security")
        
        assert success is False
        assert "Review execution failed" in error
        assert "Unexpected crash" in info["error"]
