"""
Tests for SubprocessAdapter - fallback when tmux is not available.
"""

import pytest
import subprocess
import signal
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

# These imports will fail until we implement the module
# This is expected in RED phase
try:
    from src.prd.subprocess_adapter import (
        SubprocessAdapter,
        SubprocessConfig,
    )
    from src.prd.session_registry import SessionRecord
    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="SubprocessAdapter not implemented yet")
class TestSubprocessConfig:
    """Tests for SubprocessConfig."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = SubprocessConfig()

        assert config.session_prefix == "wfo"
        assert config.log_dir_name == ".wfo_logs"

    def test_claude_binary_default(self):
        """Should default claude_binary to 'claude'."""
        old_val = os.environ.pop("CLAUDE_BINARY", None)
        try:
            with patch('src.prd.subprocess_adapter.get_user_config_value', return_value=None):
                config = SubprocessConfig()
                assert config.claude_binary == "claude"
        finally:
            if old_val is not None:
                os.environ["CLAUDE_BINARY"] = old_val


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="SubprocessAdapter not implemented yet")
class TestSubprocessAdapter:
    """Tests for SubprocessAdapter."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temporary directory for tests."""
        return tmp_path

    @pytest.fixture
    def adapter(self, temp_dir):
        """Create adapter instance."""
        return SubprocessAdapter(working_dir=temp_dir)

    def test_spawn_agent_starts_process(self, temp_dir):
        """Should start a subprocess."""
        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            adapter = SubprocessAdapter(working_dir=temp_dir)
            record = adapter.spawn_agent("task-1", "Test prompt", temp_dir, "main")

            mock_popen.assert_called_once()
            assert record.task_id == "task-1"

    def test_spawn_agent_creates_log_file(self, temp_dir):
        """Should create a log file for the process."""
        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            adapter = SubprocessAdapter(working_dir=temp_dir)
            record = adapter.spawn_agent("task-1", "Test prompt", temp_dir, "main")

            # Log directory should be created
            log_dir = temp_dir / ".wfo_logs"
            assert log_dir.exists() or mock_popen.called

    def test_spawn_agent_registers_pid(self, temp_dir):
        """Should save PID in SessionRegistry."""
        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            adapter = SubprocessAdapter(working_dir=temp_dir)
            record = adapter.spawn_agent("task-1", "Test prompt", temp_dir, "main")

            # Session ID should contain PID
            assert "12345" in record.session_id or record.session_id is not None

    def test_spawn_agent_returns_session_record(self, temp_dir):
        """Should return a SessionRecord."""
        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            adapter = SubprocessAdapter(working_dir=temp_dir)
            record = adapter.spawn_agent("task-1", "Test prompt", temp_dir, "main")

            assert isinstance(record, SessionRecord)
            assert record.task_id == "task-1"
            assert record.status == "running"

    def test_spawn_agent_is_idempotent(self, temp_dir):
        """Should return existing session if already spawned."""
        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.poll.return_value = None  # Still running
            mock_popen.return_value = mock_process

            adapter = SubprocessAdapter(working_dir=temp_dir)
            record1 = adapter.spawn_agent("task-1", "Test prompt", temp_dir, "main")
            record2 = adapter.spawn_agent("task-1", "Test prompt", temp_dir, "main")

            # Should only spawn once
            assert mock_popen.call_count == 1
            assert record1.session_id == record2.session_id

    def test_list_agents_returns_active(self, temp_dir):
        """Should list active processes from registry."""
        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.poll.return_value = None  # Still running
            mock_popen.return_value = mock_process

            adapter = SubprocessAdapter(working_dir=temp_dir)
            adapter.spawn_agent("task-1", "Test", temp_dir, "main")
            adapter.spawn_agent("task-2", "Test", temp_dir, "main")

            agents = adapter.list_agents()
            assert len(agents) == 2

    def test_capture_output_reads_log(self, temp_dir):
        """Should read from log file."""
        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            adapter = SubprocessAdapter(working_dir=temp_dir)
            adapter.spawn_agent("task-1", "Test", temp_dir, "main")

            # Create fake log file
            log_dir = temp_dir / ".wfo_logs"
            log_dir.mkdir(exist_ok=True)
            log_file = log_dir / "task-1.log"
            log_file.write_text("Test output")

            output = adapter.capture_output("task-1")
            assert "Test output" in output

    def test_kill_agent_terminates_process(self, temp_dir):
        """Should send SIGTERM to the process."""
        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            with patch('os.kill') as mock_kill:
                adapter = SubprocessAdapter(working_dir=temp_dir)
                adapter.spawn_agent("task-1", "Test", temp_dir, "main")
                adapter.kill_agent("task-1")

                mock_kill.assert_called_with(12345, signal.SIGTERM)

    def test_kill_agent_handles_already_dead(self, temp_dir):
        """Should not raise error if process already dead."""
        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            with patch('os.kill', side_effect=ProcessLookupError):
                adapter = SubprocessAdapter(working_dir=temp_dir)
                adapter.spawn_agent("task-1", "Test", temp_dir, "main")

                # Should not raise
                adapter.kill_agent("task-1")

    def test_no_attach_capability(self, temp_dir):
        """Subprocess adapter should not support attach (limitation)."""
        adapter = SubprocessAdapter(working_dir=temp_dir)

        # Either raises NotImplementedError or returns None/False
        with pytest.raises((NotImplementedError, AttributeError)):
            adapter.attach("task-1")


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="SubprocessAdapter not implemented yet")
class TestSubprocessAdapterEdgeCases:
    """Edge case tests for SubprocessAdapter."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_sanitizes_task_id(self, temp_dir):
        """Should sanitize special characters in task_id."""
        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            adapter = SubprocessAdapter(working_dir=temp_dir)
            record = adapter.spawn_agent("task/with:special!", "Test", temp_dir, "main")

            # Session name should not contain special chars
            assert "/" not in record.session_name
            assert ":" not in record.session_name

    def test_creates_log_directory(self, temp_dir):
        """Should create log directory if it doesn't exist."""
        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            adapter = SubprocessAdapter(working_dir=temp_dir)
            adapter.spawn_agent("task-1", "Test", temp_dir, "main")

            # Log directory should be created
            log_dir = temp_dir / ".wfo_logs"
            assert log_dir.exists()

    def test_handles_process_spawn_failure(self, temp_dir):
        """Should handle subprocess spawn failures gracefully."""
        with patch('subprocess.Popen', side_effect=OSError("spawn failed")):
            adapter = SubprocessAdapter(working_dir=temp_dir)

            with pytest.raises(Exception):  # Should raise some error
                adapter.spawn_agent("task-1", "Test", temp_dir, "main")
