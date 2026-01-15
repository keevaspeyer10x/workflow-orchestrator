# CORE-025 Phase 3: Session Management CLI Commands

## Context

CORE-025 implements multi-repo containment with session-based state management. Phases 1-2b are complete:

- **Phase 1** (458d302): PathResolver and SessionManager classes created
- **Phase 2** (a142e98): WorkflowEngine integration - CLI creates sessions on `orchestrator start`
- **Phase 2b** (f52cf7a): Migration complete - all repos now use `.orchestrator/sessions/<id>/`

The infrastructure is in place. Now we need CLI commands to let users interact with sessions.

## Task

Implement CLI commands for session management:

### Required Commands

1. **`orchestrator sessions list`** - List all sessions in current repo
   ```bash
   orchestrator sessions list
   # Output:
   # Sessions in /path/to/repo:
   #   * b02f0302 (current) - Task: "Implement CORE-025" - Status: active - 2h ago
   #     5b4293b1           - Task: "Fix login bug"     - Status: completed - 3d ago
   #     67c18990           - Task: "Add tests"         - Status: abandoned - 1w ago
   ```

2. **`orchestrator sessions switch <id>`** - Switch to a different session
   ```bash
   orchestrator sessions switch 5b4293b1
   # Output: Switched to session 5b4293b1
   ```

3. **`orchestrator sessions info [id]`** - Show details about a session
   ```bash
   orchestrator sessions info
   # Output: (detailed info about current session)
   ```

4. **`orchestrator sessions cleanup`** - Remove old/abandoned sessions
   ```bash
   orchestrator sessions cleanup --older-than 30d
   orchestrator sessions cleanup --status abandoned
   ```

### Implementation Files

- **`src/cli.py`**: Add new subcommand group `sessions` with list/switch/info/cleanup
- **`src/session_manager.py`**: SessionManager class already exists at `src/session_manager.py`
- **`src/path_resolver.py`**: OrchestratorPaths class already exists at `src/path_resolver.py`

### Key Classes (already exist)

```python
# src/path_resolver.py
class OrchestratorPaths:
    def __init__(self, base_dir: Path, session_id: Optional[str] = None)
    def orchestrator_dir(self) -> Path  # .orchestrator/
    def sessions_dir(self) -> Path      # .orchestrator/sessions/
    def session_dir(self) -> Path       # .orchestrator/sessions/<id>/
    def state_file(self) -> Path        # .orchestrator/sessions/<id>/state.json
    def log_file(self) -> Path          # .orchestrator/sessions/<id>/log.jsonl

# src/session_manager.py
class SessionManager:
    def __init__(self, paths: OrchestratorPaths)
    def create_session(self) -> str           # Creates new session, returns ID
    def get_current_session(self) -> Optional[str]  # Reads .orchestrator/current
    def list_sessions(self) -> List[str]      # Lists session IDs
    def get_session_info(self, session_id: str) -> Optional[dict]  # Session metadata
    def switch_session(self, session_id: str) -> bool  # Updates current pointer
```

### Test Requirements

Add tests in `tests/test_session_cli.py`:
- Test `sessions list` with 0, 1, multiple sessions
- Test `sessions switch` to valid/invalid session
- Test `sessions info` output format
- Test `sessions cleanup` removes correct sessions

### ROADMAP Tasks to Complete

From ROADMAP.md:
- [ ] Add `--workflow` flag to all orchestrator commands (optional, lower priority)
- [ ] Add workflow selection/switching UX
- [ ] Add `orchestrator workflows list` command → now `orchestrator sessions list`
- [ ] Update CLAUDE.md with multi-workflow usage

## Constraints

1. Use existing SessionManager - don't reinvent
2. Follow existing CLI patterns in src/cli.py (argparse subcommands)
3. Keep output concise and scannable
4. Handle edge cases (no sessions, invalid ID, etc.)

## Definition of Done

- [ ] `orchestrator sessions list` works and shows current session
- [ ] `orchestrator sessions switch <id>` updates current pointer
- [ ] `orchestrator sessions info` shows session details
- [ ] `orchestrator sessions cleanup` removes old sessions (with confirmation)
- [ ] Tests pass
- [ ] CLAUDE.md updated with session commands
- [ ] ROADMAP.md updated to mark Phase 3 complete
