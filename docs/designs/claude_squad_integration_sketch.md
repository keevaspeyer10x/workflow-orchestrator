# Claude Squad Integration - Architecture Sketch

## Overview

This document outlines the integration between the Workflow Orchestrator and [Claude Squad](https://github.com/smtg-ai/claude-squad), a tmux-based tool for managing multiple Claude Code terminal sessions.

## Goals

1. **Delegate spawning complexity** - Let Claude Squad handle terminal/session management
2. **Keep orchestrator focused** - Task tracking, prompt generation, merge coordination
3. **Enable interactive multi-agent work** - User can interact with each agent individually
4. **Simplify codebase** - Remove our custom spawning backends (Modal, Render, Local subprocess)

## Current State (What We're Replacing)

```
┌─────────────────────────────────────────────────────────┐
│                  Current PRD Executor                    │
├─────────────────────────────────────────────────────────┤
│  WorkerPool                                              │
│    ├── LocalBackend (subprocess.Popen)                  │
│    ├── ModalBackend (modal.Function)                    │
│    ├── RenderBackend (render API)                       │
│    ├── GitHubActionsBackend (workflow dispatch)         │
│    └── SequentialBackend (fallback)                     │
├─────────────────────────────────────────────────────────┤
│  Problems:                                               │
│  - Can't interact with spawned agents                   │
│  - No visibility into agent progress                    │
│  - Complex backend code to maintain                     │
│  - Fire-and-forget model doesn't match user needs       │
└─────────────────────────────────────────────────────────┘
```

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Workflow Orchestrator                   │
├─────────────────────────────────────────────────────────┤
│  PRD Coordinator (simplified)                            │
│    ├── Task tracking (existing schema)                  │
│    ├── Prompt generation (existing)                     │
│    ├── Branch/merge coordination (existing)             │
│    └── NEW: Claude Squad adapter                        │
└──────────────────────┬──────────────────────────────────┘
                       │
                       │ subprocess calls
                       ▼
┌─────────────────────────────────────────────────────────┐
│                    Claude Squad                          │
├─────────────────────────────────────────────────────────┤
│  - tmux session management                              │
│  - Terminal pane creation/switching                     │
│  - Claude Code process lifecycle                        │
│  - User can attach/detach to any session                │
└─────────────────────────────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    ┌─────────┐   ┌─────────┐   ┌─────────┐
    │ Claude  │   │ Claude  │   │ Claude  │
    │ task-1  │   │ task-2  │   │ task-3  │
    └─────────┘   └─────────┘   └─────────┘
```

## Integration Layer Design

### New Module: `src/prd/squad_adapter.py`

```python
"""
Claude Squad Adapter

Thin integration layer between orchestrator and Claude Squad.
Delegates all terminal/process management to Claude Squad.
"""

import subprocess
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

@dataclass
class SquadSession:
    """Represents a Claude Squad session."""
    session_id: str
    task_id: str
    branch: str
    status: str  # "running", "paused", "completed"

@dataclass
class SquadConfig:
    """Configuration for Claude Squad integration."""
    claude_squad_path: str = "claude-squad"  # Assumes in PATH
    auto_yes: bool = True  # --autoyes flag
    worktree_base: Optional[Path] = None


class ClaudeSquadAdapter:
    """
    Adapter for Claude Squad integration.

    Responsibilities:
    - Spawn new Claude Squad sessions with task prompts
    - Track session <-> task mapping
    - Query session status
    - NOT responsible for: terminal management, process lifecycle
    """

    def __init__(self, config: SquadConfig = None):
        self.config = config or SquadConfig()
        self._sessions: dict[str, SquadSession] = {}
        self._verify_installation()

    def _verify_installation(self) -> bool:
        """Check that claude-squad is installed."""
        try:
            result = subprocess.run(
                [self.config.claude_squad_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def spawn_session(
        self,
        task_id: str,
        prompt: str,
        branch: str,
        working_dir: Path
    ) -> SquadSession:
        """
        Spawn a new Claude Squad session for a task.

        Args:
            task_id: Unique task identifier
            prompt: The prompt to pass to Claude
            branch: Git branch for this task
            working_dir: Directory to run in

        Returns:
            SquadSession with session details
        """
        session_name = f"task-{task_id}"

        cmd = [
            self.config.claude_squad_path,
            "new",
            "--name", session_name,
            "--dir", str(working_dir),
            "--branch", branch,
        ]

        if self.config.auto_yes:
            cmd.append("--autoyes")

        # Pass prompt via stdin or temp file
        prompt_file = working_dir / ".claude" / f"prompt_{task_id}.md"
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(prompt)

        cmd.extend(["--prompt-file", str(prompt_file)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=working_dir
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to spawn session: {result.stderr}")

        # Parse session ID from output
        session_id = self._parse_session_id(result.stdout)

        session = SquadSession(
            session_id=session_id,
            task_id=task_id,
            branch=branch,
            status="running"
        )

        self._sessions[task_id] = session
        return session

    def spawn_batch(
        self,
        tasks: List[dict],  # [{task_id, prompt, branch}, ...]
        working_dir: Path
    ) -> List[SquadSession]:
        """
        Spawn multiple sessions for a batch of tasks.

        This is the main entry point for "spawn next 10 tasks".
        """
        sessions = []
        for task in tasks:
            session = self.spawn_session(
                task_id=task["task_id"],
                prompt=task["prompt"],
                branch=task["branch"],
                working_dir=working_dir
            )
            sessions.append(session)
        return sessions

    def get_session_status(self, task_id: str) -> Optional[str]:
        """Get the status of a session by task ID."""
        if task_id not in self._sessions:
            return None

        session = self._sessions[task_id]

        # Query Claude Squad for current status
        result = subprocess.run(
            [self.config.claude_squad_path, "status", session.session_id],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            session.status = self._parse_status(result.stdout)

        return session.status

    def list_sessions(self) -> List[SquadSession]:
        """List all active sessions."""
        # Sync with Claude Squad's actual state
        result = subprocess.run(
            [self.config.claude_squad_path, "list", "--json"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            squad_sessions = json.loads(result.stdout)
            # Update our mapping
            for squad_session in squad_sessions:
                if squad_session["name"].startswith("task-"):
                    task_id = squad_session["name"][5:]  # Remove "task-" prefix
                    if task_id in self._sessions:
                        self._sessions[task_id].status = squad_session["status"]

        return list(self._sessions.values())

    def attach_to_session(self, task_id: str) -> None:
        """
        Attach user's terminal to a session.

        This hands control to Claude Squad - user interacts directly.
        """
        if task_id not in self._sessions:
            raise ValueError(f"No session for task {task_id}")

        session = self._sessions[task_id]

        # This replaces current process with tmux attach
        subprocess.run(
            [self.config.claude_squad_path, "attach", session.session_id],
        )

    def _parse_session_id(self, output: str) -> str:
        """Parse session ID from claude-squad output."""
        # Implementation depends on claude-squad output format
        # Placeholder - would parse actual output
        for line in output.split("\n"):
            if "session:" in line.lower() or "id:" in line.lower():
                return line.split(":")[-1].strip()
        return output.strip().split()[-1]

    def _parse_status(self, output: str) -> str:
        """Parse status from claude-squad status output."""
        output_lower = output.lower()
        if "running" in output_lower:
            return "running"
        elif "completed" in output_lower or "done" in output_lower:
            return "completed"
        elif "paused" in output_lower:
            return "paused"
        return "unknown"
```

### CLI Commands

```bash
# Spawn sessions for ready tasks
orchestrator prd spawn [--count 10] [--backend squad]

# List active sessions
orchestrator prd sessions

# Attach to a specific task's session
orchestrator prd attach <task-id>

# Check status of all sessions
orchestrator prd status

# Mark task complete (after user finishes in session)
orchestrator prd done <task-id>

# Merge all completed work
orchestrator prd merge
```

### Workflow Example

```bash
# 1. Load a PRD
$ orchestrator prd load roadmap.yaml
Loaded PRD with 15 tasks

# 2. Spawn sessions for first 5 ready tasks
$ orchestrator prd spawn --count 5
Spawning 5 Claude Squad sessions...
  task-auth-login     → session cs_abc123 (running)
  task-auth-logout    → session cs_def456 (running)
  task-api-users      → session cs_ghi789 (running)
  task-api-products   → session cs_jkl012 (running)
  task-ui-dashboard   → session cs_mno345 (running)

# 3. User attaches to work on a task
$ orchestrator prd attach task-auth-login
# ... user is now in tmux session with Claude ...
# ... user works interactively until feature is done ...
# ... user detaches with Ctrl-B D ...

# 4. Mark task complete
$ orchestrator prd done task-auth-login
Task task-auth-login marked complete
Branch: claude/auth-login-abc123

# 5. Check overall status
$ orchestrator prd status
PRD: roadmap.yaml
Progress: 1/15 complete

Sessions:
  task-auth-login   ✓ completed
  task-auth-logout    running (session cs_def456)
  task-api-users      running (session cs_ghi789)
  ...

# 6. When multiple tasks complete, merge
$ orchestrator prd merge
Merging 3 completed tasks...
Wave 1: task-auth-login, task-auth-logout (no conflicts)
Wave 2: task-api-users (resolved 1 conflict)
All work merged to integration branch.
```

## What Gets Removed

After this integration, we can deprecate/remove:

```
src/prd/
├── worker_pool.py          # REMOVE - replaced by squad_adapter
├── backends/
│   ├── local.py            # REMOVE - subprocess spawning
│   ├── modal_worker.py     # REMOVE - cloud spawning
│   ├── render.py           # REMOVE - cloud spawning
│   ├── github_actions.py   # REMOVE - CI spawning
│   └── sequential.py       # REMOVE - fallback
├── executor.py             # SIMPLIFY - remove auto-orchestration loop
```

**Keep:**
- `schema.py` - Task/PRD data structures
- `queue.py` - Job tracking (simplified)
- `integration.py` - Branch management, merging
- `wave_resolver.py` - Conflict resolution

## Key Design Decisions

### 1. Thin Adapter, Not Deep Integration

The adapter is intentionally thin - it just calls claude-squad CLI commands. This means:
- Less code to maintain
- Claude Squad can evolve independently
- Easy to swap for different tools later

### 2. User Controls Session Lifecycle

Unlike our current spawner, the user decides when a task is "done":
- Attach to session, work until satisfied
- Explicitly mark complete
- Orchestrator doesn't try to detect completion automatically

### 3. Prompt Files, Not Inline

Prompts are written to `.claude/prompt_<task_id>.md` files:
- Claude can reference them during session
- Easy to inspect/modify
- Survives session restarts

### 4. Branch Per Task

Each task gets its own branch (`claude/<task-id>-<session>`):
- Clean separation of work
- Standard git workflow
- Wave resolver handles merges

## Open Questions

1. **Claude Squad API stability** - Is the CLI interface stable enough to depend on?
2. **Session persistence** - What happens if machine reboots mid-task?
3. **Remote execution** - Can Claude Squad sessions run on remote machines?
4. **Prompt passing** - Does claude-squad support `--prompt-file` or similar?

## Risks

| Risk | Mitigation |
|------|------------|
| Claude Squad changes CLI interface | Pin to specific version, wrap with adapter |
| tmux not available on all platforms | Document requirement, provide fallback guidance |
| Session state desync | Always query claude-squad for truth, don't cache heavily |
| User forgets to mark complete | Add session age warnings, optional auto-detection |

## Success Criteria

1. User can spawn 10 task sessions with one command
2. User can attach/detach to any session interactively
3. Completed work merges cleanly via wave resolver
4. Codebase is simpler (removed 5+ backend files)
5. No loss of functionality users actually need
