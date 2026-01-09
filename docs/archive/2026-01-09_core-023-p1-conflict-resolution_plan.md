# CORE-023 Part 1: Core Conflict Resolution (No LLM)

## Overview

Implement the foundation of `orchestrator resolve` - conflict detection, fast resolution strategies, and interactive escalation. **No LLM in Part 1** - that's Part 2.

## Scope: Part 1 Only

**In Scope:**
- Conflict detection (merge and rebase)
- Get base/ours/theirs from git refs
- Fast 3-way merge (diff3)
- rerere integration (read existing resolutions)
- Interactive escalation with analysis, options, recommendation
- CLI: `orchestrator resolve` (preview) + `--apply`
- Status integration (conflict warning)
- Basic validation (syntax check, no leftover markers)
- Rollback on failure
- Core unit and integration tests

**Explicitly NOT in Part 1 (see ROADMAP):**
- LLM-based resolution → Part 2
- Intent extraction from code → Part 2
- Learning/pattern detection → Part 3
- ROADMAP auto-suggestions → Part 3
- Config file system → Part 3
- Golden file tests, property-based tests → Part 2

## Resolution Philosophy: Rebase-First

**Target branch is truth. Adapt our changes to work with it.**

```
REBASE MINDSET:
  "Target is truth. Refactor our changes to be consistent with it."
```

| Scenario | Approach |
|----------|----------|
| Feature → main | Rebase: adapt our changes to main |
| PRD agent → integration | Rebase: agent adapts to integration |

---

## Part 1 Design

### Conflict Detection

```python
class GitConflictResolver:
    """Core resolver - Part 1 implementation."""

    def has_conflicts(self) -> bool:
        """Check if git is in conflict state."""
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            capture_output=True, text=True
        )
        return bool(result.stdout.strip())

    def is_rebase_conflict(self) -> bool:
        """Check if conflict is from rebase vs merge."""
        return (self.repo_path / ".git/rebase-merge").exists() or \
               (self.repo_path / ".git/rebase-apply").exists()

    def get_conflicted_files(self) -> list[str]:
        """Get list of files with conflicts."""
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            capture_output=True, text=True
        )
        return result.stdout.strip().split('\n') if result.stdout.strip() else []

    def get_conflict_info(self, file_path: str) -> ConflictedFile:
        """Get base/ours/theirs versions from git index."""
        base = self._git_show(f":1:{file_path}")    # Common ancestor
        ours = self._git_show(f":2:{file_path}")    # HEAD
        theirs = self._git_show(f":3:{file_path}")  # MERGE_HEAD
        return ConflictedFile(path=file_path, base=base, ours=ours, theirs=theirs)
```

### Resolution Strategies (Part 1 - No LLM)

```python
def resolve_file(self, file_path: str, strategy: str = "auto") -> ResolutionResult:
    """
    Resolve a single file - Part 1 strategies only.

    Strategy escalation for "auto":
    1. Check rerere for recorded resolution
    2. Try fast 3-way merge (git merge-file)
    3. If fails → escalate to interactive
    """
    conflict = self.get_conflict_info(file_path)

    # Strategy 1: Check rerere
    if strategy == "auto":
        rerere_result = self._check_rerere(file_path)
        if rerere_result:
            return ResolutionResult(
                file_path=file_path,
                resolved_content=rerere_result,
                strategy="rerere",
                confidence=0.95,
            )

    # Strategy 2: Fast 3-way merge
    if strategy in ("auto", "3way"):
        merge_result = self._try_3way_merge(conflict)
        if merge_result.success:
            return ResolutionResult(
                file_path=file_path,
                resolved_content=merge_result.content,
                strategy="3way",
                confidence=0.8,
            )

    # Strategy 3: Forced strategy
    if strategy == "ours":
        return ResolutionResult(file_path=file_path, resolved_content=conflict.ours,
                               strategy="ours", confidence=1.0)
    if strategy == "theirs":
        return ResolutionResult(file_path=file_path, resolved_content=conflict.theirs,
                               strategy="theirs", confidence=1.0)

    # Escalate to interactive
    return self._build_escalation(conflict)
```

### Interactive Escalation (Part 1)

When auto-resolution fails, present options to user:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  MANUAL DECISION REQUIRED: src/api/client.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONFLICT SUMMARY:
  Lines changed in OURS: 15-32 (added retry logic)
  Lines changed in THEIRS: 18-45 (added caching)
  Overlap: Lines 18-32

OPTIONS:
  [A] Keep OURS ⭐ RECOMMENDED (rebase-first: preserve our work)
      Keeps our changes, discards theirs

  [B] Keep THEIRS
      Accepts target branch, discards our changes

  [C] Keep BOTH (sequential)
      Concatenates both changes (may need manual cleanup)

  [D] Open in editor
      Opens file with conflict markers for manual resolution

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Enter choice [A/B/C/D] (default: A):
```

Note: Part 1 escalation is simpler than the full plan - no intent analysis, just structural analysis of what changed where.

### CLI Integration

```bash
# Default: preview mode (safe)
orchestrator resolve              # Show plan, don't execute

# Apply
orchestrator resolve --apply      # Actually resolve conflicts

# Modifiers
orchestrator resolve --apply --strategy ours    # Force ours for all
orchestrator resolve --apply --strategy theirs  # Force theirs for all
orchestrator resolve --apply --commit           # Auto-commit after

# Recovery
orchestrator resolve --abort      # Abort merge/rebase entirely
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All conflicts resolved successfully |
| 1 | Partial success (some resolved, some need manual) |
| 2 | Fatal error |
| 3 | Preview only (no --apply), conflicts exist |

### Status Integration

```python
def show_status():
    resolver = GitConflictResolver()
    if resolver.has_conflicts():
        conflict_type = "rebase" if resolver.is_rebase_conflict() else "merge"
        files = resolver.get_conflicted_files()
        print(f"""
⚠️  GIT {conflict_type.upper()} CONFLICT DETECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{len(files)} file(s) in conflict:
{chr(10).join(f'  • {f}' for f in files[:5])}

→ Run `orchestrator resolve` to resolve
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
```

### Validation (Part 1 - Basic)

```python
def _validate_resolution(self, file_path: str, content: str) -> tuple[bool, str]:
    """Basic validation - Part 1."""

    # Check for leftover conflict markers
    if "<<<<<<" in content or "======" in content or ">>>>>>" in content:
        return False, "Leftover conflict markers detected"

    # Syntax check for Python
    if file_path.endswith(".py"):
        try:
            ast.parse(content)
        except SyntaxError as e:
            return False, f"Python syntax error: {e}"

    return True, "OK"
```

### Rollback

```python
def _rollback_file(self, file_path: str):
    """Restore file to conflicted state."""
    subprocess.run(["git", "checkout", "--conflict=merge", file_path])

def _abort_merge(self):
    """Abort the entire merge/rebase."""
    if self.is_rebase_conflict():
        subprocess.run(["git", "rebase", "--abort"])
    else:
        subprocess.run(["git", "merge", "--abort"])
```

---

## Implementation Steps

### Step 1: Create `src/git_conflict_resolver.py`
- ConflictedFile dataclass
- ResolutionResult dataclass
- GitConflictResolver class
- Detection methods
- Resolution strategies (rerere, 3way, ours, theirs)
- Escalation builder (simplified)
- Validation
- Rollback

### Step 2: Add CLI command
- `resolve` subcommand in cli.py
- Flags: --apply, --strategy, --commit, --abort
- Exit codes

### Step 3: Status integration
- Check for conflicts in `orchestrator status`
- Display warning with suggested command

### Step 4: Basic tests
- Unit tests for detection
- Unit tests for resolution strategies
- Integration test with real git conflict

### Step 5: Documentation
- Add to CLAUDE.md

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `src/git_conflict_resolver.py` | CREATE | Core resolver |
| `src/cli.py` | MODIFY | Add `resolve` command |
| `tests/test_git_conflict_resolver.py` | CREATE | Unit tests |
| `tests/integration/test_resolve.py` | CREATE | Integration tests |
| `CLAUDE.md` | MODIFY | Document command |

---

## Success Criteria (Part 1)

### Core Functionality
- [ ] `orchestrator resolve` detects merge conflicts
- [ ] `orchestrator resolve` detects rebase conflicts
- [ ] Gets base/ours/theirs from git index
- [ ] rerere integration (reads existing resolutions)
- [ ] Fast 3-way merge works for non-overlapping changes
- [ ] `--strategy ours` and `--strategy theirs` work
- [ ] Default preview mode, `--apply` required to execute

### Escalation
- [ ] Interactive prompt when auto-resolution fails
- [ ] Shows conflict summary (lines changed)
- [ ] Options: A (ours), B (theirs), C (both), D (editor)
- [ ] Default recommendation (rebase-first: ours)
- [ ] Respects user choice

### Safety
- [ ] Validates no leftover conflict markers
- [ ] Validates Python syntax for .py files
- [ ] Rollback on validation failure
- [ ] `--abort` works for merge and rebase

### Integration
- [ ] `orchestrator status` shows conflict warning
- [ ] Exit codes: 0, 1, 2, 3

### Tests
- [ ] Unit tests for conflict detection
- [ ] Unit tests for resolution strategies
- [ ] Integration test with real git repo

---

## What's Deferred to Later Parts

See ROADMAP.md for:
- **CORE-023-P2**: LLM-based resolution, intent extraction, full test suite
- **CORE-023-P3**: Learning integration, ROADMAP auto-suggestions, config file
