"""
Tests for orchestrator auto-setup functionality.

Tests server discovery, health checking, and daemon process management.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import subprocess
import time

from src.orchestrator.auto_setup import (
    check_server_health,
    find_running_server,
    start_orchestrator_daemon,
    ensure_orchestrator_running,
    cleanup_server,
    ServerError,
)


class TestServerHealthCheck:
    """Tests for check_server_health function."""

    @patch('src.orchestrator.auto_setup.httpx')
    def test_check_server_health_success(self, mock_httpx):
        """Test health check when server responds OK."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_httpx.get.return_value = mock_response

        result = check_server_health("http://localhost:8000")

        assert result is True
        mock_httpx.get.assert_called_once_with(
            "http://localhost:8000/health",
            timeout=2.0
        )

    @patch('src.orchestrator.auto_setup.httpx')
    def test_check_server_health_failure_status(self, mock_httpx):
        """Test health check when server returns non-200 status."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_httpx.get.return_value = mock_response

        result = check_server_health("http://localhost:8000")

        assert result is False

    @patch('src.orchestrator.auto_setup.httpx')
    def test_check_server_health_connection_error(self, mock_httpx):
        """Test health check when connection fails."""
        mock_httpx.get.side_effect = Exception("Connection refused")

        result = check_server_health("http://localhost:8000")

        assert result is False

    @patch('src.orchestrator.auto_setup.httpx')
    def test_check_server_health_timeout(self, mock_httpx):
        """Test health check when request times out."""
        mock_httpx.get.side_effect = TimeoutError("Request timeout")

        result = check_server_health("http://localhost:8000")

        assert result is False


class TestFindRunningServer:
    """Tests for find_running_server function."""

    @patch('src.orchestrator.auto_setup.check_server_health')
    def test_find_running_server_on_default_port(self, mock_health):
        """Test finding server on default port 8000."""
        mock_health.return_value = True

        result = find_running_server()

        assert result == "http://localhost:8000"
        mock_health.assert_called_once_with("http://localhost:8000")

    @patch('src.orchestrator.auto_setup.check_server_health')
    def test_find_running_server_on_alternate_port(self, mock_health):
        """Test finding server on alternate port 8001."""
        mock_health.side_effect = [False, True]  # Fail 8000, succeed 8001

        result = find_running_server()

        assert result == "http://localhost:8001"
        assert mock_health.call_count == 2
        mock_health.assert_any_call("http://localhost:8000")
        mock_health.assert_any_call("http://localhost:8001")

    @patch('src.orchestrator.auto_setup.check_server_health')
    def test_find_running_server_none_found(self, mock_health):
        """Test when no server found on any port."""
        mock_health.return_value = False

        result = find_running_server()

        assert result is None
        assert mock_health.call_count == 3  # Tries 8000, 8001, 8002

    @patch('src.orchestrator.auto_setup.check_server_health')
    def test_find_running_server_custom_ports(self, mock_health):
        """Test with custom port list."""
        mock_health.side_effect = [False, False, True]

        result = find_running_server(ports=[9000, 9001, 9002])

        assert result == "http://localhost:9002"
        assert mock_health.call_count == 3


class TestStartOrchestratorDaemon:
    """Tests for start_orchestrator_daemon function."""

    @patch('src.orchestrator.auto_setup.check_server_health')
    @patch('src.orchestrator.auto_setup.subprocess.Popen')
    def test_start_orchestrator_daemon_success(self, mock_popen, mock_health):
        """Test successful daemon start."""
        # Setup mocks
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        mock_health.return_value = True

        result = start_orchestrator_daemon(port=8000)

        assert result == "http://localhost:8000"
        # Verify subprocess was called correctly
        mock_popen.assert_called_once()
        # Verify PID file was created (check it exists)
        pid_file = Path.cwd() / ".orchestrator" / "server.pid"
        assert pid_file.exists()
        # Cleanup
        pid_file.unlink()
        (Path.cwd() / ".orchestrator" / "server.log").unlink(missing_ok=True)

    @patch('src.orchestrator.auto_setup.check_server_health')
    @patch('src.orchestrator.auto_setup.subprocess.Popen')
    @patch('src.orchestrator.auto_setup.time.sleep')
    def test_start_orchestrator_daemon_health_check_timeout(
        self, mock_sleep, mock_popen, mock_health
    ):
        """Test daemon start when health check never succeeds."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # Still running
        mock_popen.return_value = mock_process
        mock_health.return_value = False  # Never becomes healthy

        with pytest.raises(ServerError, match="failed to start"):
            start_orchestrator_daemon(port=8000, timeout=2)

        # Verify process was killed
        mock_process.kill.assert_called_once()
        # Cleanup any created files
        (Path.cwd() / ".orchestrator" / "server.pid").unlink(missing_ok=True)
        (Path.cwd() / ".orchestrator" / "server.log").unlink(missing_ok=True)

    @patch('src.orchestrator.auto_setup.subprocess.Popen')
    def test_start_orchestrator_daemon_port_in_use(self, mock_popen):
        """Test daemon start when port is already in use."""
        mock_popen.side_effect = OSError("Address already in use")

        with pytest.raises(ServerError, match="Port 8000 already in use"):
            start_orchestrator_daemon(port=8000)

    @patch('src.orchestrator.auto_setup.check_server_health')
    @patch('src.orchestrator.auto_setup.subprocess.Popen')
    def test_start_orchestrator_daemon_creates_log_file(
        self, mock_popen, mock_health
    ):
        """Test that daemon redirects output to log file."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        mock_health.return_value = True

        start_orchestrator_daemon(port=8000)

        # Verify log file was created
        log_file = Path.cwd() / ".orchestrator" / "server.log"
        assert log_file.exists()

        # Cleanup
        (Path.cwd() / ".orchestrator" / "server.pid").unlink(missing_ok=True)
        log_file.unlink(missing_ok=True)


class TestEnsureOrchestratorRunning:
    """Tests for ensure_orchestrator_running function."""

    @patch('src.orchestrator.auto_setup.find_running_server')
    @patch('src.orchestrator.auto_setup.start_orchestrator_daemon')
    def test_ensure_orchestrator_running_already_running(
        self, mock_start, mock_find
    ):
        """Test when server is already running."""
        mock_find.return_value = "http://localhost:8000"

        result = ensure_orchestrator_running()

        assert result == "http://localhost:8000"
        mock_find.assert_called_once()
        mock_start.assert_not_called()

    @patch('src.orchestrator.auto_setup.find_running_server')
    @patch('src.orchestrator.auto_setup.start_orchestrator_daemon')
    def test_ensure_orchestrator_running_needs_start(
        self, mock_start, mock_find
    ):
        """Test when server needs to be started."""
        mock_find.return_value = None
        mock_start.return_value = "http://localhost:8000"

        result = ensure_orchestrator_running()

        assert result == "http://localhost:8000"
        mock_find.assert_called_once()
        mock_start.assert_called_once_with(port=8000)

    @patch('src.orchestrator.auto_setup.find_running_server')
    @patch('src.orchestrator.auto_setup.start_orchestrator_daemon')
    def test_ensure_orchestrator_running_start_fails(
        self, mock_start, mock_find
    ):
        """Test when server start fails."""
        mock_find.return_value = None
        mock_start.side_effect = ServerError("Failed to start")

        with pytest.raises(ServerError, match="Failed to start"):
            ensure_orchestrator_running()

    @patch('src.orchestrator.auto_setup.find_running_server')
    @patch('src.orchestrator.auto_setup.start_orchestrator_daemon')
    def test_ensure_orchestrator_running_custom_port(
        self, mock_start, mock_find
    ):
        """Test with custom port specification."""
        mock_find.return_value = None
        mock_start.return_value = "http://localhost:8002"

        result = ensure_orchestrator_running(port=8002)

        assert result == "http://localhost:8002"
        mock_start.assert_called_once_with(port=8002)


class TestCleanupServer:
    """Tests for cleanup_server function."""

    @patch('src.orchestrator.auto_setup.psutil.Process')
    def test_cleanup_server_success(self, mock_process_cls):
        """Test successful server cleanup."""
        # Create a PID file
        orchestrator_dir = Path.cwd() / ".orchestrator"
        orchestrator_dir.mkdir(exist_ok=True)
        pid_file = orchestrator_dir / "server.pid"
        pid_file.write_text("12345")

        # Mock process
        mock_process = Mock()
        mock_process.is_running.return_value = True
        mock_process.cmdline.return_value = ["python", "-m", "src.orchestrator.api"]
        mock_process_cls.return_value = mock_process

        cleanup_server()

        # Verify process was terminated
        mock_process.terminate.assert_called_once()
        # Verify PID file was deleted
        assert not pid_file.exists()

    def test_cleanup_server_no_pid_file(self):
        """Test cleanup when PID file doesn't exist."""
        # Ensure no PID file
        pid_file = Path.cwd() / ".orchestrator" / "server.pid"
        pid_file.unlink(missing_ok=True)

        # Should not raise error
        cleanup_server()

    @patch('src.orchestrator.auto_setup.psutil.Process')
    def test_cleanup_server_stale_pid(self, mock_process_cls):
        """Test cleanup when PID file points to wrong process."""
        # Create a PID file
        orchestrator_dir = Path.cwd() / ".orchestrator"
        orchestrator_dir.mkdir(exist_ok=True)
        pid_file = orchestrator_dir / "server.pid"
        pid_file.write_text("12345")

        # Mock process with wrong command line
        mock_process = Mock()
        mock_process.is_running.return_value = True
        mock_process.cmdline.return_value = ["some", "other", "process"]
        mock_process_cls.return_value = mock_process

        cleanup_server()

        # Should not terminate (wrong process)
        mock_process.terminate.assert_not_called()
        # But should clean up stale PID file
        assert not pid_file.exists()

    @patch('src.orchestrator.auto_setup.psutil')
    def test_cleanup_server_process_already_dead(self, mock_psutil):
        """Test cleanup when process is already dead."""
        # Create a PID file
        orchestrator_dir = Path.cwd() / ".orchestrator"
        orchestrator_dir.mkdir(exist_ok=True)
        pid_file = orchestrator_dir / "server.pid"
        pid_file.write_text("12345")

        # Mock psutil to be None (not installed)
        mock_psutil.Process.side_effect = Exception("No such process")

        cleanup_server()

        # Should clean up PID file even if psutil fails
        assert not pid_file.exists()
