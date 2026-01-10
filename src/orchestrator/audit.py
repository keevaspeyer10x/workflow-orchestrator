"""
Tool Audit Logging

Records all tool executions for security auditing, debugging, and compliance.
"""

from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime, timezone
import json
import threading


class AuditEntry:
    """
    Represents a single audit log entry

    Attributes:
        timestamp: ISO8601 timestamp
        task_id: Task identifier
        phase: Current workflow phase
        tool_name: Name of executed tool
        args: Tool arguments
        result: Tool execution result
        duration_ms: Execution duration in milliseconds
        success: Whether execution succeeded
        error: Error message if failed
    """

    def __init__(
        self,
        task_id: str,
        phase: str,
        tool_name: str,
        args: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        success: bool = True,
        error: Optional[str] = None
    ):
        """
        Initialize audit entry

        Args:
            task_id: Task identifier
            phase: Workflow phase
            tool_name: Tool name
            args: Tool arguments
            result: Tool result (if successful)
            duration_ms: Execution duration in milliseconds
            success: Whether execution succeeded
            error: Error message (if failed)
        """
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.task_id = task_id
        self.phase = phase
        self.tool_name = tool_name
        self.args = args
        self.result = result
        self.duration_ms = duration_ms
        self.success = success
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert entry to dictionary

        Returns:
            Dict representation of audit entry
        """
        return {
            "timestamp": self.timestamp,
            "task_id": self.task_id,
            "phase": self.phase,
            "tool_name": self.tool_name,
            "args": self.args,
            "result": self.result,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error
        }

    def to_json(self) -> str:
        """
        Convert entry to JSON string

        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict())


class AuditLogger:
    """
    Audit logger for tool executions

    Writes audit entries to JSON Lines file format for easy parsing.
    Thread-safe for concurrent logging.
    """

    def __init__(self, log_file: Path = Path(".orchestrator/audit.jsonl")):
        """
        Initialize audit logger

        Args:
            log_file: Path to audit log file
        """
        self.log_file = log_file
        self._lock = threading.Lock()

        # Create log directory if needed
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log(self, entry: AuditEntry) -> None:
        """
        Write audit entry to log file

        Thread-safe operation.

        Args:
            entry: Audit entry to log
        """
        with self._lock:
            with open(self.log_file, 'a') as f:
                f.write(entry.to_json() + '\n')

    def log_tool_execution(
        self,
        task_id: str,
        phase: str,
        tool_name: str,
        args: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        success: bool = True,
        error: Optional[str] = None
    ) -> None:
        """
        Log a tool execution

        Convenience method for creating and logging an audit entry.

        Args:
            task_id: Task identifier
            phase: Workflow phase
            tool_name: Tool name
            args: Tool arguments
            result: Tool result (if successful)
            duration_ms: Execution duration in milliseconds
            success: Whether execution succeeded
            error: Error message (if failed)
        """
        entry = AuditEntry(
            task_id=task_id,
            phase=phase,
            tool_name=tool_name,
            args=args,
            result=result,
            duration_ms=duration_ms,
            success=success,
            error=error
        )
        self.log(entry)

    def query(
        self,
        task_id: Optional[str] = None,
        phase: Optional[str] = None,
        tool_name: Optional[str] = None,
        success: Optional[bool] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Query audit log entries

        Args:
            task_id: Filter by task ID
            phase: Filter by phase
            tool_name: Filter by tool name
            success: Filter by success status
            limit: Maximum number of entries to return

        Returns:
            List of matching audit entries
        """
        if not self.log_file.exists():
            return []

        entries = []

        with open(self.log_file, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)

                    # Apply filters
                    if task_id and entry.get("task_id") != task_id:
                        continue

                    if phase and entry.get("phase") != phase:
                        continue

                    if tool_name and entry.get("tool_name") != tool_name:
                        continue

                    if success is not None and entry.get("success") != success:
                        continue

                    entries.append(entry)

                    # Check limit
                    if limit and len(entries) >= limit:
                        break

                except json.JSONDecodeError:
                    # Skip malformed lines
                    continue

        return entries

    def get_recent(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get most recent audit entries

        Args:
            count: Number of entries to return

        Returns:
            List of recent audit entries (newest first)
        """
        if not self.log_file.exists():
            return []

        entries = []

        with open(self.log_file, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue

        # Return last N entries in reverse order (newest first)
        return list(reversed(entries[-count:]))

    def get_stats(self) -> Dict[str, Any]:
        """
        Get audit log statistics

        Returns:
            Dict with audit log statistics
        """
        if not self.log_file.exists():
            return {
                "total_entries": 0,
                "total_successes": 0,
                "total_failures": 0,
                "tools_used": {},
                "phases": {}
            }

        total = 0
        successes = 0
        failures = 0
        tools: Dict[str, int] = {}
        phases: Dict[str, int] = {}

        with open(self.log_file, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    total += 1

                    if entry.get("success"):
                        successes += 1
                    else:
                        failures += 1

                    tool = entry.get("tool_name", "unknown")
                    tools[tool] = tools.get(tool, 0) + 1

                    phase = entry.get("phase", "unknown")
                    phases[phase] = phases.get(phase, 0) + 1

                except json.JSONDecodeError:
                    continue

        return {
            "total_entries": total,
            "total_successes": successes,
            "total_failures": failures,
            "success_rate": successes / total if total > 0 else 0,
            "tools_used": tools,
            "phases": phases
        }

    def clear(self) -> None:
        """
        Clear audit log file

        WARNING: This permanently deletes all audit entries.
        Use with caution.
        """
        with self._lock:
            if self.log_file.exists():
                self.log_file.unlink()


# Global audit logger instance
audit_logger = AuditLogger()
