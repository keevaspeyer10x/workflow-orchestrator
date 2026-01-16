"""
Tests for v3 Audit Logging System.

Tests cover:
- AuditLogger operations
- Tamper detection with chained hashes
- Log sanitization
"""

import json
from pathlib import Path
from datetime import datetime, timezone
import pytest


class TestAuditLogger:
    """Test audit logging functionality."""

    def test_log_checkpoint_create(self, tmp_path):
        """Log checkpoint create operation."""
        from src.audit import AuditLogger

        logger = AuditLogger(log_dir=tmp_path)
        logger.log_checkpoint_create(
            checkpoint_id="cp_test_123",
            workflow_id="wf_test",
            phase_id="PLAN"
        )

        # Verify log entry exists
        log_file = tmp_path / "audit.jsonl"
        assert log_file.exists()

        entries = [json.loads(line) for line in log_file.read_text().strip().split('\n')]
        assert len(entries) == 1
        assert entries[0]['event'] == 'checkpoint_create'
        assert entries[0]['data']['checkpoint_id'] == 'cp_test_123'
        assert 'hash' in entries[0]

    def test_log_mode_change(self, tmp_path):
        """Log mode change operation."""
        from src.audit import AuditLogger

        logger = AuditLogger(log_dir=tmp_path)
        logger.log_mode_change(
            old_mode="llm",
            new_mode="human",
            reason="emergency override"
        )

        log_file = tmp_path / "audit.jsonl"
        entries = [json.loads(line) for line in log_file.read_text().strip().split('\n')]
        assert entries[0]['event'] == 'mode_change'
        assert entries[0]['data']['old_mode'] == 'llm'
        assert entries[0]['data']['new_mode'] == 'human'

    def test_tamper_detection(self, tmp_path):
        """Tamper detection with chained hashes."""
        from src.audit import AuditLogger, AuditTamperError

        logger = AuditLogger(log_dir=tmp_path)

        # Log a few entries
        logger.log_checkpoint_create("cp_1", "wf_1", "PLAN")
        logger.log_checkpoint_create("cp_2", "wf_1", "EXECUTE")

        # Tamper with the log - change the event name which affects hash
        log_file = tmp_path / "audit.jsonl"
        lines = log_file.read_text().strip().split('\n')
        entry = json.loads(lines[0])
        entry['event'] = 'TAMPERED_EVENT'  # Change something that's in the hash content
        lines[0] = json.dumps(entry)
        log_file.write_text('\n'.join(lines) + '\n')

        # Should detect tamper
        with pytest.raises(AuditTamperError):
            logger.verify_integrity()

    def test_sanitize_paths(self, tmp_path):
        """Sensitive paths are sanitized in logs."""
        from src.audit import AuditLogger

        logger = AuditLogger(log_dir=tmp_path)
        logger.log_event("file_access", path="/home/user/.secrets/api_key.txt")

        log_file = tmp_path / "audit.jsonl"
        entries = [json.loads(line) for line in log_file.read_text().strip().split('\n')]
        # Path should be sanitized - data is stored under 'data' field
        assert 'data' in entries[0]
        assert entries[0]['data']['path'] == '[REDACTED]'
        assert '.secrets' not in entries[0]['data']['path']


class TestAuditIntegrity:
    """Test audit log integrity features."""

    def test_chained_hashes(self, tmp_path):
        """Each log entry includes hash of previous entry."""
        from src.audit import AuditLogger

        logger = AuditLogger(log_dir=tmp_path)

        logger.log_event("event_1", data="first")
        logger.log_event("event_2", data="second")
        logger.log_event("event_3", data="third")

        log_file = tmp_path / "audit.jsonl"
        entries = [json.loads(line) for line in log_file.read_text().strip().split('\n')]

        # First entry has no previous hash
        assert entries[0].get('prev_hash') is None

        # Subsequent entries chain to previous
        assert entries[1].get('prev_hash') == entries[0]['hash']
        assert entries[2].get('prev_hash') == entries[1]['hash']

    def test_verify_integrity_passes(self, tmp_path):
        """Verify integrity passes for untampered logs."""
        from src.audit import AuditLogger

        logger = AuditLogger(log_dir=tmp_path)

        logger.log_event("event_1")
        logger.log_event("event_2")
        logger.log_event("event_3")

        # Should not raise
        assert logger.verify_integrity() is True

    def test_hmac_compare_digest_used(self, tmp_path):
        """Verify hmac.compare_digest is used for timing attack prevention (#71)."""
        from src.audit import AuditLogger
        from unittest.mock import patch

        logger = AuditLogger(log_dir=tmp_path)
        logger.log_event("event_1")
        logger.log_event("event_2")

        # Patch hmac.compare_digest to verify it's called
        with patch('src.audit.hmac.compare_digest', return_value=True) as mock_compare:
            logger.verify_integrity()
            # Should be called for each entry's hash verification
            assert mock_compare.call_count >= 1


class TestAuditEfficiency:
    """Test audit log efficiency improvements (#79)."""

    def test_load_last_hash_empty_file(self, tmp_path):
        """Verify empty audit log doesn't cause errors (#79)."""
        from src.audit import AuditLogger

        # Create empty audit log file
        audit_file = tmp_path / "audit.jsonl"
        audit_file.write_text("")

        # Should initialize without error
        logger = AuditLogger(log_dir=tmp_path)
        assert logger._last_hash is None

    def test_load_last_hash_small_file(self, tmp_path):
        """Verify small files work correctly (#79)."""
        from src.audit import AuditLogger
        import json

        # Create small audit log
        logger = AuditLogger(log_dir=tmp_path)
        logger.log_event("single_event", data="test")
        expected_hash = logger._last_hash

        # Create new logger to test loading
        logger2 = AuditLogger(log_dir=tmp_path)
        assert logger2._last_hash == expected_hash

    def test_load_last_hash_multiple_entries(self, tmp_path):
        """Verify correct last hash is loaded with multiple entries (#79)."""
        from src.audit import AuditLogger

        logger = AuditLogger(log_dir=tmp_path)
        logger.log_event("event_1")
        logger.log_event("event_2")
        logger.log_event("event_3")
        expected_hash = logger._last_hash

        # Create new logger to test loading
        logger2 = AuditLogger(log_dir=tmp_path)
        assert logger2._last_hash == expected_hash

    def test_load_last_hash_binary_mode(self, tmp_path):
        """Verify binary mode reading works correctly (#79)."""
        from src.audit import AuditLogger

        logger = AuditLogger(log_dir=tmp_path)
        # Add entry with unicode characters
        logger.log_event("test_event", message="Hello 世界")
        expected_hash = logger._last_hash

        # Create new logger to verify loading works
        logger2 = AuditLogger(log_dir=tmp_path)
        assert logger2._last_hash == expected_hash
