"""
Tests for the multi-model review system.
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.review.result import (
    Severity,
    ReviewFinding,
    ReviewResult,
    parse_review_output,
)
from src.review.context import ReviewContext, ReviewContextCollector
from src.review.router import ReviewRouter, ReviewMethod, check_review_setup
from src.review.prompts import get_prompt, get_tool, REVIEW_PROMPTS
from src.review.setup import setup_reviews, ReviewSetup


class TestSeverity:
    """Tests for Severity enum."""

    def test_from_string_valid(self):
        assert Severity.from_string("critical") == Severity.CRITICAL
        assert Severity.from_string("HIGH") == Severity.HIGH
        assert Severity.from_string("Medium") == Severity.MEDIUM
        assert Severity.from_string("low") == Severity.LOW
        assert Severity.from_string("INFO") == Severity.INFO

    def test_from_string_aliases(self):
        assert Severity.from_string("WARNING") == Severity.MEDIUM
        assert Severity.from_string("ERROR") == Severity.HIGH
        assert Severity.from_string("INFORMATION") == Severity.INFO

    def test_from_string_unknown(self):
        assert Severity.from_string("unknown") == Severity.INFO
        assert Severity.from_string("") == Severity.INFO

    def test_is_blocking(self):
        assert Severity.CRITICAL.is_blocking()
        assert Severity.HIGH.is_blocking()
        assert not Severity.MEDIUM.is_blocking()
        assert not Severity.LOW.is_blocking()
        assert not Severity.INFO.is_blocking()


class TestReviewFinding:
    """Tests for ReviewFinding dataclass."""

    def test_to_dict(self):
        finding = ReviewFinding(
            severity=Severity.HIGH,
            issue="SQL injection vulnerability",
            location="src/db.py:45",
            evidence="query = 'SELECT * FROM users WHERE id=' + user_id",
            recommendation="Use parameterized queries",
        )
        d = finding.to_dict()
        assert d["severity"] == "high"
        assert d["issue"] == "SQL injection vulnerability"
        assert d["location"] == "src/db.py:45"

    def test_from_dict(self):
        data = {
            "severity": "critical",
            "issue": "Hardcoded API key",
            "location": "config.py:10",
        }
        finding = ReviewFinding.from_dict(data)
        assert finding.severity == Severity.CRITICAL
        assert finding.issue == "Hardcoded API key"


class TestReviewResult:
    """Tests for ReviewResult dataclass."""

    def test_has_blocking_findings(self):
        result = ReviewResult(
            review_type="security",
            success=True,
            model_used="codex",
            method_used="cli",
            findings=[
                ReviewFinding(severity=Severity.INFO, issue="Minor issue"),
                ReviewFinding(severity=Severity.HIGH, issue="Major issue"),
            ],
        )
        assert result.has_blocking_findings()
        assert result.blocking_count == 1

    def test_no_blocking_findings(self):
        result = ReviewResult(
            review_type="quality",
            success=True,
            model_used="gemini",
            method_used="api",
            findings=[
                ReviewFinding(severity=Severity.LOW, issue="Style issue"),
            ],
        )
        assert not result.has_blocking_findings()
        assert result.blocking_count == 0

    def test_to_dict_and_back(self):
        result = ReviewResult(
            review_type="consistency",
            success=True,
            model_used="gemini",
            method_used="cli",
            findings=[
                ReviewFinding(severity=Severity.MEDIUM, issue="Pattern mismatch"),
            ],
            summary="Generally follows patterns",
        )
        d = result.to_dict()
        restored = ReviewResult.from_dict(d)
        assert restored.review_type == result.review_type
        assert len(restored.findings) == len(result.findings)


class TestParseReviewOutput:
    """Tests for parse_review_output function."""

    def test_parse_security_findings(self):
        output = """
### [CRITICAL]
**Issue:** SQL injection in user query
**Location:** src/db.py:45
**Evidence:** `query = "SELECT * FROM users WHERE id=" + user_id`
**Fix:** Use parameterized queries

### [MEDIUM]
**Issue:** Missing input validation
**Location:** src/api.py:23
**Fix:** Validate user input before processing
"""
        findings, metadata = parse_review_output("security", output)
        assert len(findings) == 2
        assert findings[0].severity == Severity.CRITICAL
        assert "SQL injection" in findings[0].issue

    def test_parse_quality_score(self):
        output = """
### Quality Score: [7]

**Summary:** Generally good code with some improvements needed.

1. [MEDIUM] Missing error handling at src/handler.py:30
"""
        findings, metadata = parse_review_output("quality", output)
        assert metadata.get("score") == 7
        assert "Generally good" in metadata.get("summary", "")

    def test_parse_architecture_assessment(self):
        output = """
### Overall Assessment: APPROVED_WITH_NOTES

**Summary:** Changes follow existing patterns.

**Findings:**
1. [LOW] Consider extracting common logic
"""
        findings, metadata = parse_review_output("consistency", output)
        assert metadata.get("assessment") == "APPROVED_WITH_NOTES"


class TestReviewContext:
    """Tests for ReviewContext dataclass."""

    def test_format_changed_files(self):
        context = ReviewContext(
            changed_files={
                "src/main.py": "print('hello')",
                "src/utils.py": "def helper(): pass",
            }
        )
        formatted = context.format_changed_files()
        assert "src/main.py" in formatted
        assert "src/utils.py" in formatted
        assert "print('hello')" in formatted

    def test_total_size(self):
        context = ReviewContext(
            git_diff="diff content here",
            changed_files={"a.py": "x" * 100},
        )
        assert context.total_size() > 100


class TestReviewContextCollector:
    """Tests for ReviewContextCollector."""

    def test_collect_in_git_repo(self):
        """Test context collection in the actual repo."""
        collector = ReviewContextCollector(Path("."))
        context = collector.collect("security")

        # Should have at least some content
        assert context is not None
        # May or may not have diff depending on repo state

    def test_non_git_directory(self):
        """Test behavior in non-git directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = ReviewContextCollector(Path(tmpdir))
            context = collector.collect("security")
            # Should not raise, just return empty context
            assert context is not None


class TestReviewSetup:
    """Tests for review setup detection."""

    def test_check_review_setup(self):
        setup = check_review_setup(Path("."))
        assert isinstance(setup, ReviewSetup)
        # CLI tools may or may not be installed
        assert isinstance(setup.codex_cli, bool)
        assert isinstance(setup.gemini_cli, bool)

    def test_cli_available(self):
        setup = ReviewSetup(codex_cli=True, gemini_cli=True)
        assert setup.cli_available

        setup = ReviewSetup(codex_cli=True, gemini_cli=False)
        assert not setup.cli_available

    def test_api_available(self):
        setup = ReviewSetup(openrouter_key=True)
        assert setup.api_available

        setup = ReviewSetup(openrouter_key=False)
        assert not setup.api_available


class TestSetupReviews:
    """Tests for setup_reviews function."""

    def test_dry_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results = setup_reviews(Path(tmpdir), dry_run=True)
            assert len(results) == 3  # Actions, styleguide, AGENTS.md
            for path, status in results.items():
                assert "Would create" in status

    def test_creates_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results = setup_reviews(Path(tmpdir), dry_run=False)
            assert len(results) == 3

            # Check files exist
            assert (Path(tmpdir) / ".github" / "workflows" / "ai-reviews.yml").exists()
            assert (Path(tmpdir) / ".gemini" / "styleguide.md").exists()
            assert (Path(tmpdir) / "AGENTS.md").exists()

    def test_skip_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create first
            setup_reviews(Path(tmpdir), dry_run=False)

            # Try again without force
            results = setup_reviews(Path(tmpdir), dry_run=False, force=False)
            assert len(results) == 0  # Nothing new created


class TestPrompts:
    """Tests for review prompts."""

    def test_all_prompts_exist(self):
        for review_type in ["security", "consistency", "quality", "holistic"]:
            prompt = get_prompt(review_type)
            assert prompt is not None
            assert len(prompt) > 100

    def test_get_tool(self):
        assert get_tool("security") == "codex"
        assert get_tool("quality") == "codex"
        assert get_tool("consistency") == "gemini"
        assert get_tool("holistic") == "gemini"


class TestReviewRouter:
    """Tests for ReviewRouter."""

    def test_method_detection(self):
        """Test that method is detected based on available tools."""
        with patch("src.review.router.shutil.which") as mock_which:
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test"}):
                # No CLI tools, but API key available
                mock_which.return_value = None
                router = ReviewRouter(Path("."))
                assert router.method == ReviewMethod.API

    def test_cli_method_preferred(self):
        """Test that CLI is preferred when available."""
        with patch("src.review.router.shutil.which") as mock_which:
            # Both CLI tools available
            mock_which.return_value = "/usr/bin/codex"
            router = ReviewRouter(Path("."))
            assert router.method == ReviewMethod.CLI

    def test_status_message(self):
        router = ReviewRouter(Path("."))
        status = router.get_status_message()
        assert "Review Infrastructure Status" in status
        assert "CLI Tools" in status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
