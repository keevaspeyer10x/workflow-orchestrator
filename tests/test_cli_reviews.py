"""
Tests for CLI review integration.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from src.cli import run_auto_review
from src.review.router import ReviewMethod

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
