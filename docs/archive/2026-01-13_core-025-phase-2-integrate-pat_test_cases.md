# CORE-025 Test Cases: Multi-Repo Containment Strategy

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

## Acceptance Criteria

- [ ] All state stored in `.orchestrator/sessions/<session-id>/`
- [ ] Concurrent sessions don't conflict
- [ ] Legacy paths still readable (dual-read)
- [ ] Only new structure written to
- [ ] Repo root detection works from subdirectories
- [ ] File locking prevents race conditions
- [ ] meta.json generated with repo identity
