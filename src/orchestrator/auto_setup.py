"""
Auto-setup functionality for orchestrator enforcement.

Handles server discovery, health checking, and daemon process management.
"""

import time
import subprocess
import sys
from pathlib import Path
from typing import Optional, List

try:
    import httpx
except ImportError:
    httpx = None

try:
    import psutil
except ImportError:
    psutil = None


class ServerError(Exception):
    """Raised when server operations fail."""
    pass


def check_server_health(url: str, timeout: float = 2.0) -> bool:
    """
    Check if orchestrator server is healthy.

    Args:
        url: Server base URL (e.g., "http://localhost:8000")
        timeout: Request timeout in seconds

    Returns:
        True if server responds with 200 OK, False otherwise
    """
    if httpx is None:
        return False

    try:
        response = httpx.get(f"{url}/health", timeout=timeout)
        return response.status_code == 200
    except Exception:
        return False


def find_running_server(ports: Optional[List[int]] = None) -> Optional[str]:
    """
    Find a running orchestrator server on common ports.

    Args:
        ports: List of ports to check (default: [8000, 8001, 8002])

    Returns:
        Server URL if found, None otherwise
    """
    if ports is None:
        ports = [8000, 8001, 8002]

    for port in ports:
        url = f"http://localhost:{port}"
        if check_server_health(url):
            return url

    return None


def start_orchestrator_daemon(port: int = 8000, timeout: int = 10) -> str:
    """
    Start orchestrator server as a background daemon.

    Args:
        port: Port to run server on
        timeout: How long to wait for server to become healthy (seconds)

    Returns:
        Server URL

    Raises:
        ServerError: If server fails to start
    """
    # Create .orchestrator directory if it doesn't exist
    orchestrator_dir = Path.cwd() / ".orchestrator"
    orchestrator_dir.mkdir(exist_ok=True)

    # Open log file for stdout/stderr
    log_file_path = orchestrator_dir / "server.log"
    log_file = log_file_path.open('w')

    # Build command to start server
    cmd = [
        sys.executable,  # Use same Python interpreter
        "-m",
        "src.orchestrator.api",
        "--port",
        str(port)
    ]

    try:
        # Start server as subprocess
        # Use different flags for Windows vs Unix
        if sys.platform == "win32":
            # Windows: CREATE_NEW_PROCESS_GROUP
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            # Unix: setsid for proper daemon detachment
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                preexec_fn=lambda: None  # Could add os.setsid() here
            )
    except OSError as e:
        if "Address already in use" in str(e) or "Errno 98" in str(e):
            raise ServerError(
                f"Port {port} already in use. "
                f"Try a different port with --port flag or stop the existing server."
            )
        raise ServerError(f"Failed to start server: {e}")

    # Write PID file
    pid_file = orchestrator_dir / "server.pid"
    pid_file.write_text(str(process.pid))

    # Wait for server to become healthy
    server_url = f"http://localhost:{port}"
    start_time = time.time()

    while time.time() - start_time < timeout:
        if check_server_health(server_url):
            return server_url

        # Check if process died
        if process.poll() is not None:
            pid_file.unlink(missing_ok=True)
            raise ServerError(
                f"Server process died during startup. "
                f"Check {log_file_path} for details."
            )

        time.sleep(0.5)

    # Timeout - kill process and cleanup
    process.kill()
    pid_file.unlink(missing_ok=True)
    raise ServerError(
        f"Server failed to start within {timeout} seconds. "
        f"Check {log_file_path} for details."
    )


def ensure_orchestrator_running(port: int = 8000) -> str:
    """
    Ensure orchestrator server is running, starting it if necessary.

    Args:
        port: Preferred port for server

    Returns:
        Server URL

    Raises:
        ServerError: If server cannot be started
    """
    # First, check if a server is already running
    running_server = find_running_server()
    if running_server:
        return running_server

    # No server found, start one
    return start_orchestrator_daemon(port=port)


def cleanup_server():
    """
    Clean up orchestrator server process.

    Terminates the server process if running and removes PID file.
    Safe to call even if server is not running.
    """
    orchestrator_dir = Path.cwd() / ".orchestrator"
    pid_file = orchestrator_dir / "server.pid"

    if not pid_file.exists():
        return

    try:
        pid = int(pid_file.read_text().strip())

        # Check if process exists and is our server
        if psutil is not None:
            try:
                process = psutil.Process(pid)

                # Verify it's actually our orchestrator server
                if process.is_running():
                    cmdline = process.cmdline()
                    if "orchestrator" in " ".join(cmdline):
                        # It's our server, terminate it
                        process.terminate()
                        # Wait up to 5 seconds for graceful shutdown
                        process.wait(timeout=5)
            except psutil.NoSuchProcess:
                # Process already dead
                pass
            except psutil.TimeoutExpired:
                # Force kill if didn't terminate gracefully
                try:
                    process.kill()
                except:
                    pass

        # Clean up PID file
        pid_file.unlink()

    except (ValueError, FileNotFoundError, Exception):
        # Invalid or missing PID, or psutil error - just clean up file
        pid_file.unlink(missing_ok=True)
