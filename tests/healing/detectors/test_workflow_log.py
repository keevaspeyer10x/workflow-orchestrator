"""Tests for WorkflowLogDetector - Phase 1 Detection & Fingerprinting."""

import json
import tempfile
from datetime import datetime
from pathlib import Path
import pytest


class TestWorkflowLogDetector:
    """Tests for detecting errors from workflow logs."""

    def test_detect_no_errors(self):
        """Empty errors list for successful workflow."""
        from src.healing.detectors.workflow_log import WorkflowLogDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = WorkflowLogDetector(fp)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"event_type": "phase_start", "phase": "PLAN"}) + "\n")
            f.write(
                json.dumps({"event_type": "item_completed", "item": "check_roadmap"})
                + "\n"
            )
            f.flush()

            errors = detector.detect(f.name)

        assert len(errors) == 0

    def test_detect_single_error(self):
        """Parses single error event."""
        from src.healing.detectors.workflow_log import WorkflowLogDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = WorkflowLogDetector(fp)

        error_event = {
            "event_type": "error",
            "timestamp": "2026-01-16T12:00:00Z",
            "description": "TypeError: 'NoneType' is not subscriptable",
            "file_path": "src/main.py",
            "line_number": 42,
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(error_event) + "\n")
            f.flush()

            errors = detector.detect(f.name)

        assert len(errors) == 1
        assert "TypeError" in errors[0].description
        assert errors[0].fingerprint is not None

    def test_detect_multiple_errors(self):
        """Parses multiple error events."""
        from src.healing.detectors.workflow_log import WorkflowLogDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = WorkflowLogDetector(fp)

        events = [
            {"event_type": "error", "description": "Error 1"},
            {"event_type": "phase_start", "phase": "EXECUTE"},
            {"event_type": "error", "description": "Error 2"},
            {"event_type": "error", "description": "Error 3"},
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for event in events:
                f.write(json.dumps(event) + "\n")
            f.flush()

            errors = detector.detect(f.name)

        assert len(errors) == 3

    def test_detect_error_event_fields(self):
        """Correctly maps JSONL fields to ErrorEvent."""
        from src.healing.detectors.workflow_log import WorkflowLogDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = WorkflowLogDetector(fp)

        error_event = {
            "event_type": "error",
            "timestamp": "2026-01-16T12:00:00Z",
            "description": "ImportError: No module named 'foo'",
            "error_type": "ImportError",
            "file_path": "src/app.py",
            "line_number": 10,
            "stack_trace": "Traceback...",
            "workflow_id": "wf-001",
            "phase_id": "EXECUTE",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(error_event) + "\n")
            f.flush()

            errors = detector.detect(f.name)

        error = errors[0]
        assert error.error_type == "ImportError"
        assert error.file_path == "src/app.py"
        assert error.line_number == 10
        assert error.source == "workflow_log"

    def test_detect_file_not_found(self):
        """Handles missing log file gracefully."""
        from src.healing.detectors.workflow_log import WorkflowLogDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = WorkflowLogDetector(fp)

        errors = detector.detect("/nonexistent/path.jsonl")
        assert len(errors) == 0

    def test_detect_invalid_json(self):
        """Handles malformed JSONL lines."""
        from src.healing.detectors.workflow_log import WorkflowLogDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = WorkflowLogDetector(fp)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"event_type": "error", "description": "Valid error"}\n')
            f.write("not valid json\n")
            f.write('{"event_type": "error", "description": "Another error"}\n')
            f.flush()

            errors = detector.detect(f.name)

        # Should still detect the valid errors
        assert len(errors) == 2
