# CORE-025: Multi-Repo Containment Strategy - Phase 1 Plan

## Overview

Consolidate all orchestrator files into `.orchestrator/` directory with session-first architecture.

## Execution Strategy

**Sequential execution** - These tasks have dependencies and must be done in order:
1. PathResolver depends on nothing
2. SessionManager depends on PathResolver
3. WorkflowEngine integration depends on both
4. Tests depend on implementation

## Implementation Steps

### Step 1: Create PathResolver (`src/path_resolver.py`)

New file with `OrchestratorPaths` class:
- `_find_repo_root()` - Walk up to `.git/` or `workflow.yaml`
- `session_dir()` - `.orchestrator/sessions/<session-id>/`
- `state_file()` - Returns new path (always)
- `find_legacy_state_file()` - Returns old path if exists
- `log_file()`, `checkpoints_dir()`, `feedback_dir()`
- `meta_file()`, `migration_marker()`

### Step 2: Create SessionManager (`src/session_manager.py`)

New file with `SessionManager` class:
- `create_session()` - Generate UUID4[:8], create directory
- `_set_current_session()` - Write to `.orchestrator/current`
- `get_current_session()` - Read from `.orchestrator/current`
- `list_sessions()` - List all session directories

### Step 3: Implement Dual-Read/New-Write in WorkflowEngine

Update state loading to:
1. Check new path first
2. Fall back to legacy path
3. Write only to new path
4. Keep old files (don't delete)

### Step 4: Add File Locking

Install `filelock` dependency and implement:
- Migration lock (`.orchestrator/.migration.lock`)
- Atomic operations (temp-file-and-rename)
- Timeout handling

### Step 5: Update WorkflowEngine Integration

- Add `session_id` parameter to `__init__`
- Create `SessionManager` instance on workflow start
- Update all path references to use `OrchestratorPaths`

### Step 6: Generate meta.json

Create repo identity file with:
- `created_at` timestamp
- `repo_root` path
- `git_remote` URL (if available)
- `orchestrator_version`

### Step 7: Normal vs Portable Mode

- Normal: Create `.orchestrator/.gitignore` with `*`
- Portable (`--portable` flag): No gitignore

## Files to Modify

| File | Changes |
|------|---------|
| `src/path_resolver.py` | NEW - OrchestratorPaths class |
| `src/session_manager.py` | NEW - SessionManager class |
| `src/engine.py` | Update state/log/checkpoint paths |
| `src/cli.py` | Add session creation on `start` |
| `pyproject.toml` | Add `filelock` dependency |
| `tests/test_path_resolver.py` | NEW - Unit tests |
| `tests/test_session_manager.py` | NEW - Unit tests |

## Success Criteria

- [ ] All state stored in `.orchestrator/sessions/<session-id>/`
- [ ] Concurrent sessions don't conflict
- [ ] Legacy paths still readable (dual-read)
- [ ] Only new structure written to
- [ ] Repo root detection works from subdirectories
- [ ] File locking prevents race conditions
- [ ] meta.json generated with repo identity

## Out of Scope (Phase 1)

- Migration command (`orchestrator migrate`) - Phase 2
- Doctor command (`orchestrator doctor`) - Phase 2
- Config precedence hierarchy - Phase 3
- Snapshot export/import - Phase 4
- Web mode auto-commit - Phase 4
