# Orchestrator Containment Strategy - Implementation Prompt

**Use this prompt to start implementation in a new Claude Code Web session.**

---

## Task

Implement CORE-025: Multi-Repo Containment Strategy for the workflow-orchestrator project.

This is a **Phase 1 (v2.7.0)** implementation that consolidates all orchestrator files into a single `.orchestrator/` directory with session-first architecture.

## Context

The workflow-orchestrator is a 5-phase development workflow tool for AI agents. Currently it creates 10+ scattered files in the repository root (`.workflow_state.json`, `.workflow_log.jsonl`, `.workflow_checkpoints/`, etc.), which causes:

1. **Namespace pollution** - Hard to see what's orchestrator vs user code
2. **Multi-repo friction** - Difficult to migrate state between repos
3. **Concurrent session conflicts** - Multiple Claude Code sessions can corrupt state
4. **Web incompatibility** - Ephemeral sessions need different persistence strategy

## What Has Been Done

✅ **Research & Planning:**
- Original specification written ([CONTAINMENT_PROPOSAL.md](CONTAINMENT_PROPOSAL.md))
- External reviews commissioned from 3 AI models:
  - **GPT-5.2** (12.8k chars) - Architecture recommendations
  - **Claude Opus 4** (16.4k chars) - Implementation details with code examples
  - **GPT-4o** (4.9k chars) - UX and migration strategy
- All reviews are in [EXTERNAL_REVIEWS.md](EXTERNAL_REVIEWS.md)
- Comprehensive roadmap created ([ROADMAP.md](ROADMAP.md))

✅ **Key Decisions Made (based on reviews):**
- **Session-first architecture**: `.orchestrator/sessions/<session-id>/` (GPT-5.2)
- **Dual-read, new-write**: Don't auto-migrate, write to new location (GPT-5.2)
- **File locking**: Prevent concurrent access issues (all 3 reviews)
- **Atomic operations**: Temp-file-and-rename for migration safety (Claude Opus)
- **Repo root detection**: Walk up to find `.git/` or `workflow.yaml` (GPT-5.2)
- **Two modes**: normal (gitignored) vs portable (committed) (GPT-5.2)

## What Needs to Be Implemented

### Phase 1 Checklist (Priority Order)

#### 1. PathResolver (`src/path_resolver.py`)
```python
# Create new file with:
class OrchestratorPaths:
    - __init__(base_dir, session_id, web_mode)
    - _find_repo_root()              # Walk up to .git/ or workflow.yaml
    - session_dir()                  # .orchestrator/sessions/<session-id>/
    - state_file()                   # Returns new path (always)
    - find_legacy_state_file()       # Returns old path if exists
    - log_file()
    - checkpoints_dir()
    - feedback_dir()
    - meta_file()
    - migration_marker()
```

See ROADMAP.md lines 380-451 for complete implementation.

#### 2. SessionManager (`src/session_manager.py`)
```python
# Create new file with:
class SessionManager:
    - create_session()               # Generate session ID, create directory
    - _set_current_session()         # Write to .orchestrator/current
    - get_current_session()          # Read from .orchestrator/current
    - list_sessions()                # List all session directories
```

See ROADMAP.md lines 458-508 for complete implementation.

#### 3. Dual-Read, New-Write Strategy
Update `WorkflowEngine` to use dual-read pattern:
```python
def get_state(self):
    new_path = self.paths.state_file()
    old_path = self.paths.find_legacy_state_file()

    if new_path.exists():
        return self._read(new_path)
    elif old_path.exists():
        state = self._read(old_path)
        self._write(new_path, state)  # Write to new, keep old
        return state
    else:
        return self._create_new()
```

#### 4. File Locking
Add dependency:
```bash
pip install filelock
```

Implement locking in migration code:
```python
from filelock import FileLock

def _migrate_file(self, old_path: Path, new_path: Path):
    lock_file = self.orchestrator_dir / ".migration.lock"

    with FileLock(lock_file, timeout=10):
        if new_path.exists():
            return  # Already migrated

        # Atomic migration with temp file
        temp_path = new_path.with_suffix('.tmp')
        try:
            shutil.copy2(old_path, temp_path)
            temp_path.rename(new_path)  # Atomic!
            self._backup_old_file(old_path)
        except:
            if temp_path.exists():
                temp_path.unlink()
            raise
```

#### 5. Update WorkflowEngine Integration
- Add `session_id` parameter to `__init__`
- Create `SessionManager` instance
- Use `OrchestratorPaths` instead of hardcoded paths
- Update all state file references to use `paths.state_file()`
- Update all log file references to use `paths.log_file()`
- Update checkpoint references to use `paths.checkpoints_dir()`
- Update feedback references to use `paths.feedback_dir()`

#### 6. Generate meta.json
Create repo identity file with:
```python
import subprocess

def _create_meta_json(self):
    """Create repo metadata"""
    try:
        git_remote = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
    except:
        git_remote = None

    meta = {
        "created_at": datetime.now().isoformat(),
        "repo_root": str(self.paths.base_dir),
        "git_remote": git_remote,
        "orchestrator_version": "2.7.0",
    }

    self.paths.meta_file().write_text(json.dumps(meta, indent=2))
```

#### 7. Update .gitignore Handling
```python
def init_orchestrator(self, portable: bool = False):
    """Initialize .orchestrator/ directory"""
    self.paths.orchestrator_dir.mkdir(exist_ok=True)

    if not portable:
        # Normal mode: gitignore everything
        gitignore = self.paths.orchestrator_dir / ".gitignore"
        gitignore.write_text("*\n")
    # Portable mode: no gitignore (commit everything)
```

### Implementation Guidelines

1. **Start with PathResolver and SessionManager**
   - These are the foundation for everything else
   - Write unit tests as you go
   - Test with both new and legacy paths

2. **Update WorkflowEngine incrementally**
   - Don't refactor everything at once
   - Update one file path type at a time (state → log → checkpoints → feedback)
   - Test after each change

3. **Maintain backward compatibility**
   - Old workflows must continue working
   - Legacy paths should still be readable
   - Only write to new paths

4. **Edge cases to handle** (see ROADMAP.md lines 512-547):
   - Both old and new paths exist (prefer new, warn)
   - Windows filesystem compatibility
   - Partial migration crashes (atomic operations)
   - Concurrent access (file locking)
   - Symbolic links (detect and warn)

5. **Testing strategy**:
   - Unit tests for PathResolver and SessionManager
   - Integration tests for dual-read fallback
   - Test concurrent access (spawn multiple processes)
   - Test migration scenarios

### Files to Read First

1. **[ROADMAP.md](ROADMAP.md)** - Complete implementation plan (628 lines)
2. **[EXTERNAL_REVIEWS.md](EXTERNAL_REVIEWS.md)** - All 3 external reviews
3. **[CONTAINMENT_PROPOSAL.md](CONTAINMENT_PROPOSAL.md)** - Original specification
4. **`src/cli.py`** - WorkflowEngine class (current implementation)
5. **`src/engine.py`** - Core workflow engine logic

### Success Criteria

After Phase 1, the orchestrator should:
- ✅ Store all state in `.orchestrator/sessions/<session-id>/`
- ✅ Support concurrent sessions without conflicts
- ✅ Fall back to legacy paths automatically (dual-read)
- ✅ Write only to new structure
- ✅ Handle repo root detection (work from subdirectories)
- ✅ Support normal vs portable mode
- ✅ Include file locking for migration safety
- ✅ Generate repo metadata in `meta.json`

### What NOT to Do (Out of Scope for Phase 1)

- ❌ Migration command (`orchestrator migrate`) - Phase 2
- ❌ Doctor command (`orchestrator doctor`) - Phase 2
- ❌ Config precedence hierarchy - Phase 3
- ❌ Snapshot export/import - Phase 4
- ❌ Web mode auto-commit - Phase 4
- ❌ Repository templates - Phase 5

Focus **only** on the foundation: PathResolver, SessionManager, and dual-read/new-write integration.

## Key Design Principles (from Reviews)

1. **Separation of concerns** (GPT-5.2):
   - `state_file()` returns path (no side effects)
   - `find_legacy_state_file()` detects old paths
   - `migrate_if_needed()` does explicit migration

2. **Session isolation** (GPT-5.2):
   - Each session has its own directory
   - No shared state files between sessions
   - `current` file/symlink points to active session

3. **Atomic operations** (Claude Opus):
   - Temp-file-and-rename pattern
   - All-or-nothing migration
   - Proper error handling and cleanup

4. **Safe fallbacks** (all reviews):
   - Read old paths if new doesn't exist
   - Write to new paths always
   - Never delete old paths automatically

## Getting Started

```bash
# 1. Read the documentation
cat ROADMAP.md
cat EXTERNAL_REVIEWS.md

# 2. Understand current structure
grep -r "\.workflow_" src/  # Find all hardcoded paths

# 3. Create new files
touch src/path_resolver.py
touch src/session_manager.py

# 4. Start implementation
# Follow the checklist above in priority order

# 5. Test as you go
pytest tests/ -v

# 6. Commit frequently
git add src/path_resolver.py
git commit -m "feat: Add PathResolver with session support"
```

## Questions to Resolve During Implementation

1. Should `current` be a file or symlink? (GPT-5.2 suggested both)
   - **Recommendation**: File (better Windows compatibility)

2. Where to generate session_id? (engine vs manager)
   - **Recommendation**: SessionManager.create_session()

3. Should we auto-create sessions on `orchestrator start`?
   - **Recommendation**: Yes, create session on workflow start

4. What format for session IDs?
   - **Recommendation**: UUID4 first 8 chars (e.g., `a3f7b2d1`)

## Additional Resources

- **Code examples**: ROADMAP.md lines 380-508
- **Edge cases**: ROADMAP.md lines 512-547
- **Testing strategy**: ROADMAP.md lines 550-573
- **GPT-5.2 review**: EXTERNAL_REVIEWS.md (most detailed architecture)
- **Claude Opus review**: EXTERNAL_REVIEWS.md (best code examples)

## Estimated Effort

- **PathResolver + SessionManager**: 2-4 hours
- **WorkflowEngine integration**: 4-6 hours
- **Testing and debugging**: 2-4 hours
- **Total Phase 1**: 8-14 hours

## Commit Strategy

Use conventional commits with CORE-025 prefix:

```bash
git commit -m "feat(CORE-025): Add PathResolver with repo root detection"
git commit -m "feat(CORE-025): Add SessionManager for session isolation"
git commit -m "feat(CORE-025): Implement dual-read/new-write in WorkflowEngine"
git commit -m "feat(CORE-025): Add file locking for concurrent access"
git commit -m "test(CORE-025): Add PathResolver unit tests"
```

## Final Notes

- **All 3 external reviews strongly endorsed this approach**
- Focus on **safety** (file locking, atomic operations, backups)
- Maintain **backward compatibility** (dual-read pattern)
- Implement **session isolation** first (foundation for everything else)
- **Test thoroughly** (concurrent access is critical)

Good luck! The design is solid based on the external reviews - just needs careful implementation with attention to edge cases.
