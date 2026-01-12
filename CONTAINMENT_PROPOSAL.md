# Orchestrator Containment Strategy

## Goal
Keep orchestrator's footprint minimal and contained to improve multi-repo usage.

## Proposed Structure

```
repo/
├── .orchestrator/                 # Single orchestrator directory
│   ├── state.json                 # Main workflow state (was .workflow_state.json)
│   ├── log.jsonl                  # Event log (was .workflow_log.jsonl)
│   ├── checkpoints/               # Already here
│   │   └── cp_*.json
│   ├── feedback/
│   │   ├── tool.jsonl             # Was .workflow_tool_feedback.jsonl
│   │   └── process.jsonl          # Was .workflow_process_feedback.jsonl
│   ├── secrets/
│   │   ├── .enc                   # Was root .secrets.enc
│   │   └── sops.yaml              # Was root secrets.enc.yaml
│   ├── prd/
│   │   ├── state.json             # Was .claude/prd_state.json
│   │   └── sessions/              # Already in .orchestrator/sessions/
│   ├── config.yaml                # Per-repo overrides (was .orchestra.yaml)
│   ├── agent_workflow.yaml        # Already here
│   ├── audit.jsonl                # Already here
│   └── .gitignore                 # Auto-generated gitignore for orchestrator
├── workflow.yaml                  # Keep in root (user customizes, committable)
└── .claude/                       # Keep separate (Claude Code convention)
    └── hooks/session-start.sh
```

## What Stays in Root

1. **`workflow.yaml`** - User-facing configuration
   - Users customize this per-project
   - Should be visible and committable
   - Not "internal" state

2. **`.claude/hooks/`** - Claude Code convention
   - Claude Code expects hooks in `.claude/`
   - External tool's convention, not ours

## Benefits

### 1. Minimal Footprint
- **Before**: 10+ files/folders scattered in root
- **After**: 2 items in root (`.orchestrator/`, `workflow.yaml`)

### 2. Simple Gitignore
```gitignore
# Before (7 patterns)
.workflow_state.json
.workflow_log.jsonl
.workflow_checkpoints/
.workflow_sessions/
.workflow_feedback.jsonl
.workflow_tool_feedback.jsonl
.workflow_process_feedback.jsonl

# After (1 pattern)
.orchestrator/
```

### 3. Easy Cleanup
```bash
# Before
rm -f .workflow_*.json .workflow_*.jsonl .secrets.enc secrets.enc.yaml .orchestra.yaml
rm -rf .workflow_checkpoints/ .workflow_sessions/ .orchestrator/

# After
rm -rf .orchestrator/
```

### 4. Clear Ownership
- "Everything in `.orchestrator/` is orchestrator's business"
- Users don't need to understand internal file layout
- Clear separation: repo code vs orchestrator metadata

### 5. Multi-Repo Friendly
- Minimal namespace pollution
- Easy to identify orchestrator files
- Simple migration: just copy `.orchestrator/` + `workflow.yaml`
- Better for ephemeral environments (web)

### 6. Single Source of Truth
- No confusion about which state file is authoritative
- All related state in one place
- Easier debugging: "show me everything in .orchestrator/"

## Migration Strategy

### Phase 1: Backward Compatibility (v2.7.0)
Support both old and new locations:
```python
def load_state(self):
    # Try new location first
    new_path = Path(".orchestrator/state.json")
    if new_path.exists():
        return self._load(new_path)

    # Fall back to old location
    old_path = Path(".workflow_state.json")
    if old_path.exists():
        # Auto-migrate on load
        state = self._load(old_path)
        self._save(new_path, state)
        click.echo("📦 Migrated state to .orchestrator/")
        return state

    # New workflow
    return self._new_state()
```

### Phase 2: Migration Command (v2.7.0)
```bash
# Migrate existing repo to new structure
orchestrator migrate --to-contained

# Output:
# 📦 Migrating to contained structure...
# ✓ .workflow_state.json → .orchestrator/state.json
# ✓ .workflow_log.jsonl → .orchestrator/log.jsonl
# ✓ .workflow_checkpoints/ → .orchestrator/checkpoints/
# ✓ .workflow_*_feedback.jsonl → .orchestrator/feedback/
# ✓ .secrets.enc → .orchestrator/secrets/.enc
# ✓ .orchestra.yaml → .orchestrator/config.yaml
# ✓ .claude/prd_state.json → .orchestrator/prd/state.json
# ✅ Migration complete! Old files backed up to .orchestrator/migration_backup/
```

### Phase 3: Default for New Workflows (v2.8.0)
- New workflows use contained structure by default
- Old workflows continue working (backward compatible)
- Deprecation warning for old structure

### Phase 4: Remove Old Paths (v3.0.0)
- Only support contained structure
- Breaking change (major version bump)

## Implementation Checklist

- [ ] Add `PathResolver` class to centralize path logic
- [ ] Update `WorkflowEngine` to check both old/new paths
- [ ] Update `FeedbackManager` to use `.orchestrator/feedback/`
- [ ] Update `CheckpointManager` to use `.orchestrator/checkpoints/`
- [ ] Update `SecretsManager` to check `.orchestrator/secrets/`
- [ ] Update PRD commands to use `.orchestrator/prd/`
- [ ] Add `orchestrator migrate` command
- [ ] Update `orchestrator init` to create contained structure
- [ ] Update session hook to handle both structures
- [ ] Update documentation (CLAUDE.md, README.md)
- [ ] Add migration guide for existing users
- [ ] Update `.gitignore` templates

## Path Resolution Class

```python
# src/path_resolver.py
from pathlib import Path
from typing import Optional

class OrchestratorPaths:
    """Centralized path resolution with backward compatibility"""

    def __init__(self, base_dir: Path = Path(".")):
        self.base_dir = base_dir
        self.orchestrator_dir = base_dir / ".orchestrator"

    def state_file(self) -> Path:
        """Get workflow state file (with migration)"""
        new_path = self.orchestrator_dir / "state.json"
        old_path = self.base_dir / ".workflow_state.json"

        if new_path.exists():
            return new_path
        elif old_path.exists():
            # Auto-migrate
            self._ensure_dir(new_path.parent)
            self._migrate_file(old_path, new_path)
            return new_path
        else:
            return new_path

    def log_file(self) -> Path:
        new_path = self.orchestrator_dir / "log.jsonl"
        old_path = self.base_dir / ".workflow_log.jsonl"
        return self._resolve_with_migration(new_path, old_path)

    def checkpoints_dir(self) -> Path:
        new_path = self.orchestrator_dir / "checkpoints"
        old_path = self.base_dir / ".workflow_checkpoints"
        return self._resolve_with_migration(new_path, old_path)

    def feedback_dir(self) -> Path:
        return self.orchestrator_dir / "feedback"

    def tool_feedback(self) -> Path:
        new_path = self.feedback_dir() / "tool.jsonl"
        old_path = self.base_dir / ".workflow_tool_feedback.jsonl"
        return self._resolve_with_migration(new_path, old_path)

    def process_feedback(self) -> Path:
        new_path = self.feedback_dir() / "process.jsonl"
        old_path = self.base_dir / ".workflow_process_feedback.jsonl"
        return self._resolve_with_migration(new_path, old_path)

    def secrets_dir(self) -> Path:
        return self.orchestrator_dir / "secrets"

    def prd_dir(self) -> Path:
        return self.orchestrator_dir / "prd"

    def prd_state(self) -> Path:
        new_path = self.prd_dir() / "state.json"
        old_path = self.base_dir / ".claude" / "prd_state.json"
        return self._resolve_with_migration(new_path, old_path)

    def config_file(self) -> Path:
        new_path = self.orchestrator_dir / "config.yaml"
        old_path = self.base_dir / ".orchestra.yaml"
        return self._resolve_with_migration(new_path, old_path)

    def _resolve_with_migration(self, new_path: Path, old_path: Path) -> Path:
        """Resolve path with automatic migration"""
        if new_path.exists():
            return new_path
        elif old_path.exists():
            self._ensure_dir(new_path.parent)
            self._migrate_file(old_path, new_path)
            return new_path
        else:
            return new_path

    def _migrate_file(self, old_path: Path, new_path: Path):
        """Migrate file with backup"""
        import shutil

        # Copy to new location
        if old_path.is_dir():
            shutil.copytree(old_path, new_path)
        else:
            shutil.copy2(old_path, new_path)

        # Backup old location
        backup_dir = self.orchestrator_dir / "migration_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / old_path.name

        if old_path.is_dir():
            shutil.move(str(old_path), str(backup_path))
        else:
            shutil.move(str(old_path), str(backup_path))

        print(f"✓ Migrated {old_path.name} → {new_path.relative_to(self.base_dir)}")

    def _ensure_dir(self, path: Path):
        """Ensure directory exists"""
        path.mkdir(parents=True, exist_ok=True)
```

## Example Usage

```python
# Before (scattered)
state_file = Path(".workflow_state.json")
log_file = Path(".workflow_log.jsonl")
checkpoints_dir = Path(".workflow_checkpoints")
tool_feedback = Path(".workflow_tool_feedback.jsonl")

# After (contained)
paths = OrchestratorPaths()
state_file = paths.state_file()           # .orchestrator/state.json
log_file = paths.log_file()               # .orchestrator/log.jsonl
checkpoints_dir = paths.checkpoints_dir() # .orchestrator/checkpoints/
tool_feedback = paths.tool_feedback()     # .orchestrator/feedback/tool.jsonl
```

## Documentation Updates

### CLAUDE.md
Update file locations section:
```markdown
## Important Notes

- The orchestrator stores all state in `.orchestrator/`:
  - `state.json` - Main workflow state
  - `log.jsonl` - Event log
  - `checkpoints/` - Checkpoint backups
  - `feedback/` - Tool and process feedback
  - `secrets/` - Encrypted secrets (if using file-based secrets)
  - `prd/` - Parallel agent state
- `workflow.yaml` in repo root - Workflow definition (user customizes)
- `.claude/hooks/` - Session hooks (Claude Code convention)
- Add `.orchestrator/` to `.gitignore` for most projects
```

### README.md
Add quick start with contained structure:
```markdown
## Quick Start

```bash
# Initialize workflow in new repo
cd my-project
orchestrator init

# Creates:
# - .orchestrator/     (orchestrator state, gitignored)
# - workflow.yaml      (workflow definition, committable)

# Start workflow
orchestrator start "Add user authentication"
```
```

## Rollout Timeline

- **v2.7.0** (Week 1): Add PathResolver + auto-migration
- **v2.7.1** (Week 2): Add `orchestrator migrate` command
- **v2.8.0** (Week 3): New workflows use contained structure by default
- **v2.9.0** (Week 4): Deprecation warnings for old structure
- **v3.0.0** (Month 3): Remove backward compatibility (breaking change)

## Testing Strategy

1. **Unit tests**: Test PathResolver with both old/new structures
2. **Integration tests**: Test migration from scattered to contained
3. **Regression tests**: Ensure old workflows continue working
4. **Multi-repo tests**: Test migration across multiple repos
5. **Web environment tests**: Test contained structure in ephemeral environments

## Success Metrics

- [ ] New users never see scattered files
- [ ] Existing users can migrate with one command
- [ ] Gitignore complexity reduced from 7 patterns to 1
- [ ] Cleanup command is single `rm -rf .orchestrator/`
- [ ] Multi-repo usage requires minimal per-repo footprint
- [ ] Web sessions work with ephemeral `.orchestrator/` directory
