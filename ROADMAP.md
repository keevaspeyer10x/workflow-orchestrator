# Workflow Orchestrator Roadmap

This document tracks **planned** improvements, deferred features, and audit recommendations.

For completed features, see [CHANGELOG.md](CHANGELOG.md).

## Maintenance

When completing a roadmap item:
1. Add a brief entry to [CHANGELOG.md](CHANGELOG.md) under the appropriate version
2. Delete the item from this file
3. Keep changelog entries concise - what shipped, not implementation details

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

#### CORE-023-P1: Conflict Resolution - Core (No LLM)
**Status:** COMPLETED (2026-01-09)
**Complexity:** Medium
**Priority:** CRITICAL - Blocks parallel execution
**Source:** User request - Cannot run multiple Claude Code instances in parallel without this
**Plan:** `docs/plan.md`
**Implementation:** `src/git_conflict_resolver.py`, CLI in `src/cli.py`

**Description:** Part 1 of `orchestrator resolve` - conflict detection, fast resolution (rerere, 3-way merge), and interactive escalation. No LLM in Part 1.

**Scope:**
- Conflict detection (merge and rebase)
- Get base/ours/theirs from git index
- rerere integration (read existing resolutions)
- Fast 3-way merge (git merge-file)
- Interactive escalation with options (ours/theirs/both/editor)
- CLI: `orchestrator resolve` (preview) + `--apply`
- Status integration (conflict warning)
- Basic validation and rollback

**NOT in Part 1:** LLM resolution, intent extraction, learning integration (see P2, P3)

**Tasks:**
- [ ] Create `src/git_conflict_resolver.py`
- [ ] Add `resolve` command to CLI
- [ ] Add status conflict detection
- [ ] Add unit tests
- [ ] Add integration tests
- [ ] Document in CLAUDE.md

---

#### CORE-023-P2: Conflict Resolution - LLM Integration
**Status:** ✅ Completed (2026-01-09)
**Complexity:** High
**Priority:** High
**Depends on:** CORE-023-P1

**Description:** Part 2 adds LLM-based resolution for complex conflicts that can't be auto-resolved.

**Implementation:**
- Created `src/resolution/llm_resolver.py` with full LLM resolution pipeline
- Added `--use-llm` flag to `orchestrator resolve` command
- Supports OpenAI, Gemini, and OpenRouter APIs
- 36 unit tests covering all key functionality

**Features delivered:**
- LLM-based resolution (opt-in with `--use-llm`)
- Intent extraction from code with structured JSON output
- Context assembly with CLAUDE.md conventions and token budget
- Tiered validation (conflict markers, syntax, JSON, YAML)
- Confidence-based escalation (HIGH = auto-apply, MEDIUM = ask, LOW = escalate)
- `--auto-apply-threshold` and `--confirm-all` options

**Security implemented:**
- Sensitive file detection (SENSITIVE_PATTERNS: .env, secrets, keys, etc.)
- Only conflict hunks + context sent to LLM
- API keys from environment only, never logged

---

#### CORE-023-P3: Conflict Resolution - Learning & Config
**Status:** Planned (after P2)
**Complexity:** Medium
**Priority:** Medium
**Depends on:** CORE-023-P2

**Description:** Part 3 adds learning from conflict patterns and configuration.

**Scope:**
- Log conflict resolutions to `.workflow_log.jsonl`
- LEARN phase surfaces conflict patterns
- Auto-add suggestions to ROADMAP.md (inform user, don't ask)
- Config file (`~/.orchestrator/config.yaml`)
  - Sensitive file globs
  - Per-file resolution policies
  - LLM enable/disable

---

#### CORE-023-T1: Golden File Tests for Conflict Resolution
**Status:** Planned
**Complexity:** Low
**Priority:** Medium
**Source:** CORE-023-P2 implementation review

**Description:** Add golden file tests for known conflict patterns to catch edge cases.

**Scope:**
- Create `tests/golden/` directory with known conflict patterns
- Add 5-10 common patterns: import conflicts, function edits, config files
- Property-based tests (Hypothesis) for fuzzing edge cases
- Regression test framework for capturing real-world failures

---

#### CORE-023-T2: PRD WaveResolver Integration
**Status:** Planned
**Complexity:** Low
**Priority:** Medium (when PRD conflicts are actively used)
**Depends on:** CORE-023-P2

**Description:** Integrate LLM resolution with PRD WaveResolver for multi-agent conflicts.

**Scope:**
- Add LLM resolution option to `WaveResolver.resolve_in_waves()`
- Pass PRD context (manifests, task descriptions) to `LLMResolver`
- Test with multi-agent conflict scenarios

---

#### CORE-026: Review Failure Resilience & API Key Recovery
**Status:** Planned
**Complexity:** Medium
**Priority:** HIGH
**Source:** CORE-023 implementation - Reviews silently failed after context compaction lost API keys

**Problem:**
During CORE-023-P1 implementation, context compaction occurred mid-session. This caused:
1. API keys (GEMINI_API_KEY, OPENAI_API_KEY, XAI_API_KEY) to be lost from environment
2. Reviews to fail with `ReviewRouter.execute_review() got an unexpected keyword argument 'context_override'`
3. Agent proceeded without noticing reviews were broken
4. Only 1 of 4 required external reviews actually ran
5. Workflow completed with incomplete review coverage

**Current Behavior (Broken):**
- Review failures logged but not acted upon
- No attempt to recover or reload keys
- Agent doesn't detect that reviews are broken
- `orchestrator finish` shows incomplete reviews but doesn't block

**Desired Behavior:**
1. **Detect API key loss:** After compaction, check if required keys are still available
2. **Fail loudly:** If reviews fail, block workflow advancement with clear error
3. **Prompt for recovery:** "API keys missing. Run: `eval \"$(sops -d secrets.enc.yaml ...)\"` then retry"
4. **Retry mechanism:** After keys reloaded, retry failed reviews automatically
5. **Block finish:** `orchestrator finish` should FAIL if required reviews didn't complete

**Implementation:**
```python
# In cmd_complete for review items:
def complete_review_item(item_id):
    result = run_auto_review(review_type)
    if not result.success:
        if "API" in result.error or "key" in result.error.lower():
            print("ERROR: API keys may be missing after context compaction")
            print("Run: eval \"$(sops -d secrets.enc.yaml | sed 's/: /=/' | sed 's/^/export /')\"")
            print("Then retry: orchestrator complete " + item_id)
            sys.exit(1)
        # Don't silently continue - block and require fix
        print(f"ERROR: Review failed: {result.error}")
        sys.exit(1)
```

**Files Affected:**
- `src/cli.py` - Review item completion logic
- `src/review/router.py` - Fix the `context_override` argument error
- `src/engine.py` - Add review completion validation to finish

**Success Criteria:**
- [ ] Reviews that fail block workflow advancement
- [ ] Clear error messages guide user to fix
- [ ] After key reload, reviews can be retried
- [ ] `orchestrator finish` verifies all required reviews passed
- [ ] API key loss is detected and communicated

---

#### CORE-025: Context Compaction Survival
**Status:** Planned
**Complexity:** High
**Priority:** CRITICAL
**Source:** User observation - Too much is forgotten after compaction, workflows derail

**Description:** Context compaction (automatic summarization when context gets too long) causes catastrophic information loss. The agent forgets the active workflow, current phase, decisions made, and work in progress. Current mitigations (WF-012 state injection) are insufficient.

**Problem Solved:**
When compaction happens mid-workflow:
- Agent forgets there's an active workflow
- Loses track of current phase and completed items
- Forgets architectural decisions made earlier in session
- Forgets files it was working on and why
- May restart work from scratch or abandon entirely

This is the #1 cause of workflow abandonment in zero-human-review scenarios.

**Current Mitigations (Insufficient):**
- WF-012: Injects workflow state after compaction → Only shows phase/items, not context
- WF-023: Detects abandonment → Reactive, not preventive
- CONTEXT-001: North Star docs → Helps with vision, not session-specific state

**Proposed Approaches:**

**Option A: Aggressive Pre-Compaction Checkpoint**
Detect when context is getting long, proactively checkpoint everything before compaction hits.

```
Context usage: 85% (approaching compaction threshold)
─────────────────────────────────────────────────────
⚠️  AUTO-CHECKPOINT: Saving session state...
✓ Workflow state: EXECUTE phase, 3/5 items complete
✓ Current task: Implementing retry logic in api/client.py
✓ Key decisions: Using exponential backoff, max 3 retries
✓ Files in progress: api/client.py (lines 45-120)
✓ Pending questions: None
✓ Checkpoint saved: cp_auto_2026-01-09_14-32
─────────────────────────────────────────────────────
```

After compaction, inject the checkpoint summary.

**Option B: Self-Managed Handover**
When context is ~80% full, spawn a new agent session with explicit handover.

```
Context usage: 80%
─────────────────────────────────────────────────────
Initiating handover to fresh session...

HANDOVER DOCUMENT:
==================
Task: Implement authentication middleware
Workflow: wf_2026-01-09_auth (EXECUTE phase)
Progress: 3/5 items complete

Completed:
- write_tests: 12 tests in tests/test_auth.py
- implement_jwt_validation: src/middleware/jwt.py

In Progress:
- implement_session_handling: Started, 60% done
- Working on: src/middleware/session.py lines 30-80
- Approach: Using Redis for session storage (decided earlier)

Pending:
- integration_tests
- update_docs

Key Decisions Made:
- JWT tokens expire after 1 hour (security review recommendation)
- Using RS256 algorithm (discussed with user)
- Session data stored in Redis, not cookies

Files Modified This Session:
- src/middleware/jwt.py (new, 145 lines)
- src/middleware/session.py (in progress)
- tests/test_auth.py (new, 89 lines)
==================

Spawning new session with handover context...
```

**Option C: Structured Memory System**
Maintain an external "memory" file that survives compaction.

```yaml
# .workflow_memory.yaml (updated continuously)
session_id: sess_2026-01-09_14-32
workflow_id: wf_auth_middleware
phase: EXECUTE

current_task:
  item: implement_session_handling
  file: src/middleware/session.py
  progress: "Implementing Redis session store, ~60% done"

decisions:
  - "JWT expiry: 1 hour (security review)"
  - "Algorithm: RS256"
  - "Session storage: Redis"

blocked_on: null

recent_actions:
  - "Created jwt.py with validation logic"
  - "Wrote 12 unit tests"
  - "Started session.py implementation"
```

After compaction, agent reads this file to restore context.

**Option D: Shorter Sessions with Explicit Handoff**
Instead of fighting compaction, embrace it. Design workflows for shorter sessions with planned handoffs.

- Each workflow phase = one session
- Phase completion triggers handoff document generation
- New session starts with handoff context
- Never hit compaction because sessions are short

**Note:** The right approach is not yet decided. Options above are exploratory - requires proper design and planning to understand tradeoffs, Claude Code capabilities/hooks, and what's practically achievable.

**Known:** Claude Code warns when ~10% context remains. This could serve as a trigger, though ideally we'd checkpoint earlier.

**Tasks:**
- [ ] Research Claude Code compaction behavior and available hooks
- [ ] Design and plan approach (evaluate options A-D)
- [ ] Prototype and test chosen approach

**Why This Is Critical:**
Without solving compaction, zero-human-review workflows will always fail on complex tasks. The agent simply cannot maintain coherence across long sessions. This is a fundamental blocker for autonomous AI coding.

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

#### WF-024: Risk-Based Multi-AI Phase Reviews
**Status:** Planned
**Complexity:** High
**Priority:** High
**Source:** User discussion - Robust zero-human-review workflows need AI oversight at each phase

**Description:** Extend multi-model AI review beyond just the REVIEW phase. Add AI review gates at PLAN approval and after high-risk EXECUTE steps, with model selection based on task risk level and cost efficiency.

**Problem Solved:**
Currently, external AI reviews only happen during the REVIEW phase (after all code is written). This is too late to catch:
- **Bad plans** - Flawed approach approved, then hours spent implementing it
- **Bad tests** - Tests written with wrong assumptions, implementation passes bad tests
- **High-risk code** - Security-critical code merged with only one AI's perspective

In zero-human-review workflows, AI reviewers are the only safety net. They should be involved earlier and more strategically.

**Proposed Review Points:**

| Phase | Trigger | Reviewers | Model Tier |
|-------|---------|-----------|------------|
| PLAN | Before plan approval | 2 AIs (Gemini + GPT) | Standard |
| EXECUTE: `write_tests` | After tests written | 1 AI (fast/cheap) | Economy |
| EXECUTE: high-risk items | After completion | 1-2 AIs | Based on risk |
| REVIEW | All items (existing) | 3+ AIs | Standard |
| VERIFY | Optional coverage review | 1 AI (fast) | Economy |

**Risk Levels for EXECUTE Items:**

```yaml
items:
  - id: "implement_auth"
    risk: critical  # → 2 external reviews (security + quality)
  - id: "implement_api_endpoints"
    risk: high      # → 1 external review
  - id: "write_tests"
    risk: medium    # → 1 fast/cheap review (test design check)
  - id: "update_readme"
    risk: low       # → No external review
```

**Model Tiers (Cost/Speed Tradeoff):**

| Tier | Use Case | Selection Criteria |
|------|----------|-------------------|
| **Economy** | Test review, low-risk | Fastest/cheapest available |
| **Standard** | Plan review, high-risk | Balanced cost/capability |
| **Premium** | Security-critical | Best available reasoning |

Model selection handled by existing `ModelRegistry` - tiers are abstract, not tied to specific versions.

**Test Review (Special Case):**

Tests are reviewed **immediately after creation**, before implementation:

```
EXECUTE Phase Flow:
─────────────────────
1. write_tests (RED)
   ↓
   [AI Review: "Are these tests testing the right things?"]
   - Check test covers requirements
   - Check edge cases considered
   - Check no implementation assumptions leaked in
   ↓
2. implement_code (GREEN)
   ↓
   [If high-risk: AI Review of implementation]
   ↓
3. refactor (REFACTOR)
```

**Why review tests early?**
- Tests encode assumptions about requirements
- Bad tests → bad implementation that "passes"
- Cheaper to fix test design than rewrite implementation
- Fast/cheap model sufficient (test files are small)

**Plan Review Flow:**

```
PLAN Phase:
───────────
1. Agent creates plan
   ↓
2. [AI Review Gate - 2 models]

   Gemini Review:
   ✓ Approach is reasonable
   ⚠ Consider edge case: rate limiting

   GPT Review:
   ✓ Approach aligns with architecture
   ✓ No concerns
   ↓
3. Human approval (with AI feedback visible)
   ↓
4. Advance to EXECUTE
```

**Configuration:**

```yaml
# workflow.yaml
settings:
  phase_reviews:
    plan:
      enabled: true
      reviewer_count: 2           # How many AIs review the plan
      model_tier: standard
      require_consensus: false    # Any pass = proceed
    execute:
      test_review:
        enabled: true
        model_tier: economy       # Fast/cheap for test design check
      risk_based:
        enabled: true
        critical: ["security", "quality"]  # 2 review types
        high: ["quality"]                   # 1 review type
        medium: []                          # No auto-review
        low: []
    verify:
      coverage_review:
        enabled: false            # Optional
        model_tier: economy
```

**CLI Integration:**

```bash
# Plan review happens automatically before approval gate
orchestrator advance  # → Triggers plan review if in PLAN phase

# Manual plan review
orchestrator review-plan

# Check item risk level
orchestrator status --show-risk

# Override risk for an item
orchestrator complete write_tests --risk high  # Force higher review
```

**Implementation Phases:**

**Phase 1: Plan Review**
- Add `review-plan` command
- Integrate with `advance` from PLAN phase
- Display AI feedback before human approval

**Phase 2: Test Review**
- Add post-completion hook for `write_tests` item
- Use economy-tier model
- Check test design, not just syntax

**Phase 3: Risk-Based Execute Reviews**
- Add `risk` field to workflow item schema
- Route to appropriate reviewers based on risk
- Track review results in workflow log

**Tasks:**
- [ ] Add `risk` field to ChecklistItemDef schema
- [ ] Create ModelTier enum (economy, standard, premium)
- [ ] Add tier-based model selection to ReviewRouter
- [ ] Implement `review-plan` command
- [ ] Add plan review gate to `advance` from PLAN phase
- [ ] Add test review hook after `write_tests` completion
- [ ] Add risk-based review trigger in `complete` command
- [ ] Add `phase_reviews` configuration section
- [ ] Create economy-tier review prompts (concise, focused)
- [ ] Add `--show-risk` flag to status command
- [ ] Add `--risk` override to complete command
- [ ] Track per-phase review costs
- [ ] Document risk levels and review flow in CLAUDE.md

**Cost Consideration:**

More reviews = higher cost but better coverage. The tier system lets users balance:
- **Low-risk tasks**: Fewer reviews, economy tier → minimal cost
- **High-risk tasks**: More reviews, standard/premium tier → higher cost, better safety

Actual costs depend on model pricing (changes frequently) - tracked via existing cost monitoring.

**Why This Matters:**

In zero-human-review AI coding, catching issues early is critical:
- Plan review prevents wasted implementation effort
- Test review ensures we're testing the right things
- Risk-based reviews focus expensive oversight where it matters
- Economy models make frequent reviews affordable

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

#### WF-025: Documentation Update Step in LEARN Phase
**Status:** Planned
**Complexity:** Low
**Priority:** Medium
**Source:** User request - Ensure user-facing documentation is updated as part of workflow completion

**Description:** Add a documentation update step to the LEARN phase that prompts for user-facing documentation updates (CHANGELOG, README, API docs) based on the type of changes made.

**Problem Solved:**
Currently, the LEARN phase focuses on internal learnings (what went wrong, how to prevent it) but doesn't ensure user-facing documentation is updated. This leads to:
- Outdated CHANGELOGs that don't reflect recent changes
- README files missing new features or setup changes
- Undocumented public APIs

**Proposed Workflow Item:**

```yaml
- id: "update_documentation"
  name: "Update User-Facing Documentation"
  description: "Review and update user-facing documentation based on changes made."
  required: true
  skippable: true
  skip_conditions: ["internal_refactor_only", "no_user_facing_changes"]
  notes:
    - "[changelog] Update CHANGELOG.md using Keep a Changelog format (Added/Changed/Fixed/Removed/Security)"
    - "[readme] Update README.md if: new features, setup changes, usage changes, new dependencies"
    - "[api] Update API documentation if public interfaces changed"
    - "[tip] Commit message often contains good changelog content"
```

**Documentation Types & When to Update:**

| Documentation | When to Update | Format/Standard |
|--------------|----------------|-----------------|
| **CHANGELOG.md** | Any user-facing change | [Keep a Changelog](https://keepachangelog.com/) |
| **README.md** | New features, setup changes, usage patterns | Project-specific |
| **API docs** | New/changed public interfaces | OpenAPI, docstrings, or markdown |
| **Migration guides** | Breaking changes | Step-by-step upgrade instructions |

**Auto-Detection Ideas:**
- Parse git diff for new exported functions → suggest API doc update
- Detect new CLI commands → suggest README update
- Detect version bump in pyproject.toml/package.json → prompt for CHANGELOG
- Check if CHANGELOG.md was modified → if not, warn before commit

**Integration with commit_and_sync:**
The existing `commit_and_sync` item could be enhanced to:
1. Check if CHANGELOG.md was updated (warn if not for non-trivial changes)
2. Auto-generate changelog entry draft from commit message
3. Include documentation files in the commit

**Tasks:**
- [x] Add `update_documentation` item to LEARN phase in workflow.yaml
- [x] Update bundled default workflow
- [ ] Add detection logic for "user-facing change" vs "internal refactor"
- [ ] Add CHANGELOG.md template/format guidance
- [ ] Add auto-detection for missing documentation updates
- [ ] Integrate warning into `commit_and_sync` step
- [ ] Document in CLAUDE.md

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

