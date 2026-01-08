"""
Claude Squad Adapter - Revised based on AI review feedback.

Changes from v0.1:
- Uses SessionRegistry for persistent state
- Capability detection before operations
- Robust output parsing with fallbacks
- Explicit session termination
- Session name validation
- Idempotency checks
"""

import subprocess
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timezone
import logging

from .session_registry import SessionRegistry, SessionRecord
from .squad_capabilities import CapabilityDetector, SquadCapabilities

logger = logging.getLogger(__name__)


@dataclass
class SquadConfig:
    """Configuration for Claude Squad integration."""
    claude_squad_path: str = "claude-squad"
    auto_yes: bool = True
    session_prefix: str = "wfo"  # workflow-orchestrator prefix
    command_timeout: int = 30


class ClaudeSquadError(Exception):
    """Base exception for Claude Squad operations."""
    pass


class CapabilityError(ClaudeSquadError):
    """Claude Squad missing required capabilities."""
    pass


class SessionError(ClaudeSquadError):
    """Session operation failed."""
    pass


class ClaudeSquadAdapter:
    """
    Revised adapter for Claude Squad integration.

    Addresses AI review concerns:
    - Persistent state via SessionRegistry
    - Capability detection on init
    - Robust parsing with fallbacks
    - Explicit lifecycle management
    - Idempotency guarantees
    """

    def __init__(
        self,
        working_dir: Path,
        config: Optional[SquadConfig] = None,
        skip_capability_check: bool = False
    ):
        self.config = config or SquadConfig()
        self.working_dir = working_dir
        self.registry = SessionRegistry(working_dir)

        # Capability detection
        if not skip_capability_check:
            detector = CapabilityDetector(self.config.claude_squad_path)
            self.capabilities = detector.detect()

            if not self.capabilities.is_compatible:
                issues = ", ".join(self.capabilities.compatibility_issues)
                raise CapabilityError(
                    f"Claude Squad not compatible: {issues}\n"
                    f"Install: https://github.com/smtg-ai/claude-squad"
                )

            logger.info(
                f"Claude Squad v{self.capabilities.version} detected, "
                f"capabilities: prompt_file={self.capabilities.supports_prompt_file}, "
                f"json={self.capabilities.supports_json_output}"
            )
        else:
            self.capabilities = SquadCapabilities(installed=True, is_compatible=True)

        # Reconcile on init
        self._reconcile_state()

    def _reconcile_state(self) -> None:
        """Sync registry with actual Claude Squad state."""
        try:
            squad_sessions = self._list_squad_sessions()
            self.registry.reconcile(squad_sessions)
        except Exception as e:
            logger.warning(f"Failed to reconcile state: {e}")

    def _generate_session_name(self, task_id: str) -> str:
        """
        Generate safe session name from task ID.

        Addresses: "task IDs may include characters invalid for tmux/session names"
        """
        # Sanitize: only alphanumeric, dash, underscore
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '-', task_id)[:50]
        return f"{self.config.session_prefix}-{safe_id}"

    def _run_command(
        self,
        args: List[str],
        check: bool = True,
        capture: bool = True
    ) -> subprocess.CompletedProcess:
        """Run claude-squad command with error handling."""
        cmd = [self.config.claude_squad_path] + args

        logger.debug(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=capture,
                text=True,
                timeout=self.config.command_timeout,
                cwd=self.working_dir
            )

            if check and result.returncode != 0:
                raise SessionError(
                    f"Command failed: {' '.join(args)}\n"
                    f"Exit code: {result.returncode}\n"
                    f"Stderr: {result.stderr}"
                )

            return result

        except subprocess.TimeoutExpired:
            raise SessionError(f"Command timed out: {' '.join(args)}")

    def _parse_session_id(self, output: str, session_name: str) -> str:
        """
        Parse session ID from command output with multiple strategies.

        Addresses: "Session ID parsing is brittle (scraping stdout)"
        """
        # Strategy 1: Look for JSON in output
        try:
            json_match = re.search(r'\{.*"id".*\}', output, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                if "id" in data:
                    return data["id"]
        except json.JSONDecodeError:
            pass

        # Strategy 2: Look for "session: <id>" or "id: <id>" patterns
        patterns = [
            r'session[:\s]+([a-zA-Z0-9_-]+)',
            r'id[:\s]+([a-zA-Z0-9_-]+)',
            r'created[:\s]+([a-zA-Z0-9_-]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return match.group(1)

        # Strategy 3: Fall back to session name as ID
        logger.warning(
            f"Could not parse session ID from output, using session name: {session_name}"
        )
        return session_name

    def _list_squad_sessions(self) -> List[dict]:
        """List sessions from Claude Squad."""
        if self.capabilities.supports_json_output:
            result = self._run_command(["list", "--json"], check=False)
            if result.returncode == 0:
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    pass

        # Fallback: parse text output
        result = self._run_command(["list"], check=False)
        sessions = []

        for line in result.stdout.split("\n"):
            line = line.strip()
            if line and line.startswith(self.config.session_prefix):
                # Parse "name status" or just "name"
                parts = line.split()
                sessions.append({
                    "name": parts[0],
                    "status": parts[1] if len(parts) > 1 else "unknown"
                })

        return sessions

    def spawn_session(
        self,
        task_id: str,
        prompt: str,
        branch: str
    ) -> SessionRecord:
        """
        Spawn a new Claude Squad session for a task.

        Idempotent: returns existing session if already spawned.
        """
        # Check for existing session (idempotency)
        existing = self.registry.get(task_id)
        if existing and existing.status in ("pending", "running"):
            logger.info(f"Session already exists for task {task_id}: {existing.session_name}")
            return existing

        session_name = self._generate_session_name(task_id)

        # Write prompt to file
        prompt_file = self.working_dir / ".claude" / f"prompt_{task_id}.md"
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(prompt)

        # Build command
        cmd = ["new", "--name", session_name, "--dir", str(self.working_dir)]

        if self.capabilities.supports_branch:
            cmd.extend(["--branch", branch])

        if self.capabilities.supports_prompt_file:
            cmd.extend(["--prompt-file", str(prompt_file)])

        if self.config.auto_yes and self.capabilities.supports_autoyes:
            cmd.append("--autoyes")

        # Spawn
        result = self._run_command(cmd)

        # Parse session ID
        session_id = self._parse_session_id(result.stdout, session_name)

        # Create and persist record
        now = datetime.now(timezone.utc).isoformat()
        record = SessionRecord(
            task_id=task_id,
            session_id=session_id,
            session_name=session_name,
            branch=branch,
            status="running",
            created_at=now,
            updated_at=now,
            prompt_file=str(prompt_file)
        )

        self.registry.register(record)
        logger.info(f"Spawned session {session_name} for task {task_id}")

        return record

    def spawn_batch(
        self,
        tasks: List[dict]  # [{task_id, prompt, branch}, ...]
    ) -> List[SessionRecord]:
        """
        Spawn sessions for a batch of tasks.

        Note: Sequential for simplicity. AI reviewers noted this could
        be parallelized if performance becomes an issue.
        """
        sessions = []
        for task in tasks:
            try:
                session = self.spawn_session(
                    task_id=task["task_id"],
                    prompt=task["prompt"],
                    branch=task["branch"]
                )
                sessions.append(session)
            except SessionError as e:
                logger.error(f"Failed to spawn session for {task['task_id']}: {e}")

        return sessions

    def get_status(self, task_id: str) -> Optional[str]:
        """Get session status."""
        record = self.registry.get(task_id)
        if not record:
            return None

        # Refresh from Claude Squad
        self._reconcile_state()

        updated = self.registry.get(task_id)
        return updated.status if updated else None

    def list_sessions(self) -> List[SessionRecord]:
        """List all active sessions."""
        self._reconcile_state()
        return self.registry.list_active()

    def attach(self, task_id: str) -> None:
        """
        Attach user's terminal to a session.

        This replaces the current process with tmux attach.
        """
        record = self.registry.get(task_id)
        if not record:
            raise SessionError(f"No session for task {task_id}")

        if record.status not in ("pending", "running"):
            raise SessionError(f"Session {task_id} is {record.status}, cannot attach")

        # This replaces the current process
        import os
        os.execvp(
            self.config.claude_squad_path,
            [self.config.claude_squad_path, "attach", record.session_name]
        )

    def mark_complete(self, task_id: str, terminate_session: bool = True) -> None:
        """
        Mark a task as complete.

        Addresses AI concern: "What happens to underlying tmux session"
        """
        record = self.registry.get(task_id)
        if not record:
            raise SessionError(f"No session for task {task_id}")

        # Update status
        self.registry.update_status(task_id, "completed")

        # Optionally terminate the Claude Squad session
        if terminate_session:
            self._terminate_session(record.session_name)

        # Clean up prompt file
        if record.prompt_file:
            try:
                Path(record.prompt_file).unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to clean up prompt file: {e}")

        logger.info(f"Task {task_id} marked complete, session terminated: {terminate_session}")

    def _terminate_session(self, session_name: str) -> None:
        """Terminate a Claude Squad session."""
        if self.capabilities.supports_kill:
            try:
                self._run_command(["kill", session_name], check=False)
            except SessionError:
                pass  # May already be terminated
        else:
            logger.warning(
                f"Claude Squad doesn't support 'kill' command, "
                f"session {session_name} may need manual cleanup"
            )

    def cleanup_orphaned(self) -> int:
        """Clean up orphaned sessions."""
        self._reconcile_state()

        cleaned = 0
        for record in self.registry.list_all():
            if record.status == "orphaned":
                self.registry.update_status(record.task_id, "terminated")
                cleaned += 1

        return cleaned
