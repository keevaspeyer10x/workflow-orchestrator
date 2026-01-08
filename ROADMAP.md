# Workflow Orchestrator Roadmap

This document tracks **planned** improvements, deferred features, and audit recommendations.

For completed features, see [CHANGELOG.md](CHANGELOG.md).

---

## Planned Improvements

> Items identified during v2.2 implementation for future work

### Critical - Blocking Parallel Execution

#### PRD-004: Fix or Replace Claude Squad Integration
**Status:** BLOCKED - Current integration non-functional
**Complexity:** High
**Priority:** CRITICAL - Spawning feature is completely broken
**Source:** Dogfood testing 2026-01-09

**Description:** The Claude Squad integration (PRD-001) is non-functional. The `squad_adapter.py` was designed expecting a CLI interface that doesn't exist.

**Problem:**
Our adapter expects commands like:
```bash
claude-squad new --name X --dir Y --prompt-file Z
claude-squad list --json
claude-squad attach <session>
```

But Claude Squad (`cs`) is a **TUI (Terminal User Interface)** - you launch it interactively and use keyboard commands (`n` for new, etc.). There is no programmatic CLI.

**Impact:**
- `orchestrator prd spawn` falls back to "manual" mode
- No actual parallel agent spawning occurs
- PRD-001 Phase 1 "Complete" status is misleading
- The entire spawning subsystem is untestable

**Options:**

| Option | Pros | Cons |
|--------|------|------|
| **A: Fix Claude Squad integration** | Reuse existing tool | May require upstream changes to `cs`; TUI not designed for automation |
| **B: Direct tmux management** | Full control; no external deps | Reinvent wheel; session management complexity |
| **C: Use Happy API** | User already uses Happy; mobile access | Requires Happy API; coupling to specific tool |
| **D: Simple subprocess spawning** | Minimal complexity | No session management; orphan risk |

**Recommended: Option B or D**

Option B (direct tmux) gives us control without depending on external TUI tools:
```python
# Direct tmux approach
def spawn_session(task_id: str, prompt: str, working_dir: Path):
    session_name = f"wfo-{task_id}"
    subprocess.run(["tmux", "new-session", "-d", "-s", session_name, "-c", str(working_dir)])
    subprocess.run(["tmux", "send-keys", "-t", session_name, f"claude --print '{prompt}'", "Enter"])
```

Option D (simple subprocess) is even simpler for non-interactive batch execution.

**Tasks:**
- [ ] Decide on approach (A/B/C/D)
- [ ] If B: Implement direct tmux session management
- [ ] If D: Implement simple subprocess spawning
- [ ] Remove or deprecate broken Claude Squad adapter
- [ ] Update capability detection for chosen approach
- [ ] Add integration tests that actually spawn agents
- [ ] Update documentation

**Files Affected:**
- `src/prd/squad_adapter.py` - Replace or fix
- `src/prd/squad_capabilities.py` - Update for new approach
- `src/prd/backend_selector.py` - Update mode detection
- `tests/prd/test_squad_adapter.py` - Fix tests

---

#### CORE-023: Simple `orchestrator resolve` for Merge Conflicts
**Status:** Planned
**Complexity:** Medium
**Priority:** CRITICAL - Blocks parallel execution
**Source:** User request - Cannot run multiple Claude Code instances in parallel without this

**Description:** Add a zero-argument `orchestrator resolve` command that automatically resolves merge conflicts when git is in a conflict state. No branch specification needed - git already knows everything.

**Problem Solved:**
When running multiple Claude Code instances (or any parallel AI agents) independently, merge conflicts occur. The existing sophisticated conflict resolution pipeline (semantic analysis, interface harmonization, build testing) is only accessible through PRD workflows with explicit branch arguments. Users need a frictionless way to resolve conflicts without ceremony.

**Desired Behavior:**
```bash
git merge some-branch
# CONFLICT in src/api/client.py

orchestrator resolve
# ✓ Detected 1 conflict in src/api/client.py
# ✓ Analyzing conflict context...
# ✓ Applied semantic merge strategy
# ✓ Resolved src/api/client.py
# ✓ Build verification passed
#
# Conflicts resolved. Run `git commit` to complete the merge.
```

**How It Works:**
1. Detect conflict state via `git diff --name-only --diff-filter=U`
2. If no conflicts, exit with "No merge conflicts detected"
3. For each conflicted file:
   - Get base/ours/theirs via `git show :1:file`, `:2:file`, `:3:file`
   - Get MERGE_HEAD info from `.git/MERGE_HEAD`
   - Run existing conflict resolution pipeline
4. Stage resolved files with `git add`
5. Optionally verify build passes
6. User runs `git commit` (or use `--commit` flag)

**CLI Interface:**
```bash
# Basic - just resolve conflicts
orchestrator resolve

# With options (for power users/agents)
orchestrator resolve --dry-run          # Show what would be done
orchestrator resolve --strategy semantic # Force specific strategy
orchestrator resolve --commit           # Auto-commit after resolving
orchestrator resolve --no-build-check   # Skip build verification
```

**Integration with Existing Code:**
- Reuse `src/conflict/detector.py` - ConflictDetector
- Reuse `src/conflict/pipeline.py` - DetectionPipeline
- Reuse `src/resolution/harmonizer.py` - InterfaceHarmonizer
- Reuse `src/resolution/intent.py` - IntentAnalyzer
- NEW: `src/git_conflict_resolver.py` - Wrapper that gets conflict info from git state

**Key Principle:**
Zero configuration for the user. Git already knows:
- Which files have conflicts
- What the base/ours/theirs versions are
- What branch is being merged (MERGE_HEAD)

The command just reads this state and applies resolution.

**Tasks:**
- [ ] Create `src/git_conflict_resolver.py` to extract conflict state from git
- [ ] Add `resolve` command to CLI
- [ ] Wire up existing ConflictDetector with git state
- [ ] Wire up existing resolution pipeline
- [ ] Add `--dry-run` flag
- [ ] Add `--commit` flag
- [ ] Add `--no-build-check` flag
- [ ] Add tests for git state extraction
- [ ] Add tests for resolution flow
- [ ] Document in CLAUDE.md

**Why Critical:**
Without this, users cannot safely run multiple Claude Code instances in parallel because merge conflicts require manual resolution. This is the missing piece for practical parallel AI agent execution outside of the full PRD workflow.

---

#### CORE-024: Session Transcript Logging with Secret Scrubbing
**Status:** Planned
**Complexity:** Medium
**Priority:** High
**Source:** User request - Need visibility into session failures and patterns

**Description:** Log all orchestrator session transcripts with automatic secret scrubbing to enable debugging and pattern analysis without exposing sensitive data.

**Problem Solved:**
When workflows fail or behave unexpectedly, there's no record of what happened. Session transcripts would reveal patterns (e.g., "context compaction causes 80% of workflow abandonment") but raw transcripts may contain API keys, passwords, and other secrets.

**Desired Behavior:**
```bash
# Sessions automatically logged to .workflow_sessions/
ls .workflow_sessions/
# 2026-01-09_14-32-15_auth-feature.log
# 2026-01-09_16-45-22_bugfix-api.log

# View a session (secrets already scrubbed)
cat .workflow_sessions/2026-01-09_14-32-15_auth-feature.log
# ... transcript with [REDACTED:OPENAI_API_KEY] instead of actual key ...

# Analyze patterns
orchestrator sessions analyze --last 30
# Workflow completion rate: 67%
# Most common failure point: REVIEW phase (context compaction)
# Average session duration: 45 minutes
```

**Secret Scrubbing Strategy (Hybrid):**

1. **Known-secret replacement** (precise):
   - Load secrets from SecretsManager (SOPS, env, etc.)
   - Replace exact matches with `[REDACTED:SECRET_NAME]`
   - Handles: API keys, passwords, tokens you've configured

2. **Pattern-based scrubbing** (safety net):
   - Common API key formats: `sk-...`, `ghp_...`, `xai-...`, `pk_live_...`
   - Bearer tokens: `Bearer [a-zA-Z0-9_-]+`
   - Base64-encoded credentials
   - Email:password patterns

3. **Configurable patterns**:
   ```yaml
   # workflow.yaml or .orchestrator.yaml
   logging:
     scrub_patterns:
       - 'custom_secret_\w+'
       - 'internal_token_[a-f0-9]+'
   ```

**Storage & Retention:**
- Location: `.workflow_sessions/` (gitignored by default)
- Rotation: Keep last N sessions or last N days (configurable)
- Format: JSONL for structured analysis, or plain text for readability

**CLI Commands:**
```bash
orchestrator sessions list              # List recent sessions
orchestrator sessions show <id>         # View specific session
orchestrator sessions analyze           # Pattern analysis
orchestrator sessions clean --older 30d # Clean old sessions
```

**Implementation Notes:**
```python
class TranscriptLogger:
    def __init__(self, secrets_manager: SecretsManager):
        self.secrets = secrets_manager.get_all_secrets()
        self.patterns = self._load_scrub_patterns()

    def scrub(self, text: str) -> str:
        # 1. Replace known secrets
        for name, value in self.secrets.items():
            text = text.replace(value, f"[REDACTED:{name}]")

        # 2. Apply regex patterns
        for pattern in self.patterns:
            text = re.sub(pattern, "[REDACTED:PATTERN_MATCH]", text)

        return text

    def log(self, session_id: str, content: str):
        scrubbed = self.scrub(content)
        path = self.sessions_dir / f"{session_id}.log"
        path.write_text(scrubbed)
```

**Tasks:**
- [ ] Create `src/transcript_logger.py` with scrubbing logic
- [ ] Integrate with SecretsManager for known-secret loading
- [ ] Add common API key regex patterns
- [ ] Add configurable custom patterns
- [ ] Create `.workflow_sessions/` directory management
- [ ] Add `sessions` CLI command group
- [ ] Add retention/rotation policy
- [ ] Add session analysis command
- [ ] Add to .gitignore template
- [ ] Document in CLAUDE.md

---

#### WF-023: Detect and Prevent Workflow Abandonment
**Status:** Planned
**Complexity:** Medium
**Priority:** High
**Source:** User observation - Workflows aren't finishing

**Description:** Detect when workflows are being abandoned (session ends, context compacts, agent drifts) and take corrective action to ensure workflows complete.

**Problem Solved:**
AI agents frequently abandon workflows mid-execution:
- Context compaction causes agent to forget active workflow
- Session ends without completing LEARN phase
- Agent drifts to other tasks without finishing
- No record that workflow was abandoned

This leads to incomplete work, missed reviews, and no learnings captured.

**Detection Mechanisms:**

| Trigger | Detection | Action |
|---------|-----------|--------|
| Session end | Hook on session termination | Warn + force checkpoint |
| Context compaction | Post-compaction hook | Re-inject workflow state |
| Stale workflow | No progress in X minutes | Periodic reminder |
| Agent drift | Work outside workflow | Warn about active workflow |

**Desired Behavior:**

1. **On session end with active workflow:**
```
⚠️  SESSION ENDING WITH ACTIVE WORKFLOW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Workflow: "Implement auth feature"
Phase: REVIEW (3/4 items complete)
Status: IN PROGRESS

Options:
  1. Complete workflow now (`orchestrator finish`)
  2. Checkpoint for later (`orchestrator checkpoint`)
  3. Abandon workflow (`orchestrator finish --abandon`)

Creating automatic checkpoint...
✓ Checkpoint saved: cp_2026-01-09_auth-feature
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

2. **Stale workflow warning (configurable interval):**
```
⚠️  WORKFLOW STALE - No progress in 30 minutes
Current phase: EXECUTE
Last activity: write_tests (completed 32 min ago)
Remaining items: implement_core, integration_tests

Continue working or checkpoint?
```

3. **Session resume with incomplete workflow:**
```
⚠️  INCOMPLETE WORKFLOW DETECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Last session ended with active workflow:
  Task: "Implement auth feature"
  Phase: REVIEW
  Checkpoint: cp_2026-01-09_auth-feature

Resume this workflow? [Y/n]
```

**Implementation:**

1. **Session end hook** (`.claude/hooks/session_end.sh`):
```bash
#!/bin/bash
if orchestrator status --quiet 2>/dev/null | grep -q "IN_PROGRESS"; then
    echo "⚠️  Active workflow detected!"
    orchestrator checkpoint --auto --message "Auto-checkpoint on session end"
fi
```

2. **Stale detection** (background or periodic check):
```python
def check_stale_workflow(threshold_minutes: int = 30):
    state = load_workflow_state()
    if not state or state.status != "in_progress":
        return

    last_activity = get_last_activity_time(state)
    if (now() - last_activity).minutes > threshold_minutes:
        warn_stale_workflow(state, last_activity)
```

3. **Abandonment tracking:**
```python
# In workflow state
@dataclass
class WorkflowState:
    # ... existing fields ...
    session_count: int = 0  # How many sessions touched this
    abandonment_count: int = 0  # How many times abandoned
    last_checkpoint_reason: str = ""  # "manual", "session_end", "stale"
```

**CLI Additions:**
```bash
orchestrator status --check-stale     # Warn if stale
orchestrator checkpoint --auto        # Non-interactive checkpoint
orchestrator resume --last            # Resume most recent checkpoint
```

**Configuration:**
```yaml
# workflow.yaml
settings:
  abandonment_detection:
    stale_threshold_minutes: 30
    auto_checkpoint_on_session_end: true
    warn_on_resume: true
```

**4. Uncommitted changes warning:**
```
⚠️  UNCOMMITTED CHANGES DETECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Workflow completed but changes not committed:
  Modified: 5 files
  Added: 2 files

Suggested commit message:
  feat: Implement auth feature

  - Add JWT validation middleware
  - Add login/logout endpoints
  - Add auth tests

Create commit now? [Y/n/edit message]
```

**Tasks:**
- [ ] Create session end hook that checks for active workflow
- [ ] Add auto-checkpoint on session end
- [ ] Add stale workflow detection
- [ ] Add abandonment tracking to workflow state
- [ ] Add `--check-stale` flag to status command
- [ ] Add resume prompt on session start
- [ ] Add uncommitted changes check to `orchestrator finish`
- [ ] Suggest commit message based on workflow task description
- [ ] Add configuration options
- [ ] Track abandonment metrics for analysis
- [ ] Integrate with session logging (CORE-024)
- [ ] Document hooks setup in CLAUDE.md

**Metrics to Track:**
- Workflow completion rate (completed vs started)
- Average phase reached before abandonment
- Most common abandonment points
- Session count per workflow (high = many restarts)
- Recovery rate (abandoned → resumed → completed)

---

#### LEARN-001: Automated Error Analysis in LEARN Phase
**Status:** Planned
**Complexity:** Medium
**Priority:** High
**Source:** User request - Understand what went wrong and could be streamlined

**Description:** Automatically analyze session transcripts during the LEARN phase to identify errors, friction points, and wasted time - then suggest concrete improvements.

**Problem Solved:**
Currently, the LEARN phase relies on the AI agent to self-reflect on what went wrong. But:
- Agents often forget earlier errors by the time they reach LEARN
- Context compaction may have removed error details
- No systematic pattern detection across sessions
- Learnings are vague ("had some issues") rather than actionable

Automated analysis provides objective, data-driven insights.

**What Gets Detected:**

| Category | Detection Method | Example |
|----------|------------------|---------|
| **Errors** | Stack traces, error messages | `ImportError: No module named 'pytest_asyncio'` |
| **Retries** | Repeated similar commands | Same API call 3x with different params |
| **Friction** | Natural language patterns | "let me try a different approach", "that didn't work" |
| **Time sinks** | Timestamps between actions | 8 minutes between attempts on same task |
| **Tool failures** | Non-zero exit codes | `pytest` returning exit code 1 |
| **External issues** | Timeout/connection errors | API timeouts, rate limits |

**Desired Behavior:**

During LEARN phase (or via `orchestrator learn --analyze`):
```
LEARN PHASE - Session Error Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Session duration: 47 minutes
Errors detected: 3
Estimated time lost: ~12 minutes (26%)

ERRORS & FRICTION POINTS
─────────────────────────
1. pytest ImportError (3 occurrences, ~5 min)
   First seen: 14:32:15
   Error: ModuleNotFoundError: No module named 'pytest_asyncio'
   Resolution: Installed missing dependency
   → Suggestion: Add pytest-asyncio to workflow prerequisites check

2. Git merge conflict (1 occurrence, ~4 min)
   File: src/api/client.py
   Resolution: Manual edit to combine changes
   → Suggestion: Use `orchestrator resolve` for semantic merge

3. OpenRouter API timeout (2 occurrences, ~3 min)
   Error: ReadTimeout after 30s
   Resolution: Retry succeeded
   → Suggestion: Already addressed by ARCH-001 (retry utility) ✓

PATTERNS ACROSS RECENT SESSIONS
───────────────────────────────
• Missing dependencies: 4 of last 10 sessions (40%)
  Most common: pytest plugins, type stubs
• Merge conflicts: 3 of last 10 sessions (30%)
  Usually in: src/cli.py, src/engine.py

SUGGESTED IMPROVEMENTS
──────────────────────
□ Add dependency check to PLAN phase (would save ~5 min/session)
□ Document merge workflow in CLAUDE.md
□ Consider pre-commit hook for import sorting (reduces conflicts)

Add these to ROADMAP.md? [y/N/select]
```

**Integration Points:**
- **CORE-024** (Session Logging): Provides the transcript data to analyze
- **WF-023** (Abandonment Detection): Errors often precede abandonment
- **WF-007** (Learnings to Roadmap): Auto-generated suggestions feed into roadmap
- **LEARN phase items**: Enhances `capture_learnings` and `identify_improvements`

**Implementation:**

```python
class SessionErrorAnalyzer:
    """Analyze session transcripts for errors and friction."""

    # Detection patterns
    ERROR_PATTERNS = [
        (r'Traceback \(most recent call last\):.*?(?=\n\S|\Z)', 'stack_trace'),
        (r'Error: .+', 'error_message'),
        (r'FAILED|ERROR', 'test_failure'),
        (r'Command .+ returned non-zero exit status', 'command_failure'),
    ]

    FRICTION_PATTERNS = [
        (r"let me try (a different|another) approach", 'approach_change'),
        (r"that didn't work", 'failure_acknowledgment'),
        (r"I need to .+ instead", 'course_correction'),
        (r"sorry|apologies|my mistake", 'error_recovery'),
    ]

    def analyze(self, transcript: str) -> ErrorAnalysis:
        errors = self._detect_errors(transcript)
        friction = self._detect_friction(transcript)
        time_gaps = self._analyze_timing(transcript)

        return ErrorAnalysis(
            errors=errors,
            friction_points=friction,
            time_lost=self._estimate_time_lost(errors, time_gaps),
            suggestions=self._generate_suggestions(errors, friction),
        )

    def analyze_patterns(self, sessions: list[str]) -> PatternAnalysis:
        """Analyze patterns across multiple sessions."""
        all_errors = []
        for session in sessions:
            analysis = self.analyze(session)
            all_errors.extend(analysis.errors)

        return PatternAnalysis(
            common_errors=self._find_common(all_errors),
            trend=self._calculate_trend(all_errors),
            recommendations=self._cross_session_recommendations(all_errors),
        )
```

**CLI Commands:**
```bash
orchestrator learn --analyze           # Analyze current session
orchestrator learn --analyze-all       # Patterns across recent sessions
orchestrator sessions analyze-errors   # Standalone error analysis
```

**Output Formats:**
- Terminal: Formatted summary (as shown above)
- JSON: Structured data for tooling
- Markdown: For inclusion in LEARN phase notes

**Tasks:**
- [ ] Create `src/learning/error_analyzer.py`
- [ ] Define error detection regex patterns
- [ ] Define friction detection patterns
- [ ] Add timing analysis (gaps between actions)
- [ ] Implement cross-session pattern detection
- [ ] Generate actionable suggestions from errors
- [ ] Integrate with LEARN phase workflow items
- [ ] Add `--analyze` flag to `learn` command
- [ ] Add `analyze-errors` to `sessions` command
- [ ] Link suggestions to existing roadmap items when applicable
- [ ] Add tests for pattern detection
- [ ] Document in CLAUDE.md

**Privacy Consideration:**
Error analysis runs on already-scrubbed transcripts (CORE-024), so no secrets are exposed in error messages. However, file paths and code snippets in stack traces should be reviewed for sensitivity.

---

#### CONTEXT-001: Context Documents System (North Star, Architecture, UI Style Guide)
**Status:** Planned
**Complexity:** Medium
**Priority:** High
**Source:** User discussion - Ensuring AI alignment with project vision in zero-human-review workflows

**Description:** A system of persistent context documents that get injected into sessions and review prompts, ensuring AI agents stay aligned with project vision, architecture decisions, and design standards - even across context compaction and session boundaries.

**Problem Solved:**
In zero-human-review AI coding, there's no human to catch:
- "Wait, we decided to use PostgreSQL, not SQLite"
- "That button style doesn't match our design system"
- "This feature conflicts with our stated non-negotiables"

The AI needs a **persistent proxy for human intent** that survives context loss.

**Document Hierarchy:**

| Document | Purpose | Size | Injection |
|----------|---------|------|-----------|
| **NORTH_STAR.md** | Vision, non-negotiables, current focus | ~500 tokens | Always |
| **ARCHITECTURE.md** | System design, data flow, anti-patterns | ~1.5k tokens | On code changes |
| **UI_STYLE_GUIDE.md** | Visual design system, components, brand | ~1k tokens | On frontend changes |
| **PRDs/** | Feature specifications, acceptance criteria | ~2-5k each | PLAN phase / on-demand |

**1. North Star (Always Injected)**

```markdown
# NORTH_STAR.md

## Vision
A workflow orchestrator enabling zero-human-review AI coding
with quality gates enforced by multi-model review.

## Non-Negotiables
- All code changes go through external model review
- Workflows must complete (no silent abandonment)
- Secrets never appear in logs or transcripts

## Architecture Decisions
| Decision | Date | Rationale |
|----------|------|-----------|
| Use Claude Squad for multi-agent | 2026-01-08 | Simpler than custom spawning |
| Hybrid secret scrubbing | 2026-01-09 | Known secrets + regex patterns |

## What We're NOT Building
- A GUI (CLI-first)
- A SaaS product (local-first tool)

## Current Focus
PRD-001 Phase 2: Complete Claude Squad integration

## Active PRDs
- PRD-001: Claude Squad Integration [Phase 2] → docs/prd/prd-001.md
- PRD-003: Unified Parallelization [Planning] → docs/prd/prd-003.md
```

**2. Architecture Doc (On Code Changes)**

```markdown
# ARCHITECTURE.md

## System Overview
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   CLI       │────▶│   Engine    │────▶│   State     │
│ (src/cli.py)│     │(src/engine) │     │ (.json files)│
└─────────────┘     └─────────────┘     └─────────────┘

## Extension Points
- New review types: Add to src/review/registry.py
- New CLI commands: Add to src/cli.py
- New workflow phases: Modify workflow.yaml schema

## Anti-Patterns (Don't Do This)
- Don't add new state files - extend existing schema
- Don't create new util files - use src/utils.py
- Don't add dependencies without updating pyproject.toml
```

**3. UI/UX Style Guide (On Frontend Changes)**

```markdown
# UI_STYLE_GUIDE.md

## Brand
- Primary: #2563EB (blue-600)
- Secondary: #1E293B (slate-800)
- Font: Inter for UI, JetBrains Mono for code

## Components
- Buttons: rounded-md, py-2 px-4
- Inputs: border-gray-300, focus:ring-2 focus:ring-blue-500
- Cards: shadow-sm, rounded-lg, p-6

## Spacing Scale
4px base: 4, 8, 12, 16, 24, 32, 48

## Accessibility
- Minimum contrast ratio: 4.5:1
- All interactive elements keyboard accessible
```

**Injection Strategy:**

```
Session Start
    │
    ├── Always: CLAUDE.md + NORTH_STAR.md (~1k tokens)
    │
    ├── On code changes: + ARCHITECTURE.md (~1.5k tokens)
    │
    ├── On frontend changes: + UI_STYLE_GUIDE.md (~1k tokens)
    │
    └── On PLAN phase: + relevant PRD (~3k tokens)
```

**Integration with Reviews:**

External reviewers receive context document summaries:

```
REVIEW PROMPT
─────────────
Project Vision: Zero-human-review AI coding with multi-model quality gates

Non-Negotiables:
- All changes go through external review
- No secrets in logs

Architecture Constraints:
- Using Claude Squad for multi-agent (not custom spawning)
- State in JSON files, not database

UI Requirements (if frontend):
- Primary color: #2563EB
- Minimum contrast: 4.5:1

Please review this diff for:
1. Security issues
2. Alignment with stated vision and architecture
3. Violations of non-negotiables
4. Style guide compliance (if UI changes)
```

**CLI Commands:**

```bash
# Initialize context documents
orchestrator init-context              # Create template docs

# Check alignment before major changes
orchestrator align-check               # Validate against North Star
# "⚠️ This adds a database. North Star says 'No database for MVP'. Proceed?"

# Update during LEARN phase
orchestrator north-star add-decision "Use SOPS for secrets" --rationale "Team standard"
orchestrator north-star update-focus "CORE-023: Merge resolution"

# View current context
orchestrator context --show            # Display what would be injected
orchestrator context --include-prd PRD-001  # Include specific PRD
```

**Update Triggers:**

| Event | Action |
|-------|--------|
| LEARN phase | Prompt: "Any new architecture decisions to record?" |
| PRD completion | Update North Star focus to next priority |
| Major refactor | Prompt: "Update ARCHITECTURE.md?" |
| New component | Prompt: "Add to UI_STYLE_GUIDE.md?" |

**Integration Points:**
- **CORE-024** (Session Logging): Log which context was injected
- **LEARN-001** (Error Analysis): Suggest context updates based on errors
- **WF-008** (AI Critique): Reviewers use context for alignment checks
- **Visual Verification**: VV-001 already supports style guide path

**Tasks:**
- [ ] Define document schemas/templates
- [ ] Create `orchestrator init-context` command
- [ ] Implement context injection at session start
- [ ] Add smart injection (detect code vs frontend changes)
- [ ] Integrate context into review prompts
- [ ] Add `orchestrator align-check` command
- [ ] Add `orchestrator north-star` subcommands
- [ ] Create LEARN phase prompts for context updates
- [ ] Add `orchestrator context --show` command
- [ ] Update review router to include context summaries
- [ ] Add tests for injection logic
- [ ] Document in CLAUDE.md

**Why This Matters for Zero-Human-Review:**
These documents act as the **human's proxy**. When no human is reviewing:
- North Star enforces intent and priorities
- Architecture prevents structural drift
- UI Style Guide ensures visual consistency
- PRDs provide detailed requirements

The AI reviewers become enforcers of these standards, catching violations that would otherwise slip through.

---

### High Priority - Architecture Simplification

#### PRD-001: Claude Squad Integration (Replaces Multi-Agent Spawning)
**Status:** Phase 1 Complete - Core Implementation Done
**Complexity:** Medium
**Priority:** Critical
**Source:** Session 7 - Agent orchestration review
**Design Doc:** `docs/designs/claude_squad_integration_detailed.md`

**Description:** Replace complex multi-backend agent spawning with Claude Squad integration for interactive multi-agent workflows. This is a major simplification that:

1. **Removes** complex spawning backends (Modal, Render, Local subprocess)
2. **Delegates** session management to Claude Squad (tmux-based)
3. **Keeps** merge coordination, conflict resolution, task tracking
4. **Adds** persistent session registry, capability detection

**What Gets Decommissioned:**
| File | Status |
|------|--------|
| `src/prd/worker_pool.py` | PENDING REMOVAL - replaced by squad_adapter |
| `src/prd/backends/local.py` | PENDING REMOVAL - subprocess spawning |
| `src/prd/backends/modal_worker.py` | PENDING REMOVAL - cloud spawning |
| `src/prd/backends/render.py` | PENDING REMOVAL - cloud spawning |
| `src/prd/backends/sequential.py` | PENDING REMOVAL - fallback |

**What Gets Added:**
| File | Purpose | Status |
|------|---------|--------|
| `src/prd/squad_adapter.py` | Claude Squad integration | ✅ DONE |
| `src/prd/squad_capabilities.py` | Capability detection | ✅ DONE |
| `src/prd/session_registry.py` | Persistent state | ✅ DONE |
| `src/prd/backend_selector.py` | Hybrid mode selection | ✅ DONE |

**What Gets Retained:**
- `src/prd/backends/github_actions.py` - For batch/remote execution
- `src/prd/integration.py` - Branch management, merging
- `src/prd/wave_resolver.py` - Conflict resolution
- `src/prd/schema.py` - Data structures

**New CLI Commands:** (All implemented ✅)
```bash
orchestrator prd check-squad    # Verify Claude Squad compatibility
orchestrator prd spawn          # Spawn interactive sessions
orchestrator prd sessions       # List active sessions
orchestrator prd attach <id>    # Attach to session
orchestrator prd done <id>      # Mark complete
orchestrator prd cleanup        # Clean orphaned sessions
```

**AI Review Status:** Approved with minor changes (GPT-5.2, Gemini 2.5, Grok 4)
- Security review: ✅ Passed (codex/gpt-5.1-codex-max)
- Quality review: ✅ Passed (codex/gpt-5.1-codex-max)

**Tasks:**
- [x] Implement `src/prd/session_registry.py` (persistent state)
- [x] Implement `src/prd/squad_capabilities.py` (capability detection)
- [x] Implement `src/prd/squad_adapter.py` (main integration)
- [x] Implement `src/prd/backend_selector.py` (hybrid selection)
- [x] Add CLI commands
- [x] Add comprehensive tests (66 new tests, all passing)
- [ ] Update executor.py to use new adapters (Phase 2)
- [ ] Remove deprecated backend files (after executor.py update)
- [ ] Update documentation

**Remaining Work (PRD-001 Phase 2):**
1. Update `src/prd/executor.py` to use BackendSelector instead of WorkerPool
2. Remove deprecated files after executor migration
3. Update any references in documentation

---

#### PRD-002: Superseded - Multi-Backend Worker Pool
**Status:** SUPERSEDED by PRD-001
**Reason:** Claude Squad integration provides better UX (interactive sessions) with less code complexity. The worker pool approach of fire-and-forget spawning doesn't match user needs for visibility and interaction.

**Original Files (to be removed):**
- `src/prd/worker_pool.py`
- `src/prd/backends/local.py`
- `src/prd/backends/modal_worker.py`
- `src/prd/backends/render.py`
- `src/prd/backends/sequential.py`

---

### Short-term (Low Effort)

#### CORE-006: Automatic Connector Detection with User Fallback
**Status:** ✅ Completed (2026-01-07)
**Complexity:** Medium
**Priority:** High
**Source:** v2.2 Implementation Learning
**Description:** Automatically detect available agent connectors and ask user before defaulting to manual implementation when preferred agent is unavailable.

**Implementation:**
- Added `detect_manus_connector()` and `get_available_connectors()` to `src/environment.py`
- Added `get_available_providers()` and `prompt_user_for_provider()` to `src/providers/__init__.py`
- Checks Claude Code CLI, Manus connector, OpenRouter API availability
- 17 tests in `tests/test_provider_detection.py`

**Files:** `src/environment.py`, `src/providers/__init__.py`, `tests/test_provider_detection.py`

**Problem Solved:**
During v2.2 implementation, Claude Code CLI was unavailable in Manus sandbox. Instead of asking the user about alternative connection methods (Manus direct connector), the agent defaulted to manual implementation. This missed an opportunity to use a specialized coding AI.

**Desired Behavior:**
1. Check for Claude Code CLI (`which claude`)
2. Check for Manus direct connector (environment detection)
3. Check for OpenRouter API key
4. If primary agent unavailable, **ASK USER** before proceeding:
   - "Claude Code CLI is not available. Would you like me to:
     a) Use Manus direct connector (detected)
     b) Use OpenRouter API
     c) Proceed with manual implementation
     d) Help me install Claude Code CLI"

**Implementation Notes:**
```python
def get_available_providers() -> List[str]:
    """Return list of available providers in priority order."""
    available = []
    if shutil.which('claude'):
        available.append('claude_code')
    if detect_manus_connector():
        available.append('manus_direct')
    if os.environ.get('OPENROUTER_API_KEY'):
        available.append('openrouter')
    available.append('manual')  # Always available
    return available

def prompt_user_for_provider(preferred: str, available: List[str]) -> str:
    """Ask user which provider to use when preferred is unavailable."""
    if preferred in available:
        return preferred
    # Generate user prompt with available options
    ...
```

**Tasks:**
- [ ] Add `detect_manus_connector()` function to environment.py
- [ ] Add `get_available_providers()` to providers/__init__.py
- [ ] Add `prompt_user_for_provider()` interactive function
- [ ] Update `handoff` command to use interactive selection when needed
- [ ] Add `--interactive` flag to force user prompt
- [ ] Document Manus direct connector access method

---

#### CORE-007: Deprecate Legacy Claude Integration
**Status:** ✅ Completed (2026-01-06)
**Complexity:** Low
**Priority:** Medium
**Description:** Add deprecation warning to `claude_integration.py` and update documentation to use new provider system.

**Implementation:**
- Added deprecation warning at module import with `stacklevel=2`
- Warning points users to `src.providers.claude_code`

**Files:** `src/claude_integration.py`

---

#### CORE-008: Input Length Limits
**Status:** ✅ Completed (2026-01-06)
**Complexity:** Low
**Priority:** Medium
**Source:** Security Review v2.2
**Description:** Add length limits to user-provided constraints and notes to prevent DoS via extremely long strings.

**Implementation:**
- Created `src/validation.py` with `validate_constraint()` and `validate_note()` functions
- Added validation calls to CLI commands: `start`, `complete`, `approve-item`, `finish`
- 14 tests in `tests/test_validation.py`

**Files:** `src/validation.py`, `src/cli.py`, `tests/test_validation.py`

---

#### CORE-009: Constraints File Flag
**Status:** Planned
**Complexity:** Low
**Priority:** Low
**Description:** Add `--constraints-file` flag to load constraints from a file for complex multi-line constraints.

**Implementation:**
```bash
# Usage
orchestrator start "My task" --constraints-file constraints.txt

# constraints.txt
Do not modify database schema
All changes must be backwards compatible
Follow PEP 8 style guide
```

**Tasks:**
- [ ] Add `--constraints-file` argument to start command
- [ ] Read file and split by newlines
- [ ] Combine with inline `--constraints` flags
- [ ] Add documentation

---

#### CORE-010: Enhanced Skip Visibility
**Status:** ✅ Completed (2026-01-07)
**Complexity:** Low
**Priority:** High
**Source:** Learnings from roadmap items implementation (2026-01-06)
**Description:** Make skipped items more visible to force deliberate consideration and prevent lazy skipping.

**Implementation:**
- Added `get_skipped_items()`, `get_all_skipped_items()`, `get_item_definition()` methods to WorkflowEngine
- Updated `cmd_skip()` to show enhanced output with item description and implications
- Updated `cmd_advance()` to show skipped items from completed phase
- 13 tests in `tests/test_roadmap_features.py`

**Files:** `src/engine.py`, `src/cli.py`, `tests/test_roadmap_features.py`

**Problem Solved:**
When AI agents skip workflow items, the skip reason is stored but not prominently displayed. This allows:
1. **Lazy skipping** - Agent skips items without fully considering implications
2. **Silent accumulation** - Multiple skips go unnoticed until workflow ends
3. **Lost context** - User doesn't see what was skipped or why

The act of articulating rationale forces deeper consideration - it's harder to be lazy when you have to explain yourself out loud.

**Desired Behavior:**

1. **At skip time** - Enhanced output that forces consideration:
```
============================================================
⊘ SKIPPING: visual_regression_test
============================================================
Reason: Not applicable - CLI tool with no visual UI

Implications:
  • No visual regression testing will be performed
  • UI changes (if any) will not be automatically verified

This skip is acceptable because:
  • This is a CLI-only tool with no visual components
  • Visual testing would have no meaningful assertions
============================================================
```

2. **At phase advance** - Show skipped items for the completed phase:
```
Phase VERIFY completed with 1 skipped item(s):
  ⊘ visual_regression_test - "Not applicable - CLI tool with no visual UI"
```

3. **At workflow finish** - Summary of all skipped items:
```
============================================================
SKIPPED ITEMS SUMMARY
============================================================
Review these skips - were they all justified?

Phase PLAN:
  ⊘ clarifying_questions - "Roadmap items well-specified"

Phase VERIFY:
  ⊘ visual_regression_test - "CLI tool with no visual UI"

Phase LEARN:
  ⊘ backport_improvements - "No universal improvements to backport"
  ⊘ update_knowledge_base - "Handled via ROADMAP.md updates"

Total: 4 items skipped across 3 phases
============================================================
```

**Implementation Notes:**

```python
# In cmd_skip() - src/cli.py
def cmd_skip(args):
    # ... existing validation ...

    # Enhanced skip output
    print("=" * 60)
    print(f"⊘ SKIPPING: {args.item}")
    print("=" * 60)
    print(f"Reason: {args.reason}")
    print()

    # Get item definition for context
    item_def = engine.get_item_definition(args.item)
    if item_def and item_def.description:
        print("What this item does:")
        print(f"  {item_def.description}")
        print()

    print("Implications:")
    print(f"  • {item_def.name} will not be performed")
    print()
    print("=" * 60)

    # Proceed with skip
    success, message = engine.skip_item(args.item, args.reason)
    # ...

# In cmd_advance() - show skipped items for completed phase
def cmd_advance(args):
    # ... existing logic ...

    # After successful advance, show skipped items from previous phase
    skipped = engine.get_skipped_items(previous_phase_id)
    if skipped:
        print(f"\nPhase {previous_phase_id} completed with {len(skipped)} skipped item(s):")
        for item_id, reason in skipped:
            print(f"  ⊘ {item_id} - \"{reason}\"")

# In cmd_finish() - full summary
def cmd_finish(args):
    # ... existing logic ...

    # Before completing, show all skipped items
    all_skipped = engine.get_all_skipped_items()
    if all_skipped:
        print("\n" + "=" * 60)
        print("SKIPPED ITEMS SUMMARY")
        print("=" * 60)
        print("Review these skips - were they all justified?\n")

        for phase_id, items in all_skipped.items():
            print(f"Phase {phase_id}:")
            for item_id, reason in items:
                print(f"  ⊘ {item_id} - \"{reason}\"")
            print()

        total = sum(len(items) for items in all_skipped.values())
        print(f"Total: {total} items skipped across {len(all_skipped)} phases")
        print("=" * 60)
```

**Engine Methods to Add:**

```python
# In WorkflowEngine - src/engine.py

def get_skipped_items(self, phase_id: str) -> list[tuple[str, str]]:
    """Get list of (item_id, skip_reason) for skipped items in a phase."""
    if not self.state:
        return []
    phase = self.state.phases.get(phase_id)
    if not phase:
        return []
    return [
        (item_id, item.skip_reason or "No reason provided")
        for item_id, item in phase.items.items()
        if item.status == ItemStatus.SKIPPED
    ]

def get_all_skipped_items(self) -> dict[str, list[tuple[str, str]]]:
    """Get all skipped items grouped by phase."""
    if not self.state:
        return {}
    result = {}
    for phase_id, phase in self.state.phases.items():
        skipped = self.get_skipped_items(phase_id)
        if skipped:
            result[phase_id] = skipped
    return result

def get_item_definition(self, item_id: str) -> Optional[ChecklistItemDef]:
    """Get the workflow definition for an item."""
    if not self.workflow_def:
        return None
    for phase in self.workflow_def.phases:
        for item in phase.items:
            if item.id == item_id:
                return item
    return None
```

**Tasks:**
- [ ] Add `get_skipped_items()` method to WorkflowEngine
- [ ] Add `get_all_skipped_items()` method to WorkflowEngine
- [ ] Add `get_item_definition()` method to WorkflowEngine
- [ ] Update `cmd_skip()` to show enhanced output with implications
- [ ] Update `cmd_advance()` to show skipped items from completed phase
- [ ] Update `cmd_finish()` to show full skipped items summary
- [ ] Add tests for new engine methods
- [ ] Add tests for CLI output changes
- [ ] Update documentation

**Why This Matters for AI Agents:**
When an AI agent must articulate *why* something is being skipped and see the implications displayed, it:
1. Forces genuine consideration of whether skipping is appropriate
2. Makes lazy skipping visible and uncomfortable
3. Creates accountability in the conversation/logs
4. Gives the human user visibility into agent decision-making

This is particularly important for "vibe coding" workflows where AI operates with high autonomy.

---

#### CORE-011: Workflow Completion Summary & Next Steps
**Status:** ✅ Completed (2026-01-07)
**Complexity:** Low
**Priority:** High
**Source:** Learnings from roadmap items implementation (2026-01-06)
**Description:** Show comprehensive completion summary and prompt for next steps when workflow finishes, preventing conversations from "tailing off" without proper closure.

**Implementation:**
- Added `get_workflow_summary()` method to WorkflowEngine
- Added `format_duration()` helper function to CLI
- Updated `cmd_finish()` to show phase summary table, skipped items list, and next steps prompt
- 8 tests in `tests/test_roadmap_features.py`

**Files:** `src/engine.py`, `src/cli.py`, `tests/test_roadmap_features.py`

**Problem Solved:**
When `orchestrator finish` runs, it just outputs "✓ Workflow completed" and stops. This allows:
1. **Premature closure** - Agent assumes work is done when user may have more steps
2. **Missing handoff** - No prompt to create PR, merge, or continue discussion
3. **Lost context** - No summary of what was accomplished or skipped
4. **Conversation drift** - Discussion gets sidetracked and workflow silently ends

The workflow completion is a critical moment - the agent should explicitly check with the user about next steps rather than assuming the conversation is over.

**Desired Behavior:**

When `orchestrator finish` runs, show:

```
============================================================
✓ WORKFLOW COMPLETED
============================================================
Task: Implement roadmap items: CORE-007, CORE-008, ARCH-001, WF-004
Started: 2026-01-06 10:30 UTC
Finished: 2026-01-06 12:45 UTC
Duration: 2h 15m

PHASE SUMMARY
─────────────────────────────────────────────────────────────
  PLAN:     6 items (5 completed, 1 skipped)
  EXECUTE:  4 items (4 completed)
  REVIEW:   4 items (3 completed, 1 skipped)
  VERIFY:   3 items (2 completed, 1 skipped)
  LEARN:    6 items (4 completed, 2 skipped)
─────────────────────────────────────────────────────────────
  Total:    23 items (18 completed, 5 skipped)

SKIPPED ITEMS (review for justification)
─────────────────────────────────────────────────────────────
  • clarifying_questions: "Roadmap items well-specified"
  • visual_regression_test: "CLI tool with no visual UI"
  • refactoring_assessment: "Small focused changes"
  • backport_improvements: "No universal improvements"
  • update_knowledge_base: "Handled via ROADMAP.md"

============================================================
⚠️  WORKFLOW COMPLETE - WHAT'S NEXT?
============================================================

The workflow is finished, but you may still need to:

  □ Create a PR:
    gh pr create --title "feat: Implement CORE-007, CORE-008, ARCH-001, WF-004"

  □ Merge to main (if approved):
    git checkout main && git merge <branch> && git push

  □ Continue discussion with user about:
    • Any follow-up tasks?
    • Questions about the implementation?
    • Ready to close this session?

Reply to confirm next steps or start a new workflow.
============================================================
```

**Implementation Notes:**

```python
# In cmd_finish() - src/cli.py

def cmd_finish(args):
    engine = get_engine(args)

    if not engine.state:
        print("Error: No active workflow")
        sys.exit(1)

    # Capture summary before completing
    summary = engine.get_workflow_summary()
    skipped = engine.get_all_skipped_items()

    # Complete the workflow
    if args.abandon:
        engine.abandon_workflow(args.reason)
        print("✓ Workflow abandoned")
    else:
        engine.complete_workflow(notes=args.notes)

        # Show comprehensive completion summary
        print_completion_summary(summary, skipped, engine.state)

        # Prompt for next steps
        print_next_steps_prompt(engine.state)

def print_completion_summary(summary, skipped, state):
    """Print detailed completion summary."""
    print("=" * 60)
    print("✓ WORKFLOW COMPLETED")
    print("=" * 60)
    print(f"Task: {state.task_description}")

    if state.started_at and state.completed_at:
        duration = state.completed_at - state.started_at
        print(f"Duration: {format_duration(duration)}")
    print()

    # Phase summary table
    print("PHASE SUMMARY")
    print("-" * 60)
    for phase_id, phase_summary in summary.items():
        completed = phase_summary['completed']
        skipped = phase_summary['skipped']
        total = phase_summary['total']
        print(f"  {phase_id:12} {total} items ({completed} completed, {skipped} skipped)")
    print("-" * 60)

    # Skipped items
    if skipped:
        print("\nSKIPPED ITEMS (review for justification)")
        print("-" * 60)
        for phase_id, items in skipped.items():
            for item_id, reason in items:
                # Truncate long reasons
                short_reason = reason[:50] + "..." if len(reason) > 50 else reason
                print(f"  • {item_id}: \"{short_reason}\"")
    print()

def print_next_steps_prompt(state):
    """Prompt user/agent about next steps."""
    print("=" * 60)
    print("⚠️  WORKFLOW COMPLETE - WHAT'S NEXT?")
    print("=" * 60)
    print()
    print("The workflow is finished, but you may still need to:")
    print()
    print("  □ Create a PR:")
    print(f"    gh pr create --title \"{get_pr_title(state)}\"")
    print()
    print("  □ Merge to main (if approved)")
    print()
    print("  □ Continue discussion with user about:")
    print("    • Any follow-up tasks?")
    print("    • Questions about the implementation?")
    print("    • Ready to close this session?")
    print()
    print("Reply to confirm next steps or start a new workflow.")
    print("=" * 60)
```

**Engine Methods to Add:**

```python
# In WorkflowEngine - src/engine.py

def get_workflow_summary(self) -> dict:
    """Get summary of items per phase."""
    if not self.state:
        return {}

    summary = {}
    for phase_id, phase in self.state.phases.items():
        completed = sum(1 for i in phase.items.values()
                       if i.status == ItemStatus.COMPLETED)
        skipped = sum(1 for i in phase.items.values()
                     if i.status == ItemStatus.SKIPPED)
        total = len(phase.items)
        summary[phase_id] = {
            'completed': completed,
            'skipped': skipped,
            'total': total
        }
    return summary
```

**Tasks:**
- [ ] Add `get_workflow_summary()` method to WorkflowEngine
- [ ] Add `print_completion_summary()` function to CLI
- [ ] Add `print_next_steps_prompt()` function to CLI
- [ ] Update `cmd_finish()` to call both functions
- [ ] Add helper to generate suggested PR title from task description
- [ ] Add duration calculation and formatting
- [ ] Include skipped items summary (integrate with CORE-010)
- [ ] Add tests for summary generation
- [ ] Add tests for CLI output

**Why This Matters for AI Agents:**
AI agents can lose track of where they are in a conversation, especially after completing a complex multi-phase workflow. By explicitly prompting "what's next?" the orchestrator:
1. Prevents the agent from assuming work is done prematurely
2. Reminds the agent to check with the user before ending
3. Provides concrete next step suggestions (PR, merge, etc.)
4. Keeps the conversation focused on completing the full task

This is critical for "vibe coding" where the human may be minimally engaged - the agent needs explicit prompts to stay on track rather than silently stopping.

---

#### CORE-016: Multi-Model Review Routing
**Status:** ✅ Completed (2026-01-06)
**Complexity:** Medium
**Priority:** High
**Source:** Current workflow
**Description:** Route REVIEW phase items to different AI models to prevent self-review blind spots.

**Problem Solved:**
The same model that writes code shouldn't review it. Different models have different blind spots and perspectives.

**Hybrid Model Strategy:**
- `security_review` + `quality_review` → Codex (code-specialized)
- `consistency_review` + `holistic_review` → Gemini (long context)

**Implementation:**
- Context collector gathers git diff, changed files, related files
- Review router with auto-detection: CLI mode (Codex/Gemini CLIs) or API mode (OpenRouter)
- Four review types: security, consistency, quality, holistic
- `setup-reviews` command to bootstrap GitHub Actions workflow
- 27 tests covering all components

**Files:** `src/review/` module (8 files)

---

#### WF-004: Auto-Archive Workflow Documents
**Status:** ✅ Completed (2026-01-06)
**Complexity:** Low
**Priority:** Medium
**Source:** Current workflow
**Description:** Automatically archive workflow documents (plan.md, risk_analysis.md) when starting a new workflow.

**Implementation:**
- Added `archive_existing_docs()` method to `WorkflowEngine`
- Archives `docs/plan.md`, `docs/risk_analysis.md`, `tests/test_cases.md`
- Added `--no-archive` flag to skip archiving
- Uses `slugify()` utility for filename generation
- Handles duplicate filenames with counter suffix
- 10 tests in `tests/test_roadmap_features.py`

**Files:** `src/engine.py`, `src/cli.py`, `src/utils.py`, `tests/test_roadmap_features.py`

---

#### CORE-017: Auto-Update Review Models
**Status:** ✅ Completed (2026-01-07)
**Complexity:** Low
**Priority:** Medium
**Source:** Current workflow
**Description:** Automatically detect and use latest available AI models for reviews.

**Implementation:**
- Created new `src/model_registry.py` module with `ModelRegistry` class
- 30-day staleness detection with auto-update capability
- Added `update-models` CLI command with `--check` and `--force` flags
- Queries OpenRouter API for model list
- Caches model information in `.model_registry.json`
- 21 tests in `tests/test_model_registry.py`

**Files:** `src/model_registry.py`, `src/cli.py`, `tests/test_model_registry.py`

**Problem Solved:**
Model versions in config become stale as new models are released. Currently requires manual updates.

**Desired Behavior:**
1. `./orchestrator update-models` - Query OpenRouter API for latest models
2. Auto-suggest updates when newer models detected
3. Optional "latest" alias that resolves dynamically
4. **Auto-update if last update > 30 days** (with user confirmation option)

**Implementation Notes:**
```python
def get_latest_models():
    """Query OpenRouter for latest available models."""
    response = requests.get("https://openrouter.ai/api/v1/models")
    models = response.json()["data"]

    # Find latest OpenAI and Gemini models
    latest_openai = max([m for m in models if m["id"].startswith("openai/gpt-5")],
                        key=lambda m: m["created"])
    latest_gemini = max([m for m in models if "gemini-3" in m["id"]],
                        key=lambda m: m["created"])
    return {"codex": latest_openai["id"], "gemini": latest_gemini["id"]}

def check_and_auto_update():
    """Auto-update if stale (> 30 days since last update)."""
    last_update = get_last_model_update_timestamp()
    if (datetime.now() - last_update).days > 30:
        logger.info("Models not updated in 30+ days, auto-updating...")
        update_models(auto=True)
```

**Tasks:**
- [ ] Add `update-models` CLI command
- [ ] Query OpenRouter API for model list
- [ ] Update workflow.yaml models section
- [ ] Update FUNCTION_CALLING_MODELS in src/providers/openrouter.py
- [ ] Add `--check-models` flag to review command
- [ ] Warn when using outdated models
- [ ] **Auto-update if > 30 days stale** (store last_update timestamp)
- [ ] Add `--no-auto-update` flag to disable

---

#### CORE-018: Dynamic Function Calling Detection
**Status:** ✅ Completed (2026-01-07)
**Complexity:** Low
**Priority:** Medium
**Source:** Function calling implementation (this workflow)
**Description:** Detect model function calling support from OpenRouter API instead of static list.

**Implementation:**
- Added `get_model_capabilities()` and `supports_function_calling()` to `ModelRegistry`
- Registry-based capability detection with cache
- Falls back to static `STATIC_FUNCTION_CALLING_MODELS` list when API unavailable
- Integrated with model registry staleness system (CORE-017)
- Tests included in `tests/test_model_registry.py`

**Files:** `src/model_registry.py`, `tests/test_model_registry.py`

**Problem Solved:**
FUNCTION_CALLING_MODELS is a static list that requires manual updates. New models may support function calling but aren't in the list.

**Current State:**
- Static set in `src/providers/openrouter.py`
- Prefix matching for versioned models
- Conservative default (unknown = no function calling)

**Desired Behavior:**
1. Query OpenRouter API for model capabilities
2. Cache results locally (avoid repeated API calls)
3. Fall back to static list if API unavailable
4. Update static list when new models detected

**Implementation Notes:**
```python
def get_model_capabilities(model_id: str) -> dict:
    """Query OpenRouter for model capabilities."""
    response = requests.get(f"https://openrouter.ai/api/v1/models/{model_id}")
    model_info = response.json()
    return {
        "supports_function_calling": model_info.get("supports_tools", False),
        "context_length": model_info.get("context_length", 0),
        "supports_vision": model_info.get("supports_vision", False),
    }
```

**Tasks:**
- [ ] Add `get_model_capabilities()` function
- [ ] Cache capabilities in `.model_capabilities.json`
- [ ] Integrate with `_supports_function_calling()`
- [ ] Fall back to static list on API error
- [ ] Add to `update-models` command

---

### Medium-term (Medium Effort)

#### CORE-010: Checkpoint Database Backend
**Status:** Planned  
**Complexity:** Medium  
**Priority:** Medium  
**Description:** Add optional database backend for checkpoints to support multi-node deployments and better querying.

**Current State:**
- Checkpoints stored as JSON files in `.workflow_checkpoints/`
- Works well for single-node, local development

**Desired State:**
- Optional SQLite backend (default for local)
- Optional PostgreSQL backend (for teams/production)
- Configurable via `CHECKPOINT_BACKEND` env var

**Implementation Notes:**
```python
class CheckpointBackend(ABC):
    @abstractmethod
    def save(self, checkpoint: CheckpointData) -> None: ...
    @abstractmethod
    def load(self, checkpoint_id: str) -> Optional[CheckpointData]: ...
    @abstractmethod
    def list(self, workflow_id: Optional[str] = None) -> List[CheckpointData]: ...

class FileBackend(CheckpointBackend): ...  # Current implementation
class SQLiteBackend(CheckpointBackend): ...  # New
class PostgresBackend(CheckpointBackend): ...  # New
```

**Tasks:**
- [ ] Create `CheckpointBackend` abstract base class
- [ ] Refactor current file-based storage to `FileBackend`
- [ ] Implement `SQLiteBackend`
- [ ] Implement `PostgresBackend`
- [ ] Add `CHECKPOINT_BACKEND` configuration
- [ ] Add migration utility for existing checkpoints

---

#### CORE-011: Provider Caching
**Status:** Planned  
**Complexity:** Medium  
**Priority:** Low  
**Description:** Cache provider availability checks to avoid repeated subprocess calls and API pings.

**Current State:**
- `is_available()` called on each provider selection
- Claude Code check spawns subprocess each time
- OpenRouter check may make HTTP request

**Desired State:**
- Cache availability for configurable duration (default: 5 minutes)
- Invalidate cache on explicit request
- Thread-safe caching

**Implementation Notes:**
```python
from functools import lru_cache
from datetime import datetime, timedelta

class CachedProvider:
    _availability_cache: dict[str, tuple[bool, datetime]] = {}
    _cache_ttl = timedelta(minutes=5)
    
    def is_available(self) -> bool:
        cached = self._availability_cache.get(self.name)
        if cached and datetime.now() - cached[1] < self._cache_ttl:
            return cached[0]
        result = self._check_availability()
        self._availability_cache[self.name] = (result, datetime.now())
        return result
```

**Tasks:**
- [ ] Add caching to `AgentProvider` base class
- [ ] Make TTL configurable
- [ ] Add `--no-cache` flag to force fresh check
- [ ] Add cache invalidation method

---

#### CORE-012: OpenRouter Streaming Support
**Status:** ✅ Completed (2026-01-07)
**Complexity:** Medium
**Priority:** Low
**Description:** Add streaming support to OpenRouter provider for real-time output display.

**Implementation:**
- Added `execute_streaming()` method that yields chunks via generator
- Added `stream_to_console()` convenience method
- Handles SSE format (`data: {...}`) parsing
- Graceful handling of stream interruption and `[DONE]` marker

**Files:** `src/providers/openrouter.py`

---

### Long-term (High Effort)

#### CORE-013: Provider Plugin System
**Status:** Planned  
**Complexity:** High  
**Priority:** Low  
**Description:** Allow external packages to register custom providers without modifying core code.

**Desired State:**
- Providers discoverable via entry points
- Install custom provider: `pip install orchestrator-provider-anthropic`
- Auto-registered on import

**Implementation Notes:**
```toml
# In external package's pyproject.toml
[project.entry-points."orchestrator.providers"]
anthropic = "orchestrator_anthropic:AnthropicProvider"
```

```python
# In orchestrator startup
import importlib.metadata

for ep in importlib.metadata.entry_points(group='orchestrator.providers'):
    provider_class = ep.load()
    register_provider(ep.name, provider_class)
```

**Tasks:**
- [ ] Define entry point group `orchestrator.providers`
- [ ] Add provider discovery on startup
- [ ] Create provider development guide
- [ ] Create example provider package
- [ ] Add provider validation on registration

---

#### CORE-014: Checkpoint Encryption
**Status:** Planned  
**Complexity:** High  
**Priority:** Low  
**Description:** Encrypt checkpoint data for sensitive workflows containing secrets or proprietary information.

**Desired State:**
- Optional encryption via `--encrypt` flag
- Use age encryption (consistent with SOPS)
- Decrypt on resume with key from env var

**Implementation Notes:**
```python
class EncryptedCheckpointBackend(CheckpointBackend):
    def __init__(self, key: str):
        self._key = key
    
    def save(self, checkpoint: CheckpointData) -> None:
        data = json.dumps(checkpoint.to_dict())
        encrypted = age_encrypt(data, self._key)
        # Save encrypted blob
    
    def load(self, checkpoint_id: str) -> Optional[CheckpointData]:
        encrypted = # Load encrypted blob
        data = age_decrypt(encrypted, self._key)
        return CheckpointData.from_dict(json.loads(data))
```

**Tasks:**
- [ ] Add `pyage` or similar library dependency
- [ ] Create `EncryptedCheckpointBackend`
- [ ] Add `--encrypt` flag to checkpoint command
- [ ] Add `CHECKPOINT_ENCRYPTION_KEY` env var
- [ ] Document encryption setup

---

#### CORE-015: Distributed Workflow Execution
**Status:** RECONSIDERED - See PRD-001
**Complexity:** High
**Priority:** Low
**Description:** Support multiple agents working on the same workflow with item locking and claiming.

**Update (2026-01-09):** This feature is being reconsidered in light of PRD-001 (Claude Squad integration). Rather than building complex distributed coordination, we're:
1. **Delegating multi-agent management** to Claude Squad (tmux-based sessions)
2. **Focusing on merge coordination** rather than agent spawning/monitoring
3. **Keeping it simple** - user manually interacts with each agent session

The original vision of fully autonomous distributed agents with locking/claiming may be over-engineering. Claude Squad + good merge handling may be sufficient.

**Original Desired State:**
- Central workflow state (database-backed)
- Item claiming/locking mechanism
- Conflict resolution for concurrent updates
- Agent identification and tracking

**Revised Approach (PRD-001):**
- Claude Squad handles agent sessions
- Session registry tracks task↔session mapping
- Wave resolver handles merge conflicts
- User maintains visibility and control

---

## Visual Verification Improvements

### High Priority

#### VV-001: Auto-load Style Guide in Visual Verification
**Status:** ✅ Completed (2026-01-07)
**Complexity:** Low
**Description:** When `style_guide_path` is configured, automatically include the style guide content in all visual verification evaluations.

**Implementation:**
- `style_guide_path` parameter in `VisualVerificationClient.__init__()`
- Auto-loads and caches style guide content
- `auto_include_style_guide` flag (default True) controls inclusion
- `include_style_guide` parameter on `verify()` for per-call override

**Files:** `src/visual_verification.py`

---

#### VV-002: Workflow Step Integration for Visual Tests
**Status:** ✅ Completed (2026-01-07)
**Complexity:** Medium
**Description:** Wire the visual verification into the `visual_regression_test` workflow step.

**Implementation:**
- `run_all_visual_tests()` function discovers and runs all tests
- `app_url` parameter for base URL resolution
- Integrates with workflow item completion via CLI

**Files:** `src/visual_verification.py`, `src/cli.py`

---

#### VV-003: Visual Test Discovery
**Status:** ✅ Completed (2026-01-07)
**Complexity:** Low
**Description:** Automatically discover and run all visual test files in the `tests/visual/` directory.

**Implementation:**
- `discover_visual_tests()` scans `tests/visual/*.md` files
- `parse_visual_test_file()` parses YAML frontmatter + markdown body
- Test file format: `url`, `device`, `tags`, `actions` in frontmatter
- `visual-verify-all` CLI command with `--tag` filtering
- `filter_tests_by_tag()` for selective test execution

**Files:** `src/visual_verification.py`, `src/cli.py`

---

### Medium Priority

#### VV-004: Baseline Screenshot Management
**Status:** ✅ Completed (2026-01-07)
**Complexity:** Medium
**Description:** Store baseline screenshots and compare against them for regression detection.

**Implementation:**
- `save_baseline()` stores screenshot with SHA256 hash
- `get_baseline()` retrieves baseline image bytes
- `compare_with_baseline()` uses hash comparison (fast path)
- `list_baselines()` returns available baseline names
- `--save-baseline` CLI flag
- Client-side storage in `tests/visual/baselines/`

**Files:** `src/visual_verification.py`, `src/cli.py`

---

#### VV-005: CI/CD Integration
**Status:** Planned  
**Complexity:** Medium  
**Description:** GitHub Actions workflow for running visual tests on PR/push.

**Implementation Notes:**
- Create `.github/workflows/visual-tests.yml`
- Run against preview/staging deployment
- Post results as PR comment
- Block merge on failure

---

### Low Priority

#### VV-006: Cost Tracking for Visual Tests
**Status:** ✅ Completed (2026-01-07)
**Complexity:** Low
**Description:** Track Claude API usage and costs for visual verification calls.

**Implementation:**
- Added `UsageInfo` dataclass with `input_tokens`, `output_tokens`, `estimated_cost`
- Added `CostSummary` class for aggregating costs across multiple tests
- Added cost tracking to visual-verification-service (evaluator.ts)
- Added `--show-cost` flag to CLI commands
- Added `format_cost_summary()` for displaying aggregate costs

**Files:** `src/visual_verification.py`, `src/cli.py`, `visual-verification-service/src/services/evaluator.ts`

---

## Security Improvements

### SEC-001: HTTPS Enforcement
**Status:** Planned
**Complexity:** Low
**Source:** Security Review (Score: 7/10)
**Description:** Validate that `visual_verification_url` uses HTTPS to prevent API key transmission over insecure connections.

**Implementation:**
```python
if not service_url.startswith('https://'):
    raise VisualVerificationError("Service URL must use HTTPS")
```

---

### SEC-004: Cross-Repo Secrets Copy Command
**Status:** ✅ Completed (2026-01-07)
**Complexity:** Low
**Priority:** High
**Source:** Secrets Management Code Review
**Description:** Add `orchestrator secrets copy` command to easily copy encrypted secrets to other repos.

**Implementation:**
- Added `copy_secrets_file()` function to `src/secrets.py`
- Added `secrets copy` CLI action with `--from`, `--to`, `--force` flags
- Path validation with `Path.resolve()` for security
- 11 tests in `tests/test_secrets_copy.py`

**Files:** `src/secrets.py`, `src/cli.py`, `tests/test_secrets_copy.py`

**Problem Solved:**
Currently users must manually copy `.manus/secrets.enc` between repos. This is error-prone and not discoverable.

**Desired Behavior:**
```bash
# Copy secrets to another repo
orchestrator secrets copy /path/to/other/repo

# Copy from another repo to current
orchestrator secrets copy --from /path/to/source/repo
```

**Implementation Notes:**
```python
def cmd_secrets_copy(args):
    """Copy encrypted secrets between repos."""
    source = Path(args.from_dir or '.') / '.manus/secrets.enc'
    dest = Path(args.to_dir or '.') / '.manus/secrets.enc'

    if not source.exists():
        print(f"Error: No secrets file at {source}")
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, dest)
    print(f"✓ Copied secrets to {dest}")
```

**Tasks:**
- [ ] Add `secrets copy` subcommand to CLI
- [ ] Support `--from` and `--to` flags
- [ ] Validate source file exists
- [ ] Create destination directory if needed
- [ ] Add to documentation

---

### SEC-005: Per-User Encrypted Secrets
**Status:** Planned
**Complexity:** Medium
**Priority:** Medium
**Source:** Secrets Management Code Review
**Description:** Support per-user encrypted secrets files for true multi-user scenarios.

**Problem Solved:**
Current single `.manus/secrets.enc` means all users share the same password and see the same secrets. Teams need user-specific API keys.

**Desired Behavior:**
```bash
# Initialize secrets for current user
orchestrator secrets init --user

# Creates .manus/secrets.enc.USERNAME (e.g., .manus/secrets.enc.alice)

# Each user sets their own SECRETS_PASSWORD
# Files are gitignored by default
```

**Implementation Notes:**
```python
SIMPLE_SECRETS_FILE_TEMPLATE = ".manus/secrets.enc.{username}"

def get_secrets_file(user_specific: bool = False) -> Path:
    if user_specific:
        username = os.environ.get('USER', 'default')
        return Path(SIMPLE_SECRETS_FILE_TEMPLATE.format(username=username))
    return Path(SIMPLE_SECRETS_FILE)

# SecretsManager checks both:
# 1. User-specific file first
# 2. Shared file as fallback
```

**Tasks:**
- [ ] Add `--user` flag to `secrets init`
- [ ] Update SecretsManager to check user-specific file first
- [ ] Add `.manus/secrets.enc.*` to default .gitignore
- [ ] Update SessionStart hook to handle user-specific files
- [ ] Document multi-user setup

---

### SEC-006: OAuth-Based Secrets (Future)
**Status:** Planned
**Complexity:** High
**Priority:** Low
**Source:** Secrets Management Code Review
**Description:** OAuth-based secrets storage for fully invisible UX (no password per session).

**Problem Solved:**
Users must enter `SECRETS_PASSWORD` each Claude Code Web session. True "invisible" secrets would require no per-session input.

**Desired Behavior:**
1. User authenticates once via OAuth (GitHub, Google, etc.)
2. Secrets stored server-side, keyed to user identity
3. Claude Code Web sessions auto-retrieve via OAuth token
4. No password required per session

**Architecture Notes:**
- Requires server-side component (secrets vault)
- OAuth provider integration for identity
- Token exchange for secrets retrieval
- Beyond current CLI-only architecture

**Consideration:**
This is a significant architectural change. May be better suited for a separate "Orchestrator Cloud" service rather than CLI enhancement.

**Tasks:**
- [ ] Design secrets vault API
- [ ] Implement OAuth integration (GitHub first)
- [ ] Create server-side storage
- [ ] Add `orchestrator auth login` command
- [ ] Update SecretsManager to use OAuth source
- [ ] Document OAuth setup

---

### SEC-002: Input Validation
**Status:** Planned  
**Complexity:** Low  
**Source:** Security Review  
**Description:** Add validation for URLs, viewport dimensions, and action parameters.

**Implementation Notes:**
- Validate URL format using `urllib.parse`
- Validate viewport width/height are positive integers within reasonable bounds
- Validate action types against allowed list

---

### SEC-003: Exception Message Sanitization
**Status:** Planned  
**Complexity:** Low  
**Source:** Security Review  
**Description:** Sanitize exception messages to avoid leaking sensitive information like URLs or headers.

**Implementation Notes:**
- Create wrapper that strips sensitive data from exception messages
- Log full details internally, return sanitized message to caller

---

## Architecture Improvements

### ARCH-001: Extract Retry Logic
**Status:** ✅ Completed (2026-01-06)
**Complexity:** Low
**Source:** Architecture Review (Score: 7/10)
**Description:** Extract retry logic with exponential backoff into a reusable utility.

**Implementation:**
- Created `src/utils.py` with `@retry_with_backoff` decorator
- Configurable: `max_retries`, `base_delay`, `max_delay`, `exceptions`
- Also added `slugify()` utility for filename generation
- 15 tests in `tests/test_utils.py`

**Files:** `src/utils.py`, `tests/test_utils.py`

---

### ARCH-002: HTTP Client Dependency Injection
**Status:** Planned  
**Complexity:** Medium  
**Source:** Architecture Review  
**Description:** Allow injection of HTTP client for better testability.

**Implementation Notes:**
- Accept optional `session` parameter in `__init__`
- Default to `requests.Session()` if not provided
- Enables mocking without patching

---

## Workflow Improvements

### WF-001: Claude Code CLI Installation Check
**Status:** Planned  
**Complexity:** Low  
**Source:** Visual Verification Service task  
**Description:** Add setup phase that checks for Claude Code CLI and installs if missing.

**Implementation Notes:**
- Add `setup_requirements` section to workflow.yaml
- Check for `claude` command availability
- Provide installation instructions if missing

---

### WF-002: Available Secrets Documentation
**Status:** Planned  
**Complexity:** Low  
**Source:** Visual Verification Service task  
**Description:** Document available environment variables and secrets in workflow initialization.

**Implementation Notes:**
- Add `available_secrets` section to workflow.yaml
- Display during `orchestrator start`
- Include in generated plan template

---

### WF-003: Model Selection Guidance
**Status:** ✅ Completed (2026-01-07)
**Complexity:** Low
**Source:** Visual Verification Service task
**Description:** Use "latest generation available" principle for model selection instead of hardcoding specific model names.

**Implementation:**
- Added `get_latest_model(category)` function to model registry
- Categories: `codex`, `gemini`, `claude` and aliases (`security`, `quality`, `consistency`, `holistic`)
- Returns latest available model from priority list with fallbacks
- Maps review types to model families (security/quality → codex, consistency/holistic → gemini)

**Files:** `src/model_registry.py`

---

### WF-010: Auto-Run Third-Party Reviews on Completion
**Status:** ✅ Completed (2026-01-08)
**Complexity:** Medium
**Priority:** High
**Description:** When completing REVIEW phase items (security_review, quality_review, architecture_review), automatically run the corresponding third-party model review and capture results in completion notes.

**Implementation:**
- Added `REVIEW_ITEM_MAPPING` constant mapping item IDs to review types
- Added `run_auto_review()` helper function to execute reviews via ReviewRouter
- Modified `cmd_complete()` to auto-run reviews for mapped items
- Added `--skip-auto-review` flag (not recommended) for bypassing
- Blocks completion if review fails or finds blocking issues
- Guides user to use `skip --reason` with explanation if review unavailable

**Files:** `src/cli.py`

---

### WF-011: Background Parallel Reviews During Workflow
**Status:** Planned
**Complexity:** High
**Priority:** High
**Source:** Session 6 - Phase 3 Security Remediation
**Description:** Run external model reviews continuously in background during workflow execution, not just blocking at commit time.

**Problem Solved:**
Currently, external model reviews only run when explicitly invoked (e.g., via `pre_commit_review.py`). This means issues are found late in the process. Reviews should run continuously as code is written, providing faster feedback.

**Desired Behavior:**
1. When EXECUTE phase starts, begin background review daemon
2. File watcher triggers reviews on save/change
3. Results cached - don't re-review unchanged files
4. Notification when review completes (terminal, sound, etc.)
5. At commit time, use cached results if available

**Implementation Notes:**
```python
# Background review daemon
class ReviewDaemon:
    def __init__(self, watch_paths: list[str]):
        self.watcher = FileWatcher(watch_paths)
        self.cache = ReviewCache()
        self.executor = ThreadPoolExecutor(max_workers=3)

    def start(self):
        for change in self.watcher.watch():
            if not self.cache.is_valid(change.path):
                self.executor.submit(self.review_file, change.path)

    def review_file(self, path: str):
        result = run_external_review(path)
        self.cache.store(path, result)
        self.notify(result)
```

**Tasks:**
- [ ] Create `ReviewDaemon` class with file watching
- [ ] Implement `ReviewCache` with invalidation on file change
- [ ] Add notification system (terminal bell, desktop notification)
- [ ] Integrate with workflow EXECUTE phase
- [ ] Add `--background-reviews` flag to enable
- [ ] Add `orchestrator review-status` command to check background results

---

### WF-012: Workflow State Injection After Context Compaction
**Status:** Completed
**Complexity:** Medium
**Priority:** Critical
**Source:** Phase 7 Learning - Process compliance failure
**Description:** Always inject workflow state into conversation context after context compaction so the AI cannot forget there's an active workflow.

**Problem Solved:**
During Phase 7 implementation, context compaction caused the AI to lose awareness of the active orchestrator workflow. It continued coding without the workflow, bypassing all quality gates (REVIEW, VERIFY, LEARN phases).

**Implementation:**
- Added `orchestrator context-reminder` command that outputs compact JSON with active, task, phase, progress, constraints
- Can be called by hooks to inject workflow state after context compaction

**Files:** `src/cli.py`, `src/engine.py`

**Completed Tasks:**
- [x] Added `get_context_reminder()` method to WorkflowEngine
- [x] Added `cmd_context_reminder` CLI command
- [x] Output is compact (<500 chars) for context efficiency
- [x] Tests: TestContextReminder (4 tests)

---

### WF-013: Block Implementation Code Without Active Workflow Phase
**Status:** Completed
**Complexity:** Medium
**Priority:** Critical
**Source:** Phase 7 Learning - Process compliance failure
**Description:** When an orchestrator workflow is active, refuse to write implementation code unless the workflow is in the EXECUTE phase.

**Problem Solved:**
AI can currently write code regardless of workflow phase. This allows bypassing PLAN phase approval and working during REVIEW/VERIFY/LEARN phases when it should be reviewing, not coding.

**Implementation:**
- Added `orchestrator verify-write-allowed` command
- Returns exit code 0 if allowed (in EXECUTE phase or no workflow), exit code 1 if blocked
- Can be used by Claude Code hooks to check before file writes

**Files:** `src/cli.py`, `src/engine.py`

**Completed Tasks:**
- [x] Added `verify_write_allowed()` method to WorkflowEngine
- [x] Added `cmd_verify_write_allowed` CLI command
- [x] Returns True when no workflow or in EXECUTE phase
- [x] Returns False with explanation in PLAN, REVIEW, VERIFY, LEARN phases
- [x] Tests: TestVerifyWriteAllowed (5 tests)

---

### WF-014: Block Workflow Finish Without Required Reviews
**Status:** Completed
**Complexity:** Low
**Priority:** High
**Source:** Phase 7 Learning - Process compliance failure
**Description:** Prevent `orchestrator finish` from completing if required external model reviews were not run.

**Problem Solved:**
Currently, workflows can be finished even if REVIEW phase items were completed without actually running external reviews. This defeats the purpose of multi-model review.

**Implementation:**
- Added `get_completed_reviews()` method to get review types from workflow log
- Added `validate_reviews_completed()` to check if required reviews (security, quality) were done
- Added `--skip-review-check --reason` flag to `orchestrator finish` to allow bypass with explanation

**Files:** `src/cli.py`, `src/engine.py`

**Completed Tasks:**
- [x] Added `get_completed_reviews()` method to WorkflowEngine
- [x] Added `validate_reviews_completed()` method to WorkflowEngine
- [x] Added review validation to `cmd_finish()` blocking without reviews
- [x] Added `--skip-review-check` flag with required `--reason` to override
- [x] Tests: TestReviewValidation (6 tests)

---

### WF-016: Machine-Readable Status Output
**Status:** Completed
**Complexity:** Low
**Priority:** Medium
**Source:** Process Compliance Fixes PRD
**Description:** Add `--json` flag to status command for machine-readable output, enabling hooks and scripts to parse workflow state.

**Problem Solved:**
The status command only output human-readable text, making it difficult for scripts and hooks to parse workflow state programmatically.

**Implementation:**
- Added `get_status_json()` method to WorkflowEngine returning full status dict
- Added `--json` flag to `orchestrator status` command
- Output includes: active, workflow_id, task, phase, progress, items, constraints

**Files:** `src/cli.py`, `src/engine.py`

**Completed Tasks:**
- [x] Added `get_status_json()` method to WorkflowEngine
- [x] Added `--json` flag to status command
- [x] JSON output is valid and includes all key fields
- [x] Tests: TestStatusJson (4 tests)

---

### WF-015: Detect and Warn on Work Outside Active Workflow
**Status:** Planned
**Complexity:** Medium
**Priority:** High
**Source:** Phase 7 Learning - Process compliance failure
**Description:** Detect when significant work (file changes, test runs) occurs outside an active workflow and warn loudly.

**Problem Solved:**
AI can work completely outside the orchestrator, creating code without any process. This should trigger warnings so user knows process is being bypassed.

**Implementation:**
- Monitor for file writes to src/ during active workflow
- If workflow active but phase doesn't match activity, warn
- If no workflow active but significant code written, suggest starting one

**Detection Rules:**
| Activity | Expected Phase | Warning If Different |
|----------|----------------|----------------------|
| Writing src/*.py | EXECUTE | "Code changes outside EXECUTE phase" |
| Running pytest | EXECUTE or VERIFY | "Tests run outside expected phase" |
| Writing docs/*.md | DOCUMENT or LEARN | "Docs updated outside expected phase" |

**Files:** `.claude/hooks/`, `src/cli.py`

**Tasks:**
- [ ] Create activity monitoring hook
- [ ] Define activity-to-phase mapping
- [ ] Add warning display mechanism
- [ ] Track warnings in workflow log

---

### WF-017: Document Plan File Requirement
**Status:** Planned
**Complexity:** Low
**Priority:** High
**Source:** PRD-001 Session - Workflow verification failure
**Description:** The orchestrator's PLAN phase verification expects `docs/plan.md` but this requirement isn't documented anywhere.

**Problem Solved:**
Workflow failed during PRD-001 implementation with "File not found: docs/plan.md" requiring manual intervention.

**Options:**
1. **Document requirement** - Add to CLAUDE.md and workflow.yaml comments
2. **Make configurable** - `plan_file_path` setting in workflow.yaml
3. **Remove verification** - Don't require specific file path for plan

**Recommendation:** Option 2 - make configurable with `docs/plan.md` as default.

**Tasks:**
- [ ] Add `plan_file_path` setting to workflow.yaml schema
- [ ] Update verification to use configurable path
- [ ] Document in CLAUDE.md
- [ ] Add sensible default

---

### WF-018: Allow "No New Failures" Verification Mode
**Status:** Planned
**Complexity:** Medium
**Priority:** High
**Source:** PRD-001 Session - Pre-existing test failures blocking verification
**Description:** Allow `run_tests` verification to accept "no new failures" instead of requiring all tests pass.

**Problem Solved:**
2 pre-existing test failures in `tests/conflict/test_pipeline.py` caused orchestrator's `run_tests` verification to fail, even though all PRD-related tests passed. Had to skip the item.

**Implementation:**
```yaml
- id: "run_tests"
  verification:
    type: command
    command: "pytest tests/"
    mode: "no_new_failures"  # vs "all_pass" (default)
```

**Tasks:**
- [ ] Add `mode` parameter to command verification
- [ ] Implement baseline test results tracking
- [ ] Compare current failures vs baseline
- [ ] Pass if no NEW failures introduced

---

### WF-019: Enforce TDD Order in Workflow
**Status:** Planned
**Complexity:** Medium
**Priority:** Medium
**Source:** PRD-001 Session, Global Installation Learnings
**Description:** Restructure workflow to enforce test-first development (red-green-refactor).

**Problem Solved:**
Current workflow has `write_tests` as first EXECUTE item, but nothing prevents implementing code first. This reverses TDD and leads to tests that verify "what was built" not "what was intended."

**Options:**

**Option A: Split into red/green phases**
```yaml
- id: "write_failing_tests"
  name: "Write failing test stubs (red)"
  verification:
    type: command
    command: "pytest --tb=no"
    expect_exit_code: 1  # Tests SHOULD fail initially
- id: "implement_code"
  name: "Implement to pass tests (green)"
```

**Option B: Add test existence check before implementation**
```yaml
- id: "verify_test_stubs_exist"
  verification:
    type: glob
    pattern: "tests/**/test_*.py"
    min_files: 1
```

**Tasks:**
- [ ] Decide on enforcement mechanism
- [ ] Update default_workflow.yaml
- [ ] Document TDD expectations in CLAUDE.md
- [ ] Add `expect_exit_code` support to command verification

---

### WF-020: Add Missing Review Types to Default Workflow
**Status:** ✅ Completed (2026-01-09)
**Complexity:** Low
**Priority:** High
**Source:** PRD-001 Session - Only 3 of 5 review types in workflow
**Description:** Add `consistency_review` and `vibe_coding_review` items to default workflow's REVIEW phase.

**Problem Solved:**
The multi-model review system supports 5 review types, but the workflow only triggers 3:

| Review Type | Model | In Workflow? | In REVIEW_ITEM_MAPPING? |
|------------|-------|--------------|-------------------------|
| security | Codex | ✅ security_review | ✅ |
| quality | Codex | ✅ quality_review | ✅ |
| holistic | Gemini | ✅ architecture_review (maps to holistic) | ✅ |
| consistency | Gemini | ❌ Missing | ❌ |
| vibe_coding | Grok | ❌ Missing | ❌ |

During PRD-001, only 2 reviews ran (security, quality) because architecture_review wasn't completed.

**Implementation:**
```yaml
# In REVIEW phase - add these items
- id: "consistency_review"
  name: "Consistency review (patterns, utilities)"
  description: "Gemini reviews for pattern compliance and existing utility usage"
  optional: true
- id: "vibe_coding_review"
  name: "Vibe coding review (AI-specific issues)"
  description: "Grok reviews for hallucinations, cargo cult patterns, AI blind spots"
  optional: true
```

```python
# In cli.py REVIEW_ITEM_MAPPING - add these mappings
REVIEW_ITEM_MAPPING = {
    "security_review": "security",
    "quality_review": "quality",
    "architecture_review": "holistic",
    "consistency_review": "consistency",     # Add
    "vibe_coding_review": "vibe_coding",     # Add
}
```

**Implementation:**
- workflow.yaml and default_workflow.yaml already had all 5 review items
- Updated REVIEW_ITEM_MAPPING in cli.py to include all 6 mappings:
  - security_review → security
  - quality_review → quality
  - architecture_review → holistic (legacy)
  - consistency_review → consistency
  - holistic_review → holistic
  - vibe_coding_review → vibe_coding

**Files:** `src/cli.py`

**Tasks:**
- [x] Add consistency_review to default_workflow.yaml (already present)
- [x] Add vibe_coding_review to default_workflow.yaml (already present)
- [x] Update REVIEW_ITEM_MAPPING in cli.py with both new mappings
- [ ] Document all 5 review types in CLAUDE.md

---

### ARCH-003: Single Source of Truth for Review Types
**Status:** ✅ Completed (2026-01-09)
**Complexity:** Medium
**Priority:** High
**Source:** WF-020 Fix Session - Discovered structural issue
**Description:** Review types are defined in 4 different places with no validation they're in sync. This caused PRD-001 to silently miss reviews.

**Problem Solved:**
Currently, adding a new review type requires updating 4 places:
1. `workflow.yaml` REVIEW phase items
2. `REVIEW_ITEM_MAPPING` in `src/cli.py`
3. `execute_all_reviews()` in `src/review/router.py`
4. `settings.reviews.types` in `workflow.yaml`

If any are missed, reviews silently don't run. No validation catches this.

**Desired State:**
Single source of truth with derived/validated copies:

```python
# Option A: Derive from workflow.yaml
# workflow.yaml's REVIEW phase items are the source of truth
# REVIEW_ITEM_MAPPING is auto-generated from workflow items
# execute_all_reviews() reads from workflow definition

# Option B: Central registry
# src/review/registry.py defines all review types
# workflow.yaml, cli.py, router.py all import from registry
# Validation at startup checks consistency

# Option C: Validation-only
# Keep current structure but add startup validation
# Fail loudly if any review type is missing from any location
```

**Implementation (Recommended: Option C first, then Option B):**

1. **Immediate: Add validation**
```python
def validate_review_configuration():
    """Validate all review locations are in sync."""
    from src.cli import REVIEW_ITEM_MAPPING
    from src.review.router import ALL_REVIEW_TYPES

    workflow_items = get_review_items_from_workflow()
    mapping_types = set(REVIEW_ITEM_MAPPING.values())
    router_types = set(ALL_REVIEW_TYPES)

    if mapping_types != router_types:
        raise ConfigurationError(
            f"REVIEW_ITEM_MAPPING types {mapping_types} != "
            f"router types {router_types}"
        )
```

2. **Follow-up: Central registry**
```python
# src/review/registry.py
REVIEW_TYPES = {
    "security": {"model": "codex", "description": "OWASP, injection, auth"},
    "quality": {"model": "codex", "description": "Code smells, edge cases"},
    "consistency": {"model": "gemini", "description": "Pattern compliance"},
    "holistic": {"model": "gemini", "description": "Senior engineer review"},
    "vibe_coding": {"model": "grok", "description": "AI-specific issues"},
}

# All other files import from here
```

**Implementation:**
Created `src/review/registry.py` as the single source of truth:
- `REVIEW_TYPES` dict with `ReviewTypeDefinition` for each review type
- `get_review_item_mapping()` - replaces hardcoded dict in cli.py
- `get_all_review_types()` - replaces hardcoded list in router.py
- `validate_review_configuration()` - validates all locations in sync
- `get_configuration_status()` - debugging/display helper

Updated consumers to import from registry:
- `src/cli.py` - `REVIEW_ITEM_MAPPING = get_review_item_mapping()`
- `src/review/router.py` - `get_all_review_types()` in execute_all_reviews()
- `src/review/__init__.py` - exports all registry functions

**Files:**
- `src/review/registry.py` (new - 185 lines)
- `src/cli.py` (updated import)
- `src/review/router.py` (updated import)
- `src/review/__init__.py` (added exports)
- `tests/review/test_registry.py` (new - 33 tests)

**Tasks:**
- [x] Add `validate_review_configuration()` function
- [ ] Call validation at orchestrator startup (deferred - not critical path)
- [x] Add test that fails if reviews are out of sync
- [x] Create `src/review/registry.py` with canonical definitions
- [x] Update cli.py to import from registry
- [x] Update router.py to import from registry
- [ ] Update workflow.yaml to reference registry types (not needed - workflow.yaml is config, not code)

---

### WF-021: Add Manual Gate to Clarifying Questions
**Status:** Planned
**Complexity:** Low
**Priority:** High
**Source:** WF-005-009 Session - Clarifying questions not paused for
**Description:** Make `clarifying_questions` a manual gate so the agent must pause for user answers.

**Problem Solved:**
During WF-005-009 implementation, agent presented clarifying questions but immediately continued with recommended answers instead of pausing. User feedback: "You didn't pause for me to answer the questions."

**Implementation:**
```yaml
- id: "clarifying_questions"
  name: "Ask Clarifying Questions"
  verification:
    type: "manual_gate"
    description: "Present questions AND wait for user answers before proceeding"
  notes:
    - "[caution] MUST pause and wait for user answers"
    - "[caution] Do NOT proceed with defaults without explicit user confirmation"
```

**Tasks:**
- [ ] Update clarifying_questions in default_workflow.yaml
- [ ] Add manual_gate verification
- [ ] Add cautionary notes
- [ ] Test that advance is blocked until gate approved

---

### WF-022: PRD Execution Continuity After Context Compaction
**Status:** Planned
**Complexity:** High
**Priority:** Critical
**Source:** PRD-001 Phase 2 Session - User concern about forgetting merge flows
**Description:** Ensure PRD execution state and merge workflows survive context compaction and can be resumed safely.

**Problem Solved:**
During PRD-001 Phase 2 implementation, context compaction caused the AI to forget the active orchestrator workflow. The same could happen during PRD execution, leading to:
1. **Orphaned Claude Squad sessions** - Agents running with no one to merge their work
2. **Half-merged integration branch** - Some tasks merged, others forgotten
3. **Lost PRD state** - Which tasks are done, which pending, which have conflicts
4. **Wasted compute** - Sessions running indefinitely without completion

**Current State:**
- `session_registry.json` persists session state (but not consulted on context restore)
- `.prd_state.json` persists PRD execution state (but not auto-injected)
- `orchestrator status` and `prd status` can show state (but require manual invocation)

**Desired Behavior:**
1. **Auto-inject PRD state** on context restore:
   ```
   ACTIVE PRD EXECUTION DETECTED
   ─────────────────────────────
   PRD: prd-001 (5/10 tasks complete)
   Active sessions: 3 (task-6, task-7, task-8)
   Integration branch: integration/prd-001

   You MUST run `prd status` to see full state before taking any action.
   ```

2. **Warn on idle sessions**:
   - Track last activity time per session
   - Warn if session idle > 1 hour
   - Suggest `prd merge <task>` or `prd attach <task>`

3. **Resume capability**:
   - `prd resume` command to restore context from state files
   - Show what was in progress, what needs attention
   - Suggest next actions based on state

4. **State file validation**:
   - Detect inconsistencies (session says "done" but task not merged)
   - Warn about stale state (last updated > 24h ago)
   - Suggest cleanup actions

**Implementation:**
```python
# Hook for context restore (in CLAUDE.md or hooks)
def on_context_restore():
    prd_state = load_prd_state()
    if prd_state and prd_state.is_active:
        print_prd_warning(prd_state)
        inject_prd_context(prd_state)

# In src/prd/executor.py
class PRDExecutor:
    def get_resume_context(self) -> str:
        """Generate context for resuming after compaction."""
        return f"""
        PRD: {self.prd.id}
        Tasks: {self._format_task_summary()}
        Sessions: {self._format_session_summary()}
        Next action: {self._suggest_next_action()}
        """
```

**Files:** `.claude/hooks/`, `src/prd/executor.py`, `CLAUDE.md`

**Tasks:**
- [ ] Add `on_context_restore` hook that checks for active PRD
- [ ] Inject PRD state into context on restore
- [ ] Add `prd resume` command
- [ ] Add idle session warnings to `prd status`
- [ ] Add state validation with inconsistency detection
- [ ] Document PRD continuity behavior in CLAUDE.md
- [ ] Test context compaction with active PRD

**Risk if Not Implemented:**
PRD execution with Claude Squad relies on AI memory to coordinate merge timing. If context compacts mid-execution, sessions continue but merging stops. This could leave integration branches in broken states or waste significant compute on orphaned sessions.

---

### PRD-003: Unified Orchestrator with Automatic Parallelization
**Status:** Planned
**Complexity:** High
**Priority:** High
**Source:** PRD-001 Phase 2 Session - User request for integrated system
**Depends On:** PRD-001 Phase 2 (Claude Squad integration)

**Description:** Integrate the PRD multi-agent execution model directly into the orchestrator workflow, allowing automatic task parallelization when complexity is detected.

**Problem Solved:**
Currently users must choose between:
1. `orchestrator start` - Single-agent workflow (PLAN→EXECUTE→REVIEW→VERIFY→LEARN)
2. `prd spawn/merge/sync` - Multi-agent parallel execution

This creates cognitive overhead and requires users to know upfront whether a task is complex. The unified system would auto-detect complexity and offer parallelization.

**Desired Behavior:**

```
orchestrator start "Build authentication system" [--parallel | --no-parallel]
                              │
                              ▼
                    ┌─────────────────┐
                    │   PLAN PHASE    │
                    │                 │
                    │ Assess task     │
                    │ complexity...   │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
     Complex (or --parallel)        Simple (or --no-parallel)
              │                             │
              ▼                             ▼
    "Break into sub-tasks?"         Single-agent execution
    [Shows suggested breakdown]     (current behavior)
              │
              ▼
    Spawn parallel agents via Claude Squad
    Each sub-agent runs own orchestrator workflow
    Parent coordinates spawn/merge
              │
              ▼
    Aggregate REVIEW & LEARN phases
```

**CLI Interface:**

```bash
# Auto-detect complexity (prompt if complex)
orchestrator start "Build auth system"

# Force parallel execution
orchestrator start "Build auth system" --parallel

# Force single-agent (skip complexity check)
orchestrator start "Build auth system" --no-parallel

# Specify max parallel agents
orchestrator start "Build auth system" --parallel --max-agents 4
```

**Implementation Phases:**

**Phase 1: Complexity Detection**
- Analyze task description for complexity signals
- Count implied sub-tasks (e.g., "and", lists, multiple features)
- Check for domain spread (auth + API + UI = complex)
- Suggest breakdown when complexity detected

**Phase 2: Sub-Task Generation**
- AI-assisted task decomposition
- Generate PRD-style task list with dependencies
- User approval of breakdown before spawning

**Phase 3: Parallel Execution**
- Spawn Claude Squad sessions for each sub-task
- Each session runs full orchestrator workflow (PLAN→LEARN)
- Parent tracks progress across all sub-agents
- SpawnScheduler prevents conflicting tasks from running simultaneously

**Phase 4: Aggregation**
- Merge completed sub-agent work via existing `prd merge`
- Aggregate REVIEW results from all sub-agents
- Combine LEARN phase learnings
- Final integration review on merged code

**Key Benefits:**
1. **Single entry point** - Users don't need to know about PRD vs orchestrator
2. **Automatic complexity detection** - System suggests parallelization when helpful
3. **User control** - Can override with `--parallel` / `--no-parallel` flags
4. **Consistent quality** - Each sub-task still gets full PLAN→REVIEW→LEARN cycle
5. **Simpler mental model** - "Start a task, system handles the rest"

**Files to Create/Modify:**
- `src/complexity_analyzer.py` (new) - Task complexity detection
- `src/task_decomposer.py` (new) - AI-assisted task breakdown
- `src/cli.py` - Add `--parallel`, `--no-parallel`, `--max-agents` flags
- `src/engine.py` - Integrate parallel execution path
- `src/prd/executor.py` - Add sub-agent orchestrator workflow injection

**Tasks:**
- [ ] Design complexity scoring algorithm
- [ ] Implement complexity detection in PLAN phase
- [ ] Add sub-task generation with user approval
- [ ] Integrate SpawnScheduler into orchestrator flow
- [ ] Update task prompts to run full orchestrator workflow (done in Phase 2)
- [ ] Implement progress tracking across sub-agents
- [ ] Add aggregation logic for REVIEW and LEARN phases
- [ ] Add CLI flags (`--parallel`, `--no-parallel`, `--max-agents`)
- [ ] Add tests for complexity detection
- [ ] Add tests for task decomposition
- [ ] Document unified workflow in CLAUDE.md

---

### WF-016: Integrate Learning System with Git Merge Conflicts
**Status:** Planned
**Complexity:** Medium
**Priority:** High
**Source:** Phase 7 Learning - Identified gap in learning system scope
**Description:** Use the pattern memory and strategy tracker for regular git merge conflicts, not just multi-agent PRD scenarios.

**Problem Solved:**
The learning system (PatternMemory, StrategyTracker, FeedbackLoop) is currently only invoked during PRD multi-agent execution via WaveResolver. Regular git merge conflicts during normal development don't benefit from historical learning. This limits the system's usefulness.

**Desired Behavior:**
```
git pull → CONFLICT detected
         ↓
Consult PatternMemory for similar conflicts
         ↓
Suggest resolution strategy based on historical win rates
         ↓
Apply resolution (or present options to user)
         ↓
Record outcome to improve future suggestions
```

**Implementation:**
- Create `git-merge-with-learning` wrapper command
- Hook into `git pull` / `git merge` detection
- Extract conflict context (files, conflict type, code patterns)
- Query PatternMemory.suggest_resolution()
- Present StrategyTracker recommendations
- After resolution, record outcome via FeedbackLoop

**Integration Points:**
```python
# New command in CLI
def cmd_smart_merge(branch: str):
    """Merge with learning system assistance."""
    result = subprocess.run(["git", "merge", branch], capture_output=True)

    if "CONFLICT" in result.stdout:
        conflicts = parse_git_conflicts()
        for conflict in conflicts:
            suggestion = pattern_memory.suggest_resolution(
                conflict_type=conflict.type,
                files_involved=conflict.files,
                intent_categories=extract_intents(conflict),
            )
            if suggestion and suggestion.confidence > 0.7:
                print(f"Suggested: {suggestion.strategy} ({suggestion.confidence:.0%})")
                apply_suggestion(conflict, suggestion)
```

**Files:** `src/cli.py`, `src/git_integration.py` (new)

**Tasks:**
- [ ] Create git conflict parser to extract conflict context
- [ ] Add `orchestrator smart-merge` command
- [ ] Integrate with PatternMemory.suggest_resolution()
- [ ] Integrate with StrategyTracker.recommend()
- [ ] Add outcome recording after conflict resolution
- [ ] Add `--auto-resolve` flag for high-confidence suggestions
- [ ] Add `--learn-only` flag to record without suggesting

---

### CORE-019: Fix OpenAI/LiteLLM Model Configuration
**Status:** Planned
**Complexity:** Low
**Priority:** High
**Source:** Session 6 - Pre-commit review failures
**Description:** Fix OpenAI model configuration in LiteLLM integration so external reviews work correctly.

**Problem Solved:**
When running `pre_commit_review.py`, OpenAI models fail with:
```
LLM Provider NOT provided. Pass in the LLM provider you are trying to call.
You passed model=gpt-5.2-max
```

LiteLLM requires specific model ID formats (e.g., `openai/gpt-4o` not `gpt-5.2-max`).

**Files to Update:** `src/review/models.py`, `src/review/orchestrator.py`

**Implementation Notes:**
```python
# Current (broken)
ModelSpec(provider="openai", model_id="gpt-5.2-max", ...)

# Fixed
ModelSpec(provider="openai", model_id="openai/gpt-4o", ...)

# Or update LiteLLMAdapter to prepend provider
def _get_litellm_model_id(self, spec: ModelSpec) -> str:
    if "/" not in spec.model_id:
        return f"{spec.provider}/{spec.model_id}"
    return spec.model_id
```

**Tasks:**
- [ ] Update model IDs in `get_default_config()` to use litellm format
- [ ] Add model ID normalization in `LiteLLMAdapter`
- [ ] Test all configured models work with litellm
- [ ] Add fallback model configuration

---

### CORE-020: Use CLI Tools for External Reviews
**Status:** Planned
**Complexity:** Medium
**Priority:** High
**Source:** Session 6 - Review quality observation
**Description:** Use Gemini CLI and Codex CLI for external reviews instead of API calls, as CLI tools have better repository context.

**Problem Solved:**
API-based reviews send diff content in the request, limiting context. CLI tools (like `gemini` CLI, `codex` CLI) can browse the full repository, understand file relationships, and provide more comprehensive reviews.

**Current Behavior:**
```python
# API-based review - limited context
response = litellm.completion(
    model="gemini-2.5-pro",
    messages=[{"role": "user", "content": diff_content}]
)
```

**Desired Behavior:**
```python
# CLI-based review - full repo context
result = subprocess.run(
    ["gemini", "review", "--diff", diff_file],
    capture_output=True
)
```

**Implementation Notes:**
```python
class CLIReviewer:
    def __init__(self, cli_tool: str):
        self.cli_tool = cli_tool  # "gemini", "codex", "claude"

    def is_available(self) -> bool:
        return shutil.which(self.cli_tool) is not None

    async def review(self, context: ChangeContext) -> ModelReview:
        # Write diff to temp file
        with tempfile.NamedTemporaryFile(suffix=".diff") as f:
            f.write(context.diff_content.encode())
            f.flush()

            result = subprocess.run(
                [self.cli_tool, "review", f.name],
                capture_output=True,
                text=True
            )

        return self._parse_output(result.stdout)

# In ReviewerFactory
def create(spec: ModelSpec) -> Reviewer:
    cli = CLIReviewer(spec.provider)
    if cli.is_available():
        return cli  # Prefer CLI
    return LiteLLMAdapter(spec)  # Fall back to API
```

**Tasks:**
- [ ] Create `CLIReviewer` class
- [ ] Add CLI detection to `ReviewerFactory`
- [ ] Parse CLI output into `ReviewIssue` format
- [ ] Handle CLI tool authentication (if required)
- [ ] Add `--prefer-api` flag to force API mode
- [ ] Document CLI tool setup requirements

---

### CORE-022: Fix ReviewRouter context_override Parameter
**Status:** Planned
**Complexity:** Low
**Priority:** High
**Source:** PRD-001 Session - Error during workflow execution
**Description:** Fix the `execute_review()` method in ReviewRouter that fails with "got unexpected keyword argument 'context_override'".

**Problem Solved:**
During PRD-001 workflow execution, the orchestrator displayed an error:
```
ReviewRouter.execute_review() got unexpected keyword argument 'context_override'
```

This indicates a mismatch between how the CLI calls the ReviewRouter and the actual method signature.

**Implementation:**
```python
# Either add the parameter to the method signature:
def execute_review(self, review_type: str, context_override: Optional[dict] = None) -> ReviewResult:
    ...

# Or fix the calling code in cli.py to not pass it:
result = router.execute_review(review_type)  # Remove context_override
```

**Tasks:**
- [ ] Find where `execute_review()` is called with `context_override`
- [ ] Determine if the parameter is needed
- [ ] Either add parameter to method or remove from call site
- [ ] Add test to prevent regression

---

### CORE-021: Model Availability Validation Testing
**Status:** Planned
**Complexity:** Medium
**Priority:** High
**Source:** Session 6 - Review reliability issues
**Description:** Add comprehensive testing and validation for model availability before attempting reviews. Ensure correct methodology is used (LiteLLM API, OpenRouter, CLI, direct).

**Problem Solved:**
External model reviews fail silently or with cryptic errors when:
1. Model IDs are incorrect or fictional (e.g., `gpt-5.2-max` doesn't exist)
2. LiteLLM provider prefix is wrong
3. API keys are missing or expired
4. CLI tools are not installed
5. OpenRouter routing fails

**Current Behavior:**
Reviews fail at runtime with errors like:
```
LLM Provider NOT provided. Pass in the LLM provider you are trying to call.
You passed model=gpt-5.2-max
```

**Desired Behavior:**
```python
# Before any review starts
validation = await orchestrator.validate_models()
if not validation.all_available:
    for model in validation.unavailable:
        print(f"⚠ {model.id}: {model.error}")
    print("\nAvailable alternatives:")
    for alt in validation.alternatives:
        print(f"  {alt.original} → {alt.replacement}")
```

**Implementation Notes:**
```python
class ModelValidator:
    async def validate(self, spec: ModelSpec) -> ValidationResult:
        # 1. Check model ID is real and supported
        if spec.full_id in KNOWN_FICTIONAL_MODELS:
            return ValidationResult(
                valid=False,
                error="fictional_model",
                suggestion=KNOWN_FICTIONAL_MODELS[spec.full_id]
            )

        # 2. Check API key availability
        key_name = f"{spec.provider.upper()}_API_KEY"
        if not os.environ.get(key_name):
            return ValidationResult(valid=False, error="missing_api_key")

        # 3. Check CLI availability (if CLI preferred)
        if self.prefer_cli and not shutil.which(spec.provider):
            # Fall back to API
            pass

        # 4. Test actual connectivity (optional health check)
        try:
            await litellm.acompletion(
                model=spec.litellm_id,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1
            )
        except Exception as e:
            return ValidationResult(valid=False, error=str(e))

        return ValidationResult(valid=True)

# Add to ReviewOrchestrator.review()
async def review(self, context: ChangeContext) -> ReviewResult:
    # Validate all models first
    validation = await self._validate_models()
    if not validation.all_valid:
        # Log warnings, use fallbacks
        for model, result in validation.failures.items():
            logger.warning(f"Model {model} unavailable: {result.error}")
            if result.fallback:
                self._use_fallback(model, result.fallback)
```

**Tasks:**
- [ ] Create `ModelValidator` class in `src/review/validation.py`
- [ ] Add model ID validation (known real vs fictional models)
- [ ] Add API key detection for each provider
- [ ] Add CLI tool detection
- [ ] Add health check endpoint testing
- [ ] Create test suite for validation logic
- [ ] Add `--validate-models` flag to pre-commit review script
- [ ] Document model configuration requirements

---

### WF-005: Summary Before Approval Gates
**Status:** Planned
**Complexity:** Low
**Priority:** High
**Source:** ideas.md - "Provide a summary on screen before asking for approval"
**Description:** Show a concise summary of work completed, issues found, and AI feedback before any manual approval gate.

**Problem Solved:**
When workflows reach manual gates (phase advances, item approvals), users must scroll back through logs to understand what happened. This slows down review and increases the chance of rubber-stamping approvals.

**Desired Behavior:**
Before any manual gate, display:
```
============================================================
📋 SUMMARY BEFORE APPROVAL
============================================================
Phase: EXECUTE → REVIEW

Completed Items:
  ✓ implement_core_logic - "Added retry mechanism to API client"
  ✓ write_unit_tests - "18 tests, all passing"
  ✓ integration_tests - "3 integration tests added"

Skipped Items:
  ⊘ performance_tests - "Deferred to follow-up task"

Files Modified: 8
  • src/api/client.py (+45, -12)
  • src/api/retry.py (new, +78)
  • tests/test_client.py (+156)
  • ...

Ready to advance to REVIEW phase?
============================================================
```

**Implementation Notes:**
- Hook into `cmd_advance()` and any approval commands
- Gather: completed items with notes, skipped items with reasons, file changes (git diff --stat)
- Display summary, then prompt for confirmation
- Add `--yes` flag to skip confirmation for automation

**Tasks:**
- [ ] Create `generate_phase_summary()` function in CLI
- [ ] Integrate git diff --stat for file change summary
- [ ] Add summary display before `advance` confirmation
- [ ] Add `--yes` flag to bypass for CI/automation
- [ ] Add tests for summary generation

---

### WF-006: File Links in Status Output
**Status:** Planned
**Complexity:** Low
**Priority:** Medium
**Source:** ideas.md - "Need a link to the relevant files in the comments after each section before approve"
**Description:** Include direct file paths in status output and completion notes to speed up human review.

**Problem Solved:**
When reviewing completed items, humans need to find the relevant code. Currently they must search or ask the agent. Direct file links make review faster.

**Desired Behavior:**
```
✓ implement_auth_middleware
  Notes: Added JWT validation middleware
  Files:
    • src/middleware/auth.py:15-45 (new function)
    • src/routes/api.py:8 (import added)
    • tests/test_auth.py:1-89 (new file)
```

**Implementation Notes:**
- Track files modified during item completion (via git diff or explicit logging)
- Store file list in item completion metadata
- Display in `orchestrator status` output
- Format as clickable paths for terminal emulators that support it

**Tasks:**
- [ ] Add `files_modified` field to item completion metadata
- [ ] Auto-detect files from git diff when completing items
- [ ] Update status display to show file links
- [ ] Add `--files` flag to show/hide file details
- [ ] Support terminal hyperlinks (OSC 8) for clickable paths

---

### WF-007: Learnings to Roadmap Pipeline
**Status:** Planned
**Complexity:** Low
**Priority:** Medium
**Source:** ideas.md - "Are we checking if Learnings implies new things for the ROADMAP?"
**Description:** Automatically suggest roadmap items based on captured learnings during the LEARN phase.

**Problem Solved:**
Learnings are captured but often not actioned. The loop from "lesson learned" to "roadmap item" to "implemented improvement" is manual and often forgotten.

**Desired Behavior:**
When completing the LEARN phase:
```
============================================================
📚 LEARNINGS CAPTURED
============================================================
1. "API retry logic was duplicated in 3 places - should extract to utility"
   → Suggested roadmap item: ARCH-XXX: Extract API retry utility

2. "Test setup took 20 minutes due to missing documentation"
   → Suggested roadmap item: WF-XXX: Improve test setup docs

3. "Model context window exceeded during large file review"
   → Suggested roadmap item: CORE-XXX: Chunked file review

Add these to ROADMAP.md? [y/N/edit]
============================================================
```

**Implementation Notes:**
- Parse learnings for actionable patterns (e.g., "should", "need to", "next time")
- Generate suggested roadmap entries with appropriate prefixes
- Optionally use AI to categorize and format suggestions
- Append to ROADMAP.md under a "Suggested from Learnings" section

**Tasks:**
- [ ] Create `analyze_learnings()` function to extract actionable items
- [ ] Generate roadmap entry templates from learnings
- [ ] Add interactive prompt to accept/edit/skip suggestions
- [ ] Append accepted items to ROADMAP.md
- [ ] Add `--auto-roadmap` flag to skip interactive prompt

---

### WF-008: AI Critique at Phase Gates
**Status:** Planned
**Complexity:** Medium
**Priority:** Medium
**Source:** ideas.md - "Should we have an AI critique the plan - or every step?"
**Description:** Add optional AI critique checkpoints at phase transitions, not just during REVIEW phase.

**Problem Solved:**
Currently multi-model review (CORE-016) only happens in REVIEW phase. Problems in planning or design aren't caught until code is written. Earlier critique catches issues sooner.

**Desired Behavior:**
At each phase gate, optionally run a quick AI critique:
```
============================================================
🔍 PHASE CRITIQUE: PLAN → EXECUTE
============================================================
Reviewer: gemini-2.0-flash (quick critique mode)

Observations:
  ⚠️ Risk analysis doesn't address API rate limiting
  ⚠️ No rollback plan specified
  ✓ Test strategy is comprehensive
  ✓ Dependencies correctly identified

Recommendation: Address rate limiting before proceeding

Continue anyway? [y/N/address]
============================================================
```

**Implementation Notes:**
- Lighter-weight than full REVIEW phase reviews
- Use fast/cheap model (e.g., gemini-flash, gpt-4o-mini)
- Focus on gaps, risks, and completeness rather than deep analysis
- Configurable: `phase_critique: true/false` in workflow.yaml
- Can be skipped with `--no-critique` flag

**Critique Focus by Phase:**
- PLAN → EXECUTE: Are requirements clear? Risks identified?
- EXECUTE → REVIEW: Are all items complete? Tests passing?
- REVIEW → VERIFY: Were review findings addressed?
- VERIFY → LEARN: Did verification pass? Any remaining issues?

**Tasks:**
- [ ] Create `PhaseTransitionCritique` class
- [ ] Define critique prompts for each phase transition
- [ ] Integrate with `cmd_advance()`
- [ ] Add `phase_critique` setting to workflow.yaml
- [ ] Add `--no-critique` flag to bypass
- [ ] Use existing review router for model selection

---

### WF-009: Document Phase
**Status:** Planned
**Complexity:** Low
**Priority:** Medium
**Source:** ideas.md - "Add a final stage - document - update PRD, spec document, README files, set-up instructions"
**Description:** Add optional DOCUMENT phase after VERIFY to ensure documentation stays current.

**Problem Solved:**
Documentation often lags behind code changes. After verification passes, there's no prompt to update READMEs, setup guides, or specs. This leads to documentation drift.

**Desired Behavior:**
After VERIFY phase, optionally run DOCUMENT phase:
```yaml
# workflow.yaml
phases:
  # ... existing phases ...
  - id: DOCUMENT
    name: Documentation Update
    optional: true  # Can be skipped if no docs needed
    items:
      - id: update_readme
        name: Update README if needed
        optional: true
      - id: update_setup_guide
        name: Update setup/install instructions
        optional: true
      - id: update_api_docs
        name: Update API documentation
        optional: true
      - id: changelog_entry
        name: Add changelog entry
        optional: false  # Always required
```

**Implementation Notes:**
- Phase is optional - can be skipped entirely for small changes
- Individual items are mostly optional
- AI can auto-detect which docs need updates based on changes
- Changelog entry is typically required

**Tasks:**
- [ ] Add DOCUMENT phase to default workflow.yaml
- [ ] Make phase skippable with `orchestrator skip-phase DOCUMENT`
- [ ] Add doc-update detection (which files changed → which docs affected)
- [ ] Add changelog entry template generation
- [ ] Document when to skip vs. complete this phase

---

## Deferred Features

These features were considered but deferred for future consideration:

### DEF-001: Video Recording of Visual Tests
**Complexity:** Medium-High
**Reason Deferred:** Nice-to-have, not core functionality. Adds ffmpeg dependency and storage requirements.

### DEF-002: Response Caching
**Complexity:** Medium
**Reason Deferred:** Optimization that adds complexity. Evaluate need based on actual usage patterns.

### DEF-003: Network Interception
**Complexity:** High
**Reason Deferred:** Significant scope creep. Would change service architecture substantially.

### DEF-004: Sub-Agent Type Hints
**Complexity:** Low
**Reason Deferred:** `agent_hint` field on items (explore, plan, execute). Deferred until provider abstraction settles.

### DEF-005: Tool Result Compression
**Complexity:** Low
**Reason Deferred:** Change handoff prompts to reference files rather than include content. Optimize later if needed.

### DEF-006: Slack Integration
**Complexity:** Medium
**Reason Deferred:** Slack bot/channel for workflow notifications, approval requests, status updates. Future consideration.

### DEF-007: GitHub Integration
**Complexity:** Medium
**Reason Deferred:** Create issues from workflow items, link PRs to phases, auto-complete on merge. Future consideration.

### DEF-008: VS Code Extension
**Complexity:** High
**Reason Deferred:** Sidebar showing workflow status, click to complete/skip. Future consideration.

### DEF-009: Workflow Templates Library
**Complexity:** Medium
**Reason Deferred:** Pre-built workflows for common tasks. `orchestrator init --template bugfix`. Future consideration.

### DEF-010: Distributed/Team Workflows
**Complexity:** High
**Reason Deferred:** Multiple agents on same workflow, locking/claiming items. Complex, long-term.
**Update (2026-01-09):** See PRD-001 for simpler approach using Claude Squad + merge coordination.

### DEF-011: LLM-Assisted Workflow Generation
**Complexity:** Medium
**Reason Deferred:** Describe task, LLM generates workflow.yaml. Experimental idea.

---

## Completed Items

See [CHANGELOG.md](CHANGELOG.md) for completed features and their details.

---

## Contributing

When adding items to this roadmap:
1. Use the appropriate prefix (CORE-, VV-, SEC-, ARCH-, WF-, DEF-)
2. Include: Status, Complexity, Description, Implementation Notes
3. For audit items, include Source reference
4. When completed, move to CHANGELOG.md and remove from this file
