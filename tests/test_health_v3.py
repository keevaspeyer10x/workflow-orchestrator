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

        # Create valid state file
        state_dir = tmp_path / ".orchestrator" / "v3"
        state_dir.mkdir(parents=True)
        state_file = state_dir / "state.json"
        state_file.write_text('{"_version": "3.0", "_checksum": "abc123"}')

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
