# PRD-004: TmuxAdapter Test Cases

## Unit Tests: TmuxAdapter

### test_tmux_adapter.py

| Test | Description | Mocks |
|------|-------------|-------|
| `test_spawn_agent_creates_session` | Spawns agent, verifies tmux commands called | subprocess.run |
| `test_spawn_agent_creates_window` | Verifies new-window command for each task | subprocess.run |
| `test_spawn_agent_sends_claude_command` | Verifies send-keys with correct prompt | subprocess.run |
| `test_spawn_agent_registers_in_registry` | Session saved to SessionRegistry | subprocess.run |
| `test_spawn_agent_reuses_existing_session` | Second spawn uses existing tmux session | subprocess.run |
| `test_list_agents_parses_tmux_output` | Parses `tmux list-windows` output | subprocess.run |
| `test_list_agents_empty_session` | Handles no windows gracefully | subprocess.run |
| `test_capture_output_returns_pane_content` | Gets output via capture-pane | subprocess.run |
| `test_kill_agent_removes_window` | Calls kill-window for task | subprocess.run |
| `test_cleanup_kills_entire_session` | Calls kill-session | subprocess.run |
| `test_attach_execs_tmux` | Verifies os.execvp called | os.execvp |
| `test_happy_integration_uses_custom_binary` | Uses CLAUDE_BINARY env | subprocess.run |
| `test_session_name_sanitization` | Special chars in task_id handled | - |
| `test_tmux_not_available_raises` | Error when tmux missing | shutil.which |

## Unit Tests: SubprocessAdapter

### test_subprocess_adapter.py

| Test | Description | Mocks |
|------|-------------|-------|
| `test_spawn_agent_starts_process` | subprocess.Popen called | subprocess.Popen |
| `test_spawn_agent_creates_log_file` | Log file created at expected path | subprocess.Popen |
| `test_spawn_agent_registers_pid` | PID saved in SessionRegistry | subprocess.Popen |
| `test_list_agents_returns_active` | Lists processes from registry | - |
| `test_capture_output_reads_log` | Returns content from log file | - |
| `test_kill_agent_terminates_process` | Sends SIGTERM to PID | os.kill |
| `test_kill_agent_handles_already_dead` | No error if process gone | os.kill |

## Unit Tests: BackendSelector

### test_backend_selector.py

| Test | Description |
|------|-------------|
| `test_detect_tmux_available` | Returns INTERACTIVE when tmux found |
| `test_detect_tmux_unavailable` | Falls back to SUBPROCESS |
| `test_detect_gha_available` | Returns BATCH when GHA configured |
| `test_select_prefers_interactive` | INTERACTIVE over SUBPROCESS |
| `test_select_respects_prefer_remote` | BATCH when prefer_remote=True |
| `test_get_available_modes` | Lists all detected modes |

## Integration Tests

### test_integration_tmux.py

| Test | Conditions | Description |
|------|------------|-------------|
| `test_spawn_real_agent` | Requires tmux | Actually creates tmux session |
| `test_list_real_sessions` | Requires tmux | Lists real windows |
| `test_capture_real_output` | Requires tmux | Captures real pane content |
| `test_cleanup_real_sessions` | Requires tmux | Cleans up test sessions |

## Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| Task ID with spaces | Sanitized to dashes |
| Task ID with unicode | Sanitized to ASCII |
| Very long task ID | Truncated to 50 chars |
| Empty prompt | Still spawns (empty file) |
| Working dir doesn't exist | Creates .wfo_prompt dir |
| Multiple spawn same task | Idempotent - returns existing |
| Kill non-existent task | No error, logs warning |
| Attach to completed task | Error with helpful message |
