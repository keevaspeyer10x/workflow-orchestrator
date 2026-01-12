"""
Tests for enhanced SessionLogger (CORE-024).

These tests verify:
- SessionLogger creates sessions with correct ID format
- Async logging works without blocking
- Structured events are logged correctly
- SessionAnalyzer generates accurate statistics
- No secrets appear in session logs
"""

import json
import tempfile
import time
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.session_logger import (
    SessionLogger,
    SessionContext,
    SessionAnalyzer,
    format_analysis_report,
    EVENT_WORKFLOW_STARTED,
    EVENT_WORKFLOW_FINISHED,
    EVENT_WORKFLOW_ABANDONED,
    EVENT_PHASE_ADVANCED,
    EVENT_ITEM_COMPLETED,
    EVENT_ERROR,
    EVENT_COMMAND,
    EVENT_OUTPUT,
)
from src.secrets import SecretsManager


class TestSessionContext:
    """Tests for SessionContext dataclass."""

    def test_session_context_creation(self):
        """TC-SESSION-001: SessionContext can be created with required fields."""
        session = SessionContext(
            session_id="2026-01-12_14-30-15_test-task",
            task_description="Test task",
            workflow_id="wf_123",
            start_time=datetime.now(),
            log_file=Path("/tmp/test.jsonl"),
        )

        assert session.session_id == "2026-01-12_14-30-15_test-task"
        assert session.task_description == "Test task"
        assert session.workflow_id == "wf_123"
        assert session.log_file == Path("/tmp/test.jsonl")

    def test_session_context_to_dict(self):
        """SessionContext can be serialized to dict."""
        session = SessionContext(
            session_id="test-session",
            task_description="Test",
            workflow_id="wf_123",
            start_time=datetime(2026, 1, 12, 14, 30, 15),
            log_file=Path("/tmp/test.jsonl"),
        )

        data = session.to_dict()
        assert data["session_id"] == "test-session"
        assert data["workflow_id"] == "wf_123"
        assert "2026-01-12T14:30:15" in data["start_time"]


class TestSessionLogger:
    """Tests for SessionLogger class."""

    def test_session_id_format(self):
        """TC-SESSION-002: Session ID follows YYYY-MM-DD_HH-MM-SS_task-slug format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(
                working_dir=Path(tmpdir),
                async_logging=False,  # Disable async for simpler testing
            )

            session = logger.start_session("Implement CORE-024 Feature")

            # Verify format: YYYY-MM-DD_HH-MM-SS_task-slug
            parts = session.session_id.split("_")
            assert len(parts) >= 3  # date, time, and task slug

            # Check date part (YYYY-MM-DD)
            date_part = parts[0]
            assert len(date_part) == 10
            assert date_part.count("-") == 2

            # Check time part (HH-MM-SS)
            time_part = parts[1]
            assert len(time_part) == 8
            assert time_part.count("-") == 2

            # Check slug part
            slug = "_".join(parts[2:])
            assert "implement-core-024-feature" in slug

    def test_start_session_creates_file(self):
        """TC-SESSION-003: start_session creates session log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(
                working_dir=Path(tmpdir),
                async_logging=False,
            )

            session = logger.start_session("Test task", workflow_id="wf_123")

            assert session.log_file.exists()
            assert session.log_file.suffix == ".jsonl"

    def test_start_session_logs_workflow_started_event(self):
        """Session start logs WORKFLOW_STARTED event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(
                working_dir=Path(tmpdir),
                async_logging=False,
            )

            session = logger.start_session("Test task", workflow_id="wf_123")

            # Read log file
            with open(session.log_file, 'r') as f:
                first_event = json.loads(f.readline())

            assert first_event["type"] == EVENT_WORKFLOW_STARTED
            assert first_event["data"]["task"] == "Test task"
            assert first_event["data"]["workflow_id"] == "wf_123"

    def test_log_event_writes_structured_event(self):
        """TC-SESSION-004: log_event writes structured JSONL events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(
                working_dir=Path(tmpdir),
                async_logging=False,
            )

            session = logger.start_session("Test")
            logger.log_event(EVENT_ITEM_COMPLETED, {"item_id": "check_roadmap"})
            logger.end_session("completed")

            # Read all events
            events = []
            with open(session.log_file, 'r') as f:
                for line in f:
                    events.append(json.loads(line))

            # Check that item_completed event was logged
            item_event = next((e for e in events if e["type"] == EVENT_ITEM_COMPLETED), None)
            assert item_event is not None
            assert item_event["data"]["item_id"] == "check_roadmap"

    def test_end_session_updates_status(self):
        """TC-SESSION-005: end_session updates session status and logs finish event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(
                working_dir=Path(tmpdir),
                async_logging=False,
            )

            session = logger.start_session("Test")
            logger.end_session("completed")

            # Read last event
            with open(session.log_file, 'r') as f:
                lines = f.readlines()
                last_event = json.loads(lines[-1])

            assert last_event["type"] == EVENT_WORKFLOW_FINISHED
            assert last_event["data"]["status"] == "completed"
            assert "duration_seconds" in last_event["data"]

    def test_async_logging_performance(self):
        """TC-SESSION-006: Async logging completes quickly (<5% overhead target)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Test with async enabled
            logger_async = SessionLogger(
                working_dir=Path(tmpdir),
                async_logging=True,
            )

            session = logger_async.start_session("Performance test")

            # Log many events
            start_time = time.time()
            for i in range(100):
                logger_async.log_event(EVENT_ITEM_COMPLETED, {"item_id": f"item_{i}"})
            async_duration = time.time() - start_time

            logger_async.end_session("completed")
            logger_async.shutdown()

            # Async logging should complete in <1ms per event (very fast due to queuing)
            assert async_duration < 0.1  # 100 events in <100ms

    def test_secret_scrubbing_in_events(self):
        """TC-SESSION-007: Secrets are scrubbed from logged events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock secrets manager
            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {
                "TEST_SECRET": "secret_value_12345"
            }

            logger = SessionLogger(
                working_dir=Path(tmpdir),
                secrets_manager=secrets_manager,
                async_logging=False,
            )

            session = logger.start_session("Test")
            logger.log_event(EVENT_COMMAND, {"command": "export TEST_SECRET=secret_value_12345"})
            logger.end_session("completed")

            # Read log file and verify secret is scrubbed
            with open(session.log_file, 'r') as f:
                content = f.read()

            assert "secret_value_12345" not in content
            assert "[REDACTED:TEST_SECRET]" in content

    def test_list_sessions(self):
        """TC-SESSION-008: list_sessions returns session metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(
                working_dir=Path(tmpdir),
                async_logging=False,
            )

            # Create multiple sessions
            logger.start_session("Task 1", workflow_id="wf_1")
            logger.end_session("completed")

            logger.start_session("Task 2", workflow_id="wf_2")
            logger.end_session("completed")

            # List sessions
            sessions = logger.list_sessions()

            assert len(sessions) == 2
            assert any("Task 1" in s["task"] for s in sessions)
            assert any("Task 2" in s["task"] for s in sessions)

    def test_list_sessions_with_limit(self):
        """list_sessions respects limit parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(
                working_dir=Path(tmpdir),
                async_logging=False,
            )

            # Create 5 sessions
            for i in range(5):
                logger.start_session(f"Task {i}")
                logger.end_session("completed")

            sessions = logger.list_sessions(limit=3)
            assert len(sessions) == 3

    def test_list_sessions_filter_by_workflow_id(self):
        """list_sessions can filter by workflow_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(
                working_dir=Path(tmpdir),
                async_logging=False,
            )

            logger.start_session("Task 1", workflow_id="wf_123")
            logger.end_session("completed")

            logger.start_session("Task 2", workflow_id="wf_456")
            logger.end_session("completed")

            # Filter by workflow_id
            sessions = logger.list_sessions(workflow_id="wf_123")

            assert len(sessions) == 1
            assert sessions[0]["workflow_id"] == "wf_123"

    def test_get_session_events(self):
        """TC-SESSION-009: get_session_events returns all events for a session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(
                working_dir=Path(tmpdir),
                async_logging=False,
            )

            session = logger.start_session("Test")
            logger.log_event(EVENT_ITEM_COMPLETED, {"item_id": "item_1"})
            logger.log_event(EVENT_ITEM_COMPLETED, {"item_id": "item_2"})
            logger.end_session("completed")

            # Get events
            events = logger.get_session_events(session.session_id)

            assert events is not None
            assert len(events) >= 3  # start, 2 items, end
            assert any(e["type"] == EVENT_WORKFLOW_STARTED for e in events)
            assert any(e["type"] == EVENT_ITEM_COMPLETED for e in events)
            assert any(e["type"] == EVENT_WORKFLOW_FINISHED for e in events)


class TestSessionAnalyzer:
    """Tests for SessionAnalyzer class."""

    def test_analyze_empty_sessions(self):
        """TC-ANALYZE-001: Analyzer handles empty sessions directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / ".orchestrator" / "sessions"
            sessions_dir.mkdir(parents=True)

            analyzer = SessionAnalyzer(sessions_dir)
            report = analyzer.analyze()

            assert report["total_sessions"] == 0

    def test_completion_rate_calculation(self):
        """TC-ANALYZE-002: Completion rate calculated correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(
                working_dir=Path(tmpdir),
                async_logging=False,
            )

            # 2 completed, 1 abandoned
            logger.start_session("Task 1")
            logger.end_session("completed")

            logger.start_session("Task 2")
            logger.end_session("completed")

            logger.start_session("Task 3")
            logger.end_session("abandoned")

            # Analyze
            analyzer = SessionAnalyzer(logger.sessions_dir)
            report = analyzer.analyze()

            # 2/3 = 66.67%
            assert report["completion_rate"] == pytest.approx(0.666, abs=0.01)

    def test_failure_point_detection(self):
        """TC-ANALYZE-003: Failure points identified correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(
                working_dir=Path(tmpdir),
                async_logging=False,
            )

            # Session that fails in REVIEW phase
            logger.start_session("Task 1")
            logger.log_event(EVENT_PHASE_ADVANCED, {"phase": "EXECUTE", "to_phase": "REVIEW"})
            logger.end_session("abandoned")

            # Session that fails in REVIEW phase (again)
            logger.start_session("Task 2")
            logger.log_event(EVENT_PHASE_ADVANCED, {"phase": "EXECUTE", "to_phase": "REVIEW"})
            logger.end_session("abandoned")

            # Analyze
            analyzer = SessionAnalyzer(logger.sessions_dir)
            report = analyzer.analyze()

            # REVIEW should be most common failure point
            failure_points = report.get("failure_points", {})
            assert "REVIEW" in failure_points
            assert failure_points["REVIEW"] == 2

    def test_duration_stats_calculation(self):
        """TC-ANALYZE-004: Duration statistics calculated correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(
                working_dir=Path(tmpdir),
                async_logging=False,
            )

            # Create session with known duration
            logger.start_session("Task 1")
            time.sleep(0.1)  # 100ms delay
            logger.end_session("completed")

            # Analyze
            analyzer = SessionAnalyzer(logger.sessions_dir)
            report = analyzer.analyze()

            duration_stats = report.get("duration_stats", {})
            assert duration_stats["total_sessions"] == 1
            assert duration_stats["average_minutes"] > 0

    def test_error_frequency_calculation(self):
        """TC-ANALYZE-005: Error frequency calculated correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(
                working_dir=Path(tmpdir),
                async_logging=False,
            )

            logger.start_session("Task 1")
            logger.log_event(EVENT_ERROR, {"message": "Test error 1"})
            logger.log_event(EVENT_ERROR, {"message": "Test error 1"})
            logger.log_event(EVENT_ERROR, {"message": "Test error 2"})
            logger.end_session("completed")

            # Analyze
            analyzer = SessionAnalyzer(logger.sessions_dir)
            report = analyzer.analyze()

            error_frequency = report.get("error_frequency", [])
            assert len(error_frequency) > 0
            # Most frequent error should be "Test error 1"
            assert error_frequency[0][1] == 2  # 2 occurrences

    def test_phase_stats_calculation(self):
        """TC-ANALYZE-006: Phase completion stats calculated correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(
                working_dir=Path(tmpdir),
                async_logging=False,
            )

            # Session 1
            logger.start_session("Task 1")
            logger.log_event(EVENT_PHASE_ADVANCED, {"to_phase": "EXECUTE"})
            logger.log_event(EVENT_PHASE_ADVANCED, {"to_phase": "REVIEW"})
            logger.end_session("completed")

            # Session 2
            logger.start_session("Task 2")
            logger.log_event(EVENT_PHASE_ADVANCED, {"to_phase": "EXECUTE"})
            logger.end_session("completed")

            # Analyze
            analyzer = SessionAnalyzer(logger.sessions_dir)
            report = analyzer.analyze()

            phase_stats = report.get("phase_stats", {})
            assert phase_stats["EXECUTE"] == 2  # Both sessions
            assert phase_stats["REVIEW"] == 1   # Only session 1


class TestAnalysisReportFormatting:
    """Tests for report formatting."""

    def test_format_analysis_report(self):
        """TC-ANALYZE-007: Analysis report formats correctly."""
        analysis = {
            "total_sessions": 10,
            "completion_rate": 0.8,
            "failure_points": {"REVIEW": 5, "EXECUTE": 2},
            "duration_stats": {
                "average_minutes": 45.5,
                "min_minutes": 10.0,
                "max_minutes": 90.0,
            },
            "error_frequency": [
                ("Test error 1", 10),
                ("Test error 2", 5),
            ],
            "phase_stats": {"EXECUTE": 8, "REVIEW": 6},
            "analysis_period_days": 30,
        }

        report = format_analysis_report(analysis)

        assert "Total Sessions: 10" in report
        assert "80.0%" in report  # Completion rate
        assert "REVIEW: 5 failures" in report
        assert "45.5 minutes" in report

    def test_format_empty_analysis(self):
        """Report formats correctly for empty analysis."""
        analysis = {
            "total_sessions": 0,
            "message": "No sessions found",
        }

        report = format_analysis_report(analysis)

        assert "No sessions found" in report


class TestSecurityAndPerformance:
    """Security and performance tests."""

    def test_no_secrets_in_log_files(self):
        """TC-SECURITY-001: CRITICAL - No secrets appear in session log files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock secrets manager with real-looking secrets
            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {
                "OPENAI_API_KEY": "sk-proj-abc123def456ghi789jkl012",
                "GITHUB_TOKEN": "ghp_1234567890abcdefghijklmnopqrstuvwxyz",
            }

            logger = SessionLogger(
                working_dir=Path(tmpdir),
                secrets_manager=secrets_manager,
                async_logging=False,
            )

            # Log events with secrets
            session = logger.start_session("Test")
            logger.log_event(EVENT_COMMAND, {
                "command": "export OPENAI_API_KEY=sk-proj-abc123def456ghi789jkl012"
            })
            logger.log_event(EVENT_OUTPUT, {
                "text": "Using token ghp_1234567890abcdefghijklmnopqrstuvwxyz"
            })
            logger.end_session("completed")

            # Read raw log file
            with open(session.log_file, 'r') as f:
                content = f.read()

            # CRITICAL: Verify secrets are NOT in file
            assert "sk-proj-abc123def456ghi789jkl012" not in content
            assert "ghp_1234567890abcdefghijklmnopqrstuvwxyz" not in content

            # Verify redaction markers ARE in file
            assert "[REDACTED:OPENAI_API_KEY]" in content
            assert "[REDACTED:GITHUB_TOKEN]" in content

    def test_performance_overhead(self):
        """TC-PERFORMANCE-001: Async logging completes quickly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Test that async logging doesn't block the main thread
            logger = SessionLogger(
                working_dir=Path(tmpdir),
                async_logging=True,
            )
            session = logger.start_session("Performance test")

            # Log many events - should complete quickly due to async
            start = time.time()
            for i in range(1000):
                logger.log_event(EVENT_ITEM_COMPLETED, {"item_id": f"item_{i}"})
            log_time = time.time() - start

            logger.end_session("completed")
            logger.shutdown()

            # With async logging, this should be very fast (<1 second for 1000 events)
            # Being very generous for test stability across different systems
            assert log_time < 5.0  # 5 seconds max


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
