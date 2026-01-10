# PRD-004: Replace Claude Squad with Direct tmux Management

## Summary

Replace the broken `squad_adapter.py` (which expects non-existent Claude Squad CLI commands) with a `TmuxAdapter` that manages tmux sessions directly. Include subprocess fallback for non-tmux environments.

## Background

The current `ClaudeSquadAdapter` expects commands like:
- `claude-squad new --name X --dir Y --prompt-file Z`
- `claude-squad list --json`
- `claude-squad attach <session>`

But Claude Squad (`cs`) is a **TUI** - it has no CLI interface. This makes the entire spawning subsystem non-functional.

**Validation:** Prototype testing confirmed direct tmux management works with `claude --print`.

## Implementation Plan

### Phase 1: Create TmuxAdapter

**File:** `src/prd/tmux_adapter.py`

```python
class TmuxAdapter:
    """Direct tmux management for parallel Claude Code agents."""

    def spawn_agent(task_id, prompt, working_dir, branch) -> SessionRecord
    def list_agents() -> List[SessionRecord]
    def attach(task_id) -> None  # replaces current process
    def capture_output(task_id, lines=100) -> str
    def kill_agent(task_id) -> None
    def cleanup() -> None  # kill entire session
```

Key implementation details:
- Session name: `wfo-main` (workflow-orchestrator main session)
- Window names: `task-{task_id}`
- Uses `tmux send-keys` to run `claude --print < prompt_file`
- Reuses existing `SessionRegistry` for persistence
- Supports `get_claude_binary()` for Happy integration

### Phase 2: Create SubprocessFallback

**File:** `src/prd/subprocess_adapter.py`

```python
class SubprocessAdapter:
    """Fallback when tmux not available."""

    def spawn_agent(task_id, prompt, working_dir, branch) -> SessionRecord
    def list_agents() -> List[SessionRecord]
    def capture_output(task_id) -> str  # from log file
    def kill_agent(task_id) -> None
```

- Fire-and-forget subprocess spawning
- Logs to `.wfo_log_{task_id}.txt`
- No attach capability (limitation of fallback)

### Phase 3: Update BackendSelector

**File:** `src/prd/backend_selector.py`

Add new execution mode and detection:
```python
class ExecutionMode(Enum):
    INTERACTIVE = "interactive"  # TmuxAdapter
    BATCH = "batch"              # GitHub Actions
    SUBPROCESS = "subprocess"    # SubprocessAdapter fallback
    MANUAL = "manual"            # Generate prompts only
```

Detection priority:
1. tmux available → `TmuxAdapter`
2. GitHub Actions available → `GitHubActionsBackend`
3. Neither → `SubprocessAdapter`
4. User override → `MANUAL`

### Phase 4: Update CLI Commands

**File:** `src/cli.py`

Update these functions to use new adapters:
- `cmd_prd_spawn` - Use TmuxAdapter.spawn_agent()
- `cmd_prd_sessions` - Use TmuxAdapter.list_agents()
- `cmd_prd_attach` - Use TmuxAdapter.attach()
- `cmd_prd_done` - Use TmuxAdapter.kill_agent()
- `cmd_prd_cleanup` - Use TmuxAdapter.cleanup()
- `cmd_prd_check_squad` → rename to `cmd_prd_check_backend`

### Phase 5: Deprecate/Remove Old Code

Files to deprecate:
- `src/prd/squad_adapter.py` - Replace with tmux_adapter.py
- `src/prd/squad_capabilities.py` - No longer needed

Keep:
- `src/prd/session_registry.py` - Reuse as-is
- `src/prd/backends/github_actions.py` - Still used for batch mode

### Phase 6: Tests

- Unit tests for TmuxAdapter (mock subprocess calls)
- Unit tests for SubprocessAdapter
- Integration tests (actually spawn tmux sessions)
- Update existing squad_adapter tests

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `src/prd/tmux_adapter.py` | CREATE | New tmux-based adapter |
| `src/prd/subprocess_adapter.py` | CREATE | Fallback adapter |
| `src/prd/backend_selector.py` | MODIFY | Add new modes, detection |
| `src/cli.py` | MODIFY | Update prd commands |
| `src/prd/squad_adapter.py` | DEPRECATE | Mark for removal |
| `src/prd/squad_capabilities.py` | DEPRECATE | Mark for removal |
| `tests/prd/test_tmux_adapter.py` | CREATE | New tests |
| `tests/prd/test_subprocess_adapter.py` | CREATE | New tests |

## Success Criteria

1. `orchestrator prd spawn --count 3` creates 3 tmux windows with Claude agents
2. `orchestrator prd sessions` lists active agents
3. `orchestrator prd attach task-1` attaches to agent window
4. `orchestrator prd done task-1` terminates agent
5. Fallback to subprocess when tmux unavailable
6. Happy integration works (`CLAUDE_BINARY=happy`)
7. All existing tests pass (or are updated)
