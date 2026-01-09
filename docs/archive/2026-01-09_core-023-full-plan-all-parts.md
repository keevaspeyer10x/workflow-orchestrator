# CORE-023: Complete `orchestrator resolve` Implementation Plan

## Overview

Add a zero-argument `orchestrator resolve` command that automatically resolves merge conflicts when git is in a conflict state. Optimized for the common case: resolving conflicts between your work and the target branch.

**This is the FULL plan covering all 3 parts:**
- Part 1: Core resolution (no LLM)
- Part 2: LLM integration
- Part 3: Learning & config

---

## Scope

**Target scenario:**
```
Working on feature → merge/rebase to main → CONFLICT → resolve
```

Two-way merge (ours vs theirs), plus PRD multi-agent scenarios (common code).

## Resolution Philosophy: Rebase-First

**Key insight**: Don't treat both sides as equal. The target branch (main/theirs) is the source of truth. Our job is to adapt our changes to work with it.

```
MERGE MINDSET (complex):
  "Preserve both intents equally, find synthesis"

REBASE MINDSET (simpler):
  "Target is truth. Refactor our changes to be consistent with it."
```

### Why Rebase-First is Better

1. **Clear priority**: Target branch wins ties
2. **Simpler LLM task**: "Adapt this code to the new base" vs "merge two equals"
3. **Matches developer intuition**: "I need to update my code to work with main"
4. **Reduces ambiguity**: No "which intent matters more?" debates

### When to Use Each

| Scenario | Approach |
|----------|----------|
| Feature branch → main | Rebase: adapt our changes to main |
| Main → feature (sync) | Rebase: bring main's changes in, keep our structure |
| PRD agent → integration | Rebase: agent adapts to integration branch |
| Two PRD agents conflict | Merge: neither is "truth", need synthesis |

For the common case (developer merging to main), rebase-first is almost always right.

---

## Critical: Discoverability

**The user/AI cannot be relied on to remember this command exists.**

### Automatic Detection (3 layers)

1. **`orchestrator status` checks for conflicts** - shows warning with suggested command
2. **Startup hook** - detects conflicts on session start
3. **Workflow gates** - `orchestrator complete/advance` warns if conflicts exist

---

## Learning Integration

### During Resolution
Log every conflict resolution to `.workflow_log.jsonl`:
```python
log_event(EventType.CONFLICT_RESOLVED, {
    "file": "src/cli.py",
    "strategy": "sequential_merge",
    "confidence": 0.85,
    "resolution_time_ms": 1250,
})
```

### LEARN Phase → ROADMAP (Automatic)

**Key principle: Learnings become actionable roadmap items automatically.**

When patterns are detected:
```
LEARN phase detects:
  "src/cli.py conflicts in 4 of last 10 sessions"
       ↓
Automatically adds to ROADMAP.md:
       ↓
  #### AI-SUGGESTED: Reduce cli.py conflicts
  **Status:** Suggested
  **Source:** AI analysis (LEARN phase, 2026-01-09)
  **Evidence:** cli.py conflicted in 4/10 sessions

  **Recommendation:** Extract argument parsing to separate module
  to reduce merge conflict surface area.
       ↓
User is INFORMED (not asked):
  "ℹ️  Added AI suggestion to ROADMAP: Reduce cli.py conflicts"
```

---

## External Review Feedback

### Gemini Review - Incorporated:

1. **Tiered "auto" strategy**
   - First: Fast 3-way merge (no LLM)
   - Then: LLM-based resolution if needed
   - Efficient and cost-effective

2. **Post-resolution guardrail**
   - Auto-run build/tests after resolution
   - If fails → rollback (`git checkout --ours` / `git merge --abort`)
   - Never commit broken resolution

3. **Handle rebase + binary conflicts**
   - Detect rebase via `.git/rebase-merge` directory
   - Binary files: skip and require `ours`/`theirs` choice
   - Submodules: warn and skip

4. **Interactive fallback**
   - When confidence < threshold, don't fail
   - Prompt: "Cannot auto-resolve X. Choose: [o]urs / [t]heirs / [s]kip"

### OpenAI (GPT-5.2) Review - Incorporated:

1. **Rename/move conflict handling**
   - Handle: rename/rename, rename/modify, rename/delete, directory moves
   - Case-only renames (macOS/Windows path collisions)
   - Track content across renames using Git's rename detection

2. **Conflict marker validation**
   - Post-resolution check for leftover `<<<<<<<` markers
   - Validate with `git diff --check` and `git ls-files -u`
   - Sanity scan avoiding false positives in docs/code samples

3. **Rebase edge cases + rerere integration**
   - Handle repeated conflicts across multiple rebase commits
   - Integrate with `git rerere`:
     - Read existing rerere resolutions as higher-priority tier
     - Optionally record successful resolutions for future use
   - Define behavior for same file conflicting in multiple steps

4. **Special file types**
   - Submodules: SHA pointer conflicts, not text - require ours/theirs choice
   - Generated files (lockfiles, vendor): policy layer ("regenerate" vs "resolve")
   - Symlinks, filemode conflicts (100644 vs 100755), line endings
   - Respect `.gitattributes` merge drivers

5. **Enhanced safety gates**
   - Beyond build: lint/format checks if configured
   - Secret detection strategy: path globs, repo policy file, scanners
   - Auto-revert if resolution INCREASES conflict surface (more changes = suspicious)
   - Prevent sensitive context from leaking when resolving adjacent files

### Grok 4.1 Review - Incorporated:

1. **Mandatory preview mode (safety)**
   - Zero-arg auto-resolution is dangerous - users will lose hours to bad merges
   - Default to preview: `orchestrator resolve` shows plan, requires `--apply` to execute
   - Or: `orchestrator resolve --preview` then `orchestrator resolve --apply`
   - Prevents irreversible damage

2. **Configurable per-file policies**
   - Add `~/.orchestrator/config.yaml` for:
     - Sensitive globs: `['secrets/*', '*.pem', '.env*']`
     - Generated file policy: `delete | ours | theirs | regenerate`
     - LLM toggle: `disable_llm: true` for air-gapped environments
   - Default skip LLM for >10MB files or >50 conflicts (cost/timeout protection)

3. **Timeouts and partial success**
   - Build validation can take 5-30min in monorepos - needs timeout
   - Default 2min/file timeout with fallback to interactive
   - Log partial successes - don't halt entire resolution for one failure
   - Use stash-based per-file validation for safer rollback

### Claude (Opus 4.5) Review - Incorporated:

1. **Worktree/index state handling**
   - Check for unstaged/staged changes before resolution
   - Warn or refuse if uncommitted work could be lost during rollback
   - `git status --porcelain` check at start

2. **Partial resolution / interrupt handling**
   - What if Ctrl+C or crash mid-resolution?
   - State file to track resolved files: `.git/orchestrator-resolve-state`
   - Support `orchestrator resolve --continue` to resume
   - Atomic operations where possible

3. **LLM context window definition**
   - Define what gets sent to LLM:
     - Conflicted hunks + 50 lines surrounding context
     - File header and import statements
     - NOT entire file (token cost)
   - Max token budget per file (configurable)

4. **Exit codes and machine-readability**
   - Exit 0: All conflicts resolved successfully
   - Exit 1: Some resolved, some skipped/failed (partial success)
   - Exit 2: Fatal error (git state corrupt, etc.)
   - Add `--json` flag for CI/scripting integration

5. **Concurrent resolution safety**
   - Detect if another `orchestrator resolve` is running
   - Lock file: `.git/orchestrator-resolve.lock`
   - Fail fast with clear message if locked

---

## LLM Context Strategy

**Critical**: The LLM needs sufficient context to understand what both sides intended, not just the raw conflict hunks.

### Existing Infrastructure (Reuse)

| Module | What It Provides |
|--------|------------------|
| `ContextAssembler` | Related files (imports, callers), project conventions |
| `IntentExtractor` | What each side intended, constraints, compatibility analysis |

### Context Assembly Flow

```
1. CONFLICT DETECTION
   └── Get base/ours/theirs from git (:1:, :2:, :3:)

2. CONTEXT GATHERING (ContextAssembler)
   ├── Find related files (imports, callers of conflicted code)
   ├── Detect project conventions (naming, patterns)
   └── Get file structure context

3. INTENT ANALYSIS (IntentExtractor)
   ├── Extract "ours" intent: What were we trying to do?
   ├── Extract "theirs" intent: What were they trying to do?
   ├── Compare: Compatible? Conflicting? Orthogonal?
   └── Calculate confidence

4. BUILD LLM PROMPT
   ├── Conflict hunks with markers
   ├── Intent analysis summary
   ├── Related code snippets (limited to token budget)
   ├── Project conventions
   └── Explicit instructions based on intent comparison

5. LLM RESOLUTION (only if confidence >= medium)
   └── If low confidence → escalate to interactive
```

### Prompt Structure

```python
def build_llm_prompt(conflict: ConflictedFile, intent_analysis: IntentAnalysis, context: ConflictContext) -> str:
    """Build structured prompt for LLM resolution."""

    prompt = f"""
## Merge Conflict Resolution

### Intent Analysis
- Ours intended: {intent_analysis.intents[0].primary_intent}
- Theirs intended: {intent_analysis.intents[1].primary_intent}
- Relationship: {intent_analysis.comparison.relationship}
- Suggested approach: {intent_analysis.comparison.suggested_resolution}

### Constraints
Hard constraints (must satisfy):
{format_constraints(intent_analysis.hard_constraints)}

Soft constraints (prefer):
{format_constraints(intent_analysis.soft_constraints)}

### The Conflict
File: {conflict.path}

BASE (common ancestor):
```
{conflict.base_content}
```

OURS (our changes):
```
{conflict.ours_content}
```

THEIRS (their changes):
```
{conflict.theirs_content}
```

### Related Context
{format_related_context(context.related_files, max_tokens=2000)}

### Project Conventions
{format_conventions(context.conventions)}

### Task
Resolve this conflict by producing a merged version that:
1. Satisfies all hard constraints
2. Preserves the intent of both changes if compatible
3. If intents conflict, prefer the approach that {get_preference(intent_analysis)}
4. Follows project conventions

Output ONLY the resolved code, no explanations.
"""
    return prompt
```

### Token Budget Management

```python
@dataclass
class TokenBudget:
    """Controls how much context to send to LLM."""

    conflict_hunks: int = 4000      # The actual conflict
    intent_summary: int = 500        # Intent analysis
    related_code: int = 2000         # Imports, callers
    conventions: int = 300           # Style guide
    instructions: int = 500          # Task description

    total: int = 7300               # Well under 8k for most models

    # Scale down for large conflicts
    def scale_for_conflict_size(self, conflict_tokens: int):
        if conflict_tokens > 3000:
            self.related_code = 1000
            self.conventions = 200
```

### Confidence-Based Escalation

```python
def resolve_with_llm(conflict, intent_analysis, context):
    # Don't guess on low confidence
    if intent_analysis.overall_confidence == "low":
        return build_escalation(conflict, intent_analysis, context,
                                reason="Low confidence in intent analysis")

    # If intents are conflicting, escalate
    if intent_analysis.comparison.relationship == "conflicting":
        return build_escalation(conflict, intent_analysis, context,
                                reason="Conflicting intents detected")

    # Proceed with LLM resolution
    prompt = build_llm_prompt(conflict, intent_analysis, context)
    resolved = call_llm(prompt)

    # Validate the resolution
    if not validate_resolution(resolved, conflict, intent_analysis):
        return build_escalation(conflict, intent_analysis, context,
                                reason="Resolution failed validation")

    return ResolutionResult(
        resolved_content=resolved,
        strategy="llm",
        confidence=intent_analysis.overall_confidence
    )
```

### Human Escalation UX

**Critical**: When escalating, do the analysis work for the human. Don't expect them to read code.

```python
def build_escalation(conflict, intent_analysis, context, reason) -> EscalationResult:
    """Build a human-friendly escalation with analysis, options, and recommendation."""

    # Generate candidate resolutions
    candidates = generate_candidates(conflict, intent_analysis)

    # Analyze each candidate
    analyzed_options = []
    for i, candidate in enumerate(candidates):
        analyzed_options.append(AnalyzedOption(
            id=chr(65 + i),  # A, B, C...
            name=candidate.name,
            description=candidate.description,
            pros=candidate.pros,
            cons=candidate.cons,
            risk_level=assess_risk(candidate),
            preview=candidate.preview_diff,
        ))

    # Make a recommendation
    recommendation = pick_best_option(analyzed_options, intent_analysis)

    return EscalationResult(
        conflict=conflict,
        reason=reason,
        analysis=build_analysis_summary(intent_analysis),
        options=analyzed_options,
        recommendation=recommendation,
    )
```

### Escalation Output Format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  MANUAL DECISION REQUIRED: src/api/client.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REASON: Conflicting intents detected

ANALYSIS:
┌─────────────────────────────────────────────────────────────────────┐
│ OURS was trying to:                                                 │
│   Add retry logic to API calls for reliability                      │
│   Constraint: Must handle timeout errors                            │
│                                                                     │
│ THEIRS was trying to:                                               │
│   Add caching to API calls for performance                          │
│   Constraint: Cache must be invalidated on error                    │
│                                                                     │
│ CONFLICT: Both modify the same function signature and error handling│
└─────────────────────────────────────────────────────────────────────┘

OPTIONS:

  [A] Keep OURS (retry logic) ⭐ RECOMMENDED
      ✓ Reliability is typically more important than performance
      ✓ Retry logic can work with caching added later
      ✗ Loses caching performance benefit
      Risk: LOW

  [B] Keep THEIRS (caching)
      ✓ Better performance
      ✗ No retry on failures - less reliable
      ✗ Harder to add retry logic to cached calls later
      Risk: MEDIUM

  [C] Combine both (retry + caching)
      ✓ Gets both benefits
      ✗ Complex interaction: should retry use cache?
      ✗ Needs careful thought about cache invalidation on retry
      Risk: MEDIUM - may have subtle bugs

  [D] View full diff and decide manually
      Opens conflicted file in editor

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Enter choice [A/B/C/D] (default: A):
```

### Making It Easy

The human should be able to:
1. **Scan in 10 seconds**: See the conflict summary and recommendation
2. **Decide in 30 seconds**: Pick A/B/C or accept default
3. **Press Enter for default**: Recommendation is pre-selected

---

## Design

### New Module: `src/git_conflict_resolver.py`

```python
@dataclass
class ConflictedFile:
    """A file in git conflict state."""
    path: str
    base_content: Optional[str]   # :1: - may be None for new files
    ours_content: str             # :2: - our version (HEAD)
    theirs_content: str           # :3: - their version (MERGE_HEAD)
    is_binary: bool = False

@dataclass
class ResolutionResult:
    """Result of resolving a conflict."""
    file_path: str
    resolved_content: Optional[str]  # None if skipped
    strategy: str          # "sequential", "ours", "theirs", "skipped", "manual"
    confidence: float
    requires_review: bool  # True if low confidence

class GitConflictResolver:
    """
    Resolves git merge conflicts from current repository state.
    """

    def __init__(self, repo_path: Path = None):
        self.repo_path = repo_path or Path.cwd()

    # Detection
    def has_conflicts(self) -> bool:
        """Check if git is in conflict state (merge or rebase)."""

    def is_rebase_conflict(self) -> bool:
        """Check if conflict is from rebase (vs merge)."""
        return (self.repo_path / ".git/rebase-merge").exists()

    def get_conflicted_files(self) -> list[str]:
        """Get list of files with conflicts."""

    def get_conflict_info(self, file_path: str) -> ConflictedFile:
        """Get base/ours/theirs versions."""

    # Resolution
    def resolve_file(self, file_path: str, strategy: str = "auto") -> ResolutionResult:
        """
        Resolve a single file.

        Strategy escalation for "auto":
        1. Try fast 3-way merge (diff3)
        2. If fails, try sequential (non-overlapping changes)
        3. If fails, try LLM-based resolution
        4. If low confidence, mark for interactive choice
        """

    def resolve_all(
        self,
        dry_run: bool = False,
        commit: bool = False,
        verify_build: bool = True,
        interactive: bool = True,  # Prompt for low-confidence
    ) -> list[ResolutionResult]:
        """Resolve all conflicts."""

    # Guardrails
    def _verify_resolution(self) -> tuple[bool, str]:
        """Run build/tests to verify resolution is valid."""

    def _rollback(self):
        """Rollback failed resolution."""
        # For merge: git merge --abort or git checkout --conflict=merge
        # For rebase: git rebase --abort

    # Logging
    def _log_resolution(self, result: ResolutionResult):
        """Log for LEARN phase analysis."""
```

### CLI Integration

```bash
# Default: preview mode (safe)
orchestrator resolve              # Show plan, don't execute
orchestrator resolve --apply      # Actually resolve conflicts

# Modifiers
orchestrator resolve --apply --commit     # Resolve + auto-commit
orchestrator resolve --apply --no-verify  # Skip build check
orchestrator resolve --apply --no-interactive  # Fail instead of prompt
orchestrator resolve --apply --strategy ours   # Force strategy for all

# Recovery
orchestrator resolve --continue   # Resume interrupted resolution
orchestrator resolve --abort      # Abort and restore original state

# Output
orchestrator resolve --json       # Machine-readable output for CI
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All conflicts resolved successfully |
| 1 | Partial success (some resolved, some skipped) |
| 2 | Fatal error (corrupt state, locked, etc.) |
| 3 | Preview only (no --apply), conflicts exist |

### Status Integration

```python
def show_status():
    # Check for git conflicts FIRST
    resolver = GitConflictResolver()
    if resolver.has_conflicts():
        conflict_type = "rebase" if resolver.is_rebase_conflict() else "merge"
        files = resolver.get_conflicted_files()
        print(f"""
⚠️  GIT {conflict_type.upper()} CONFLICT DETECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{len(files)} file(s) in conflict:
{chr(10).join(f'  • {f}' for f in files[:5])}
{'  ...' if len(files) > 5 else ''}

→ Run `orchestrator resolve` to auto-resolve
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")

    # ... rest of status ...
```

---

## PRD Integration

**Requirement**: The resolver must work for both CLI usage and PRD parallel execution, using common code.

### Shared Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    SHARED RESOLUTION CORE                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ GitConflict  │  │ Intent       │  │ Resolution           │  │
│  │ Resolver     │  │ Extractor    │  │ Pipeline             │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Context      │  │ Escalation   │  │ Validation           │  │
│  │ Assembler    │  │ Builder      │  │ Engine               │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                            ▲
            ┌───────────────┼───────────────┐
            │               │               │
     ┌──────┴──────┐ ┌──────┴──────┐ ┌──────┴──────┐
     │ CLI Command │ │ PRD Wave    │ │ PRD Agent   │
     │ orchestrator│ │ Resolver    │ │ Merge       │
     │ resolve     │ │             │ │             │
     └─────────────┘ └─────────────┘ └─────────────┘
```

### Integration Points

```python
# src/git_conflict_resolver.py - shared core
class GitConflictResolver:
    """Used by both CLI and PRD workflows."""

    def resolve_conflicts(
        self,
        mode: Literal["rebase", "merge"] = "rebase",
        source_of_truth: str = "theirs",  # For rebase mode
        interactive: bool = True,
        context: Optional[PRDContext] = None,  # PRD provides extra context
    ) -> list[ResolutionResult]:
        ...

# src/cli.py - CLI entry point
def cmd_resolve(args):
    resolver = GitConflictResolver()
    results = resolver.resolve_conflicts(
        interactive=not args.no_interactive,
    )

# src/prd/wave_resolver.py - PRD entry point
class WaveResolver:
    def resolve_agent_conflicts(self, agent_branches, prd_context):
        resolver = GitConflictResolver()
        for branch in agent_branches:
            # Merge agent to integration branch
            results = resolver.resolve_conflicts(
                mode="rebase",
                source_of_truth="integration",
                context=prd_context,  # Includes manifests, task descriptions
            )
```

### PRD Context Advantage

When called from PRD workflows, we have richer context:
- Agent manifests with task descriptions
- Explicit decisions and reasoning
- Known agent IDs and relationships

```python
@dataclass
class PRDContext:
    """Extra context available in PRD workflows."""
    agent_id: str
    task_description: str
    manifest: Optional[AgentManifest]
    prd_id: str
    integration_branch: str
```

This makes intent extraction much more reliable for PRD conflicts.

---

## Comprehensive Testing Strategy

Given the complexity and risk of automated conflict resolution, testing is critical.

### Test Pyramid

```
                    ┌───────────────┐
                    │  E2E Tests    │  ← Real git repos, real conflicts
                    │  (10 tests)   │
                ┌───┴───────────────┴───┐
                │  Integration Tests    │  ← Git operations, file I/O
                │  (50 tests)           │
            ┌───┴───────────────────────┴───┐
            │  Unit Tests                   │  ← Logic, parsing, analysis
            │  (200+ tests)                 │
        ────┴───────────────────────────────┴────
```

### 1. Unit Tests

**Conflict Detection** (`test_conflict_detection.py`)
```python
def test_detect_merge_conflict():
def test_detect_rebase_conflict():
def test_detect_no_conflict():
def test_get_conflicted_files():
def test_get_base_ours_theirs_content():
def test_detect_binary_file():
def test_detect_rename_conflict():
def test_detect_submodule_conflict():
```

**Intent Extraction** (`test_intent_extraction.py`)
```python
def test_extract_intent_from_manifest():
def test_extract_intent_from_code_only():
def test_extract_intent_from_commit_message():
def test_compare_compatible_intents():
def test_compare_conflicting_intents():
def test_compare_orthogonal_intents():
def test_confidence_calculation():
```

**Resolution Strategies** (`test_resolution_strategies.py`)
```python
def test_fast_3way_merge_success():
def test_fast_3way_merge_conflict():
def test_sequential_merge_non_overlapping():
def test_sequential_merge_overlapping():
def test_rebase_strategy_adapts_code():
def test_escalation_on_low_confidence():
```

**Escalation Builder** (`test_escalation.py`)
```python
def test_generate_options():
def test_analyze_pros_cons():
def test_pick_recommendation():
def test_format_escalation_output():
```

### 2. Integration Tests

**Git Operations** (`test_git_integration.py`)
```python
@pytest.fixture
def temp_git_repo():
    """Create a temporary git repo with conflict."""
    ...

def test_resolve_simple_conflict(temp_git_repo):
def test_resolve_multiple_files(temp_git_repo):
def test_rollback_on_validation_failure(temp_git_repo):
def test_state_file_created_and_cleaned(temp_git_repo):
def test_lock_prevents_concurrent_resolution(temp_git_repo):
def test_continue_after_interrupt(temp_git_repo):
```

**CLI Integration** (`test_cli_integration.py`)
```python
def test_resolve_preview_mode():
def test_resolve_apply_mode():
def test_resolve_dry_run():
def test_resolve_commit_flag():
def test_resolve_json_output():
def test_status_shows_conflict_warning():
def test_exit_codes():
```

### 3. Golden File Tests

Test against known conflict patterns with expected resolutions:

```
tests/golden/
├── simple_function_edit/
│   ├── base.py
│   ├── ours.py
│   ├── theirs.py
│   └── expected.py
├── import_conflict/
│   ├── base.py
│   ├── ours.py
│   ├── theirs.py
│   └── expected.py
├── class_method_conflict/
│   └── ...
├── config_file_conflict/
│   └── ...
└── README.md  # Documents each case
```

```python
@pytest.mark.parametrize("case", list_golden_cases())
def test_golden_resolution(case):
    base, ours, theirs, expected = load_golden_case(case)
    result = resolve_conflict(base, ours, theirs)
    assert result == expected, f"Golden test {case} failed"
```

### 4. Property-Based Tests (Fuzzing)

Use Hypothesis to find edge cases:

```python
from hypothesis import given, strategies as st

@given(
    base=st.text(min_size=10, max_size=1000),
    ours_changes=st.lists(st.tuples(st.integers(), st.text())),
    theirs_changes=st.lists(st.tuples(st.integers(), st.text())),
)
def test_resolution_never_crashes(base, ours_changes, theirs_changes):
    """Resolution should never crash, only escalate."""
    ours = apply_changes(base, ours_changes)
    theirs = apply_changes(base, theirs_changes)

    result = resolve_conflict(base, ours, theirs)

    # Should either resolve or escalate, never crash
    assert result.strategy in ["resolved", "escalate"]

@given(conflict=conflict_strategy())
def test_resolution_preserves_syntax(conflict):
    """Resolved Python should be syntactically valid."""
    result = resolve_conflict(conflict.base, conflict.ours, conflict.theirs)
    if result.strategy == "resolved" and conflict.path.endswith(".py"):
        # Should parse without SyntaxError
        ast.parse(result.content)
```

### 5. Regression Tests

Capture real-world failures as regression tests:

```python
# tests/regressions/test_real_world.py

def test_regression_cli_argument_conflict():
    """
    Regression: Issue #123
    CLI argument parsing conflict caused infinite loop.
    """
    ...

def test_regression_unicode_in_conflict_markers():
    """
    Regression: Issue #145
    Unicode characters in conflict markers broke parser.
    """
    ...
```

### 6. LLM Resolution Tests

Test LLM integration with mocked responses:

```python
def test_llm_prompt_structure():
    """Verify prompt contains required sections."""
    prompt = build_llm_prompt(conflict, intent, context)
    assert "Intent Analysis" in prompt
    assert "BASE" in prompt
    assert "OURS" in prompt
    assert "THEIRS" in prompt

def test_llm_response_parsing():
    """Verify we correctly parse LLM output."""
    mock_response = "```python\ndef foo(): pass\n```"
    result = parse_llm_response(mock_response)
    assert result == "def foo(): pass"

@pytest.mark.llm  # Marked for optional real LLM tests
def test_llm_resolution_quality():
    """Test with real LLM (expensive, run sparingly)."""
    ...
```

### 7. PRD Integration Tests

```python
def test_prd_wave_resolver_uses_git_conflict_resolver():
    """WaveResolver should delegate to GitConflictResolver."""
    ...

def test_prd_context_improves_intent_extraction():
    """With PRD context, intent extraction should be higher confidence."""
    ...

def test_prd_manifest_used_for_resolution():
    """Agent manifest should inform resolution strategy."""
    ...
```

### Test Coverage Targets

| Component | Target | Rationale |
|-----------|--------|-----------|
| Conflict detection | 95% | Core safety |
| Intent extraction | 90% | Complex logic |
| Resolution strategies | 90% | Core functionality |
| Escalation | 85% | UX, less critical |
| CLI integration | 80% | Thin layer |
| Git operations | 75% | Hard to test exhaustively |

---

## Success Criteria

### Core Functionality
- [ ] `orchestrator resolve` detects and resolves conflicts
- [ ] Handles both merge and rebase conflicts
- [ ] Tiered strategy: rerere → fast 3-way → recursive → LLM → interactive
- [ ] Default preview mode (safe), require `--apply` to execute

### Edge Cases (from GPT-5.2)
- [ ] Rename/move conflicts handled (rename/rename, rename/delete, etc.)
- [ ] Conflict marker validation post-resolution (`git diff --check`)
- [ ] Rebase repeated conflicts handled correctly
- [ ] `git rerere` integration (read existing, optionally record new)

### Special Files
- [ ] Binary files: notify user, require explicit choice
- [ ] Submodules: detect and require ours/theirs
- [ ] Generated files: policy-based handling
- [ ] Respect `.gitattributes` merge drivers

### Security
- [ ] Sensitive files skip LLM resolution
- [ ] Secret detection via path globs / policy file
- [ ] No sensitive context leaked to adjacent file resolution
- [ ] LLM context limited (hunks + context, not full files)

### Safety (from Grok + Claude)
- [ ] Check worktree state before resolution (warn on uncommitted changes)
- [ ] Post-resolution build/lint validation with timeout (2min default)
- [ ] Granular rollback on failure (per-file, not all-or-nothing)
- [ ] Auto-revert if resolution increases conflict surface
- [ ] Lock file prevents concurrent resolution
- [ ] State file enables `--continue` after interrupt

### Configuration
- [ ] `~/.orchestrator/config.yaml` for policies
- [ ] Sensitive globs configurable
- [ ] LLM disable option for air-gapped environments
- [ ] Skip LLM for >10MB files or >50 conflicts

### Integration
- [ ] `orchestrator status` shows conflict warning
- [ ] Resolutions logged with full telemetry
- [ ] Patterns auto-generate ROADMAP suggestions
- [ ] Exit codes: 0 (success), 1 (partial), 2 (fatal), 3 (preview)
- [ ] `--json` output for CI/scripting

---

## Implementation Phasing

### Part 1: Core (No LLM) - FIRST
- Conflict detection
- rerere + 3-way merge
- Interactive escalation (simple)
- CLI basics
- Status integration
- Basic tests

### Part 2: LLM Integration - SECOND
- LLM resolution (opt-in)
- Intent extraction
- Context assembly
- Full test suite
- PRD integration

### Part 3: Learning & Config - THIRD
- LEARN phase integration
- ROADMAP auto-suggestions
- Config file system
