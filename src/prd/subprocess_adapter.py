"""
SubprocessAdapter - Fallback when tmux is not available.

Fire-and-forget subprocess spawning with log capture.
No interactive attach capability (limitation of fallback).
"""

import subprocess
import signal
import os
import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime, timezone

from .session_registry import SessionRegistry, SessionRecord
from .tmux_adapter import generate_approval_gate_instructions
from src.secrets import get_user_config_value

logger = logging.getLogger(__name__)


def get_claude_binary() -> str:
    """Get the Claude binary to use (supports Happy integration)."""
    env_binary = os.environ.get("CLAUDE_BINARY")
    if env_binary:
        return env_binary

    configured = get_user_config_value("claude_binary")
    if configured:
        return configured

    return "claude"


@dataclass
class SubprocessConfig:
    """Configuration for subprocess-based agent management."""
    claude_binary: str = field(default_factory=get_claude_binary)
    session_prefix: str = "wfo"
    log_dir_name: str = ".wfo_logs"
    inject_approval_gate: bool = True  # PRD-006: Auto-inject gate instructions


class SubprocessError(Exception):
    """Base exception for subprocess operations."""
    pass


class SubprocessAdapter:
    """
    Fallback adapter using simple subprocess spawning.

    Limitations:
    - No interactive attach (fire-and-forget)
    - Less visibility than tmux
    - Processes may orphan if orchestrator crashes

    Use when tmux is not available (CI, Windows, containers).
    """

    def __init__(
        self,
        working_dir: Path,
        config: Optional[SubprocessConfig] = None,
    ):
        self.config = config or SubprocessConfig()
        self.working_dir = Path(working_dir)
        self.registry = SessionRegistry(self.working_dir)

        # Track running processes in memory (PIDs)
        self._processes: Dict[str, subprocess.Popen] = {}

        # Ensure log directory exists
        self.log_dir = self.working_dir / self.config.log_dir_name
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _generate_session_name(self, task_id: str) -> str:
        """Generate safe session name from task ID."""
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '-', task_id)[:50]
        return f"{self.config.session_prefix}-{safe_id}"

    def _get_log_file(self, task_id: str) -> Path:
        """Get log file path for a task."""
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '-', task_id)
        return self.log_dir / f"{safe_id}.log"

    def _get_prompt_file(self, task_id: str) -> Path:
        """Get prompt file path for a task."""
        # Sanitize task_id for filename
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '-', task_id)[:50]
        prompt_dir = self.working_dir / ".claude"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        return prompt_dir / f"prompt_{safe_id}.md"

    def spawn_agent(
        self,
        task_id: str,
        prompt: str,
        working_dir: Path,
        branch: str
    ) -> SessionRecord:
        """
        Spawn a new Claude Code agent as a subprocess.

        Idempotent: returns existing session if already spawned.
        """
        # Check for existing session (idempotency)
        existing = self.registry.get(task_id)
        if existing and existing.status in ("pending", "running"):
            # Check if process is still running
            if task_id in self._processes:
                proc = self._processes[task_id]
                if proc.poll() is None:  # Still running
                    logger.info(f"Process already running for task {task_id}")
                    return existing

        session_name = self._generate_session_name(task_id)

        # PRD-006: Inject approval gate instructions if enabled
        if self.config.inject_approval_gate:
            db_path = str(working_dir / ".workflow_approvals.db")
            gate_instructions = generate_approval_gate_instructions(
                agent_id=task_id,
                db_path=db_path
            )
            prompt = prompt + "\n\n" + gate_instructions

        # Write prompt to file
        prompt_file = self._get_prompt_file(task_id)
        prompt_file.write_text(prompt)

        # Open log file
        log_file = self._get_log_file(task_id)

        try:
            with open(log_file, "w") as log_handle:
                with open(prompt_file, "r") as prompt_handle:
                    proc = subprocess.Popen(
                        [self.config.claude_binary, "--print"],
                        stdin=prompt_handle,
                        stdout=log_handle,
                        stderr=subprocess.STDOUT,
                        cwd=working_dir,
                        start_new_session=True,  # Detach from parent
                    )

            self._processes[task_id] = proc
            pid = proc.pid

        except OSError as e:
            raise SubprocessError(f"Failed to spawn process: {e}")

        # Create and persist record
        now = datetime.now(timezone.utc).isoformat()
        record = SessionRecord(
            task_id=task_id,
            session_id=f"pid-{pid}",
            session_name=session_name,
            branch=branch,
            status="running",
            created_at=now,
            updated_at=now,
            prompt_file=str(prompt_file)
        )

        self.registry.register(record)
        logger.info(f"Spawned subprocess for task {task_id} (PID: {pid})")

        return record

    def list_agents(self) -> List[SessionRecord]:
        """List all active agent sessions."""
        active = []
        for record in self.registry.list_active():
            # Check if process is still running
            if record.task_id in self._processes:
                proc = self._processes[record.task_id]
                if proc.poll() is not None:
                    # Process finished, update status
                    self.registry.update_status(record.task_id, "completed")
                    continue
            active.append(record)

        return active

    def capture_output(self, task_id: str, lines: int = 100) -> str:
        """Read from log file."""
        log_file = self._get_log_file(task_id)

        if not log_file.exists():
            return ""

        try:
            content = log_file.read_text()
            # Return last N lines
            all_lines = content.split("\n")
            return "\n".join(all_lines[-lines:])
        except Exception as e:
            logger.warning(f"Failed to read log file: {e}")
            return ""

    def kill_agent(self, task_id: str) -> None:
        """Kill a running subprocess."""
        record = self.registry.get(task_id)

        # Try to kill the process
        if task_id in self._processes:
            proc = self._processes[task_id]
            if proc.poll() is None:  # Still running
                try:
                    os.kill(proc.pid, signal.SIGTERM)
                    logger.info(f"Sent SIGTERM to PID {proc.pid}")
                except ProcessLookupError:
                    pass  # Already dead

            del self._processes[task_id]

        # Also try by PID from registry
        if record and record.session_id.startswith("pid-"):
            try:
                pid = int(record.session_id.split("-")[1])
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, ValueError, IndexError):
                pass

        # Update registry
        if record:
            self.registry.update_status(task_id, "terminated")

            # Clean up prompt file
            if record.prompt_file:
                try:
                    Path(record.prompt_file).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Failed to clean up prompt file: {e}")

    def attach(self, task_id: str) -> None:
        """
        Not supported for subprocess adapter.

        Subprocesses run detached - there's no terminal to attach to.
        """
        raise NotImplementedError(
            "SubprocessAdapter does not support attach. "
            "Use TmuxAdapter for interactive sessions."
        )

    def mark_complete(self, task_id: str) -> None:
        """Mark a task as complete."""
        self.registry.update_status(task_id, "completed")
        self.kill_agent(task_id)

    def cleanup(self) -> None:
        """Kill all running processes."""
        for task_id in list(self._processes.keys()):
            self.kill_agent(task_id)

        # Update all active sessions in registry
        for record in self.registry.list_active():
            self.registry.update_status(record.task_id, "terminated")

        logger.info("Cleaned up all subprocess agents")

    def get_status(self, task_id: str) -> Optional[str]:
        """Get status of a task."""
        record = self.registry.get(task_id)
        if not record:
            return None

        # Check if process is still running
        if task_id in self._processes:
            proc = self._processes[task_id]
            if proc.poll() is None:
                return "running"
            else:
                self.registry.update_status(task_id, "completed")
                return "completed"

        return record.status
