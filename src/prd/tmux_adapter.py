"""
TmuxAdapter - Direct tmux management for parallel Claude Code agents.

Replaces the broken Claude Squad integration (PRD-004).
Uses tmux sessions/windows directly instead of automating a TUI.
"""

import subprocess
import shutil
import re
import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timezone

from .session_registry import SessionRegistry, SessionRecord
from src.secrets import get_user_config_value

logger = logging.getLogger(__name__)


def get_claude_binary() -> str:
    """
    Get the Claude binary to use for spawning sessions.

    Priority (highest to lowest):
    1. CLAUDE_BINARY environment variable
    2. Global orchestrator config (claude_binary)
    3. Default: "claude"

    This enables Happy (https://happy.engineering) integration by setting:
    - `CLAUDE_BINARY=happy` in environment, or
    - `orchestrator config set claude_binary happy` globally
    """
    # 1. Environment variable (highest priority)
    env_binary = os.environ.get("CLAUDE_BINARY")
    if env_binary:
        return env_binary

    # 2. Global orchestrator config
    configured = get_user_config_value("claude_binary")
    if configured:
        return configured

    # 3. Default
    return "claude"


def generate_approval_gate_instructions(agent_id: str, db_path: str) -> str:
    """
    Generate instructions for an agent to use the ApprovalGate.

    These instructions are injected into the agent's prompt so it knows
    to pause at workflow gates and request human approval.

    Args:
        agent_id: Identifier for this agent
        db_path: Path to the approval database

    Returns:
        Markdown-formatted instructions for the agent
    """
    return f"""
## Approval Gate Integration (PRD-005)

You are running as part of a parallel agent system. You MUST request human approval
at certain workflow gates before proceeding with risky operations.

### Risk Classification Guide

Classify each operation by risk level:

| Risk Level | Examples | Approval |
|------------|----------|----------|
| **low** | Read files, run tests, lint, format | Auto-approved |
| **medium** | Create files, small edits (<50 lines), install deps | Auto in PLAN/VERIFY, human in EXECUTE |
| **high** | Major refactoring (>100 lines), config changes, deps | Always requires human |
| **critical** | Force push, delete branches, prod deploy, rm -rf | Always requires human |

### How to Request Approval

Before risky operations in EXECUTE phase, request approval:

```python
from src.approval_gate import create_gate

# Initialize gate (once at start)
gate = create_gate(agent_id="{agent_id}", db_path="{db_path}")

# Before risky operations
result = gate.request_approval(
    phase="EXECUTE",
    operation="Modify database schema",  # Human-readable description
    risk_level="high",  # low, medium, high, critical
    context={{"files": ["schema.py"], "lines_changed": 150}}
)

if result == WaitResult.REJECTED:
    print("Operation rejected by human")
    # Handle rejection gracefully
```

### When to Request Approval

1. **EXECUTE phase** - Before making changes to files, configs, or dependencies
2. **High/Critical risk** - Always request, regardless of phase
3. **Irreversible operations** - Always request (force push, deletions)

### Auto-Approval (Transparency)

Low-risk and some medium-risk operations are auto-approved for efficiency.
All decisions (auto and human) are logged for transparency.
At the end of your session, report what was auto-approved so the human knows.

### Waiting for Approval

When you submit a high-risk request:
1. The request appears in `orchestrator approval pending`
2. Wait for human to run `orchestrator approval approve <id>`
3. Your gate.request_approval() call will return when decided

Agent ID: {agent_id}
Approval DB: {db_path}
"""


@dataclass
class TmuxConfig:
    """Configuration for tmux-based agent management."""
    claude_binary: str = field(default_factory=get_claude_binary)
    session_prefix: str = "wfo"  # workflow-orchestrator prefix
    command_timeout: int = 30
    inject_approval_gate: bool = True  # PRD-006: Auto-inject gate instructions


class TmuxError(Exception):
    """Base exception for tmux operations."""
    pass


class TmuxNotAvailableError(TmuxError):
    """tmux is not installed or not available."""
    pass


class SessionNotFoundError(TmuxError):
    """Session or task not found."""
    pass


class TmuxAdapter:
    """
    Direct tmux management for parallel Claude Code agents.

    Features:
    - Session persistence (survives orchestrator crashes)
    - Human can attach to any agent window
    - Output capture via capture-pane
    - Idempotent spawning
    - Happy integration via CLAUDE_BINARY
    """

    def __init__(
        self,
        working_dir: Path,
        config: Optional[TmuxConfig] = None,
        session_name: Optional[str] = None,
    ):
        self.config = config or TmuxConfig()
        self.working_dir = Path(working_dir)
        self.registry = SessionRegistry(self.working_dir)

        # Generate session name based on working dir
        self.session_name = session_name or self._default_session_name()

        # Verify tmux is available
        if not self._is_tmux_available():
            raise TmuxNotAvailableError(
                "tmux is not installed. Install with: brew install tmux (macOS) "
                "or apt install tmux (Linux)"
            )

    def _is_tmux_available(self) -> bool:
        """Check if tmux is installed."""
        return shutil.which("tmux") is not None

    def _default_session_name(self) -> str:
        """Generate default session name from working dir."""
        dir_name = self.working_dir.name[:20]
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '-', dir_name)
        return f"{self.config.session_prefix}-{safe_name}"

    def _generate_window_name(self, task_id: str) -> str:
        """
        Generate safe window name from task ID.

        tmux window names have restrictions on characters.
        """
        # Sanitize: only alphanumeric, dash, underscore
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '-', task_id)[:50]
        return f"task-{safe_id}"

    def _run_tmux(
        self,
        args: List[str],
        check: bool = True,
        capture: bool = True
    ) -> subprocess.CompletedProcess:
        """Run tmux command with error handling."""
        cmd = ["tmux"] + args

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
                logger.warning(f"tmux command failed: {' '.join(args)}, stderr: {result.stderr}")

            return result

        except subprocess.TimeoutExpired:
            raise TmuxError(f"tmux command timed out: {' '.join(args)}")

    def _ensure_session(self) -> None:
        """Create tmux session if it doesn't exist."""
        result = self._run_tmux(
            ["has-session", "-t", self.session_name],
            check=False
        )

        if result.returncode != 0:
            # Session doesn't exist, create it
            self._run_tmux([
                "new-session",
                "-d",  # detached
                "-s", self.session_name,
                "-c", str(self.working_dir),
            ])
            logger.info(f"Created tmux session: {self.session_name}")

    def spawn_agent(
        self,
        task_id: str,
        prompt: str,
        working_dir: Path,
        branch: str
    ) -> SessionRecord:
        """
        Spawn a new Claude Code agent in a tmux window.

        Idempotent: returns existing session if already spawned.
        """
        # Check for existing session (idempotency)
        existing = self.registry.get(task_id)
        if existing and existing.status in ("pending", "running"):
            logger.info(f"Session already exists for task {task_id}")
            return existing

        # Ensure session exists
        self._ensure_session()

        window_name = self._generate_window_name(task_id)

        # PRD-006: Inject approval gate instructions if enabled
        if self.config.inject_approval_gate:
            db_path = str(working_dir / ".workflow_approvals.db")
            gate_instructions = generate_approval_gate_instructions(
                agent_id=task_id,
                db_path=db_path
            )
            prompt = prompt + "\n\n" + gate_instructions

        # Write prompt to file (avoids shell escaping issues)
        # Use sanitized task_id for filename
        safe_task_id = re.sub(r'[^a-zA-Z0-9_-]', '-', task_id)[:50]
        prompt_dir = self.working_dir / ".claude"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = prompt_dir / f"prompt_{safe_task_id}.md"
        prompt_file.write_text(prompt)

        # Create new window for this task
        self._run_tmux([
            "new-window",
            "-t", self.session_name,
            "-n", window_name,
            "-c", str(working_dir),
        ])

        # Build claude command
        claude_cmd = f"cat {prompt_file} | {self.config.claude_binary}"

        # Send command to the window
        self._run_tmux([
            "send-keys",
            "-t", f"{self.session_name}:{window_name}",
            claude_cmd,
            "Enter"
        ])

        # Create and persist record
        now = datetime.now(timezone.utc).isoformat()
        record = SessionRecord(
            task_id=task_id,
            session_id=f"{self.session_name}:{window_name}",
            session_name=window_name,
            branch=branch,
            status="running",
            created_at=now,
            updated_at=now,
            prompt_file=str(prompt_file)
        )

        self.registry.register(record)
        logger.info(f"Spawned agent {window_name} for task {task_id}")

        return record

    def list_agents(self) -> List[SessionRecord]:
        """List all active agent sessions from registry."""
        return self.registry.list_active()

    def list_windows(self) -> List[dict]:
        """List actual tmux windows (for reconciliation)."""
        result = self._run_tmux([
            "list-windows",
            "-t", self.session_name,
            "-F", "#{window_name}:#{pane_current_path}"
        ], check=False)

        if result.returncode != 0:
            return []

        windows = []
        for line in result.stdout.strip().split("\n"):
            if ":" in line:
                name, path = line.split(":", 1)
                windows.append({
                    "name": name,
                    "path": path
                })

        return windows

    def capture_output(self, task_id: str, lines: int = 100) -> str:
        """Capture recent output from an agent's window."""
        record = self.registry.get(task_id)
        if not record:
            raise SessionNotFoundError(f"No session for task {task_id}")

        target = f"{self.session_name}:{record.session_name}"

        result = self._run_tmux([
            "capture-pane",
            "-t", target,
            "-p",  # print to stdout
            "-S", f"-{lines}"  # last N lines
        ], check=False)

        return result.stdout if result.returncode == 0 else ""

    def attach(self, task_id: str) -> None:
        """
        Attach user's terminal to an agent's window.

        This replaces the current process with tmux attach.
        """
        record = self.registry.get(task_id)
        if not record:
            raise SessionNotFoundError(f"No session for task {task_id}")

        if record.status not in ("pending", "running"):
            raise TmuxError(f"Session {task_id} is {record.status}, cannot attach")

        # Select the window first
        self._run_tmux([
            "select-window",
            "-t", f"{self.session_name}:{record.session_name}"
        ])

        # Replace current process with tmux attach
        os.execvp("tmux", ["tmux", "attach", "-t", self.session_name])

    def kill_agent(self, task_id: str) -> None:
        """Kill an agent's window."""
        record = self.registry.get(task_id)
        if not record:
            logger.warning(f"No session found for task {task_id}")
            return

        target = f"{self.session_name}:{record.session_name}"

        # Kill the window (may fail if already dead)
        self._run_tmux([
            "kill-window",
            "-t", target
        ], check=False)

        # Update registry
        self.registry.update_status(task_id, "terminated")

        # Clean up prompt file
        if record.prompt_file:
            try:
                Path(record.prompt_file).unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to clean up prompt file: {e}")

        logger.info(f"Killed agent for task {task_id}")

    def mark_complete(self, task_id: str) -> None:
        """Mark a task as complete and optionally kill its window."""
        record = self.registry.get(task_id)
        if not record:
            raise SessionNotFoundError(f"No session for task {task_id}")

        self.registry.update_status(task_id, "completed")
        self.kill_agent(task_id)

    def cleanup(self) -> None:
        """Kill entire session and all agents."""
        self._run_tmux([
            "kill-session",
            "-t", self.session_name
        ], check=False)

        # Update all active sessions in registry to terminated
        for record in self.registry.list_active():
            self.registry.update_status(record.task_id, "terminated")

        logger.info(f"Cleaned up session {self.session_name}")

    def get_session_info(self) -> dict:
        """Get information about the tmux session."""
        result = self._run_tmux([
            "display-message",
            "-t", self.session_name,
            "-p", "#{session_name}: #{session_windows} windows"
        ], check=False)

        return {
            "session_name": self.session_name,
            "exists": result.returncode == 0,
            "info": result.stdout.strip() if result.returncode == 0 else None,
            "windows": self.list_windows()
        }
