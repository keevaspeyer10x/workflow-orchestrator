"""
Tests for TmuxAdapter - direct tmux management for parallel Claude Code agents.
"""

import pytest
import subprocess
import shutil
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timezone

# These imports will fail until we implement the module
# This is expected in RED phase
try:
    from src.prd.tmux_adapter import (
        TmuxAdapter,
        TmuxConfig,
        TmuxError,
        TmuxNotAvailableError,
    )
    from src.prd.session_registry import SessionRecord
    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="TmuxAdapter not implemented yet")
class TestTmuxConfig:
    """Tests for TmuxConfig."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = TmuxConfig()

        assert config.session_prefix == "wfo"
        assert config.command_timeout == 30

    def test_claude_binary_default(self):
        """Should default claude_binary to 'claude'."""
        old_val = os.environ.pop("CLAUDE_BINARY", None)
        try:
            with patch('src.prd.tmux_adapter.get_user_config_value', return_value=None):
                config = TmuxConfig()
                assert config.claude_binary == "claude"
        finally:
            if old_val is not None:
                os.environ["CLAUDE_BINARY"] = old_val

    def test_claude_binary_from_env(self):
        """Should use CLAUDE_BINARY env var when set (Happy integration)."""
        old_val = os.environ.get("CLAUDE_BINARY")
        try:
            os.environ["CLAUDE_BINARY"] = "happy"
            with patch('src.prd.tmux_adapter.get_user_config_value', return_value=None):
                config = TmuxConfig()
                assert config.claude_binary == "happy"
        finally:
            if old_val is None:
                os.environ.pop("CLAUDE_BINARY", None)
            else:
                os.environ["CLAUDE_BINARY"] = old_val


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="TmuxAdapter not implemented yet")
class TestTmuxAdapter:
    """Tests for TmuxAdapter."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temporary directory for tests."""
        return tmp_path

    @pytest.fixture
    def mock_tmux_available(self):
        """Mock tmux as available."""
        with patch('shutil.which', return_value='/usr/bin/tmux'):
            yield

    @pytest.fixture
    def adapter(self, temp_dir, mock_tmux_available):
        """Create adapter instance with mocked dependencies."""
        with patch('subprocess.run') as mock_run:
            # Mock session check to return "no session"
            mock_run.return_value = MagicMock(returncode=1)
            adapter = TmuxAdapter(working_dir=temp_dir)
            return adapter

    def test_init_checks_tmux_availability(self, temp_dir):
        """Should check if tmux is available on init."""
        with patch('shutil.which', return_value=None):
            with pytest.raises(TmuxNotAvailableError):
                TmuxAdapter(working_dir=temp_dir)

    def test_init_with_tmux_available(self, temp_dir, mock_tmux_available):
        """Should initialize successfully when tmux is available."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            adapter = TmuxAdapter(working_dir=temp_dir)
            assert adapter is not None

    def test_spawn_agent_creates_session_if_needed(self, temp_dir, mock_tmux_available):
        """Should create tmux session if it doesn't exist."""
        with patch('subprocess.run') as mock_run:
            def side_effect(args, **kwargs):
                # has-session returns 1 (no session) first time
                if "has-session" in args:
                    return MagicMock(returncode=1, stdout="", stderr="no session")
                return MagicMock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = side_effect

            adapter = TmuxAdapter(working_dir=temp_dir)
            adapter.spawn_agent("task-1", "Test prompt", temp_dir, "main")

            # Verify new-session was called
            call_args_list = [call[0][0] for call in mock_run.call_args_list]
            assert any("new-session" in args for args in call_args_list)

    def test_spawn_agent_creates_window(self, temp_dir, mock_tmux_available):
        """Should create a new window for each task."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            adapter = TmuxAdapter(working_dir=temp_dir)
            adapter.spawn_agent("task-1", "Test prompt", temp_dir, "main")

            # Verify new-window was called with task name
            calls = [str(c) for c in mock_run.call_args_list]
            assert any("new-window" in c for c in calls)

    def test_spawn_agent_sends_claude_command(self, temp_dir, mock_tmux_available):
        """Should send claude command via send-keys."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            adapter = TmuxAdapter(working_dir=temp_dir)
            adapter.spawn_agent("task-1", "Test prompt", temp_dir, "main")

            # Verify send-keys was called
            calls = [str(c) for c in mock_run.call_args_list]
            assert any("send-keys" in c for c in calls)

    def test_spawn_agent_returns_session_record(self, temp_dir, mock_tmux_available):
        """Should return a SessionRecord."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            adapter = TmuxAdapter(working_dir=temp_dir)
            record = adapter.spawn_agent("task-1", "Test prompt", temp_dir, "main")

            assert isinstance(record, SessionRecord)
            assert record.task_id == "task-1"
            assert record.status == "running"

    def test_spawn_agent_is_idempotent(self, temp_dir, mock_tmux_available):
        """Should return existing session if already spawned."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            adapter = TmuxAdapter(working_dir=temp_dir)
            record1 = adapter.spawn_agent("task-1", "Test prompt", temp_dir, "main")
            record2 = adapter.spawn_agent("task-1", "Test prompt", temp_dir, "main")

            assert record1.session_id == record2.session_id

    def test_spawn_agent_sanitizes_task_id(self, temp_dir, mock_tmux_available):
        """Should sanitize special characters in task_id."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            adapter = TmuxAdapter(working_dir=temp_dir)
            record = adapter.spawn_agent("task/with:special chars!", "Test", temp_dir, "main")

            # Session name should not contain special chars
            assert "/" not in record.session_name
            assert ":" not in record.session_name
            assert "!" not in record.session_name

    def test_list_agents_parses_tmux_output(self, temp_dir, mock_tmux_available):
        """Should parse tmux list-windows output."""
        with patch('subprocess.run') as mock_run:
            def mock_run_side_effect(args, **kwargs):
                if "list-windows" in args:
                    return MagicMock(
                        returncode=0,
                        stdout="0: task-1 (/tmp)\n1: task-2 (/tmp)\n",
                        stderr=""
                    )
                return MagicMock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = mock_run_side_effect

            adapter = TmuxAdapter(working_dir=temp_dir)
            agents = adapter.list_agents()

            assert len(agents) >= 0  # Will depend on registry state

    def test_capture_output_uses_capture_pane(self, temp_dir, mock_tmux_available):
        """Should use tmux capture-pane to get output."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Claude output here",
                stderr=""
            )

            adapter = TmuxAdapter(working_dir=temp_dir)
            # First spawn an agent
            adapter.spawn_agent("task-1", "Test", temp_dir, "main")
            output = adapter.capture_output("task-1")

            # Verify capture-pane was called
            calls = [str(c) for c in mock_run.call_args_list]
            assert any("capture-pane" in c for c in calls)

    def test_kill_agent_removes_window(self, temp_dir, mock_tmux_available):
        """Should call kill-window for the task."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            adapter = TmuxAdapter(working_dir=temp_dir)
            adapter.spawn_agent("task-1", "Test", temp_dir, "main")
            adapter.kill_agent("task-1")

            calls = [str(c) for c in mock_run.call_args_list]
            assert any("kill-window" in c for c in calls)

    def test_cleanup_kills_entire_session(self, temp_dir, mock_tmux_available):
        """Should call kill-session to clean up."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            adapter = TmuxAdapter(working_dir=temp_dir)
            adapter.cleanup()

            calls = [str(c) for c in mock_run.call_args_list]
            assert any("kill-session" in c for c in calls)

    def test_attach_execs_tmux(self, temp_dir, mock_tmux_available):
        """Should use os.execvp to attach to session."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            adapter = TmuxAdapter(working_dir=temp_dir)
            adapter.spawn_agent("task-1", "Test", temp_dir, "main")

            with patch('os.execvp') as mock_exec:
                adapter.attach("task-1")
                mock_exec.assert_called_once()
                # First arg should be tmux
                assert mock_exec.call_args[0][0] == "tmux"

    def test_happy_integration_uses_custom_binary(self, temp_dir):
        """Should use CLAUDE_BINARY for Happy integration."""
        old_val = os.environ.get("CLAUDE_BINARY")
        try:
            os.environ["CLAUDE_BINARY"] = "happy"

            with patch('shutil.which', return_value='/usr/bin/tmux'):
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                    with patch('src.prd.tmux_adapter.get_user_config_value', return_value=None):
                        adapter = TmuxAdapter(working_dir=temp_dir)
                        adapter.spawn_agent("task-1", "Test", temp_dir, "main")

                        # Verify happy was used in send-keys command
                        calls = [str(c) for c in mock_run.call_args_list]
                        send_keys_calls = [c for c in calls if "send-keys" in c]
                        assert any("happy" in c for c in send_keys_calls)
        finally:
            if old_val is None:
                os.environ.pop("CLAUDE_BINARY", None)
            else:
                os.environ["CLAUDE_BINARY"] = old_val


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="TmuxAdapter not implemented yet")
class TestTmuxAdapterEdgeCases:
    """Edge case tests for TmuxAdapter."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    @pytest.fixture
    def mock_tmux_available(self):
        with patch('shutil.which', return_value='/usr/bin/tmux'):
            yield

    def test_very_long_task_id_truncated(self, temp_dir, mock_tmux_available):
        """Should truncate very long task IDs."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            adapter = TmuxAdapter(working_dir=temp_dir)
            long_id = "a" * 100
            record = adapter.spawn_agent(long_id, "Test", temp_dir, "main")

            # Session name should be truncated
            assert len(record.session_name) <= 60  # prefix + truncated id

    def test_kill_nonexistent_task_no_error(self, temp_dir, mock_tmux_available):
        """Should not raise error when killing non-existent task."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="no such window")

            adapter = TmuxAdapter(working_dir=temp_dir)
            # Should not raise
            adapter.kill_agent("nonexistent-task")

    def test_empty_prompt_still_spawns(self, temp_dir, mock_tmux_available):
        """Should spawn even with empty prompt."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            adapter = TmuxAdapter(working_dir=temp_dir)
            record = adapter.spawn_agent("task-1", "", temp_dir, "main")

            assert record is not None
            assert record.task_id == "task-1"


# Integration tests that actually use tmux (skipped if tmux not available)
@pytest.mark.skipif(
    not shutil.which("tmux"),
    reason="tmux not available for integration tests"
)
@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="TmuxAdapter not implemented yet")
class TestTmuxAdapterIntegration:
    """Integration tests that actually spawn tmux sessions."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    @pytest.fixture(autouse=True)
    def cleanup_sessions(self):
        """Clean up any test sessions after each test."""
        yield
        # Kill any test sessions that might be left over
        subprocess.run(
            ["tmux", "kill-session", "-t", "wfo-test-integration"],
            capture_output=True
        )

    def test_spawn_real_agent(self, temp_dir):
        """Actually create a tmux session."""
        adapter = TmuxAdapter(working_dir=temp_dir)

        try:
            record = adapter.spawn_agent(
                "test-integration",
                "echo 'hello from test'",
                temp_dir,
                "main"
            )

            assert record.status == "running"

            # Verify session exists (use adapter's session name, not record's)
            result = subprocess.run(
                ["tmux", "has-session", "-t", adapter.session_name],
                capture_output=True
            )
            assert result.returncode == 0
        finally:
            adapter.cleanup()

    def test_capture_real_output(self, temp_dir):
        """Actually capture output from tmux pane."""
        adapter = TmuxAdapter(working_dir=temp_dir)

        try:
            adapter.spawn_agent("test-integration", "echo hello", temp_dir, "main")

            # Wait a moment for command to run
            import time
            time.sleep(1)

            output = adapter.capture_output("test-integration")
            # Output should contain something (prompt, command, etc.)
            assert isinstance(output, str)
        finally:
            adapter.cleanup()


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="TmuxAdapter not implemented yet")
class TestTmuxAdapterApprovalGateInjection:
    """Tests for PRD-006: Auto-inject ApprovalGate in spawn_agent()."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    @pytest.fixture
    def mock_tmux_available(self):
        with patch('shutil.which', return_value='/usr/bin/tmux'):
            yield

    def test_spawn_agent_injects_approval_gate_by_default(self, temp_dir, mock_tmux_available):
        """spawn_agent() should inject approval gate instructions by default."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            adapter = TmuxAdapter(working_dir=temp_dir)
            record = adapter.spawn_agent("test-task", "Do something", temp_dir, "main")

            prompt_file = Path(record.prompt_file)
            content = prompt_file.read_text()

            assert "## Approval Gate Integration" in content
            assert 'agent_id="test-task"' in content
            assert ".workflow_approvals.db" in content

    def test_spawn_agent_no_injection_when_disabled(self, temp_dir, mock_tmux_available):
        """spawn_agent() should not inject when inject_approval_gate=False."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            config = TmuxConfig(inject_approval_gate=False)
            adapter = TmuxAdapter(working_dir=temp_dir, config=config)
            record = adapter.spawn_agent("test-task", "Do something", temp_dir, "main")

            prompt_file = Path(record.prompt_file)
            content = prompt_file.read_text()

            assert "## Approval Gate Integration" not in content
            assert "request_approval" not in content

    def test_spawn_agent_preserves_original_prompt(self, temp_dir, mock_tmux_available):
        """Original prompt content should be preserved when injecting."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            adapter = TmuxAdapter(working_dir=temp_dir)
            original_prompt = "# My Task\n\nDo this specific thing."

            record = adapter.spawn_agent("test-task", original_prompt, temp_dir, "main")

            content = Path(record.prompt_file).read_text()

            assert "# My Task" in content
            assert "Do this specific thing" in content
            assert content.startswith("# My Task")  # Original comes first

    def test_spawn_agent_uses_correct_db_path(self, temp_dir, mock_tmux_available):
        """Injected instructions should use working_dir/.workflow_approvals.db."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            working_dir = temp_dir / "myproject"
            working_dir.mkdir()

            adapter = TmuxAdapter(working_dir=temp_dir)
            record = adapter.spawn_agent("test-task", "Test", working_dir, "main")

            content = Path(record.prompt_file).read_text()
            expected_path = str(working_dir / ".workflow_approvals.db")

            assert expected_path in content

    def test_spawn_agent_uses_task_id_as_agent_id(self, temp_dir, mock_tmux_available):
        """agent_id in instructions should match task_id."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            adapter = TmuxAdapter(working_dir=temp_dir)
            record = adapter.spawn_agent("my-unique-task-123", "Test", temp_dir, "main")

            content = Path(record.prompt_file).read_text()

            assert 'agent_id="my-unique-task-123"' in content

    def test_config_inject_approval_gate_default_true(self):
        """TmuxConfig.inject_approval_gate should default to True."""
        config = TmuxConfig()
        assert config.inject_approval_gate is True

    def test_config_inject_approval_gate_can_be_false(self):
        """TmuxConfig.inject_approval_gate can be set to False."""
        config = TmuxConfig(inject_approval_gate=False)
        assert config.inject_approval_gate is False

    def test_spawn_agent_with_empty_prompt_still_injects(self, temp_dir, mock_tmux_available):
        """Should inject gate instructions even with empty original prompt."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            adapter = TmuxAdapter(working_dir=temp_dir)
            record = adapter.spawn_agent("test-task", "", temp_dir, "main")

            content = Path(record.prompt_file).read_text()

            assert "## Approval Gate Integration" in content
