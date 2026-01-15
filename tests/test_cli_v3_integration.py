"""
Tests for V3 CLI Integration - Phase 5.

Tests cover:
- orchestrator health command
- Mode detection at workflow start
- Audit logging integration
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


class TestHealthCommand:
    """Test orchestrator health CLI command."""

    def test_cmd_health_returns_ok(self, tmp_path, monkeypatch, capsys):
        """Health command returns OK for healthy system."""
        monkeypatch.chdir(tmp_path)

        # Import after chdir to pick up correct working directory
        from src.cli import cmd_health

        args = MagicMock()
        args.dir = str(tmp_path)
        args.json = False

        result = cmd_health(args)

        captured = capsys.readouterr()
        assert "ok" in captured.out.lower() or result == 0

    def test_cmd_health_json_output(self, tmp_path, monkeypatch, capsys):
        """Health command returns valid JSON with --json flag."""
        monkeypatch.chdir(tmp_path)

        from src.cli import cmd_health

        args = MagicMock()
        args.dir = str(tmp_path)
        args.json = True

        cmd_health(args)

        captured = capsys.readouterr()
        # Should be valid JSON
        report = json.loads(captured.out)
        assert 'overall_status' in report
        assert 'components' in report

    def test_cmd_health_shows_warning_for_corrupted_state(self, tmp_path, monkeypatch, capsys):
        """Health command shows warning for corrupted state file."""
        monkeypatch.chdir(tmp_path)

        # Create corrupted state file
        state_dir = tmp_path / ".orchestrator" / "v3"
        state_dir.mkdir(parents=True)
        state_file = state_dir / "state.json"
        state_file.write_text("not valid json")

        from src.cli import cmd_health

        args = MagicMock()
        args.dir = str(tmp_path)
        args.json = False

        cmd_health(args)

        captured = capsys.readouterr()
        # Should indicate error or warning
        assert "error" in captured.out.lower() or "warning" in captured.out.lower()


class TestModeDetectionIntegration:
    """Test mode detection integration with workflow start."""

    def test_mode_detection_called_at_start(self, tmp_path, monkeypatch):
        """Mode detection is called when starting a workflow."""
        from src.mode_detection import detect_operator_mode, OperatorMode

        # Clear environment to get consistent results
        monkeypatch.delenv("CLAUDECODE", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
        monkeypatch.delenv("ORCHESTRATOR_MODE", raising=False)

        result = detect_operator_mode()

        # Should return a valid result
        assert result.mode in (OperatorMode.HUMAN, OperatorMode.LLM)
        assert result.confidence in ("high", "medium", "low")
        assert result.reason  # Should have a reason

    def test_mode_detection_llm_mode_detected(self, tmp_path, monkeypatch):
        """LLM mode is detected when CLAUDECODE=1."""
        monkeypatch.setenv("CLAUDECODE", "1")

        from src.mode_detection import detect_operator_mode, OperatorMode

        result = detect_operator_mode()

        assert result.mode == OperatorMode.LLM
        assert result.confidence == "high"
        assert "CLAUDECODE" in result.reason


class TestAuditLoggingIntegration:
    """Test audit logging integration."""

    def test_audit_logger_creates_log_file(self, tmp_path):
        """Audit logger creates log file in .orchestrator directory."""
        from src.audit import AuditLogger

        log_dir = tmp_path / ".orchestrator"
        logger = AuditLogger(log_dir)

        # Log an event
        logger.log_event("test_event", key="value")

        # Check log file exists
        assert (log_dir / "audit.jsonl").exists()

        # Check content
        content = (log_dir / "audit.jsonl").read_text()
        entry = json.loads(content.strip())
        assert entry['event'] == "test_event"
        assert 'hash' in entry

    def test_audit_logger_chained_hashes(self, tmp_path):
        """Audit logger maintains chained hashes."""
        from src.audit import AuditLogger

        log_dir = tmp_path / ".orchestrator"
        logger = AuditLogger(log_dir)

        # Log multiple events
        logger.log_event("event1")
        logger.log_event("event2")
        logger.log_event("event3")

        # Read and verify chain
        content = (log_dir / "audit.jsonl").read_text().strip().split('\n')
        entries = [json.loads(line) for line in content]

        # First entry has no prev_hash (key may be absent or None)
        assert entries[0].get('prev_hash') is None

        # Subsequent entries chain to previous
        assert entries[1]['prev_hash'] == entries[0]['hash']
        assert entries[2]['prev_hash'] == entries[1]['hash']

    def test_audit_logger_verify_integrity(self, tmp_path):
        """Audit logger can verify log integrity."""
        from src.audit import AuditLogger

        log_dir = tmp_path / ".orchestrator"
        logger = AuditLogger(log_dir)

        # Log some events
        logger.log_event("event1")
        logger.log_event("event2")

        # Verify integrity
        assert logger.verify_integrity() is True


class TestStateVersionIntegration:
    """Test v3 state versioning integration."""

    def test_state_save_with_integrity(self, tmp_path):
        """State is saved with version and checksum."""
        from src.state_version import save_state_with_integrity, STATE_VERSION

        state_file = tmp_path / "state.json"
        state_data = {"workflow_id": "wf_test", "phase": "PLAN"}

        save_state_with_integrity(state_file, state_data)

        # Read and verify
        with open(state_file) as f:
            saved = json.load(f)

        assert saved['_version'] == STATE_VERSION
        assert '_checksum' in saved
        assert '_updated_at' in saved

    def test_state_load_with_verification(self, tmp_path):
        """State load verifies integrity."""
        from src.state_version import (
            save_state_with_integrity,
            load_state_with_verification
        )

        state_file = tmp_path / "state.json"
        original = {"workflow_id": "wf_test", "phase": "EXECUTE"}

        save_state_with_integrity(state_file, original)
        loaded = load_state_with_verification(state_file)

        assert loaded['workflow_id'] == original['workflow_id']
        assert loaded['phase'] == original['phase']

    def test_state_integrity_error_on_tampering(self, tmp_path):
        """State load raises error if tampered."""
        from src.state_version import (
            save_state_with_integrity,
            load_state_with_verification,
            StateIntegrityError
        )

        state_file = tmp_path / "state.json"
        save_state_with_integrity(state_file, {"key": "value"})

        # Tamper with file
        with open(state_file, 'r+') as f:
            data = json.load(f)
            data['key'] = 'tampered'
            f.seek(0)
            json.dump(data, f)
            f.truncate()

        with pytest.raises(StateIntegrityError):
            load_state_with_verification(state_file)


class TestGateEnforcementIntegration:
    """Test gate enforcement in CLI."""

    def test_artifact_gate_blocks_on_missing_file(self, tmp_path):
        """Artifact gate blocks completion when file is missing."""
        from src.gates import ArtifactGate

        gate = ArtifactGate(path="missing.md", validator="not_empty")
        result = gate.validate(tmp_path)

        assert result is False

    def test_artifact_gate_passes_on_existing_file(self, tmp_path):
        """Artifact gate passes when file exists and is not empty."""
        from src.gates import ArtifactGate

        # Create file
        test_file = tmp_path / "plan.md"
        test_file.write_text("# Plan\n\nContent here.")

        gate = ArtifactGate(path="plan.md", validator="not_empty")
        result = gate.validate(tmp_path)

        assert result is True

    def test_command_gate_passes_on_success(self, tmp_path):
        """Command gate passes when command succeeds."""
        from src.gates import CommandGate

        gate = CommandGate(command="true")
        result = gate.validate(tmp_path)

        assert result is True

    def test_command_gate_fails_on_error(self, tmp_path):
        """Command gate fails when command fails."""
        from src.gates import CommandGate

        gate = CommandGate(command="false")
        result = gate.validate(tmp_path)

        assert result is False
