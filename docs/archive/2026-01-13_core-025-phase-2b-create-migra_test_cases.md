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

---

# PRD-007: Agent Workflow Enforcement System Test Cases

## Unit Tests: Workflow Loading (enforcement.py)

| Test | Description |
|------|-------------|
| `test_load_valid_workflow` | Load agent_workflow.yaml with valid structure |
| `test_reject_invalid_yaml_missing_phases` | ValidationError when phases missing |
| `test_reject_invalid_yaml_missing_transitions` | ValidationError when transitions missing |
| `test_reject_invalid_yaml_missing_enforcement` | ValidationError when enforcement missing |
| `test_get_phase_by_id` | _get_phase("TDD") returns correct phase definition |
| `test_get_phase_not_found` | Returns None for unknown phase |
| `test_find_transition` | _find_transition("PLAN", "TDD") returns transition |
| `test_find_transition_not_found` | Returns None for invalid transition |

## Unit Tests: Phase Tokens (enforcement.py)

| Test | Description |
|------|-------------|
| `test_generate_valid_token` | generate_phase_token creates valid JWT |
| `test_token_contains_task_id` | Decoded token has task_id claim |
| `test_token_contains_phase` | Decoded token has phase claim |
| `test_token_contains_allowed_tools` | Decoded token has allowed_tools claim |
| `test_token_has_expiry` | Token expires in 2 hours |
| `test_verify_valid_token` | _verify_phase_token returns True for valid token |
| `test_reject_expired_token` | Returns False for expired token |
| `test_reject_tampered_token` | Returns False for modified payload |
| `test_reject_wrong_task_id` | Returns False when task_id mismatch |
| `test_reject_wrong_phase` | Returns False when phase mismatch |

## Unit Tests: Artifact Validation (enforcement.py)

| Test | Description |
|------|-------------|
| `test_validate_valid_artifacts` | Valid artifacts pass schema validation |
| `test_reject_missing_artifact` | ValidationError when required artifact missing |
| `test_reject_invalid_schema_missing_field` | ValidationError for missing required field |
| `test_reject_invalid_schema_wrong_type` | ValidationError for type mismatch |
| `test_reject_invalid_schema_empty_array` | ValidationError when minItems violated |
| `test_validate_plan_document` | Plan with acceptance criteria validates |
| `test_validate_scope_definition` | Scope with in/out scope validates |
| `test_validate_test_result` | Test result with required fields validates |

## Unit Tests: Gate Validation (enforcement.py)

| Test | Description |
|------|-------------|
| `test_check_plan_has_acceptance_criteria_pass` | Returns True when criteria present |
| `test_check_plan_has_acceptance_criteria_fail` | Returns False when missing |
| `test_check_tests_are_failing_pass` | Returns True when failed > 0 |
| `test_check_tests_are_failing_fail_no_failures` | Returns False when failed == 0 |
| `test_check_all_tests_pass_success` | Returns True when all pass |
| `test_check_all_tests_pass_fail_some_failing` | Returns False when failures exist |
| `test_check_all_tests_pass_fail_no_tests_run` | Returns False when passed == 0 |
| `test_check_no_blocking_issues` | Returns True when blocking_issues empty |

## Unit Tests: Tool Permissions (enforcement.py)

| Test | Description |
|------|-------------|
| `test_get_allowed_tools_plan_phase` | Returns correct tool list for PLAN |
| `test_get_allowed_tools_tdd_phase` | Returns correct tool list for TDD |
| `test_get_allowed_tools_impl_phase` | Returns correct tool list for IMPL |
| `test_is_tool_forbidden_plan_write_files` | write_files forbidden in PLAN |
| `test_is_tool_forbidden_impl_write_files` | write_files allowed in IMPL |
| `test_tool_constraint_tdd_write_tests_only` | Can write to tests/ in TDD |
| `test_tool_constraint_tdd_block_write_src` | Cannot write to src/ in TDD |

## Unit Tests: API Endpoints (api.py)

| Test | Description |
|------|-------------|
| `test_claim_task_success` | POST /tasks/claim returns task and token |
| `test_claim_task_no_tasks` | Returns 404 when no tasks available |
| `test_claim_task_creates_valid_token` | phase_token is valid JWT for PLAN |
| `test_request_transition_success` | POST /tasks/transition returns new token |
| `test_request_transition_blocked_gate` | Returns 403 with blockers |
| `test_request_transition_invalid_token` | Returns 401 for expired token |
| `test_request_transition_missing_artifacts` | Returns 400 with error details |
| `test_execute_tool_allowed` | POST /tools/execute succeeds for allowed tool |
| `test_execute_tool_forbidden` | Returns 403 for forbidden tool |
| `test_execute_tool_invalid_token` | Returns 401 for invalid token |
| `test_get_state_snapshot` | GET /state/snapshot returns filtered state |
| `test_audit_log_created` | Tool execution logged to tool_audit.jsonl |

## Unit Tests: Agent SDK (client.py)

| Test | Description |
|------|-------------|
| `test_client_init` | AgentClient initializes with agent_id and URL |
| `test_claim_task_posts_to_api` | claim_task() makes POST to /tasks/claim |
| `test_claim_task_sets_phase_token` | Sets client.phase_token from response |
| `test_request_transition_updates_token` | Success updates phase_token |
| `test_request_transition_raises_on_blocked` | Raises exception when blocked |
| `test_use_tool_allowed` | use_tool() succeeds for allowed tool |
| `test_use_tool_forbidden_raises` | Raises PermissionError for forbidden |
| `test_use_tool_includes_token` | Sends phase_token in request |
| `test_get_state_snapshot` | get_state_snapshot() fetches state |

## Integration Tests: Phase Transitions

| Test | Description |
|------|-------------|
| `test_full_plan_to_tdd_transition` | Complete artifacts, pass gate, get new token |
| `test_blocked_transition_missing_artifacts` | Transition rejected with clear error |
| `test_blocked_transition_gate_failure` | Transition rejected when gate fails |
| `test_tool_permissions_change_by_phase` | write_files changes from forbidden to allowed |
| `test_tool_audit_logs_all_calls` | All tool executions logged |

## Integration Tests: State Snapshots

| Test | Description |
|------|-------------|
| `test_state_snapshot_contents` | Includes dependencies, blockers, phase |
| `test_state_snapshot_filtered_by_task` | Only shows relevant task data |
| `test_state_snapshot_caching` | Second request within 5s uses cache |
| `test_state_snapshot_cache_invalidation` | Cache expires after 5 seconds |

## End-to-End Tests: Full Workflow

| Test | Description | Duration |
|------|-------------|----------|
| `test_complete_agent_workflow` | PLAN → TDD → IMPL → REVIEW → COMPLETE | Slow |
| `test_agent_blocked_missing_tests` | Cannot skip TDD phase | Fast |
| `test_agent_blocked_failing_tests` | Cannot exit IMPL with failing tests | Medium |
| `test_multi_agent_independent_tasks` | 2 agents with separate tokens and state | Medium |
| `test_agent_crash_recovery` | Timeout detection and task stall | Slow |

## Security Tests

| Test | Description |
|------|-------------|
| `test_token_reuse_attack` | Cannot reuse token from different task |
| `test_token_expiry_enforced` | Expired token rejected |
| `test_token_signature_validation` | Modified token rejected |
| `test_tool_permission_escalation` | Cannot add forbidden tools to token |
| `test_artifact_injection` | Cannot inject malicious artifacts |

## Performance Tests

| Test | Target | Description |
|------|--------|-------------|
| `test_tool_permission_check_latency` | <100ms | 1000 permission checks |
| `test_phase_transition_latency` | <500ms | Transition with artifacts |
| `test_state_snapshot_latency` | <200ms | Generate filtered snapshot |
| `test_concurrent_agents` | No failures | 10 agents, simultaneous requests |
| `test_sqlite_no_lock_timeouts` | 0 timeouts | Concurrent API requests |

## Manual Testing Checklist

- [ ] Orchestrator API starts: `python -m src.orchestrator.api`
- [ ] Health check responds: `curl http://localhost:8000/health`
- [ ] Agent spawns with SDK instructions
- [ ] Agent claims task successfully
- [ ] Agent blocked from write_files in PLAN phase
- [ ] Agent transitions PLAN → TDD with valid artifacts
- [ ] Agent writes tests in TDD (allowed)
- [ ] Agent writes code in IMPL (allowed)
- [ ] Tests pass, agent transitions IMPL → REVIEW
- [ ] Review agents auto-spawn
- [ ] Agent blocked until reviews complete
- [ ] Agent transitions REVIEW → COMPLETE
- [ ] tool_audit.jsonl contains all tool calls
- [ ] State in .workflow_state.json correct

## Test Coverage Goals

- **Unit Tests:** >90% code coverage for enforcement.py, api.py, client.py
- **Integration Tests:** All 4 phase transitions covered
- **E2E Tests:** Full workflow PLAN → COMPLETE tested
- **Security Tests:** All attack vectors tested

## Test Execution

```bash
# Unit tests
pytest tests/orchestrator/test_enforcement.py -v
pytest tests/orchestrator/test_api.py -v
pytest tests/agent_sdk/test_client.py -v

# Integration tests
pytest tests/integration/test_phase_transitions.py -v
pytest tests/integration/test_state_snapshots.py -v

# E2E tests (slower)
pytest tests/e2e/test_agent_workflow.py -v --slow

# Performance tests
pytest tests/performance/test_latency.py -v --benchmark

# Security tests
pytest tests/security/test_token_security.py -v

# All tests with coverage
pytest tests/ -v --cov=src/orchestrator --cov=src/agent_sdk
```

## Acceptance Criteria

- [ ] agent_workflow.yaml loaded without errors
- [ ] Orchestrator API running at http://localhost:8000
- [ ] Agent SDK functional and pip-installable
- [ ] 100% phase transitions validated
- [ ] 0 tool calls bypass permission checks
- [ ] All 5 phases enforced
- [ ] Phase tokens cryptographically secure
- [ ] Tool check latency <100ms (p95)
- [ ] Phase transition latency <500ms (p95)
- [ ] All tests pass (unit + integration + e2e)
- [ ] Test coverage >90%

---

# CORE-025: Multi-Repo Containment Strategy Test Cases

## Unit Tests: PathResolver (`tests/test_path_resolver.py`)

### Repo Root Detection
| Test | Description |
|------|-------------|
| `test_repo_root_detection_git` | CWD subdirectory with `.git/` in parent → `base_dir` points to parent |
| `test_repo_root_detection_workflow_yaml` | `workflow.yaml` found before `.git/` → uses that directory |
| `test_repo_root_fallback_cwd` | No `.git/` or `workflow.yaml` → falls back to CWD |

### Path Resolution
| Test | Description |
|------|-------------|
| `test_session_dir_path` | `session_id="abc12345"` → returns `.orchestrator/sessions/abc12345/` |
| `test_session_dir_no_id_raises` | `session_id=None` → raises ValueError |
| `test_state_file_with_session` | Returns `.orchestrator/sessions/<id>/state.json` |
| `test_state_file_without_session` | Returns `.orchestrator/state.json` |
| `test_log_file_path` | Returns correct log path based on session |
| `test_checkpoints_dir_path` | Returns correct checkpoints directory |
| `test_feedback_dir_path` | Returns correct feedback directory |
| `test_meta_file_path` | Returns `.orchestrator/meta.json` |
| `test_migration_marker_path` | Returns `.orchestrator/.migration_complete` |

### Legacy Path Detection
| Test | Description |
|------|-------------|
| `test_find_legacy_state_exists` | `.workflow_state.json` exists → returns path |
| `test_find_legacy_state_not_exists` | No legacy file → returns None |

## Unit Tests: SessionManager (`tests/test_session_manager.py`)

### Session Creation
| Test | Description |
|------|-------------|
| `test_create_session_returns_id` | Returns 8-char UUID |
| `test_create_session_creates_directory` | Session directory created |
| `test_create_session_creates_meta_json` | `meta.json` created with session info |
| `test_create_session_sets_current` | `current` file updated |

### Session Management
| Test | Description |
|------|-------------|
| `test_get_current_session_exists` | Returns session ID from `current` file |
| `test_get_current_session_not_exists` | No `current` file → returns None |
| `test_list_sessions_multiple` | Returns list of all session directories |
| `test_list_sessions_empty` | No sessions → returns empty list |

## Integration Tests

### Dual-Read Strategy
| Test | Description |
|------|-------------|
| `test_dual_read_new_path_exists` | State in new path → reads from new |
| `test_dual_read_legacy_fallback` | State only in legacy → reads legacy, writes new |
| `test_dual_read_both_exist` | Both exist → prefers new, logs warning |

### File Locking
| Test | Description |
|------|-------------|
| `test_file_lock_prevents_concurrent_migration` | Second process waits for lock |
| `test_file_lock_timeout` | Lock timeout raises appropriate error |

### Atomic Operations
| Test | Description |
|------|-------------|
| `test_atomic_write_temp_and_rename` | Temp file created then renamed |
| `test_atomic_write_crash_recovery` | Temp file exists → can clean up |

### Session Isolation
| Test | Description |
|------|-------------|
| `test_concurrent_sessions_no_corruption` | Two processes, different sessions, no data corruption |

## Edge Case Tests

| Case | Expected Behavior |
|------|-------------------|
| Windows paths | Handle backslashes correctly |
| Nested repos | Find nearest repo root |
| Cross-filesystem migration | Uses copy + delete |
| Symbolic link detection | Warn, don't follow |
| Empty session ID | Raises ValueError |
| Permissions error on write | Raises PermissionError with clear message |
| Disk full during migration | Atomic operation cleans up temp file |

## Acceptance Criteria

- [ ] All state stored in `.orchestrator/sessions/<session-id>/`
- [ ] Concurrent sessions don't conflict
- [ ] Legacy paths still readable (dual-read)
- [ ] Only new structure written to
- [ ] Repo root detection works from subdirectories
- [ ] File locking prevents race conditions
- [ ] meta.json generated with repo identity

---

# CORE-025 Phase 2: WorkflowEngine Integration Test Cases

## Unit Tests: WorkflowEngine (`tests/test_engine.py`)

### Engine Initialization
| Test | Description |
|------|-------------|
| `test_engine_init_with_session` | Engine with session_id sets up paths correctly |
| `test_engine_init_without_session` | Engine without session_id uses default paths |
| `test_engine_state_file_uses_paths` | `engine.state_file` matches `paths.state_file()` |
| `test_engine_log_file_uses_paths` | `engine.log_file` matches `paths.log_file()` |

### Dual-Read Pattern
| Test | Description |
|------|-------------|
| `test_load_state_from_legacy` | Legacy `.workflow_state.json` loads correctly |
| `test_load_state_prefers_new_path` | New path preferred when both exist |
| `test_save_state_uses_new_path` | State saved to new path only |
| `test_save_state_creates_session_dir` | Session directory created on first save |
| `test_legacy_not_modified_on_save` | Legacy file unchanged when writing to new path |

### Log File Handling
| Test | Description |
|------|-------------|
| `test_log_event_uses_new_path` | Events logged to session log file |
| `test_get_events_reads_from_new_path` | Events read from session log file |

## Unit Tests: CLI (`tests/test_cli.py`)

### Session Creation
| Test | Description |
|------|-------------|
| `test_cmd_start_creates_session` | `orchestrator start` creates session |
| `test_cmd_start_creates_gitignore` | `.orchestrator/.gitignore` created with `*` |
| `test_cmd_start_sets_current_session` | Current session pointer updated |
| `test_get_engine_uses_current_session` | `get_engine()` uses current session |

### Session Continuity
| Test | Description |
|------|-------------|
| `test_cmd_status_uses_current_session` | Status shows workflow from current session |
| `test_cmd_complete_uses_current_session` | Complete updates correct session state |

## Unit Tests: CheckpointManager (`tests/test_checkpoint.py`)

### Path Integration
| Test | Description |
|------|-------------|
| `test_checkpoint_init_with_paths` | Accepts OrchestratorPaths in constructor |
| `test_checkpoint_uses_session_dir` | Uses `paths.checkpoints_dir()` |
| `test_checkpoint_dual_read_legacy` | Reads legacy `.workflow_checkpoints/` |

## Unit Tests: LearningEngine (`tests/test_learning_engine.py`)

### Path Integration
| Test | Description |
|------|-------------|
| `test_learning_init_with_paths` | Accepts OrchestratorPaths in constructor |
| `test_learning_uses_session_paths` | Uses session paths for state/log files |

## Integration Tests (`tests/test_engine_integration.py`)

### Full Workflow Lifecycle
| Test | Description |
|------|-------------|
| `test_full_workflow_with_sessions` | Complete workflow in session directory |
| `test_workflow_state_in_session_dir` | State file in `.orchestrator/sessions/<id>/state.json` |
| `test_workflow_log_in_session_dir` | Log file in `.orchestrator/sessions/<id>/log.jsonl` |

### Backward Compatibility
| Test | Description |
|------|-------------|
| `test_legacy_state_loads` | Existing `.workflow_state.json` works |
| `test_legacy_workflow_completes` | Can complete workflow from legacy state |

### Multiple Sessions
| Test | Description |
|------|-------------|
| `test_concurrent_sessions` | Two workflows in different dirs don't conflict |
| `test_session_isolation` | State changes in one session don't affect another |

## Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| Empty session_id string | Raises ValueError |
| Session directory creation fails | Clear error message |
| Legacy state corrupt | Clear error, don't crash |
| Mixed legacy and new checkpoints | Both accessible |

## Test Execution

```bash
# Run Phase 2 specific tests
pytest tests/test_engine.py -v -k "session"
pytest tests/test_cli.py -v -k "session"
pytest tests/test_engine_integration.py -v

# All tests with coverage
pytest tests/ -v --cov=src
```

## Acceptance Criteria

- [ ] `orchestrator start` creates session in `.orchestrator/sessions/<id>/`
- [ ] State and log files go to session directory
- [ ] Legacy `.workflow_state.json` still readable
- [ ] CheckpointManager uses session paths
- [ ] LearningEngine uses session paths
- [ ] `.orchestrator/.gitignore` created automatically
