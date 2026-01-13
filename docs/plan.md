# CORE-025 Phase 3: Session Management CLI - Implementation Plan

## Overview

Add CLI commands for workflow session management using the `orchestrator workflow` subcommand group.

**Naming Decision:** Use `orchestrator workflow` instead of `orchestrator sessions` to avoid conflict with existing `sessions` command (CORE-024) which manages session transcripts.

## Commands to Implement

### 1. `orchestrator workflow list`
List all workflow sessions in current repository.

**Output Format:**
```
Workflow Sessions in /path/to/repo:
  * b02f0302 (current) - Task: "Implement CORE-025" - Status: active - 2h ago
    5b4293b1           - Task: "Fix login bug"     - Status: completed - 3d ago
    67c18990           - Task: "Add tests"         - Status: abandoned - 1w ago
```

**Implementation:**
- Use `SessionManager.list_sessions()` to get session IDs
- Use `SessionManager.get_session_info()` for each to get metadata
- Read state.json from each session to get task/status
- Format with current session marked with `*`
- Show relative timestamps (2h ago, 3d ago, etc.)

### 2. `orchestrator workflow switch <id>`
Switch to a different workflow session.

**Output Format:**
```
Switched to session 5b4293b1
```

**Implementation:**
- Use `SessionManager.set_current_session(session_id)` (already validates existence)
- Print confirmation message

### 3. `orchestrator workflow info [id]`
Show detailed information about a session.

**Output Format:**
```
Session: b02f0302 (current)
Task: Implement CORE-025 Phase 3
Created: 2026-01-13 10:30:00
Status: active
Phase: EXECUTE (3/5)
Items: 4/8 completed
```

**Implementation:**
- If no ID provided, use current session
- Read session meta.json for creation time
- Read state.json for task, status, phase, progress
- Format as readable output

### 4. `orchestrator workflow cleanup`
Remove old/abandoned sessions.

**Flags:**
- `--older-than <days>` - Remove sessions older than N days (default: 30)
- `--status <status>` - Only remove sessions with this status (e.g., "abandoned", "completed")
- `--dry-run` - Show what would be removed without removing
- `--yes` - Skip confirmation prompt

**Output Format:**
```
Found 3 sessions to remove:
  67c18990 - abandoned - 45d old
  abc12345 - completed - 60d old
  def67890 - abandoned - 90d old

Remove these sessions? [y/N]: y
Removed 3 sessions.
```

**Implementation:**
- Iterate sessions, filter by age and/or status
- Show preview, prompt for confirmation (unless --yes)
- Use `SessionManager.delete_session()` for each

## Files to Modify

### 1. `src/cli.py`
Add new subcommand group and handlers:

```python
# Add workflow subcommand group (after prd_parser)
workflow_parser = subparsers.add_parser('workflow', help='Manage workflow sessions (CORE-025)')
workflow_subparsers = workflow_parser.add_subparsers(dest='workflow_command', help='Workflow session commands')

# workflow list
workflow_list = workflow_subparsers.add_parser('list', help='List all workflow sessions')
workflow_list.add_argument('-d', '--dir', help='Working directory')
workflow_list.set_defaults(func=cmd_workflow_list)

# workflow switch
workflow_switch = workflow_subparsers.add_parser('switch', help='Switch to a different session')
workflow_switch.add_argument('session_id', help='Session ID to switch to')
workflow_switch.add_argument('-d', '--dir', help='Working directory')
workflow_switch.set_defaults(func=cmd_workflow_switch)

# workflow info
workflow_info = workflow_subparsers.add_parser('info', help='Show session details')
workflow_info.add_argument('session_id', nargs='?', help='Session ID (default: current)')
workflow_info.add_argument('-d', '--dir', help='Working directory')
workflow_info.set_defaults(func=cmd_workflow_info)

# workflow cleanup
workflow_cleanup = workflow_subparsers.add_parser('cleanup', help='Remove old sessions')
workflow_cleanup.add_argument('--older-than', type=int, default=30, help='Days threshold (default: 30)')
workflow_cleanup.add_argument('--status', choices=['abandoned', 'completed', 'all'], help='Filter by status')
workflow_cleanup.add_argument('--dry-run', action='store_true', help='Show what would be removed')
workflow_cleanup.add_argument('--yes', '-y', action='store_true', help='Skip confirmation')
workflow_cleanup.add_argument('-d', '--dir', help='Working directory')
workflow_cleanup.set_defaults(func=cmd_workflow_cleanup)
```

Add command handler functions:
- `cmd_workflow_list(args)`
- `cmd_workflow_switch(args)`
- `cmd_workflow_info(args)`
- `cmd_workflow_cleanup(args)`

### 2. `src/session_manager.py`
May need minor enhancements:
- Add method to get session status from state.json (or keep in CLI)
- Session age calculation helper

### 3. `tests/test_session_cli.py` (new file)
Test all four commands with various scenarios.

## Implementation Order

1. Add parser and subparsers for `workflow` command group
2. Implement `cmd_workflow_list` - most complex, handles output formatting
3. Implement `cmd_workflow_switch` - simplest, just calls SessionManager
4. Implement `cmd_workflow_info` - reads and formats session data
5. Implement `cmd_workflow_cleanup` - handles filtering and confirmation
6. Add tests for all commands
7. Update CLAUDE.md documentation
8. Update ROADMAP.md to mark Phase 3 complete

## Dependencies

- `OrchestratorPaths` (src/path_resolver.py) - already exists
- `SessionManager` (src/session_manager.py) - already exists
- Existing CLI patterns in src/cli.py

## Definition of Done

- [ ] `orchestrator workflow list` shows all sessions with current marked
- [ ] `orchestrator workflow switch <id>` updates current pointer
- [ ] `orchestrator workflow info` shows session details
- [ ] `orchestrator workflow cleanup` removes old sessions with confirmation
- [ ] Tests pass in tests/test_session_cli.py
- [ ] CLAUDE.md updated with workflow session commands
- [ ] ROADMAP.md updated to mark Phase 3 complete
