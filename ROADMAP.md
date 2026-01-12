# Workflow Orchestrator Roadmap

This document tracks planned improvements for the orchestrator.

For completed features, see [CHANGELOG.md](CHANGELOG.md).

---

## CRITICAL: Multi-Repo Containment Strategy (CORE-025)

**Status:** Ready for Implementation
**Priority:** P0 - Foundation for all other improvements
**External Reviews:** GPT-5.2 ✅ | Claude Opus 4 ✅ | GPT-4o ✅

### Overview

Consolidate all orchestrator files into `.orchestrator/` directory with session-first architecture to solve:
- **File pollution** (10+ scattered files → 1 directory)
- **Multi-repo friction** (hard to migrate state between repos)
- **Concurrent session conflicts** (multiple Claude sessions corrupt state)
- **Web compatibility** (ephemeral sessions need different persistence)

### Documents to Review

1. **[CONTAINMENT_PROPOSAL.md](CONTAINMENT_PROPOSAL.md)** - Original technical specification
2. **[EXTERNAL_REVIEWS.md](EXTERNAL_REVIEWS.md)** - Reviews from GPT-5.2, Claude Opus 4, GPT-4o
3. **[REVIEW_PACKAGE.md](REVIEW_PACKAGE.md)** - Context provided to reviewers

### Key Insights from External Reviews

**GPT-5.2 (12.8k chars) - Architecture Focus:**
- ✅ Recommends **session-first architecture**: `.orchestrator/sessions/<session-id>/`
- ✅ **Dual-read, new-write** instead of auto-migration (safer)
- ✅ **Two modes**: normal (gitignored) vs portable (committed)
- ✅ **Snapshot export** for web instead of auto-commit
- ✅ Separate `resolve()` from `migrate()` in PathResolver
- ✅ **Repo root detection** (walk up to `.git/` or `workflow.yaml`)

**Claude Opus 4 (16.4k chars) - Implementation Focus:**
- ✅ **File locking** during migration (prevent race conditions)
- ✅ **Atomic operations** (temp-file-and-rename pattern)
- ✅ **All-or-nothing migration** with marker file
- ✅ **Ephemeral state persistence** strategies (orphan branch, git notes, S3)
- ✅ Configuration hierarchy implementation
- ✅ Extensive code examples for PathResolver enhancements

**GPT-4o (4.9k chars) - UX Focus:**
- ✅ Clear migration communication (visual notice box)
- ✅ Interactive migration tool with customization
- ✅ Dry-run and rollback support
- ✅ Plugin/extension model for flexibility

### Critical Consensus (All 3 Models)

| Issue | Solution | Priority |
|-------|----------|----------|
| Concurrent access | File locking (`.orchestrator/lock`) | 🚨 P0 |
| Atomic migration | Temp-file-and-rename pattern | 🚨 P0 |
| Partial migration | All-or-nothing with marker | 🚨 P0 |
| Web persistence | Snapshot export OR orphan branch | ⚡ P1 |
| Migration safety | Dry-run, rollback, backups | ⚡ P1 |
| Auto-migration | Warn, don't auto (explicit opt-in) | ⚡ P1 |

---

## Implementation Phases

### Phase 1: Foundation (v2.7.0) - CRITICAL

**Goal:** Session-first architecture with safe migration

#### 1.1 PathResolver Refactor
- [x] Document current issues (CONTAINMENT_PROPOSAL.md)
- [x] Get external reviews (3 models reviewed)
- [ ] Create `src/path_resolver.py` with:
  - `state_file()` - Returns intended new path (always)
  - `find_legacy_state_file()` - Returns old path if exists
  - `migrate_if_needed()` - Explicit migration (not on read)
  - `_find_repo_root()` - Walk up to `.git/` or `workflow.yaml`

#### 1.2 Session-First Architecture (GPT-5.2)
```
.orchestrator/
├── sessions/
│   ├── <session-id>/
│   │   ├── state.json           # Workflow state
│   │   ├── log.jsonl            # Event log
│   │   ├── feedback/
│   │   │   ├── tool.jsonl       # Tool feedback
│   │   │   └── process.jsonl    # Process feedback
│   │   └── checkpoints/
│   └── <another-session>/
├── current → symlink to active session
├── meta.json                     # Repo identity (created, git remote, version)
├── prd/                          # PRD state (parallel agents)
├── secrets/                      # Repo-scoped secrets
└── config.yaml                   # Repo config
```

**Implementation Steps:**
- [ ] Add `session_id` to WorkflowEngine
- [ ] Create `SessionManager` class
- [ ] Update all state reads/writes to use sessions
- [ ] Add `current` symlink/file for active session
- [ ] Generate `meta.json` with repo identity

#### 1.3 Dual-Read, New-Write Strategy
```python
def get_state(self):
    new_path = self.paths.state_file()
    old_path = self.paths.find_legacy_state_file()

    if new_path.exists():
        return self._read(new_path)
    elif old_path.exists():
        state = self._read(old_path)
        self._write(new_path, state)  # Write to new
        # Keep old (don't delete) - only migrate command deletes
        return state
    else:
        return self._create_new()
```

**Benefits:**
- No surprising side effects on read-only commands
- Safe fallback to old structure
- Only `orchestrator migrate` does destructive moves

#### 1.4 File Locking for Concurrent Access
```python
from filelock import FileLock

def _migrate_file(self, old_path: Path, new_path: Path):
    lock_file = self.orchestrator_dir / ".migration.lock"

    with FileLock(lock_file, timeout=10):
        if new_path.exists():
            return  # Already migrated

        # Atomic migration
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

**Install dependency:**
```bash
pip install filelock
```

#### 1.5 Repo Root Detection
```python
def _find_repo_root(self) -> Path:
    """Walk up to find repo root"""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".git").exists():
            return parent
        if (parent / "workflow.yaml").exists():
            return parent
    return cwd  # Fallback
```

#### 1.6 Two Modes: Normal vs Portable
```bash
# Normal mode (desktop): .orchestrator/ gitignored
orchestrator init

# Portable mode (web): .orchestrator/ committed
orchestrator init --portable
```

**Implementation:**
- Normal: Creates `.orchestrator/.gitignore` with `*`
- Portable: No gitignore, all state is committed

---

### Phase 2: Migration Tools (v2.7.x)

#### 2.1 Migration Command
```bash
# Preview what would change
orchestrator migrate --dry-run

# Migrate with auto-rollback on error
orchestrator migrate --auto-rollback

# Rollback if needed
orchestrator migrate --rollback
```

**Features:**
- [x] Backup to `.orchestrator/migration_backup/`
- [ ] Show size estimates
- [ ] Validate disk space before migration
- [ ] Create `.orchestrator/.migration_complete` marker
- [ ] Store migration metadata (timestamp, version, files moved)

#### 2.2 Doctor Command (Validation)
```bash
orchestrator doctor
```

**Checks:**
- [ ] Secrets accessible (all required keys present)
- [ ] Conflicting state files (old + new both exist)
- [ ] Concurrent lock status
- [ ] Web-incompatible features enabled
- [ ] Disk space for migration
- [ ] Permissions on .orchestrator/

#### 2.3 Visual Migration Notice (GPT-4o)
```
╔════════════════════════════════════════════════════════════╗
║ Orchestrator File Structure Update                         ║
╠════════════════════════════════════════════════════════════╣
║ We're updating how orchestrator organizes its files.       ║
║                                                            ║
║ Old: Multiple .workflow_* files in your repository root    ║
║ New: Everything organized in a single .orchestrator/ folder║
║                                                            ║
║ Benefits:                                                  ║
║ • Cleaner repository root                                  ║
║ • Easier to gitignore (just .orchestrator/)              ║
║ • Better for using across multiple repositories           ║
║                                                            ║
║ Run 'orchestrator migrate' to update now                   ║
╚════════════════════════════════════════════════════════════╝
```

---

### Phase 3: Configuration & Secrets (v2.8.0)

#### 3.1 Config Precedence Hierarchy
```python
# Strict order (lowest → highest):
1. Defaults
2. ~/.orchestrator/config.yaml       # Global user config
3. .orchestrator/config.yaml         # Repo config
4. ORCHESTRATOR_* env vars           # Environment
5. CLI flags                         # Highest precedence
```

**Implementation:**
```python
class ConfigLoader:
    def load_config(self) -> dict:
        config = {}
        config.update(self.DEFAULT_CONFIG)
        config.update(self._load_global_config())
        config.update(self._load_local_config())
        config.update(self._load_env_vars())
        return config
```

#### 3.2 Show Effective Config
```bash
orchestrator config show --effective

# Output:
# Configuration (showing effective values):
#
#   feedback_sync: false (from: env ORCHESTRATOR_FEEDBACK_SYNC)
#   secrets_repo: user/secrets (from: ~/.orchestrator/config.yaml)
#   claude_binary: happy (from: .orchestrator/config.yaml)
```

#### 3.3 Secrets Management
```bash
# Validate secrets
orchestrator secrets doctor

# Test specific secret
orchestrator secrets test OPENAI_API_KEY
```

**Strategy:**
- Per-repo secrets: `.orchestrator/secrets/`
- Global secrets: `~/.orchestrator/secrets/`
- Precedence: repo → global → env vars

---

### Phase 4: Web Compatibility (v2.8.x)

#### 4.1 Snapshot Export/Import
```bash
# Export state for ephemeral sessions
orchestrator snapshot export > state.tar.gz

# Later restore
orchestrator snapshot import state.tar.gz
```

**Implementation:**
- Tar/gzip `.orchestrator/` directory
- Optionally encrypt with password
- Include metadata (repo identity, export timestamp)

#### 4.2 Orphan Branch Persistence (Opt-In)
```bash
# Enable for web sessions
orchestrator config set web_mode true
orchestrator config set state_branch "orchestrator-state-<repo-id>"

# Auto-commit to orphan branch after each phase
git checkout --orphan orchestrator-state-<repo-id>
git add .orchestrator/
git commit -m "State snapshot $(date)"
git push origin orchestrator-state-<repo-id>
```

#### 4.3 Bootstrap Without pip
```bash
# Create Python zipapp
python -m zipapp orchestrator/ -o dist/orchestrator.pyz -p "/usr/bin/env python3"

# Use without installation
curl -O https://github.com/.../orchestrator.pyz
python orchestrator.pyz start "task"
```

#### 4.4 Ephemeral Environment Detection
```python
def _detect_ephemeral_env(self) -> bool:
    return any([
        os.getenv("CLAUDE_CODE_WEB") == "1",
        os.getenv("GITHUB_CODESPACES") == "1",
        os.getenv("GITPOD_WORKSPACE_ID") is not None,
        not os.access(os.path.expanduser("~"), os.W_OK),
    ])
```

---

### Phase 5: Cleanup (v3.0.0)

#### 5.1 Remove Legacy Write Support
- [ ] Remove all code that writes to old paths
- [ ] Keep read support for legacy import
- [ ] Add `orchestrator import-legacy` command

#### 5.2 Repository Templates
```bash
# Initialize from template
orchestrator init --template github.com/org/workflow-templates/web-app

# Or from local
orchestrator init --template ~/.orchestrator/templates/my-template
```

#### 5.3 Cross-Repo Workflows
```yaml
# workflow.yaml
include:
  - repo: "../shared-workflows/common.yaml"

steps:
  - name: "Update dependency in other repo"
    repo: "../api-repo"
    command: "npm update @myorg/shared"
```

---

## Detailed Code Specifications

### PathResolver Implementation

**File:** `src/path_resolver.py`

```python
from pathlib import Path
from typing import Optional
import hashlib

class OrchestratorPaths:
    """Centralized path resolution with session support"""

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        session_id: Optional[str] = None,
        web_mode: bool = False
    ):
        self.base_dir = base_dir or self._find_repo_root()
        self.session_id = session_id
        self.web_mode = web_mode
        self.orchestrator_dir = self.base_dir / ".orchestrator"

    def _find_repo_root(self) -> Path:
        """Walk up to find repo root"""
        cwd = Path.cwd()
        for parent in [cwd, *cwd.parents]:
            if (parent / ".git").exists():
                return parent
            if (parent / "workflow.yaml").exists():
                return parent
        return cwd

    def session_dir(self) -> Path:
        """Get current session directory"""
        if not self.session_id:
            raise ValueError("No session ID set")
        return self.orchestrator_dir / "sessions" / self.session_id

    def state_file(self) -> Path:
        """Get state file (new structure)"""
        if self.session_id:
            return self.session_dir() / "state.json"
        return self.orchestrator_dir / "state.json"

    def find_legacy_state_file(self) -> Optional[Path]:
        """Find old state file if it exists"""
        old = self.base_dir / ".workflow_state.json"
        return old if old.exists() else None

    def log_file(self) -> Path:
        """Get log file"""
        if self.session_id:
            return self.session_dir() / "log.jsonl"
        return self.orchestrator_dir / "log.jsonl"

    def checkpoints_dir(self) -> Path:
        """Get checkpoints directory"""
        if self.session_id:
            return self.session_dir() / "checkpoints"
        return self.orchestrator_dir / "checkpoints"

    def feedback_dir(self) -> Path:
        """Get feedback directory"""
        if self.session_id:
            return self.session_dir() / "feedback"
        return self.orchestrator_dir / "feedback"

    def meta_file(self) -> Path:
        """Get repo metadata file"""
        return self.orchestrator_dir / "meta.json"

    def migration_marker(self) -> Path:
        """Get migration completion marker"""
        return self.orchestrator_dir / ".migration_complete"
```

### Session Manager

**File:** `src/session_manager.py`

```python
import uuid
from datetime import datetime
from pathlib import Path
import json

class SessionManager:
    """Manage orchestrator sessions"""

    def __init__(self, paths: OrchestratorPaths):
        self.paths = paths

    def create_session(self) -> str:
        """Create new session"""
        session_id = str(uuid.uuid4())[:8]
        session_dir = self.paths.orchestrator_dir / "sessions" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Create session metadata
        meta = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "repo_root": str(self.paths.base_dir),
        }

        (session_dir / "meta.json").write_text(json.dumps(meta, indent=2))

        # Set as current
        self._set_current_session(session_id)

        return session_id

    def _set_current_session(self, session_id: str):
        """Set current active session"""
        current_file = self.paths.orchestrator_dir / "current"
        current_file.write_text(session_id)

    def get_current_session(self) -> Optional[str]:
        """Get current active session ID"""
        current_file = self.paths.orchestrator_dir / "current"
        if current_file.exists():
            return current_file.read_text().strip()
        return None

    def list_sessions(self) -> list:
        """List all sessions"""
        sessions_dir = self.paths.orchestrator_dir / "sessions"
        if not sessions_dir.exists():
            return []

        return [d.name for d in sessions_dir.iterdir() if d.is_dir()]
```

---

## Edge Cases to Handle

From external reviews:

1. **Both old and new exist and differ** (GPT-5.2)
   - Prefer `.orchestrator/` always
   - Emit warning
   - Offer `--force-from-old` / `--force-from-new` flags

2. **Windows filesystem compatibility** (GPT-5.2)
   - `shutil.move` across filesystems = copy+delete
   - No symlink assumptions
   - Test on Windows paths

3. **`.claude/prd_state.json` ownership** (GPT-5.2)
   - If orchestrator-owned: move to `.orchestrator/prd/`
   - If Claude-owned: keep external, treat as input

4. **Partial migration crashes** (All reviews)
   - Use atomic operations (temp + rename)
   - All-or-nothing with marker file
   - Create backups before migration

5. **Concurrent access** (All reviews)
   - File locking with timeout
   - Session isolation via directories
   - Advisory locks (fcntl on Unix, msvcrt on Windows)

6. **Symbolic links to old paths** (Claude Opus)
   - Detect and warn
   - Don't follow symlinks during migration

7. **Custom permissions on migrated files** (Claude Opus)
   - Preserve permissions with `shutil.copy2`
   - Document permission handling

---

## Testing Strategy

1. **Unit Tests**
   - PathResolver with both old/new structures
   - SessionManager CRUD operations
   - Config precedence hierarchy
   - Migration atomic operations

2. **Integration Tests**
   - Full migration from scattered → contained
   - Concurrent sessions (multiple processes)
   - Rollback scenarios
   - Web mode vs normal mode

3. **Cross-Platform Tests**
   - Linux, macOS, Windows
   - Different filesystems (ext4, APFS, NTFS)
   - Repo on different mount point

4. **Regression Tests**
   - Old workflows continue working
   - Dual-read fallback functions
   - Legacy import command

---

## Success Metrics

- [ ] New users never see scattered files
- [ ] Existing users can migrate with one command
- [ ] Gitignore complexity: 7 patterns → 1 pattern
- [ ] Cleanup: multi-step → `rm -rf .orchestrator/`
- [ ] Multi-repo: manual setup → copy one directory
- [ ] Concurrent sessions: crashes → works safely
- [ ] Web sessions: complex setup → auto-bootstrap

---

## References

- **[CONTAINMENT_PROPOSAL.md](CONTAINMENT_PROPOSAL.md)** - Original specification
- **[EXTERNAL_REVIEWS.md](EXTERNAL_REVIEWS.md)** - GPT-5.2, Claude Opus 4, GPT-4o reviews
- **[REVIEW_PACKAGE.md](REVIEW_PACKAGE.md)** - Context for reviewers
- **WF-030** - Session isolation (previous roadmap item, now superseded by this)

---

## Deferred Features (v3.x+)

### Plugin Architecture
```python
class StorageBackend(ABC):
    @abstractmethod
    def read_state(self) -> dict: ...

    @abstractmethod
    def write_state(self, state: dict): ...
```

### Hybrid Storage Model (GPT-5.2)
- Auto-detect best strategy (ephemeral, compressed, remote)
- Support multiple backends (filesystem, S3, database)

### Multi-Repo Orchestration
- Cross-repo workflows
- Dependency management between repos
- State synchronization

---

## Timeline (Estimated)

- **Phase 1 (v2.7.0)**: 1-2 weeks - Foundation & session architecture
- **Phase 2 (v2.7.x)**: 1 week - Migration tools & validation
- **Phase 3 (v2.8.0)**: 1 week - Config hierarchy & secrets
- **Phase 4 (v2.8.x)**: 1 week - Web compatibility
- **Phase 5 (v3.0.0)**: 2-4 weeks - Cleanup & advanced features

**Total:** 6-10 weeks for full implementation
