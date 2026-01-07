"""
Tests for Aider review provider integration.

Tests cover:
- AiderExecutor execution (success, timeout, not found)
- ReviewSetup aider detection
- ReviewRouter aider routing
"""

import subprocess
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.review.result import ReviewResult


class TestAiderExecutor:
    """Tests for AiderExecutor class."""

    def test_execute_success(self):
        """TC-AID-001: Execute review with Aider returns successful ReviewResult."""
        from src.review.aider_executor import AiderExecutor

        executor = AiderExecutor(Path("."))

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch("subprocess.Popen") as mock_popen:
                mock_process = MagicMock()
                mock_process.communicate.return_value = (
                    "## Security Review\n\nNo critical issues found.\n\n**Score: 8/10**",
                    ""
                )
                mock_process.returncode = 0
                mock_popen.return_value = mock_process

                result = executor.execute("security")

                assert result.success is True
                assert result.method_used == "aider"
                assert "gemini" in result.model_used.lower()
                assert result.raw_output is not None

    def test_execute_timeout(self):
        """TC-AID-002: Handle timeout when Aider takes too long."""
        from src.review.aider_executor import AiderExecutor

        executor = AiderExecutor(Path("."), timeout=1)

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch("subprocess.Popen") as mock_popen:
                mock_process = MagicMock()
                mock_process.communicate.side_effect = subprocess.TimeoutExpired("aider", 1)
                mock_process.kill = MagicMock()
                mock_process.wait = MagicMock()
                mock_process.poll.return_value = None
                mock_popen.return_value = mock_process

                result = executor.execute("holistic")

                assert result.success is False
                assert "timed out" in result.error.lower() or "timeout" in result.error.lower()

    def test_execute_command_not_found(self):
        """TC-AID-003: Handle missing aider command gracefully."""
        from src.review.aider_executor import AiderExecutor

        executor = AiderExecutor(Path("."))

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.side_effect = FileNotFoundError("aider not found")

                result = executor.execute("quality")

                assert result.success is False
                assert "aider" in result.error.lower() or "install" in result.error.lower()

    def test_execute_parses_output(self):
        """TC-AID-004: Parse Aider output into findings."""
        from src.review.aider_executor import AiderExecutor

        executor = AiderExecutor(Path("."))

        review_output = """## Code Review

### Findings

1. **HIGH**: SQL injection vulnerability in user input handling
2. **MEDIUM**: Missing input validation on API endpoint

### Summary
Found 2 issues that need attention.

**Score: 6/10**
"""

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch("subprocess.Popen") as mock_popen:
                mock_process = MagicMock()
                mock_process.communicate.return_value = (review_output, "")
                mock_process.returncode = 0
                mock_popen.return_value = mock_process

                result = executor.execute("consistency")

                assert result.raw_output is not None
                assert len(result.raw_output) > 0


class TestReviewSetupAider:
    """Tests for ReviewSetup aider detection."""

    def test_check_aider_available(self):
        """TC-AID-005: Detect when aider is installed."""
        from src.review.setup import check_review_setup

        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda cmd: "/usr/bin/aider" if cmd == "aider" else None

            setup = check_review_setup(Path("."))

            assert setup.aider_cli is True

    def test_check_aider_not_available(self):
        """TC-AID-006: Detect when aider is not installed."""
        from src.review.setup import check_review_setup

        with patch("shutil.which") as mock_which:
            mock_which.return_value = None

            setup = check_review_setup(Path("."))

            assert setup.aider_cli is False


class TestReviewRouterAider:
    """Tests for ReviewRouter aider integration."""

    def test_route_to_aider_when_available(self):
        """TC-AID-007: Router selects aider method when available."""
        from src.review.router import ReviewRouter, ReviewMethod

        with patch("src.review.router.check_review_setup") as mock_setup:
            mock_setup.return_value = MagicMock(
                aider_cli=True,
                openrouter_key=True,
                codex_cli=False,
                gemini_cli=False,
                github_actions=False,
                best_method=lambda: "aider"
            )

            router = ReviewRouter(Path("."), method="aider")

            assert router.method == ReviewMethod.AIDER

    def test_fallback_when_aider_unavailable(self):
        """TC-AID-008: Router falls back to API when aider unavailable."""
        from src.review.router import ReviewRouter, ReviewMethod

        with patch("src.review.router.check_review_setup") as mock_setup:
            mock_setup.return_value = MagicMock(
                aider_cli=False,
                openrouter_key=True,
                codex_cli=False,
                gemini_cli=False,
                github_actions=False,
                best_method=lambda: "api"
            )

            router = ReviewRouter(Path("."), method="auto")

            assert router.method == ReviewMethod.API

    def test_status_message_shows_aider(self):
        """TC-AID-009: Status message includes aider availability."""
        from src.review.router import ReviewRouter

        with patch("src.review.router.check_review_setup") as mock_setup:
            mock_setup.return_value = MagicMock(
                aider_cli=True,
                openrouter_key=True,
                codex_cli=False,
                gemini_cli=False,
                github_actions=False,
                best_method=lambda: "aider"
            )

            router = ReviewRouter(Path("."), method="aider")
            status = router.get_status_message()

            assert "aider" in status.lower()
