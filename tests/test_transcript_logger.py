"""
Tests for the session transcript logging module.

CORE-024: Session Transcript Logging with Secret Scrubbing
"""

import os
import json
import tempfile
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.transcript_logger import (
    TranscriptLogger,
    DEFAULT_SCRUB_PATTERNS,
    DEFAULT_RETENTION_DAYS,
    SESSIONS_DIR_NAME,
)
from src.secrets import SecretsManager


class TestSecretScrubbing:
    """Tests for secret scrubbing functionality."""

    def test_scrub_known_secret(self):
        """TC-SCRUB-001: Known secrets replaced with [REDACTED:NAME]."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock secrets manager with a known secret
            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {
                "OPENAI_API_KEY": "sk-real-secret-key-12345"
            }

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=Path(tmpdir) / ".workflow_sessions"
            )

            text = "Using API key: sk-real-secret-key-12345 for request"
            scrubbed = logger.scrub(text)

            assert "sk-real-secret-key-12345" not in scrubbed
            assert "[REDACTED:OPENAI_API_KEY]" in scrubbed

    def test_scrub_openai_pattern(self):
        """TC-SCRUB-002: Pattern-based scrubbing for OpenAI keys (sk-...)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=Path(tmpdir) / ".workflow_sessions"
            )

            text = "OpenAI key: sk-proj-abc123XYZdef456"
            scrubbed = logger.scrub(text)

            assert "sk-proj-abc123XYZdef456" not in scrubbed
            assert "[REDACTED:OPENAI_KEY]" in scrubbed

    def test_scrub_github_pattern(self):
        """TC-SCRUB-003: Pattern-based scrubbing for GitHub tokens (ghp_...)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=Path(tmpdir) / ".workflow_sessions"
            )

            # GitHub tokens are at least 36 chars after ghp_
            text = "GitHub token: ghp_abcdefghijklmnopqrstuvwxyz1234567890AB"
            scrubbed = logger.scrub(text)

            assert "ghp_abcdefghijklmnopqrstuvwxyz1234567890AB" not in scrubbed
            assert "[REDACTED:GITHUB_TOKEN]" in scrubbed

    def test_scrub_xai_pattern(self):
        """TC-SCRUB-004: Pattern-based scrubbing for xAI keys (xai-...)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=Path(tmpdir) / ".workflow_sessions"
            )

            # xAI keys are at least 20 chars after xai-
            text = "xAI API key: xai-abc123def456ghi789jkl012"
            scrubbed = logger.scrub(text)

            assert "xai-abc123def456ghi789jkl012" not in scrubbed
            assert "[REDACTED:XAI_KEY]" in scrubbed

    def test_scrub_stripe_pattern(self):
        """TC-SCRUB-005: Pattern-based scrubbing for Stripe keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=Path(tmpdir) / ".workflow_sessions"
            )

            # Stripe keys are at least 20 chars after pk_live_ or sk_live_
            text = "Stripe keys: pk_live_abc123def456ghi789jkl and sk_live_xyz789abc123def456ghi"
            scrubbed = logger.scrub(text)

            assert "pk_live_abc123def456ghi789jkl" not in scrubbed
            assert "sk_live_xyz789abc123def456ghi" not in scrubbed
            assert "[REDACTED:STRIPE_KEY]" in scrubbed

    def test_scrub_bearer_token(self):
        """TC-SCRUB-006: Pattern-based scrubbing for Bearer tokens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=Path(tmpdir) / ".workflow_sessions"
            )

            text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
            scrubbed = logger.scrub(text)

            assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in scrubbed
            assert "[REDACTED:BEARER_TOKEN]" in scrubbed

    def test_scrub_multiple_secrets(self):
        """Scrubbing handles multiple secrets in same text."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {
                "API_KEY": "secret123"
            }

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=Path(tmpdir) / ".workflow_sessions"
            )

            # Use tokens that are long enough to match patterns
            text = "Using secret123 and ghp_tokenvalue12345678901234567890123456 and sk-openaikeyabcdef123456789"
            scrubbed = logger.scrub(text)

            assert "secret123" not in scrubbed
            assert "ghp_tokenvalue" not in scrubbed
            assert "sk-openaikey" not in scrubbed

    def test_scrub_preserves_non_secret_text(self):
        """Scrubbing preserves text that isn't a secret."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=Path(tmpdir) / ".workflow_sessions"
            )

            text = "Normal text with sk- prefix but no key following"
            scrubbed = logger.scrub(text)

            # Text without actual patterns should be mostly preserved
            assert "Normal text" in scrubbed

    def test_known_secret_priority_over_pattern(self):
        """Known secrets are replaced before pattern matching."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_manager = MagicMock(spec=SecretsManager)
            # Known secret that matches a pattern
            secrets_manager.get_all_known_secrets.return_value = {
                "MY_OPENAI_KEY": "sk-my-specific-key-abc123"
            }

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=Path(tmpdir) / ".workflow_sessions"
            )

            text = "Using key: sk-my-specific-key-abc123"
            scrubbed = logger.scrub(text)

            # Should use the known secret name, not generic pattern name
            assert "[REDACTED:MY_OPENAI_KEY]" in scrubbed


class TestSessionLogging:
    """Tests for session logging functionality."""

    def test_log_creates_session_file(self):
        """TC-LOG-001: Session logged to correct directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / ".workflow_sessions"
            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=sessions_dir
            )

            logger.log("test-session-001", "Session content here")

            # Check file was created
            session_files = list(sessions_dir.glob("*.jsonl"))
            assert len(session_files) == 1
            assert "test-session-001" in session_files[0].name

    def test_log_auto_creates_directory(self):
        """TC-LOG-002: Session directory auto-created on first log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / ".workflow_sessions"
            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=sessions_dir
            )

            assert not sessions_dir.exists()
            logger.log("test-session", "content")
            assert sessions_dir.exists()

    def test_log_content_is_scrubbed(self):
        """Logged content has secrets scrubbed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / ".workflow_sessions"
            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {
                "API_KEY": "supersecret123"
            }

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=sessions_dir
            )

            logger.log("test-session", "Content with supersecret123 in it")

            # Read the file and verify secret is scrubbed
            session_files = list(sessions_dir.glob("*.jsonl"))
            content = session_files[0].read_text()

            assert "supersecret123" not in content
            assert "[REDACTED:API_KEY]" in content

    def test_log_append_mode(self):
        """Multiple log calls append to same session file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / ".workflow_sessions"
            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=sessions_dir
            )

            logger.log("test-session", "First entry")
            logger.log("test-session", "Second entry")

            # Should still be one file
            session_files = list(sessions_dir.glob("*test-session*.jsonl"))
            assert len(session_files) == 1

            content = session_files[0].read_text()
            lines = content.strip().split("\n")
            assert len(lines) == 2


class TestSessionListing:
    """Tests for session listing functionality."""

    def test_list_sessions_empty(self):
        """List returns empty when no sessions exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / ".workflow_sessions"
            sessions_dir.mkdir()

            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=sessions_dir
            )

            sessions = logger.list_sessions()
            assert sessions == []

    def test_list_sessions_sorted_by_date(self):
        """TC-LIST-001: Sessions returned sorted by date, newest first."""
        import time
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / ".workflow_sessions"
            sessions_dir.mkdir()

            # Create sessions with different timestamps - set mtime explicitly
            f1 = sessions_dir / "2024-01-01_session1.jsonl"
            f1.write_text("{}")
            os.utime(f1, (time.time() - 300, time.time() - 300))  # oldest

            f3 = sessions_dir / "2024-01-03_session3.jsonl"
            f3.write_text("{}")
            os.utime(f3, (time.time() - 100, time.time() - 100))  # newest

            f2 = sessions_dir / "2024-01-02_session2.jsonl"
            f2.write_text("{}")
            os.utime(f2, (time.time() - 200, time.time() - 200))  # middle

            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=sessions_dir
            )

            sessions = logger.list_sessions()

            # Newest first (by mtime)
            assert len(sessions) == 3
            assert "session3" in sessions[0]["session_id"]
            assert "session2" in sessions[1]["session_id"]
            assert "session1" in sessions[2]["session_id"]

    def test_list_sessions_with_limit(self):
        """List respects limit parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / ".workflow_sessions"
            sessions_dir.mkdir()

            for i in range(5):
                (sessions_dir / f"2024-01-0{i+1}_session{i}.jsonl").write_text("{}")

            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=sessions_dir
            )

            sessions = logger.list_sessions(limit=3)
            assert len(sessions) == 3


class TestSessionRetrieval:
    """Tests for session retrieval functionality."""

    def test_get_session_content(self):
        """TC-SHOW-001: Get session returns content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / ".workflow_sessions"
            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=sessions_dir
            )

            # Log some content
            logger.log("my-session", "Line 1")
            logger.log("my-session", "Line 2")

            # Retrieve it
            content = logger.get_session("my-session")

            assert content is not None
            assert "Line 1" in content
            assert "Line 2" in content

    def test_get_session_not_found(self):
        """Get session returns None for non-existent session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / ".workflow_sessions"
            sessions_dir.mkdir()

            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=sessions_dir
            )

            content = logger.get_session("nonexistent")
            assert content is None


class TestSessionCleanup:
    """Tests for session cleanup functionality."""

    def test_clean_old_sessions(self):
        """TC-CLEAN-001: Old sessions removed, new ones kept."""
        import time
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / ".workflow_sessions"
            sessions_dir.mkdir()

            # Create old session - set mtime to 60 days ago
            old_file = sessions_dir / "2020-01-01_old-session.jsonl"
            old_file.write_text("{}")
            old_mtime = time.time() - (60 * 24 * 60 * 60)  # 60 days ago
            os.utime(old_file, (old_mtime, old_mtime))

            # Create new session (today)
            today = datetime.now().strftime("%Y-%m-%d")
            new_file = sessions_dir / f"{today}_new-session.jsonl"
            new_file.write_text("{}")
            # mtime is automatically now

            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=sessions_dir
            )

            removed = logger.clean(older_than_days=30)

            assert removed == 1
            assert not old_file.exists()
            assert new_file.exists()

    def test_clean_respects_retention(self):
        """Clean only removes sessions older than specified days."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / ".workflow_sessions"
            sessions_dir.mkdir()

            # Create sessions with different date prefixes in filename
            now = datetime.now()
            for days_ago in [5, 15, 25, 35]:
                date = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
                f = sessions_dir / f"{date}_session-{days_ago}.jsonl"
                f.write_text("{}")

            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=sessions_dir
            )

            # Clean sessions older than 20 days
            removed = logger.clean(older_than_days=20)

            assert removed == 2  # 25 and 35 days old
            remaining = list(sessions_dir.glob("*.jsonl"))
            assert len(remaining) == 2


class TestCustomPatterns:
    """Tests for custom scrubbing patterns."""

    def test_add_custom_pattern(self):
        """Custom patterns can be added."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_manager = MagicMock(spec=SecretsManager)
            secrets_manager.get_all_known_secrets.return_value = {}

            logger = TranscriptLogger(
                secrets_manager=secrets_manager,
                sessions_dir=Path(tmpdir) / ".workflow_sessions",
                custom_patterns=[
                    (r"internal_token_[a-f0-9]+", "[REDACTED:INTERNAL_TOKEN]")
                ]
            )

            text = "Using internal_token_abc123def456"
            scrubbed = logger.scrub(text)

            assert "internal_token_abc123def456" not in scrubbed
            assert "[REDACTED:INTERNAL_TOKEN]" in scrubbed


class TestDefaultPatterns:
    """Tests for default pattern definitions."""

    def test_default_patterns_defined(self):
        """Default patterns are properly defined."""
        assert DEFAULT_SCRUB_PATTERNS is not None
        assert len(DEFAULT_SCRUB_PATTERNS) > 0

    def test_default_retention_days(self):
        """Default retention period is 30 days."""
        assert DEFAULT_RETENTION_DAYS == 30

    def test_sessions_dir_name(self):
        """Sessions directory name is correct."""
        assert SESSIONS_DIR_NAME == ".workflow_sessions"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
