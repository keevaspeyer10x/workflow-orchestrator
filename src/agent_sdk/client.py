"""
Agent SDK Client

Required for all agents to interact with workflow orchestrator.
Handles:
- Task claiming
- Phase transitions
- Tool execution with permission checks
- State snapshot access
"""

from typing import Optional, Dict, Any, List

try:
    import httpx
except ImportError:
    httpx = None  # Will be installed on Day 10


class AgentClient:
    """
    Client for agents to interact with workflow orchestrator

    All agent operations must go through this client.
    Direct file/state mutation is forbidden.
    """

    def __init__(
        self,
        agent_id: str,
        orchestrator_url: str = "http://localhost:8000"
    ):
        """
        Initialize agent client

        Args:
            agent_id: Unique agent identifier
            orchestrator_url: URL of orchestrator API
        """
        self.agent_id = agent_id
        self.orchestrator_url = orchestrator_url.rstrip("/")
        self.phase_token: Optional[str] = None
        self.current_phase: Optional[str] = None
        self.task_id: Optional[str] = None

        if httpx is None:
            raise ImportError("httpx not installed. Run: pip install httpx")

        self.client = httpx.Client(base_url=self.orchestrator_url)

    def claim_task(self, capabilities: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Claim a task from the orchestrator

        Args:
            capabilities: Agent capabilities

        Returns:
            Task details with initial phase token

        Raises:
            PermissionError: If claim denied
            httpx.HTTPError: If request fails
        """
        response = self.client.post(
            "/api/v1/tasks/claim",
            json={
                "agent_id": self.agent_id,
                "capabilities": capabilities or []
            }
        )

        if response.status_code == 403:
            raise PermissionError("Task claim denied by orchestrator")

        response.raise_for_status()

        data = response.json()

        # Store credentials
        self.task_id = data["task"]["id"]
        self.phase_token = data["phase_token"]
        self.current_phase = data["phase"]

        return data

    def request_transition(
        self,
        target_phase: str,
        artifacts: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Request phase transition

        Args:
            target_phase: Target phase ID (e.g., "TDD")
            artifacts: Artifacts required for transition

        Returns:
            Transition result with new token if approved

        Raises:
            PermissionError: If transition blocked by gate
            ValueError: If artifacts invalid
            RuntimeError: If not claimed or missing credentials
        """
        if not self.task_id or not self.phase_token or not self.current_phase:
            raise RuntimeError("Must claim task before requesting transition")

        response = self.client.post(
            "/api/v1/tasks/transition",
            json={
                "task_id": self.task_id,
                "current_phase": self.current_phase,
                "target_phase": target_phase,
                "phase_token": self.phase_token,
                "artifacts": artifacts
            }
        )

        if response.status_code == 403:
            raise PermissionError("Transition denied: invalid or expired token")

        response.raise_for_status()

        data = response.json()

        # Check if transition was allowed
        if not data.get("allowed"):
            blockers = data.get("blockers", [])
            raise PermissionError(f"Transition blocked: {'; '.join(blockers)}")

        # Update credentials with new token
        self.phase_token = data["new_token"]
        self.current_phase = target_phase

        return data

    def use_tool(self, tool_name: str, **kwargs) -> Any:
        """
        Execute tool with permission check

        Args:
            tool_name: Tool to execute
            **kwargs: Tool arguments

        Returns:
            Tool execution result

        Raises:
            PermissionError: If tool forbidden in current phase
            RuntimeError: If not claimed or missing credentials
        """
        if not self.task_id or not self.phase_token:
            raise RuntimeError("Must claim task before using tools")

        response = self.client.post(
            "/api/v1/tools/execute",
            json={
                "task_id": self.task_id,
                "phase_token": self.phase_token,
                "tool_name": tool_name,
                "args": kwargs
            }
        )

        if response.status_code == 403:
            raise PermissionError(f"Tool '{tool_name}' not allowed in current phase")

        if response.status_code == 400:
            error_detail = response.json().get("detail", "Tool execution failed")
            raise ValueError(error_detail)

        response.raise_for_status()

        data = response.json()
        return data.get("result")

    def get_state_snapshot(self) -> Dict[str, Any]:
        """
        Get read-only state snapshot

        Returns:
            Filtered state showing task dependencies, blockers, etc.

        Raises:
            RuntimeError: If not claimed or missing credentials
        """
        if not self.phase_token:
            raise RuntimeError("Must claim task before getting state snapshot")

        response = self.client.get(
            "/api/v1/state/snapshot",
            params={"phase_token": self.phase_token}
        )

        if response.status_code == 403:
            raise PermissionError("Invalid or expired token")

        response.raise_for_status()

        return response.json()

    # Convenience methods
    def read_file(self, path: str, offset: int = 0, limit: Optional[int] = None) -> str:
        """
        Read file using orchestrator API

        Args:
            path: File path to read
            offset: Line offset to start reading
            limit: Maximum lines to read

        Returns:
            File content
        """
        result = self.use_tool("read_files", path=path, offset=offset, limit=limit)
        return result.get("content", "")

    def write_file(self, path: str, content: str, mode: str = "w") -> Dict[str, Any]:
        """
        Write file using orchestrator API

        Args:
            path: File path to write
            content: Content to write
            mode: Write mode ('w' for overwrite, 'a' for append)

        Returns:
            Write result with bytes written
        """
        return self.use_tool("write_files", path=path, content=content, mode=mode)

    def run_command(self, command: str, timeout: int = 30, cwd: Optional[str] = None) -> Dict[str, Any]:
        """
        Run bash command using orchestrator API

        Args:
            command: Bash command to execute
            timeout: Timeout in seconds
            cwd: Working directory

        Returns:
            Command result with stdout, stderr, exit_code
        """
        return self.use_tool("bash", command=command, timeout=timeout, cwd=cwd)

    def grep(self, pattern: str, path: str) -> Dict[str, Any]:
        """
        Search for pattern in files

        Args:
            pattern: Regex pattern
            path: File or directory to search

        Returns:
            Search results with matches
        """
        return self.use_tool("grep", pattern=pattern, path=path)

    def close(self):
        """Close the HTTP client"""
        self.client.close()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
