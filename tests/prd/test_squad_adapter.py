"""
Tests for Claude Squad adapter.
"""

import pytest
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, timezone

from src.prd._deprecated.squad_adapter import (
    ClaudeSquadAdapter,
    SquadConfig,
    ClaudeSquadError,
    CapabilityError,
    SessionError,
)
from src.prd.session_registry import SessionRecord
from src.prd._deprecated.squad_capabilities import SquadCapabilities


class TestSquadConfig:
    """Tests for SquadConfig."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = SquadConfig()

        assert config.claude_squad_path == "claude-squad"
        assert config.auto_yes is True
        assert config.session_prefix == "wfo"
        assert config.command_timeout == 30

    def test_claude_binary_default(self):
        """Should default claude_binary to 'claude'."""
        # Clear any env var that might interfere
        import os
        old_val = os.environ.pop("CLAUDE_BINARY", None)
        try:
            # Also mock the config lookup to return None
            with patch('src.prd._deprecated.squad_adapter.get_user_config_value', return_value=None):
                config = SquadConfig()
                assert config.claude_binary == "claude"
        finally:
            if old_val is not None:
                os.environ["CLAUDE_BINARY"] = old_val

    def test_claude_binary_from_env(self):
        """Should use CLAUDE_BINARY env var when set."""
        import os
        old_val = os.environ.get("CLAUDE_BINARY")
        try:
            os.environ["CLAUDE_BINARY"] = "happy"
            with patch('src.prd._deprecated.squad_adapter.get_user_config_value', return_value=None):
                config = SquadConfig()
                assert config.claude_binary == "happy"
        finally:
            if old_val is None:
                os.environ.pop("CLAUDE_BINARY", None)
            else:
                os.environ["CLAUDE_BINARY"] = old_val

    def test_claude_binary_from_config(self):
        """Should use global config when env var not set."""
        import os
        old_val = os.environ.pop("CLAUDE_BINARY", None)
        try:
            with patch('src.prd._deprecated.squad_adapter.get_user_config_value', return_value="happy"):
                config = SquadConfig()
                assert config.claude_binary == "happy"
        finally:
            if old_val is not None:
                os.environ["CLAUDE_BINARY"] = old_val

    def test_claude_binary_env_overrides_config(self):
        """Environment variable should take priority over config."""
        import os
        old_val = os.environ.get("CLAUDE_BINARY")
        try:
            os.environ["CLAUDE_BINARY"] = "env-binary"
            with patch('src.prd._deprecated.squad_adapter.get_user_config_value', return_value="config-binary"):
                config = SquadConfig()
                assert config.claude_binary == "env-binary"
        finally:
            if old_val is None:
                os.environ.pop("CLAUDE_BINARY", None)
            else:
                os.environ["CLAUDE_BINARY"] = old_val

    def test_claude_binary_explicit_override(self):
        """Explicitly passed value should be used."""
        config = SquadConfig(claude_binary="custom-binary")
        assert config.claude_binary == "custom-binary"


class TestClaudeSquadAdapter:
    """Tests for ClaudeSquadAdapter."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temporary working directory."""
        return tmp_path

    @pytest.fixture
    def mock_capabilities(self):
        """Create mock capabilities showing full support."""
        return SquadCapabilities(
            installed=True,
            version="1.2.3",
            supports_new=True,
            supports_list=True,
            supports_attach=True,
            supports_kill=True,
            supports_prompt_file=True,
            supports_branch=True,
            supports_dir=True,
            supports_autoyes=True,
            supports_json_output=True,
            is_compatible=True,
        )

    @pytest.fixture
    def adapter(self, temp_dir, mock_capabilities):
        """Create an adapter with mocked capabilities."""
        with patch('src.prd._deprecated.squad_adapter.CapabilityDetector') as mock_detector:
            mock_detector.return_value.detect.return_value = mock_capabilities
            adapter = ClaudeSquadAdapter(temp_dir)
            # Also mock _list_squad_sessions to avoid subprocess calls
            adapter._list_squad_sessions = MagicMock(return_value=[])
            return adapter

    def test_init_checks_capabilities(self, temp_dir):
        """Should check capabilities on init."""
        with patch('src.prd._deprecated.squad_adapter.CapabilityDetector') as mock_detector:
            mock_caps = SquadCapabilities(
                installed=False,
                is_compatible=False,
                compatibility_issues=["not installed"]
            )
            mock_detector.return_value.detect.return_value = mock_caps

            with pytest.raises(CapabilityError) as exc:
                ClaudeSquadAdapter(temp_dir)

            assert "not installed" in str(exc.value)

    def test_skip_capability_check(self, temp_dir):
        """Should allow skipping capability check."""
        adapter = ClaudeSquadAdapter(temp_dir, skip_capability_check=True)
        assert adapter.capabilities.is_compatible is True

    def test_generate_session_name_sanitizes(self, adapter):
        """Should sanitize task IDs for session names."""
        # Normal task ID
        name = adapter._generate_session_name("task-123")
        assert name == "wfo-task-123"

        # Task ID with special characters
        name = adapter._generate_session_name("task/with:special@chars!")
        assert name == "wfo-task-with-special-chars-"
        assert "/" not in name
        assert ":" not in name
        assert "@" not in name

    def test_generate_session_name_truncates_long_ids(self, adapter):
        """Should truncate very long task IDs."""
        long_id = "a" * 100
        name = adapter._generate_session_name(long_id)

        # Should be prefix + truncated ID
        assert name.startswith("wfo-")
        assert len(name) <= 54  # "wfo-" + 50 chars

    def test_spawn_session_creates_prompt_file(self, adapter, temp_dir):
        """Should create prompt file when spawning."""
        with patch.object(adapter, '_run_command') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="session: test-session",
                returncode=0
            )

            adapter.spawn_session(
                task_id="test-task",
                prompt="Test prompt content",
                branch="claude/test"
            )

        prompt_file = temp_dir / ".claude" / "prompt_test-task.md"
        assert prompt_file.exists()
        assert prompt_file.read_text() == "Test prompt content"

    def test_spawn_session_idempotent(self, adapter, temp_dir):
        """Should return existing session if already spawned."""
        # First spawn
        with patch.object(adapter, '_run_command') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="session: test-session",
                returncode=0
            )
            first = adapter.spawn_session("test-task", "prompt", "branch")

        # Second spawn should not call command again
        with patch.object(adapter, '_run_command') as mock_run:
            second = adapter.spawn_session("test-task", "prompt", "branch")
            mock_run.assert_not_called()

        assert first.session_name == second.session_name

    def test_spawn_session_registers(self, adapter):
        """Should register session in registry."""
        with patch.object(adapter, '_run_command') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="session: test-session",
                returncode=0
            )

            record = adapter.spawn_session("reg-test", "prompt", "branch")

        retrieved = adapter.registry.get("reg-test")
        assert retrieved is not None
        assert retrieved.session_name == record.session_name

    def test_spawn_session_includes_p_flag(self, temp_dir, mock_capabilities):
        """Should include -p flag with claude_binary in spawn command."""
        with patch('src.prd._deprecated.squad_adapter.CapabilityDetector') as mock_detector:
            mock_detector.return_value.detect.return_value = mock_capabilities
            with patch('src.prd._deprecated.squad_adapter.get_user_config_value', return_value=None):
                config = SquadConfig(claude_binary="happy")
                adapter = ClaudeSquadAdapter(temp_dir, config=config)
                adapter._list_squad_sessions = MagicMock(return_value=[])

        with patch.object(adapter, '_run_command') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="session: test-session",
                returncode=0
            )

            adapter.spawn_session("p-flag-test", "prompt", "branch")

            # Verify -p flag was included
            call_args = mock_run.call_args[0][0]
            assert "-p" in call_args
            p_index = call_args.index("-p")
            assert call_args[p_index + 1] == "happy"

    def test_spawn_session_default_claude_binary(self, temp_dir, mock_capabilities):
        """Should use 'claude' as default binary in -p flag."""
        import os
        old_val = os.environ.pop("CLAUDE_BINARY", None)
        try:
            with patch('src.prd._deprecated.squad_adapter.CapabilityDetector') as mock_detector:
                mock_detector.return_value.detect.return_value = mock_capabilities
                with patch('src.prd._deprecated.squad_adapter.get_user_config_value', return_value=None):
                    adapter = ClaudeSquadAdapter(temp_dir)
                    adapter._list_squad_sessions = MagicMock(return_value=[])

            with patch.object(adapter, '_run_command') as mock_run:
                mock_run.return_value = MagicMock(
                    stdout="session: test-session",
                    returncode=0
                )

                adapter.spawn_session("default-binary-test", "prompt", "branch")

                # Verify -p flag uses 'claude' by default
                call_args = mock_run.call_args[0][0]
                assert "-p" in call_args
                p_index = call_args.index("-p")
                assert call_args[p_index + 1] == "claude"
        finally:
            if old_val is not None:
                os.environ["CLAUDE_BINARY"] = old_val

    def test_spawn_batch(self, adapter):
        """Should spawn multiple sessions."""
        with patch.object(adapter, '_run_command') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="session: test",
                returncode=0
            )

            tasks = [
                {"task_id": "t1", "prompt": "p1", "branch": "b1"},
                {"task_id": "t2", "prompt": "p2", "branch": "b2"},
                {"task_id": "t3", "prompt": "p3", "branch": "b3"},
            ]

            sessions = adapter.spawn_batch(tasks)

        assert len(sessions) == 3

    def test_spawn_batch_continues_on_error(self, adapter):
        """Should continue spawning even if one fails."""
        call_count = 0

        def mock_run_side_effect(args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise SessionError("Failed")
            return MagicMock(stdout="session: test", returncode=0)

        with patch.object(adapter, '_run_command', side_effect=mock_run_side_effect):
            tasks = [
                {"task_id": "t1", "prompt": "p1", "branch": "b1"},
                {"task_id": "t2", "prompt": "p2", "branch": "b2"},
                {"task_id": "t3", "prompt": "p3", "branch": "b3"},
            ]

            sessions = adapter.spawn_batch(tasks)

        assert len(sessions) == 2  # t1 and t3 succeeded

    def test_get_status(self, adapter):
        """Should get session status."""
        with patch.object(adapter, '_run_command') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="session: test",
                returncode=0
            )
            adapter.spawn_session("status-test", "prompt", "branch")

        # Mock list to include our session (avoid orphaning)
        adapter._list_squad_sessions = MagicMock(return_value=[
            {"name": "wfo-status-test", "status": "running"}
        ])

        status = adapter.get_status("status-test")
        assert status == "running"

    def test_get_status_nonexistent(self, adapter):
        """Should return None for nonexistent task."""
        status = adapter.get_status("nonexistent")
        assert status is None

    def test_list_sessions(self, adapter):
        """Should list active sessions."""
        with patch.object(adapter, '_run_command') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="session: test",
                returncode=0
            )
            adapter.spawn_session("list-test", "prompt", "branch")

        # Mock list to include our session (avoid orphaning during reconcile)
        adapter._list_squad_sessions = MagicMock(return_value=[
            {"name": "wfo-list-test", "status": "running"}
        ])

        sessions = adapter.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].task_id == "list-test"

    def test_mark_complete(self, adapter, temp_dir):
        """Should mark task complete and cleanup."""
        # Create session
        with patch.object(adapter, '_run_command') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="session: test",
                returncode=0
            )
            adapter.spawn_session("complete-test", "prompt", "branch")

        # Mark complete
        with patch.object(adapter, '_run_command') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            adapter.mark_complete("complete-test")

        record = adapter.registry.get("complete-test")
        assert record.status == "completed"

    def test_mark_complete_nonexistent(self, adapter):
        """Should raise error for nonexistent task."""
        with pytest.raises(SessionError) as exc:
            adapter.mark_complete("nonexistent")

        assert "No session" in str(exc.value)

    def test_cleanup_orphaned(self, adapter):
        """Should cleanup orphaned sessions."""
        # Create and orphan a session
        with patch.object(adapter, '_run_command') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="session: test",
                returncode=0
            )
            adapter.spawn_session("orphan-test", "prompt", "branch")

        # Manually set to orphaned
        adapter.registry.update_status("orphan-test", "orphaned")

        # Cleanup
        cleaned = adapter.cleanup_orphaned()
        assert cleaned == 1

        record = adapter.registry.get("orphan-test")
        assert record.status == "terminated"

    def test_parse_session_id_json(self, adapter):
        """Should parse session ID from JSON output."""
        output = '{"id": "session-abc", "name": "test"}'
        result = adapter._parse_session_id(output, "fallback")
        assert result == "session-abc"

    def test_parse_session_id_pattern(self, adapter):
        """Should parse session ID from pattern."""
        output = "Created session: my-session-123\nDone"
        result = adapter._parse_session_id(output, "fallback")
        assert result == "my-session-123"

    def test_parse_session_id_fallback(self, adapter):
        """Should fall back to session name."""
        output = "Some random output with no ID"
        result = adapter._parse_session_id(output, "fallback-name")
        assert result == "fallback-name"

    def test_command_timeout(self, adapter):
        """Should raise error on command timeout."""
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd="test", timeout=30)):
            with pytest.raises(SessionError) as exc:
                adapter._run_command(["test"])

            assert "timed out" in str(exc.value)

    def test_command_failure(self, adapter):
        """Should raise error on command failure."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="Command failed"
            )

            with pytest.raises(SessionError) as exc:
                adapter._run_command(["test"])

            assert "Command failed" in str(exc.value)


class TestListSquadSessions:
    """Tests for _list_squad_sessions method."""

    @pytest.fixture
    def adapter(self, tmp_path):
        """Create adapter with skipped capability check."""
        return ClaudeSquadAdapter(tmp_path, skip_capability_check=True)

    def test_json_output(self, adapter):
        """Should parse JSON list output."""
        adapter.capabilities.supports_json_output = True

        with patch.object(adapter, '_run_command') as mock_run:
            mock_run.return_value = MagicMock(
                stdout='[{"name": "wfo-test", "status": "running"}]',
                returncode=0
            )

            sessions = adapter._list_squad_sessions()

        assert len(sessions) == 1
        assert sessions[0]["name"] == "wfo-test"

    def test_text_output_fallback(self, adapter):
        """Should parse text output as fallback."""
        adapter.capabilities.supports_json_output = False

        with patch.object(adapter, '_run_command') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="wfo-test running\nwfo-other pending\n",
                returncode=0
            )

            sessions = adapter._list_squad_sessions()

        assert len(sessions) == 2
        assert sessions[0]["name"] == "wfo-test"
        assert sessions[0]["status"] == "running"
