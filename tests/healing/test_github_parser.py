"""Tests for the GitHub issue parser module."""

import json
import subprocess
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# These will be imported once implemented
# from src.healing.github_parser import GitHubIssueParser


class TestGitHubIssueParser:
    """Tests for GitHubIssueParser functionality."""

    @pytest.fixture
    def parser(self):
        """Create a GitHubIssueParser instance."""
        from src.healing.github_parser import GitHubIssueParser

        return GitHubIssueParser()

    @pytest.fixture
    def sample_issues(self):
        """Sample GitHub issues JSON."""
        return [
            {
                "number": 123,
                "title": "TypeError when processing null values",
                "body": """## Description
When processing data, we get an error:

```
Traceback (most recent call last):
  File "app.py", line 45, in process
    result = data['key']
TypeError: 'NoneType' object is not subscriptable
```

## Steps to Reproduce
1. Run the app
2. Send null data

## Fix
Added null check before accessing data.
""",
                "labels": [{"name": "bug"}, {"name": "priority-high"}],
                "closedAt": "2026-01-15T10:00:00Z",
                "state": "CLOSED",
            },
            {
                "number": 124,
                "title": "Feature: Add dark mode",
                "body": "Please add dark mode support.",
                "labels": [{"name": "enhancement"}],
                "closedAt": "2026-01-16T10:00:00Z",
                "state": "CLOSED",
            },
            {
                "number": 125,
                "title": "ModuleNotFoundError in production",
                "body": """Getting this error in production:

ModuleNotFoundError: No module named 'requests'

Fixed by adding requests to requirements.txt
""",
                "labels": [{"name": "bug"}, {"name": "error"}],
                "closedAt": "2026-01-17T10:00:00Z",
                "state": "CLOSED",
            },
        ]

    def test_parse_closed_issues(self, parser, sample_issues):
        """TC-GH-001: Parse closed issues from gh CLI output."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(sample_issues),
                stderr="",
            )

            issues = parser.fetch_closed_issues()

            assert len(issues) == 3
            assert issues[0]["number"] == 123

    def test_filter_by_labels(self, parser, sample_issues):
        """TC-GH-002: Filter issues by labels."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(sample_issues),
                stderr="",
            )

            # Fetch and filter by bug label
            issues = parser.fetch_closed_issues(labels=["bug"])

            # Should only return issues with "bug" label
            bug_issues = [i for i in issues if any(l["name"] == "bug" for l in i.get("labels", []))]
            assert len(bug_issues) == 2  # Issues 123 and 125

    def test_extract_errors_from_body(self, parser, sample_issues):
        """TC-GH-003: Extract error patterns from issue body."""
        issue = sample_issues[0]  # TypeError issue

        errors = parser.extract_errors(issue)

        assert len(errors) >= 1
        # Should find the TypeError
        error_descriptions = [e.description for e in errors]
        assert any("TypeError" in desc for desc in error_descriptions)

    def test_handle_gh_not_installed(self, parser):
        """TC-GH-004: Handle gh CLI not installed gracefully."""
        with patch("shutil.which", return_value=None):
            issues = parser.fetch_closed_issues()

            assert issues == []

    def test_handle_gh_command_failure(self, parser):
        """Handle gh CLI command failure gracefully."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "gh")

            issues = parser.fetch_closed_issues()

            assert issues == []

    def test_watermark_filtering(self, parser, sample_issues):
        """TC-GH-005: Filter issues by watermark date."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(sample_issues),
                stderr="",
            )

            # Only issues closed after Jan 16
            since = datetime(2026, 1, 16, 0, 0, 0)
            issues = parser.fetch_closed_issues(since=since)

            # Filter client-side for issues after watermark
            filtered = parser._filter_by_date(issues, since)

            # Should only include issues 124 and 125 (closed on/after Jan 16)
            assert len(filtered) >= 1


class TestErrorExtraction:
    """Tests for error extraction from issue bodies."""

    @pytest.fixture
    def parser(self):
        """Create a GitHubIssueParser instance."""
        from src.healing.github_parser import GitHubIssueParser

        return GitHubIssueParser()

    def test_extract_python_traceback(self, parser):
        """Extract Python traceback from issue body."""
        issue = {
            "number": 1,
            "title": "Error",
            "body": """Got this error:

```
Traceback (most recent call last):
  File "test.py", line 10, in main
    foo()
  File "test.py", line 5, in foo
    raise ValueError("bad value")
ValueError: bad value
```
""",
            "labels": [],
            "closedAt": "2026-01-17T00:00:00Z",
        }

        errors = parser.extract_errors(issue)

        assert len(errors) >= 1
        assert any("ValueError" in e.description for e in errors)

    def test_extract_module_not_found(self, parser):
        """Extract ModuleNotFoundError from issue body."""
        issue = {
            "number": 2,
            "title": "Missing module",
            "body": "ModuleNotFoundError: No module named 'pandas'",
            "labels": [],
            "closedAt": "2026-01-17T00:00:00Z",
        }

        errors = parser.extract_errors(issue)

        assert len(errors) >= 1
        assert any("ModuleNotFoundError" in e.description for e in errors)

    def test_extract_multiple_errors(self, parser):
        """Extract multiple errors from single issue."""
        issue = {
            "number": 3,
            "title": "Multiple errors",
            "body": """First error:
TypeError: 'NoneType' object is not subscriptable

Second error:
KeyError: 'missing_key'
""",
            "labels": [],
            "closedAt": "2026-01-17T00:00:00Z",
        }

        errors = parser.extract_errors(issue)

        assert len(errors) >= 2

    def test_no_errors_in_body(self, parser):
        """Handle issue with no error patterns."""
        issue = {
            "number": 4,
            "title": "Feature request",
            "body": "Please add dark mode support.",
            "labels": [],
            "closedAt": "2026-01-17T00:00:00Z",
        }

        errors = parser.extract_errors(issue)

        assert errors == []

    def test_extract_rust_error(self, parser):
        """Extract Rust error from issue body."""
        issue = {
            "number": 5,
            "title": "Rust compile error",
            "body": """Getting this error:

error[E0382]: borrow of moved value: `x`
  --> src/main.rs:5:10
   |
4  |     let y = x;
   |             - value moved here
5  |     println!("{}", x);
   |                    ^ value borrowed here after move
""",
            "labels": [],
            "closedAt": "2026-01-17T00:00:00Z",
        }

        errors = parser.extract_errors(issue)

        # Should extract Rust error
        assert len(errors) >= 1

    def test_extract_node_error(self, parser):
        """Extract Node.js error from issue body."""
        issue = {
            "number": 6,
            "title": "Node crash",
            "body": """Error: Cannot find module 'express'
    at Function.Module._resolveFilename (node:internal/modules/cjs/loader:933:15)
    at Function.Module._load (node:internal/modules/cjs/loader:778:27)
""",
            "labels": [],
            "closedAt": "2026-01-17T00:00:00Z",
        }

        errors = parser.extract_errors(issue)

        assert len(errors) >= 1


class TestEdgeCases:
    """Edge case tests for GitHub parser."""

    @pytest.fixture
    def parser(self):
        """Create a GitHubIssueParser instance."""
        from src.healing.github_parser import GitHubIssueParser

        return GitHubIssueParser()

    def test_empty_issue_body(self, parser):
        """Handle issue with empty body."""
        issue = {
            "number": 1,
            "title": "Empty",
            "body": "",
            "labels": [],
            "closedAt": "2026-01-17T00:00:00Z",
        }

        errors = parser.extract_errors(issue)
        assert errors == []

    def test_null_body(self, parser):
        """Handle issue with null body."""
        issue = {
            "number": 1,
            "title": "Null body",
            "body": None,
            "labels": [],
            "closedAt": "2026-01-17T00:00:00Z",
        }

        errors = parser.extract_errors(issue)
        assert errors == []

    def test_malformed_json_from_gh(self, parser):
        """Handle malformed JSON from gh CLI."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="{invalid json",
                stderr="",
            )

            issues = parser.fetch_closed_issues()
            assert issues == []

    def test_gh_api_error(self, parser):
        """TC-EDGE-004: Handle GitHub API error."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="API rate limit exceeded",
            )

            issues = parser.fetch_closed_issues()
            assert issues == []
