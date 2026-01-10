# Test Cases: Multi-Model Review Fixes

## Automated Tests

### API Key Check (check_review_api_keys)
1. **No keys set** → Should warn with full message
2. **One key set** → Should NOT warn (at least one method available)
3. **All keys set** → Should NOT warn
4. **Empty string key** → Should treat as missing

## Manual Verification

### Test File in Git
- `git status` should show test file staged

### default_test Bug
- Run `orchestrator start` with Python project
- Mismatch warning should say "npm test" not "npm run build"

### sops Command Syntax
- Copy suggested command and verify it's valid bash
- Should not have spaces around `=`

### Skip Summary with item_id
- Create workflow, skip an item, run `orchestrator finish`
- Should show `item_id: description` format

### Gate Bypass Highlighting
- Force-skip a gate item, run `orchestrator finish`
- Should show `⚠️ GATE BYPASSED:` prefix

## Existing Test Suite
- Run `pytest tests/` to ensure no regressions

---

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

---

# Parallel Agent Approval System Test Cases

## ApprovalQueue Tests (test_approval_queue.py)

### Basic Operations
| Test | Description |
|------|-------------|
| `test_submit_creates_pending_request` | Submit creates request with PENDING status |
| `test_check_returns_status` | Check returns correct status for request |
| `test_check_returns_none_for_unknown` | Check returns None for unknown ID |
| `test_decide_approves_request` | Decide changes status to APPROVED |
| `test_decide_rejects_request` | Decide changes status to REJECTED |
| `test_consume_marks_consumed` | Consume marks approved request as CONSUMED |
| `test_consume_fails_for_pending` | Cannot consume pending request |
| `test_consume_once_semantics` | Cannot consume same request twice |

### Concurrent Access
| Test | Description |
|------|-------------|
| `test_concurrent_submits` | Multiple agents can submit simultaneously |
| `test_concurrent_reads` | Multiple agents can check status simultaneously |
| `test_wal_mode_enabled` | WAL journal mode is active |

### Maintenance
| Test | Description |
|------|-------------|
| `test_heartbeat_updates_timestamp` | Heartbeat updates last_heartbeat |
| `test_expire_stale_marks_expired` | Stale requests get expired |
| `test_cleanup_removes_old_consumed` | Old consumed requests deleted |
| `test_stats_returns_counts` | Stats returns correct counts by status |

## ApprovalGate Tests (test_approval_gate.py)

### Polling
| Test | Description |
|------|-------------|
| `test_request_approval_submits` | request_approval submits to queue |
| `test_polling_returns_on_approval` | Polling exits when approved |
| `test_polling_returns_on_rejection` | Polling exits when rejected |
| `test_timeout_returns_timeout` | Returns TIMEOUT after timeout period |
| `test_exponential_backoff` | Polling interval increases over time |

### Auto-Approval
| Test | Description |
|------|-------------|
| `test_low_risk_auto_approves` | LOW risk operations auto-approve |
| `test_critical_never_auto_approves` | CRITICAL always requires human |
| `test_phase_affects_risk` | PLAN phase more permissive than EXECUTE |

## CLI Tests

### orchestrator pending
| Test | Description |
|------|-------------|
| `test_pending_shows_waiting_agents` | Shows all pending requests |
| `test_pending_empty_message` | Shows message when no pending |
| `test_pending_shows_wait_time` | Shows how long each has been waiting |

### orchestrator review
| Test | Description |
|------|-------------|
| `test_review_lists_pending` | Shows pending requests for review |
| `test_review_approve_single` | Can approve single request |
| `test_review_reject_single` | Can reject single request |
| `test_review_approve_all` | Can approve all pending |

## Integration Tests
| Test | Description |
|------|-------------|
| `test_full_flow_single_agent` | Agent submits, user approves, agent continues |
| `test_full_flow_parallel_agents` | Multiple agents coordinate correctly |
| `test_tmux_session_integration` | Works with TmuxAdapter sessions |

---

# PRD-005: ApprovalGate + TmuxAdapter Integration Test Cases

## Unit Tests: Enhanced ApprovalGate

### Auto-Approval Logging
| Test | Description |
|------|-------------|
| `test_auto_approval_logs_decision` | Auto-approved requests logged with rationale |
| `test_auto_approval_log_includes_risk` | Log entry includes risk level explanation |
| `test_get_decision_log_returns_all` | Decision log includes human + auto approvals |
| `test_decision_log_format` | Each entry has: operation, risk, phase, rationale, timestamp |

### Decision Transparency
| Test | Description |
|------|-------------|
| `test_high_risk_never_auto_approves` | HIGH risk always requires human |
| `test_critical_never_auto_approves` | CRITICAL risk always requires human |
| `test_medium_execute_requires_human` | MEDIUM in EXECUTE phase requires human |
| `test_medium_plan_auto_approves` | MEDIUM in PLAN phase auto-approves (with logging) |

## Unit Tests: ApprovalQueue Enhancements

### Decision Summary
| Test | Description |
|------|-------------|
| `test_decision_summary_groups_by_type` | Summary separates auto/human approved |
| `test_decision_summary_includes_rationale` | Auto-approved items show why |
| `test_decision_summary_shows_all_session` | Shows all decisions from current session |

### Auto-Approved Status
| Test | Description |
|------|-------------|
| `test_auto_approved_status_stored` | New status value works in DB |
| `test_auto_approved_in_stats` | Stats include auto_approved count |

## Unit Tests: TmuxAdapter Integration

### Prompt Injection
| Test | Description |
|------|-------------|
| `test_spawn_injects_gate_setup` | Prompt includes ApprovalGate initialization |
| `test_spawn_injects_risk_guidelines` | Prompt includes risk classification guide |
| `test_spawn_injects_sample_code` | Prompt includes request_approval example |
| `test_spawn_passes_db_path` | Gate uses same .workflow_approvals.db |

## Unit Tests: CLI Watch Command

### Watch Functionality
| Test | Description |
|------|-------------|
| `test_watch_detects_pending` | Watch finds new pending requests |
| `test_watch_triggers_tmux_bell` | Bell command sent via tmux |
| `test_watch_shows_context` | Displays operation, risk, phase |
| `test_watch_auto_approve_option` | --auto-approve-low flag works |
| `test_watch_once_exits` | --once flag exits after one check |

## Integration Tests

| Test | Description |
|------|-------------|
| `test_spawn_to_approval_flow` | Spawned agent pauses at gate, user approves |
| `test_auto_approve_logged_in_summary` | Auto-approved items appear in summary |
| `test_watch_notifies_on_high_risk` | Watch bell triggers for high risk |

## Acceptance Criteria

- [ ] Low-risk operations auto-approve with logged rationale
- [ ] High/critical risk operations pause for human approval
- [ ] Watch command triggers tmux bell notification
- [ ] Decision summary shows all auto-approved items with rationale
- [ ] Agent prompts include gate initialization code
- [ ] Backwards compatible with existing prompts (no gate = no pause)

---

# PRD-006: Auto-Inject ApprovalGate in spawn_agent() Test Cases

## Unit Tests: TmuxAdapter Injection

### test_tmux_adapter.py (additions)

| Test | Description |
|------|-------------|
| `test_spawn_agent_injects_approval_gate_by_default` | Prompt file contains approval gate instructions |
| `test_spawn_agent_no_injection_when_disabled` | With inject_approval_gate=False, no injection |
| `test_spawn_agent_preserves_original_prompt` | Original prompt content appears first |
| `test_spawn_agent_uses_correct_db_path` | db_path matches working_dir/.workflow_approvals.db |
| `test_spawn_agent_uses_task_id_as_agent_id` | agent_id in instructions matches task_id |

### TmuxConfig Tests

| Test | Description |
|------|-------------|
| `test_config_inject_approval_gate_default_true` | Default value is True |
| `test_config_inject_approval_gate_can_be_false` | Can set to False explicitly |

## Unit Tests: SubprocessAdapter Injection

### test_subprocess_adapter.py (additions)

| Test | Description |
|------|-------------|
| `test_subprocess_adapter_injects_approval_gate` | Same injection behavior as TmuxAdapter |
| `test_subprocess_adapter_no_injection_when_disabled` | Respects config flag |

## CLI Tests

### test_cli.py (additions)

| Test | Description |
|------|-------------|
| `test_prd_spawn_no_approval_gate_flag_recognized` | --no-approval-gate flag is valid |
| `test_prd_spawn_no_approval_gate_disables_injection` | Flag propagates to adapter config |

## Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| Empty original prompt | Gate instructions still added |
| Unicode in task_id | task_id sanitized for agent_id |
| Very long prompt | Injection appends cleanly |
| Multiple spawns same task | Idempotent, both have gate instructions |

## Integration Tests

| Test | Description |
|------|-------------|
| `test_end_to_end_spawn_with_injection` | Full spawn flow creates prompt with gate instructions |
| `test_end_to_end_spawn_without_injection` | With --no-approval-gate, no instructions |

## Acceptance Criteria

- [ ] spawn_agent() injects approval gate instructions by default
- [ ] TmuxConfig.inject_approval_gate controls injection
- [ ] SubprocessAdapter has same behavior as TmuxAdapter
- [ ] --no-approval-gate CLI flag disables injection
- [ ] Original prompt preserved and appears first
- [ ] db_path and agent_id correctly populated in instructions
