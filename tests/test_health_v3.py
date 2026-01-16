"""
Tests for v3 Health Check System.

Tests cover:
- HealthChecker component checks
- Health report generation
- CLI command integration
"""

import json
from pathlib import Path
import pytest


class TestHealthChecker:
    """Test health check functionality."""

    def test_state_file_healthy(self, tmp_path):
        """State file passes health check when valid."""
        from src.health import HealthChecker
        from src.state_version import save_state_with_integrity

        # Create valid state file using save_state_with_integrity
        state_dir = tmp_path / ".orchestrator" / "v3"
        state_dir.mkdir(parents=True)
        state_file = state_dir / "state.json"

        # Use proper state creation with valid checksum
        state_data = {"workflow_id": "test", "phase": "PLAN"}
        save_state_with_integrity(state_file, state_data)

        checker = HealthChecker(working_dir=tmp_path)
        report = checker.check_state()

        assert report.status == "ok"

    def test_state_file_corrupted(self, tmp_path):
        """State file fails health check when corrupted."""
        from src.health import HealthChecker

        # Create corrupted state file
        state_dir = tmp_path / ".orchestrator" / "v3"
        state_dir.mkdir(parents=True)
        state_file = state_dir / "state.json"
        state_file.write_text('not valid json')

        checker = HealthChecker(working_dir=tmp_path)
        report = checker.check_state()

        assert report.status == "error"
        assert "json" in report.message.lower() or "invalid" in report.message.lower()

    def test_state_file_missing(self, tmp_path):
        """State file passes when missing (no workflow active)."""
        from src.health import HealthChecker

        checker = HealthChecker(working_dir=tmp_path)
        report = checker.check_state()

        # Missing is OK (no active workflow)
        assert report.status in ("ok", "warning")

    def test_lock_state_healthy(self, tmp_path):
        """Lock state passes health check when no stale locks."""
        from src.health import HealthChecker

        checker = HealthChecker(working_dir=tmp_path)
        report = checker.check_locks()

        assert report.status == "ok"

    def test_full_health_report(self, tmp_path):
        """Full health report includes all components."""
        from src.health import HealthChecker

        checker = HealthChecker(working_dir=tmp_path)
        report = checker.full_check()

        # Should have multiple component checks
        assert len(report.components) >= 2
        assert report.overall_status in ("ok", "warning", "error")


class TestHealthReport:
    """Test health report structure."""

    def test_report_to_dict(self, tmp_path):
        """Health report can be serialized to dict."""
        from src.health import HealthChecker

        checker = HealthChecker(working_dir=tmp_path)
        report = checker.full_check()
        report_dict = report.to_dict()

        assert 'overall_status' in report_dict
        assert 'components' in report_dict
        assert isinstance(report_dict['components'], list)

    def test_report_to_json(self, tmp_path):
        """Health report can be serialized to JSON."""
        from src.health import HealthChecker

        checker = HealthChecker(working_dir=tmp_path)
        report = checker.full_check()

        # Should not raise
        json_str = report.to_json()
        parsed = json.loads(json_str)
        assert 'overall_status' in parsed


class TestAuditIntegrityCheck:
    """Test audit log integrity verification (#74)."""

    def test_audit_integrity_no_log(self, tmp_path):
        """Missing audit log returns ok status (#74)."""
        from src.health import HealthChecker

        checker = HealthChecker(working_dir=tmp_path)
        report = checker.check_audit_integrity()

        assert report.status == "ok"
        assert "No audit log present" in report.message

    def test_audit_integrity_valid_chain(self, tmp_path):
        """Valid audit log chain passes integrity check (#74)."""
        from src.health import HealthChecker
        from src.audit import AuditLogger

        # Create valid audit log
        orchestrator_dir = tmp_path / ".orchestrator"
        orchestrator_dir.mkdir(parents=True)

        audit_logger = AuditLogger(log_dir=orchestrator_dir)
        audit_logger.log_event("event_1")
        audit_logger.log_event("event_2")
        audit_logger.log_event("event_3")

        # Check integrity
        checker = HealthChecker(working_dir=tmp_path)
        report = checker.check_audit_integrity()

        assert report.status == "ok"
        assert "3 entries" in report.message

    def test_audit_integrity_broken_chain(self, tmp_path):
        """Broken hash chain is detected (#74)."""
        from src.health import HealthChecker
        from src.audit import AuditLogger

        # Create valid audit log first
        orchestrator_dir = tmp_path / ".orchestrator"
        orchestrator_dir.mkdir(parents=True)

        audit_logger = AuditLogger(log_dir=orchestrator_dir)
        audit_logger.log_event("event_1")
        audit_logger.log_event("event_2")

        # Now tamper with the prev_hash of the second entry
        audit_file = orchestrator_dir / "audit.jsonl"
        lines = audit_file.read_text().strip().split('\n')
        entry = json.loads(lines[1])
        entry['prev_hash'] = "tampered_hash"
        lines[1] = json.dumps(entry)
        audit_file.write_text('\n'.join(lines) + '\n')

        # Check integrity
        checker = HealthChecker(working_dir=tmp_path)
        report = checker.check_audit_integrity()

        assert report.status == "error"
        assert "chain broken" in report.message.lower()

    def test_audit_integrity_tampered_hash(self, tmp_path):
        """Tampered entry hash is detected (#74 - from minds review)."""
        from src.health import HealthChecker
        from src.audit import AuditLogger

        # Create valid audit log first
        orchestrator_dir = tmp_path / ".orchestrator"
        orchestrator_dir.mkdir(parents=True)

        audit_logger = AuditLogger(log_dir=orchestrator_dir)
        audit_logger.log_event("event_1")

        # Now tamper with the event (which changes the expected hash)
        audit_file = orchestrator_dir / "audit.jsonl"
        lines = audit_file.read_text().strip().split('\n')
        entry = json.loads(lines[0])
        entry['event'] = "tampered_event"  # Change event but keep original hash
        lines[0] = json.dumps(entry)
        audit_file.write_text('\n'.join(lines) + '\n')

        # Check integrity - should detect hash mismatch
        checker = HealthChecker(working_dir=tmp_path)
        report = checker.check_audit_integrity()

        assert report.status == "error"
        assert "hash mismatch" in report.message.lower()

    def test_audit_integrity_invalid_json(self, tmp_path):
        """Invalid JSON in audit log is detected (#74)."""
        from src.health import HealthChecker

        # Create audit log with invalid JSON on second line
        orchestrator_dir = tmp_path / ".orchestrator"
        orchestrator_dir.mkdir(parents=True)
        audit_file = orchestrator_dir / "audit.jsonl"
        audit_file.write_text('not valid json at all\n')

        # Check integrity
        checker = HealthChecker(working_dir=tmp_path)
        report = checker.check_audit_integrity()

        assert report.status == "error"
        # Error could be "Invalid JSON" or caught by general exception handler
        assert "error" in report.status or "Invalid" in report.message or "Error" in report.message

    def test_full_check_includes_audit_integrity(self, tmp_path):
        """Full health check includes audit integrity (#74)."""
        from src.health import HealthChecker

        checker = HealthChecker(working_dir=tmp_path)
        report = checker.full_check()

        # Should have audit_log component
        component_names = [c.name for c in report.components]
        assert "audit_log" in component_names
