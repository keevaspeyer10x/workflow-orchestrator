# Claude Squad Integration - Detailed Design

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2026-01-09 | Claude | Initial sketch |
| 0.2 | 2026-01-09 | Claude | Detailed design addressing AI review feedback |

## 1. Executive Summary

This design integrates the Workflow Orchestrator with [Claude Squad](https://github.com/smtg-ai/claude-squad) for managing multiple interactive Claude Code sessions. Based on external AI reviews (GPT-5.2, Gemini 2.5, Grok 4), this revision addresses:

- **State persistence** across orchestrator restarts
- **CLI capability detection** before assuming features exist
- **Session lifecycle management** with explicit cleanup
- **Robust parsing** with fallback strategies
- **Hybrid backend approach** retaining one remote option

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Workflow Orchestrator                        │
├─────────────────────────────────────────────────────────────────┤
│  PRD Coordinator                                                 │
│    ├── Task Schema & State (existing)                           │
│    ├── Prompt Generation (existing)                             │
│    ├── Branch/Merge Coordination (existing)                     │
│    ├── Session Registry (NEW - persistent)                      │
│    └── Backend Selector (NEW - hybrid)                          │
│            │                                                     │
│            ├── ClaudeSquadAdapter (interactive local)           │
│            └── GitHubActionsBackend (batch remote) [RETAINED]   │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       │ Subprocess / REST
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Claude Squad                                │
│  (Session lifecycle, tmux management, Claude process control)   │
└─────────────────────────────────────────────────────────────────┘
```

## 3. Detailed Components

### 3.1 Session Registry (Persistent State)

**Problem**: AI reviewers flagged that in-memory `_sessions` dict is lost on restart.

**Solution**: Persist session mapping to `.claude/squad_sessions.json`.

```python
# src/prd/session_registry.py
"""
Persistent session registry for Claude Squad integration.

Addresses AI review concern: "In-memory session mapping will be lost
on orchestrator restart"
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
from filelock import FileLock


@dataclass
class SessionRecord:
    """Persistent record of a Claude Squad session."""
    task_id: str
    session_id: str
    session_name: str
    branch: str
    status: str  # pending, running, completed, terminated, orphaned
    created_at: str
    updated_at: str
    prompt_file: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SessionRecord":
        return cls(**data)


class SessionRegistry:
    """
    Persistent registry for task <-> session mappings.

    Features:
    - Survives orchestrator restart
    - Thread-safe via file locking
    - Auto-reconciliation with Claude Squad state
    """

    def __init__(self, working_dir: Path):
        self.working_dir = working_dir
        self.registry_file = working_dir / ".claude" / "squad_sessions.json"
        self.lock_file = self.registry_file.with_suffix(".lock")
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, SessionRecord]:
        """Load registry from disk."""
        if not self.registry_file.exists():
            return {}

        with FileLock(self.lock_file):
            data = json.loads(self.registry_file.read_text())
            return {
                task_id: SessionRecord.from_dict(record)
                for task_id, record in data.items()
            }

    def _save(self, registry: dict[str, SessionRecord]) -> None:
        """Save registry to disk."""
        with FileLock(self.lock_file):
            data = {
                task_id: record.to_dict()
                for task_id, record in registry.items()
            }
            self.registry_file.write_text(json.dumps(data, indent=2))

    def register(self, record: SessionRecord) -> None:
        """Register a new session."""
        registry = self._load()
        registry[record.task_id] = record
        self._save(registry)

    def get(self, task_id: str) -> Optional[SessionRecord]:
        """Get session record by task ID."""
        return self._load().get(task_id)

    def update_status(self, task_id: str, status: str) -> None:
        """Update session status."""
        registry = self._load()
        if task_id in registry:
            registry[task_id].status = status
            registry[task_id].updated_at = datetime.now(timezone.utc).isoformat()
            self._save(registry)

    def list_active(self) -> list[SessionRecord]:
        """List all active (non-terminated) sessions."""
        return [
            r for r in self._load().values()
            if r.status in ("pending", "running")
        ]

    def reconcile(self, squad_sessions: list[dict]) -> None:
        """
        Reconcile registry with Claude Squad's actual state.

        Marks sessions as 'orphaned' if they exist in registry
        but not in Claude Squad (e.g., manual termination).
        """
        registry = self._load()
        squad_names = {s["name"] for s in squad_sessions}

        for task_id, record in registry.items():
            if record.status in ("pending", "running"):
                if record.session_name not in squad_names:
                    record.status = "orphaned"
                    record.updated_at = datetime.now(timezone.utc).isoformat()

        self._save(registry)

    def cleanup_old(self, days: int = 7) -> int:
        """Remove records older than N days."""
        registry = self._load()
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)

        to_remove = []
        for task_id, record in registry.items():
            if record.status in ("completed", "terminated", "orphaned"):
                record_time = datetime.fromisoformat(record.updated_at).timestamp()
                if record_time < cutoff:
                    to_remove.append(task_id)

        for task_id in to_remove:
            del registry[task_id]

        self._save(registry)
        return len(to_remove)
```

### 3.2 Capability Detection

**Problem**: AI reviewers flagged unverified assumptions about CLI flags.

**Solution**: Detect capabilities on initialization, fail fast if critical features missing.

```python
# src/prd/squad_capabilities.py
"""
Claude Squad capability detection.

Addresses AI review concern: "Assumptions about Claude Squad features
(e.g., --prompt-file, JSON output for list) are unverified"
"""

import subprocess
import json
import re
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class SquadCapabilities:
    """Detected Claude Squad capabilities."""
    installed: bool = False
    version: Optional[str] = None

    # Command support
    supports_new: bool = False
    supports_list: bool = False
    supports_status: bool = False
    supports_attach: bool = False
    supports_kill: bool = False

    # Flag support
    supports_prompt_file: bool = False
    supports_branch: bool = False
    supports_dir: bool = False
    supports_autoyes: bool = False
    supports_json_output: bool = False

    # Overall
    is_compatible: bool = False
    compatibility_issues: list[str] = None

    def __post_init__(self):
        if self.compatibility_issues is None:
            self.compatibility_issues = []


class CapabilityDetector:
    """
    Detect Claude Squad capabilities by probing the CLI.

    Strategy:
    1. Check if installed via --version
    2. Parse --help output for supported commands/flags
    3. Validate minimum required capabilities
    """

    REQUIRED_COMMANDS = {"new", "list", "attach"}
    REQUIRED_FLAGS = {"--name", "--dir"}
    MIN_VERSION = "0.5.0"  # Hypothetical minimum

    def __init__(self, claude_squad_path: str = "claude-squad"):
        self.path = claude_squad_path

    def detect(self) -> SquadCapabilities:
        """Run full capability detection."""
        caps = SquadCapabilities()

        # Check installation
        version_result = self._run(["--version"])
        if version_result is None:
            caps.compatibility_issues.append("claude-squad not installed or not in PATH")
            return caps

        caps.installed = True
        caps.version = self._parse_version(version_result)

        # Check version compatibility
        if caps.version and not self._version_gte(caps.version, self.MIN_VERSION):
            caps.compatibility_issues.append(
                f"Version {caps.version} < {self.MIN_VERSION} (minimum required)"
            )

        # Parse main help
        help_result = self._run(["--help"])
        if help_result:
            caps.supports_new = "new" in help_result
            caps.supports_list = "list" in help_result
            caps.supports_status = "status" in help_result
            caps.supports_attach = "attach" in help_result
            caps.supports_kill = "kill" in help_result or "stop" in help_result

        # Parse 'new' command help for flags
        new_help = self._run(["new", "--help"])
        if new_help:
            caps.supports_prompt_file = "--prompt-file" in new_help or "--prompt" in new_help
            caps.supports_branch = "--branch" in new_help
            caps.supports_dir = "--dir" in new_help or "--directory" in new_help
            caps.supports_autoyes = "--autoyes" in new_help or "-y" in new_help

        # Check if list supports JSON
        list_help = self._run(["list", "--help"])
        if list_help:
            caps.supports_json_output = "--json" in list_help

        # Validate required capabilities
        missing_commands = self.REQUIRED_COMMANDS - {
            cmd for cmd, supported in [
                ("new", caps.supports_new),
                ("list", caps.supports_list),
                ("attach", caps.supports_attach),
            ] if supported
        }

        if missing_commands:
            caps.compatibility_issues.append(
                f"Missing required commands: {missing_commands}"
            )

        if not caps.supports_dir:
            caps.compatibility_issues.append(
                "Missing required flag: --dir for 'new' command"
            )

        # Overall compatibility
        caps.is_compatible = len(caps.compatibility_issues) == 0

        return caps

    def _run(self, args: list[str]) -> Optional[str]:
        """Run claude-squad command and return output."""
        try:
            result = subprocess.run(
                [self.path] + args,
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout + result.stderr
        except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
            return None

    def _parse_version(self, output: str) -> Optional[str]:
        """Extract version number from --version output."""
        # Match patterns like "v1.2.3", "1.2.3", "claude-squad 1.2.3"
        match = re.search(r"v?(\d+\.\d+\.\d+)", output)
        return match.group(1) if match else None

    def _version_gte(self, version: str, minimum: str) -> bool:
        """Check if version >= minimum."""
        def parse(v):
            return tuple(int(x) for x in v.split("."))
        try:
            return parse(version) >= parse(minimum)
        except ValueError:
            return False
```

### 3.3 Claude Squad Adapter (Revised)

**Problem**: Original adapter lacked error handling, parsing robustness, and lifecycle management.

**Solution**: Comprehensive adapter with all concerns addressed.

```python
# src/prd/squad_adapter.py
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
import shlex
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

        return self.registry.get(task_id).status

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
        for record in self.registry._load().values():
            if record.status == "orphaned":
                self.registry.update_status(record.task_id, "terminated")
                cleaned += 1

        return cleaned
```

### 3.4 Hybrid Backend Selector

**Problem**: AI reviewers noted "significant feature regression: loss of remote execution."

**Solution**: Retain GitHub Actions backend for batch/remote work.

```python
# src/prd/backend_selector.py
"""
Backend selector for hybrid local/remote execution.

Addresses AI concern: "Consider retaining one remote backend for
non-interactive tasks"
"""

from enum import Enum
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    """Execution mode for PRD tasks."""
    INTERACTIVE = "interactive"  # Claude Squad - user interacts
    BATCH = "batch"              # GitHub Actions - fire and forget
    MANUAL = "manual"            # Generate prompts only


class BackendSelector:
    """
    Select appropriate backend based on task requirements.

    Strategy:
    - Interactive tasks (need user input) → Claude Squad
    - Batch tasks (can run unattended) → GitHub Actions
    - No backend available → Manual (prompts only)
    """

    def __init__(
        self,
        working_dir: Path,
        squad_available: bool = False,
        gha_available: bool = False
    ):
        self.working_dir = working_dir
        self.squad_available = squad_available
        self.gha_available = gha_available

    def select(
        self,
        task_count: int,
        interactive: bool = True,
        prefer_remote: bool = False
    ) -> ExecutionMode:
        """
        Select backend for given parameters.

        Args:
            task_count: Number of tasks to execute
            interactive: Whether user interaction is needed
            prefer_remote: Prefer remote execution if available
        """
        if interactive and self.squad_available:
            return ExecutionMode.INTERACTIVE

        if prefer_remote and self.gha_available:
            return ExecutionMode.BATCH

        if not interactive and self.gha_available:
            return ExecutionMode.BATCH

        if self.squad_available:
            return ExecutionMode.INTERACTIVE

        logger.warning("No execution backend available, falling back to manual")
        return ExecutionMode.MANUAL
```

## 4. CLI Commands

```bash
# Check Claude Squad compatibility
orchestrator prd check-squad
# Output: Claude Squad v1.2.3 detected
#         Capabilities: prompt_file=✓, json=✓, branch=✓
#         Status: Compatible

# Spawn interactive sessions
orchestrator prd spawn [--count N] [--mode interactive|batch]

# List active sessions
orchestrator prd sessions
# Output:
#   TASK             SESSION              STATUS    AGE
#   auth-login       wfo-auth-login       running   5m
#   auth-logout      wfo-auth-logout      running   3m

# Attach to session
orchestrator prd attach <task-id>

# Mark complete (terminates session)
orchestrator prd done <task-id> [--keep-session]

# Cleanup orphaned sessions
orchestrator prd cleanup

# Status overview
orchestrator prd status
```

## 5. What Gets Decommissioned

### Removed Files

| File | Reason |
|------|--------|
| `src/prd/worker_pool.py` | Replaced by BackendSelector + adapters |
| `src/prd/backends/local.py` | Subprocess spawning → Claude Squad |
| `src/prd/backends/modal_worker.py` | Cloud spawning not needed |
| `src/prd/backends/render.py` | Cloud spawning not needed |
| `src/prd/backends/sequential.py` | Claude Squad handles this |

### Retained (Simplified)

| File | Changes |
|------|---------|
| `src/prd/backends/github_actions.py` | Retained for batch/remote |
| `src/prd/backends/manual.py` | Retained as fallback |
| `src/prd/executor.py` | Simplified - uses new adapters |
| `src/prd/integration.py` | Unchanged - merge coordination |
| `src/prd/wave_resolver.py` | Unchanged - conflict resolution |
| `src/prd/schema.py` | Minor additions for sessions |

### New Files

| File | Purpose |
|------|---------|
| `src/prd/squad_adapter.py` | Claude Squad integration |
| `src/prd/squad_capabilities.py` | Capability detection |
| `src/prd/session_registry.py` | Persistent state |
| `src/prd/backend_selector.py` | Hybrid mode selection |

## 6. Migration Path

### Phase 1: Add New Components
1. Implement session_registry.py
2. Implement squad_capabilities.py
3. Implement squad_adapter.py
4. Add CLI commands

### Phase 2: Integration
1. Add backend_selector.py
2. Update executor.py to use new adapters
3. Add `orchestrator prd spawn` command
4. Test with real Claude Squad

### Phase 3: Cleanup
1. Deprecate worker_pool.py
2. Remove Modal, Render, Local backends
3. Update documentation
4. Update roadmap

## 7. Testing Strategy

### Unit Tests
- SessionRegistry persistence
- Capability detection parsing
- Session name sanitization
- Idempotency checks

### Integration Tests
- Mock Claude Squad CLI
- Full spawn → attach → complete flow
- Reconciliation after restart

### Manual Testing
- Install Claude Squad
- Run 5-task batch
- Attach/detach sessions
- Verify merge coordination

## 8. Risks and Mitigations (Updated)

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Claude Squad CLI changes | Medium | High | Version pinning, capability detection |
| tmux not available | Low | Medium | Clear error message, manual fallback |
| Session state desync | Medium | Medium | Reconciliation on every operation |
| Machine reboot mid-task | Low | High | Persistent registry, orphan detection |
| Session name collision | Low | Low | Prefix + sanitization |

## 9. Success Criteria

1. [ ] Claude Squad spawns 10 tasks with one command
2. [ ] Sessions survive orchestrator restart
3. [ ] Orphaned sessions detected and reported
4. [ ] Completed work merges via wave resolver
5. [ ] 5 backend files removed
6. [ ] No functional regression for merge coordination
7. [ ] Clear error if Claude Squad not installed
