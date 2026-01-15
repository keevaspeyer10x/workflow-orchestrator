# CORE-025 Phase 2: WorkflowEngine Integration

## Context

Phase 1 (completed in commit `458d302`) created the foundation:
- `src/path_resolver.py` - OrchestratorPaths class for centralized path resolution
- `src/session_manager.py` - SessionManager class for session lifecycle
- 34 unit tests passing

## Phase 2 Goal

Integrate PathResolver and SessionManager with WorkflowEngine so all orchestrator files are stored in `.orchestrator/sessions/<session-id>/` instead of scattered across repo root.

## What Needs to Be Done

### 1. Update WorkflowEngine (`src/engine.py`)

Modify `__init__` to use OrchestratorPaths:
```python
from .path_resolver import OrchestratorPaths
from .session_manager import SessionManager

class WorkflowEngine:
    def __init__(self, working_dir: str = ".", session_id: str = None, ...):
        self.paths = OrchestratorPaths(base_dir=working_dir, session_id=session_id)
        self.state_file = self.paths.state_file()  # Instead of hardcoded path
        self.log_file = self.paths.log_file()
```

### 2. Implement Dual-Read Pattern

In `load_state()`:
1. Check new path first: `.orchestrator/sessions/<id>/state.json`
2. Fall back to legacy: `.workflow_state.json`
3. Always write to new path only
4. Don't delete legacy files (user can clean up manually)

### 3. Update CLI (`src/cli.py`)

On `orchestrator start`:
1. Create session via SessionManager
2. Pass session_id to WorkflowEngine
3. Create `.orchestrator/.gitignore` with `*` (normal mode)

### 4. Update Related Modules

These modules also access state/log files directly:
- `src/checkpoint.py` - checkpoint storage
- `src/learning_engine.py` - feedback files
- `src/dashboard.py` - reads state

### 5. Add Integration Tests

Test the full flow:
- Start workflow → creates session
- Complete items → writes to new path
- Legacy files still readable
- Multiple concurrent sessions don't conflict

## Key Files to Modify

| File | Changes |
|------|---------|
| `src/engine.py` | Use OrchestratorPaths, dual-read pattern |
| `src/cli.py` | Create session on start, pass session_id |
| `src/checkpoint.py` | Use paths.checkpoints_dir() |
| `src/learning_engine.py` | Use paths.feedback_dir() |

## Safety Requirements (from external reviews)

- File locking already in engine.py (keep it)
- Atomic operations (temp-file-and-rename) already in save_state()
- Don't auto-delete legacy files
- Session isolation prevents concurrent workflow conflicts

## Start Command

```bash
orchestrator start "CORE-025 Phase 2: Integrate PathResolver/SessionManager with WorkflowEngine for .orchestrator/ containment"
```

## Reference

- Phase 1 commit: `458d302`
- ROADMAP.md: Lines 68-182 (CORE-025 spec)
- External reviews: EXTERNAL_REVIEWS.md (GPT-5.2, Claude Opus 4, GPT-4o all endorsed approach)
