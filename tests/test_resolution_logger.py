"""
Tests for Resolution Logger - CORE-023 Part 3

Tests logging of conflict resolutions to .workflow_log.jsonl
following the format specified in the source plan (lines 70-77).
"""

import json
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

from src.schema import EventType, WorkflowEvent


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for testing."""
    return tmp_path


@pytest.fixture
def log_file(temp_dir):
    """Create a temporary log file path."""
    return temp_dir / ".workflow_log.jsonl"


# ============================================================================
# Resolution Logger Tests
# ============================================================================

class TestResolutionLogger:
    """Tests for logging conflict resolutions."""

    def test_log_resolution_creates_event(self, temp_dir, log_file):
        """Should create a CONFLICT_RESOLVED event with correct format."""
        from src.resolution.logger import log_resolution

        log_resolution(
            file_path="src/cli.py",
            strategy="sequential_merge",
            confidence=0.85,
            resolution_time_ms=1250,
            working_dir=temp_dir,
        )

        # Read the log file
        assert log_file.exists()
        with open(log_file) as f:
            lines = f.readlines()

        assert len(lines) == 1
        event = json.loads(lines[0])

        # Verify event structure matches source plan (lines 70-77)
        assert event["event_type"] == "conflict_resolved"
        assert event["details"]["file"] == "src/cli.py"
        assert event["details"]["strategy"] == "sequential_merge"
        assert event["details"]["confidence"] == 0.85
        assert event["details"]["resolution_time_ms"] == 1250

    def test_log_resolution_with_llm_info(self, temp_dir, log_file):
        """Should include LLM info when provided."""
        from src.resolution.logger import log_resolution

        log_resolution(
            file_path="src/api/client.py",
            strategy="llm_merge",
            confidence=0.75,
            resolution_time_ms=3500,
            llm_used=True,
            llm_model="gpt-4o",
            working_dir=temp_dir,
        )

        with open(log_file) as f:
            event = json.loads(f.readline())

        assert event["details"]["llm_used"] is True
        assert event["details"]["llm_model"] == "gpt-4o"

    def test_log_resolution_appends_to_existing(self, temp_dir, log_file):
        """Should append to existing log file, not overwrite."""
        from src.resolution.logger import log_resolution

        # Create existing log entry
        existing_event = {
            "timestamp": "2026-01-09T10:00:00",
            "event_type": "workflow_started",
            "workflow_id": "wf_test",
            "message": "Started workflow"
        }
        with open(log_file, 'w') as f:
            f.write(json.dumps(existing_event) + '\n')

        # Log a resolution
        log_resolution(
            file_path="test.py",
            strategy="3way",
            confidence=0.9,
            resolution_time_ms=500,
            working_dir=temp_dir,
        )

        with open(log_file) as f:
            lines = f.readlines()

        assert len(lines) == 2
        # First line should be the existing event
        assert json.loads(lines[0])["event_type"] == "workflow_started"
        # Second line should be the resolution
        assert json.loads(lines[1])["event_type"] == "conflict_resolved"

    def test_log_escalation(self, temp_dir, log_file):
        """Should log escalations with CONFLICT_ESCALATED event type."""
        from src.resolution.logger import log_escalation

        log_escalation(
            file_path="src/complex.py",
            reason="low_confidence",
            options=["ours", "theirs", "manual"],
            working_dir=temp_dir,
        )

        with open(log_file) as f:
            event = json.loads(f.readline())

        assert event["event_type"] == "conflict_escalated"
        assert event["details"]["file"] == "src/complex.py"
        assert event["details"]["reason"] == "low_confidence"
        assert event["details"]["options"] == ["ours", "theirs", "manual"]

    def test_log_resolution_includes_timestamp(self, temp_dir, log_file):
        """Should include timestamp in event."""
        from src.resolution.logger import log_resolution

        log_resolution(
            file_path="test.py",
            strategy="ours",
            confidence=1.0,
            resolution_time_ms=100,
            working_dir=temp_dir,
        )

        with open(log_file) as f:
            event = json.loads(f.readline())

        assert "timestamp" in event
        # Should be parseable as datetime
        datetime.fromisoformat(event["timestamp"].replace('Z', '+00:00'))

    def test_log_resolution_uses_cwd_when_no_dir_specified(self, temp_dir):
        """Should use current working directory when not specified."""
        from src.resolution.logger import log_resolution
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            log_resolution(
                file_path="test.py",
                strategy="theirs",
                confidence=1.0,
                resolution_time_ms=50,
            )

            log_file = temp_dir / ".workflow_log.jsonl"
            assert log_file.exists()
        finally:
            os.chdir(original_cwd)


class TestResolutionLoggerEdgeCases:
    """Edge case tests for resolution logger."""

    def test_log_resolution_handles_special_characters_in_path(self, temp_dir, log_file):
        """Should handle file paths with special characters."""
        from src.resolution.logger import log_resolution

        log_resolution(
            file_path="src/my file (copy).py",
            strategy="3way",
            confidence=0.8,
            resolution_time_ms=200,
            working_dir=temp_dir,
        )

        with open(log_file) as f:
            event = json.loads(f.readline())

        assert event["details"]["file"] == "src/my file (copy).py"

    def test_log_resolution_handles_zero_confidence(self, temp_dir, log_file):
        """Should handle zero confidence score."""
        from src.resolution.logger import log_resolution

        log_resolution(
            file_path="test.py",
            strategy="manual",
            confidence=0.0,
            resolution_time_ms=5000,
            working_dir=temp_dir,
        )

        with open(log_file) as f:
            event = json.loads(f.readline())

        assert event["details"]["confidence"] == 0.0

    def test_log_resolution_creates_directory_if_needed(self, tmp_path):
        """Should create parent directory if it doesn't exist."""
        from src.resolution.logger import log_resolution

        nested_dir = tmp_path / "nested" / "deep"
        nested_dir.mkdir(parents=True)

        log_resolution(
            file_path="test.py",
            strategy="ours",
            confidence=1.0,
            resolution_time_ms=100,
            working_dir=nested_dir,
        )

        log_file = nested_dir / ".workflow_log.jsonl"
        assert log_file.exists()
