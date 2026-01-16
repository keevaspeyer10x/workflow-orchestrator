"""Tests for ErrorEvent model - Phase 1 Detection & Fingerprinting."""

from datetime import datetime
import pytest


class TestErrorEvent:
    """Tests for ErrorEvent data model."""

    def test_error_event_required_fields(self):
        """Creates with required fields only."""
        from src.healing.models import ErrorEvent

        error = ErrorEvent(
            error_id="err-001",
            timestamp=datetime(2026, 1, 16, 12, 0, 0),
            source="subprocess",
            description="ImportError: No module named 'foo'",
        )

        assert error.error_id == "err-001"
        assert error.source == "subprocess"
        assert error.description == "ImportError: No module named 'foo'"
        assert error.error_type is None
        assert error.file_path is None
        assert error.fingerprint is None

    def test_error_event_all_fields(self):
        """Creates with all optional fields."""
        from src.healing.models import ErrorEvent

        error = ErrorEvent(
            error_id="err-002",
            timestamp=datetime(2026, 1, 16, 12, 0, 0),
            source="workflow_log",
            description="TypeError: 'NoneType' object is not subscriptable",
            error_type="TypeError",
            file_path="src/main.py",
            line_number=42,
            stack_trace='File "src/main.py", line 42, in main\n    x = data[0]',
            command=None,
            exit_code=None,
            fingerprint="abc123",
            fingerprint_coarse="abc1",
            workflow_id="wf-001",
            phase_id="EXECUTE",
            project_id="proj-001",
        )

        assert error.error_type == "TypeError"
        assert error.file_path == "src/main.py"
        assert error.line_number == 42
        assert error.fingerprint == "abc123"

    def test_error_event_timestamp_default(self):
        """Uses provided timestamp."""
        from src.healing.models import ErrorEvent

        ts = datetime(2026, 1, 16, 14, 30, 0)
        error = ErrorEvent(
            error_id="err-003",
            timestamp=ts,
            source="hook",
            description="Test error",
        )

        assert error.timestamp == ts

    def test_error_event_source_literal(self):
        """Validates source is one of allowed values."""
        from src.healing.models import ErrorEvent

        # Valid sources
        for source in ["workflow_log", "transcript", "subprocess", "hook"]:
            error = ErrorEvent(
                error_id="err-004",
                timestamp=datetime.now(),
                source=source,
                description="Test",
            )
            assert error.source == source
