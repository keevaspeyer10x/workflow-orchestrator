# CORE-025 Phase 2: WorkflowEngine Integration Plan

## Overview

Integrate `OrchestratorPaths` and `SessionManager` (from Phase 1) with `WorkflowEngine` so all orchestrator files are stored in `.orchestrator/sessions/<session-id>/` instead of scattered across repo root.

## Prerequisites (Phase 1 Complete)

- `src/path_resolver.py` - `OrchestratorPaths` class
- `src/session_manager.py` - `SessionManager` class
- 34 unit tests passing (commit 458d302)

## Implementation Tasks

### Task 1: Update WorkflowEngine (`src/engine.py`)

**Changes:**
1. Add `session_id` parameter to `__init__`
2. Initialize `OrchestratorPaths` with base_dir and session_id
3. Replace hardcoded paths with `self.paths.state_file()` and `self.paths.log_file()`
4. Implement dual-read pattern in `load_state()`:
   - Check new path first: `.orchestrator/sessions/<id>/state.json`
   - Fall back to legacy: `.workflow_state.json`
   - Always write to new path only

**Key code changes:**
```python
from .path_resolver import OrchestratorPaths

class WorkflowEngine:
    def __init__(self, working_dir: str = ".", session_id: str = None, ...):
        self.working_dir = Path(working_dir).resolve()
        self.paths = OrchestratorPaths(base_dir=self.working_dir, session_id=session_id)
        self.state_file = self.paths.state_file()
        self.log_file = self.paths.log_file()
        # ... rest unchanged
```

### Task 2: Update CLI (`src/cli.py`)

**Changes:**
1. Update `get_engine()` to:
   - Check for current session via SessionManager
   - Pass session_id to WorkflowEngine
2. Update `cmd_start()` to:
   - Create new session via SessionManager
   - Create `.orchestrator/.gitignore` with `*` content
   - Pass session_id to WorkflowEngine
3. Add session-related CLI commands (optional, defer to Phase 3)

**Key code changes:**
```python
from src.session_manager import SessionManager
from src.path_resolver import OrchestratorPaths

def get_engine(args) -> WorkflowEngine:
    working_dir = getattr(args, 'dir', '.') or '.'
    paths = OrchestratorPaths(base_dir=Path(working_dir))
    session_mgr = SessionManager(paths)
    session_id = session_mgr.get_current_session()

    # Pass session_id to engine
    engine = WorkflowEngine(working_dir, session_id=session_id)
    engine.load_state()
    # ...
```

### Task 3: Update CheckpointManager (`src/checkpoint.py`)

**Changes:**
1. Accept `OrchestratorPaths` or `session_id` in constructor
2. Replace hardcoded `.workflow_checkpoints` with `paths.checkpoints_dir()`
3. Implement dual-read for existing checkpoints

### Task 4: Update LearningEngine (`src/learning_engine.py`)

**Changes:**
1. Accept `OrchestratorPaths` in constructor
2. Replace hardcoded paths with path resolver methods
3. Support reading from both legacy and new locations

### Task 5: Create `.orchestrator/.gitignore`

**Location:** `.orchestrator/.gitignore`
**Content:** `*` (ignore all files - sessions contain ephemeral state)

This is created automatically on `orchestrator start`.

### Task 6: Integration Tests

Add tests for:
1. Start workflow → creates session in `.orchestrator/sessions/<id>/`
2. Complete items → writes state to new path
3. Legacy `.workflow_state.json` still readable (backward compat)
4. Multiple concurrent sessions don't conflict
5. Resume from checkpoint works with new paths

## Execution Mode

**Decision:** SEQUENTIAL execution

**Reasoning:**
- Tasks are highly interdependent (Task 2 depends on Task 1, etc.)
- Codebase is small and focused
- Need to maintain backward compatibility throughout
- Single agent can complete efficiently

## Safety Requirements

1. **File locking** - Keep existing fcntl locking in engine.py
2. **Atomic writes** - Keep temp-file-and-rename pattern in save_state()
3. **No auto-delete** - Don't automatically delete legacy files
4. **Backward compat** - Legacy files readable, but writes go to new location

## Testing Strategy

1. Unit tests for each modified module
2. Integration test for full workflow lifecycle
3. Migration test: existing `.workflow_state.json` loads correctly
4. Concurrent access test: multiple sessions work independently

## Files to Modify

| File | Type | Description |
|------|------|-------------|
| `src/engine.py` | Major | Add paths integration, dual-read |
| `src/cli.py` | Major | Session creation, engine init |
| `src/checkpoint.py` | Minor | Use paths.checkpoints_dir() |
| `src/learning_engine.py` | Minor | Use paths for state/log files |
| `tests/test_engine_integration.py` | New | Integration tests |
