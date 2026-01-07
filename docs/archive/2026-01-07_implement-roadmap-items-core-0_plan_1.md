# Implementation Plan: Workflow Improvements WF-005 through WF-009

## Executive Summary

Implement 5 workflow improvements to make the development process more autonomous and robust:
- **WF-008** (Priority): AI critique at phase gates for early issue detection
- **WF-005**: Summary before approval gates for informed decisions
- **WF-009**: Document phase for consistent documentation updates
- **WF-006**: File links in status output for faster review
- **WF-007**: Learnings to roadmap pipeline for continuous improvement

## Implementation Order

Based on the goal of **autonomous and robust development**, prioritized by impact:

1. **WF-008: AI Critique at Phase Gates** (HIGH - enables autonomous quality)
2. **WF-005: Summary Before Approval Gates** (HIGH - enables informed decisions)
3. **WF-009: Document Phase** (MEDIUM - workflow.yaml change)
4. **WF-006: File Links in Status** (LOW - metadata enhancement)
5. **WF-007: Learnings to Roadmap** (LOW - requires AI parsing)

---

## Phase 1: WF-008 - AI Critique at Phase Gates

### Goal
Add lightweight AI critique at each phase transition to catch issues early, before they compound.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     cmd_advance() in cli.py                      │
├─────────────────────────────────────────────────────────────────┤
│ 1. Check can_advance_phase()                                     │
│ 2. Collect critique context (items, git diff, constraints)       │
│ 3. Call PhaseCritique.run() → ReviewRouter → gemini-2.0-flash   │
│ 4. Display critique results                                      │
│ 5. If critical issues: prompt user (continue/address)            │
│ 6. Execute advance_phase()                                       │
└─────────────────────────────────────────────────────────────────┘
```

### New Files
- `src/critique.py` - PhaseCritique class

### Modified Files
- `src/cli.py` - Integrate critique into cmd_advance()
- `src/default_workflow.yaml` - Add `phase_critique: true` setting
- `workflow.yaml` - Add `phase_critique: true` setting

### Implementation Details

```python
# src/critique.py
class PhaseCritique:
    """Lightweight AI critique at phase transitions."""

    def __init__(self, working_dir: Path):
        self.working_dir = working_dir
        self.router = ReviewRouter(working_dir, context_limit=8000)

    def collect_context(self, engine: WorkflowEngine) -> dict:
        """Gather context for critique."""
        return {
            "task": engine.state.task_description,
            "constraints": engine.state.constraints,
            "current_phase": engine.state.current_phase_id,
            "next_phase": self._get_next_phase_id(engine),
            "completed_items": self._get_completed_items(engine),
            "skipped_items": engine.get_skipped_items(engine.state.current_phase_id),
            "git_diff_stat": self._get_git_diff_stat(),
        }

    def run(self, context: dict, transition: str) -> CritiqueResult:
        """Run critique for a specific transition."""
        prompt = CRITIQUE_PROMPTS[transition].format(**context)
        result = self.router.execute_review("critique", prompt)
        return CritiqueResult.from_review(result)

class CritiqueResult:
    observations: list[Observation]  # warnings, passes
    recommendation: str
    should_block: bool  # True if critical issues found
```

### Critique Prompts by Transition

| Transition | Focus Areas |
|------------|-------------|
| PLAN → EXECUTE | Requirements clarity, risk identification, test strategy |
| EXECUTE → REVIEW | All items complete, tests passing, no TODO comments |
| REVIEW → VERIFY | Review findings addressed, no unresolved issues |
| VERIFY → LEARN | Verification passed, any remaining concerns |

### Configuration

```yaml
# workflow.yaml
settings:
  phase_critique: true  # Enable/disable critique
  critique_model: "latest"  # Use latest available model (resolves via ModelRegistry)
  critique_block_on_critical: true  # Block on critical issues
```

**Note:** The `critique_model: "latest"` setting uses the ModelRegistry (CORE-017) to resolve to the current best model (e.g., Gemini 3 Pro when available). This ensures critique always uses cutting-edge models.

---

## Phase 2: WF-005 - Summary Before Approval Gates

### Goal
Show a concise summary before any manual approval gate to enable informed decisions.

### Modified Files
- `src/cli.py` - Add `generate_phase_summary()`, integrate into `cmd_advance()`

### Implementation Details

```python
def generate_phase_summary(engine: WorkflowEngine) -> str:
    """Generate summary of current phase for approval."""
    phase_id = engine.state.current_phase_id
    phase = engine.state.phases[phase_id]

    # Completed items with notes
    completed = [(id, item.notes) for id, item in phase.items.items()
                 if item.status == ItemStatus.COMPLETED]

    # Skipped items with reasons
    skipped = engine.get_skipped_items(phase_id)

    # Git diff stat
    diff_stat = subprocess.run(
        ["git", "diff", "--stat", "HEAD~5"],  # Last 5 commits
        capture_output=True, text=True
    ).stdout

    return format_summary(completed, skipped, diff_stat)
```

### Output Format
```
============================================================
📋 PHASE SUMMARY: EXECUTE → REVIEW
============================================================
Completed Items (4):
  ✓ implement_core_logic - "Added PhaseCritique class"
  ✓ write_unit_tests - "23 tests, all passing"
  ...

Skipped Items (1):
  ⊘ performance_tests - "Deferred - not applicable"

Files Modified (since phase start):
  src/critique.py | 145 ++++++++++++
  src/cli.py      |  42 ++++--
  tests/test_critique.py | 89 ++++++++
  3 files changed, 276 insertions(+), 8 deletions(-)

Ready to advance to REVIEW phase? [Y/n]
============================================================
```

---

## Phase 3: WF-009 - Document Phase

### Goal
Add optional DOCUMENT phase to ensure documentation stays current.

### Modified Files
- `src/default_workflow.yaml` - Add DOCUMENT phase
- `workflow.yaml` - Add DOCUMENT phase

### Phase Definition

```yaml
- id: DOCUMENT
  name: Documentation Update
  type: documentation
  description: Update documentation to reflect changes
  items:
    - id: update_readme
      name: Update README if needed
      description: Review and update README.md for any new features or changes
      optional: true
    - id: update_setup_guide
      name: Update setup/installation instructions
      description: Ensure setup guides reflect current installation process
      optional: true
    - id: update_api_docs
      name: Update API documentation
      description: Document any new CLI commands or options
      optional: true
    - id: changelog_entry
      name: Add changelog entry
      description: Document changes in CHANGELOG.md
      required: true
      gate: manual
```

---

## Phase 4: WF-006 - File Links in Status Output

### Goal
Include file paths in completion metadata for faster human review.

### Modified Files
- `src/schema.py` - Add `files_modified` field to ItemState
- `src/engine.py` - Track files on item completion
- `src/cli.py` - Display files in status output

### Implementation Details

```python
# src/schema.py - Add to ItemState
class ItemState:
    # ... existing fields ...
    files_modified: Optional[list[str]] = None  # New field

# src/engine.py - Track files on completion
def complete_item(self, item_id: str, notes: str = "", files: list[str] = None):
    # ... existing logic ...
    if files is None:
        # Auto-detect from git diff
        files = self._get_changed_files_since_item_start()
    item.files_modified = files
```

---

## Phase 5: WF-007 - Learnings to Roadmap Pipeline

### Goal
Automatically suggest roadmap items from captured learnings.

### New Files
- `src/learnings_pipeline.py` - Parse learnings and suggest roadmap items

### Implementation Details

```python
def analyze_learnings(learnings_file: Path) -> list[RoadmapSuggestion]:
    """Parse learnings for actionable patterns."""
    patterns = [
        r"should (\w+)",
        r"next time (\w+)",
        r"need to (\w+)",
        r"could improve (\w+)",
    ]
    # ... pattern matching and suggestion generation
```

---

## Test Strategy

| Feature | Test Count | Type |
|---------|------------|------|
| WF-008 Critique | 15 | Unit + Integration |
| WF-005 Summary | 8 | Unit |
| WF-009 Document Phase | 5 | Integration |
| WF-006 File Links | 10 | Unit |
| WF-007 Learnings | 8 | Unit |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Critique API failures | Medium | Low | Graceful fallback (continue without critique) |
| Critique too slow | Low | Medium | Use fast model (gemini-flash), timeout |
| Over-blocking | Medium | High | Advisory mode by default |
| Context too large | Medium | Medium | Truncate to 8k tokens |

---

## Success Criteria

1. **WF-008**: AI critique runs at each phase transition, catching at least 1 issue in 5 workflows
2. **WF-005**: Summary displayed before every advance command
3. **WF-009**: DOCUMENT phase appears in workflow.yaml
4. **WF-006**: Files appear in status output for completed items
5. **WF-007**: Learnings suggest at least one roadmap item when actionable patterns found

---

## Timeline

| Phase | Items | Effort |
|-------|-------|--------|
| 1: WF-008 | Critique class, prompts, CLI integration | ~2 hours |
| 2: WF-005 | Summary generation | ~1 hour |
| 3: WF-009 | Workflow.yaml update | ~15 min |
| 4: WF-006 | File tracking | ~1 hour |
| 5: WF-007 | Learnings pipeline | ~1.5 hours |
| Testing | All features | ~1 hour |

**Total: ~7 hours**
