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


#### WF-030: Session Isolation for Multi-Workflow Support
**Status:** Planned
**Complexity:** MEDIUM (requires state file refactoring + locking)
**Priority:** HIGH - Blocks parallel multi-session workflows
**Source:** User observation (2026-01-11) - "It will break the process if I run 2 at once won't it?"

**Problem Statement:**
Currently, the orchestrator uses a single `.workflow_state.json` file per repository, which means:
1. **Cannot run multiple workflows simultaneously** in different Claude Code sessions
2. **State corruption risk** if two sessions modify the file concurrently
3. **Workflow isolation impossible** - starting new workflow abandons previous one
4. **No safe handoff between sessions** without finishing current workflow

**Real-World Impact:**
User wanted to work on WF-029 in one session while PRD-008 was active in another session. This is currently impossible without breaking the orchestrator state.

**Proposed Solution:**

**Option A: Session-Scoped State Files** (RECOMMENDED)
```bash
# State files include session/workflow ID
.workflow_state_prd-008.json
.workflow_state_wf-029.json

# Commands specify which workflow to use
orchestrator status --workflow prd-008
orchestrator advance --workflow wf-029

# Default workflow (most recent or user-selected)
orchestrator status  # Uses default workflow
```

**Option B: File Locking**
- Use file locks (fcntl/flock) on `.workflow_state.json`
- Block if another session holds the lock
- Simpler but prevents parallel workflows entirely

**Option C: Workflow Database**
- SQLite database instead of JSON files
- Transaction-based isolation
- Supports concurrent reads, serialized writes
- Higher complexity, better for many workflows

**Complexity vs Benefit Analysis:**

| Factor | Current | Option A | Option B | Option C |
|--------|---------|----------|----------|----------|
| Complexity | N/A | MEDIUM (refactor state access) | LOW (add locking) | HIGH (DB migration) |
| Parallel workflows | ❌ No | ✅ Yes | ❌ No | ✅ Yes |
| Session isolation | ❌ No | ✅ Yes | ⚠️ Queued | ✅ Yes |
| Backward compat | N/A | ✅ (auto-migrate) | ✅ | ⚠️ (migration req'd) |

**Current Evidence:**
- ✅ User actively blocked by this limitation
- ✅ Natural use case (work on different features in parallel)
- ✅ Aligns with parallel agent spawning (PRD execution)
- ❌ No production data (not shipped yet)

**YAGNI Check:**
- Solving a problem we **actually have** (user hit this today)
- Would **NOT** be okay without this for 6-12 months (blocks parallel work)
- Current solution **fails in practice** (user had to ask before breaking state)

**Recommendation:** ✅ IMPLEMENT (Option A)

**Reasoning:**
Low-medium effort, high value for users who want to multitask. Option A provides full isolation without DB complexity. Should trigger implementation when users attempt parallel workflows (not before).

**Tasks:**
- [ ] Design session-scoped state file naming scheme
- [ ] Refactor StateManager to support multiple state files
- [ ] Add `--workflow` flag to all orchestrator commands
- [ ] Add workflow selection/switching UX
- [ ] Auto-migrate existing `.workflow_state.json` to new format
- [ ] Add `orchestrator workflows list` command
- [ ] Update CLAUDE.md with multi-workflow usage
- [ ] Add tests for concurrent workflow state access

---



#### CORE-023-P3: Conflict Resolution - Learning & Config
**Status:** ✅ **RECOMMENDED** - Natural completion of P1/P2
**Complexity:** MEDIUM
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

**Complexity vs Benefit Tradeoff:**

| Factor | Current (No Learning) | With P3 |
|--------|----------------------|---------|
| Complexity | LOW - conflicts resolved per-instance | MEDIUM - pattern detection, config management |
| User Benefit | Good - conflicts resolved | Better - conflicts prevented over time |
| Time Savings | Per-conflict | Cumulative (learns from past) |
| Configuration | None | User can customize behavior |

**Current Evidence:**
- ✅ P1 and P2 already exist (partial implementation)
- ✅ Users hit same conflicts repeatedly (naturally follows from P2)
- ✅ Configuration requested in original design
- ❌ No data yet on actual conflict frequency

**YAGNI Check:**
- Solving a problem we **will have** after P2 ships (repeated conflicts)
- Would be **okay** without this for 6-12 months (P2 resolves conflicts, just doesn't learn)
- Current solution **works** but misses opportunity for improvement

**Recommendation:** ✅ **IMPLEMENT** (after P2 completes and users report repeated conflicts)

**Reasoning:**
Natural evolution of conflict resolution system. Wait until P2 is in production and users experience repeated patterns, then add learning. Low-medium effort with clear long-term value.

---

#### CORE-023-T1: Golden File Tests for Conflict Resolution
**Status:** ✅ **RECOMMENDED** - Testing best practice
**Complexity:** LOW
**Priority:** Medium
**Source:** CORE-023-P2 implementation review

**Description:** Add golden file tests for known conflict patterns to catch edge cases.

**Scope:**
- Create `tests/golden/` directory with known conflict patterns
- Add 5-10 common patterns: import conflicts, function edits, config files
- Property-based tests (Hypothesis) for fuzzing edge cases
- Regression test framework for capturing real-world failures

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Basic Tests) | With Golden Files |
|--------|----------------------|-------------------|
| Complexity | LOW - unit tests only | LOW - golden files are simple |
| Test Coverage | Basic edge cases | Known real-world patterns |
| Regression Prevention | Weak | Strong |
| Maintenance | Low | Low (add pattern when found) |

**Current Evidence:**
- ✅ Testing best practice for complex algorithms
- ✅ Conflict resolution has many edge cases
- ✅ Real-world patterns are valuable test cases
- ❌ No production data yet on actual conflict patterns

**YAGNI Check:**
- Solving a problem we **will have** (regressions in conflict resolution)
- Would be **okay** without this for 3-6 months (until patterns emerge)
- Current solution **works** but risks regressions

**Recommendation:** ✅ **IMPLEMENT** (after collecting real-world conflict patterns)

**Reasoning:**
Low-effort testing improvement. Wait until P2 is in production and we've seen actual conflict patterns, then capture them as golden files. Prevents future regressions with minimal cost.

---

#### CORE-023-T2: PRD WaveResolver Integration
**Status:** ⚠️ **DEFER** - Wait for PRD multi-agent use
**Complexity:** LOW
**Priority:** Low (only needed when PRD conflicts occur)
**Depends on:** CORE-023-P2 + PRD multi-agent actually being used

**Description:** Integrate LLM resolution with PRD WaveResolver for multi-agent conflicts.

**Scope:**
- Add LLM resolution option to `WaveResolver.resolve_in_waves()`
- Pass PRD context (manifests, task descriptions) to `LLMResolver`
- Test with multi-agent conflict scenarios

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Manual PRD Merge) | With LLM Integration |
|--------|---------------------------|---------------------|
| Complexity | None needed | LOW - hook existing LLMResolver |
| PRD Use Case | Manual merge | Auto-resolve with context |
| Benefit | N/A | Only if PRD agents create conflicts |
| Dependencies | None | CORE-023-P2 + active PRD usage |

**Current Evidence:**
- ❌ No evidence PRD multi-agent spawning creates file conflicts
- ❌ No production use of PRD multi-agent yet
- ❌ WaveResolver may not even be needed (task decomposition may prevent conflicts)
- ✅ Low implementation cost IF needed

**YAGNI Check:**
- Solving a **hypothetical** problem (PRD agent conflicts)
- Would be **completely fine** without this for 12+ months
- Current solution **doesn't exist yet** because problem doesn't exist yet

**Recommendation:** ⚠️ **DEFER** - Only implement when PRD multi-agent is proven to create conflicts

**Reasoning:**
Premature. PRD multi-agent spawning is not yet battle-tested. We don't know if conflicts will even occur (good task decomposition may prevent them). Wait for evidence of actual conflicts before building solution.

---

#### CORE-026: Review Failure Resilience & API Key Recovery
**Status:** ✅ **CRITICAL** - Reviews failing silently is unacceptable
**Complexity:** MEDIUM
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

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Silent Failures) | With Resilience |
|--------|--------------------------|-----------------|
| Complexity | None (broken) | MEDIUM - error detection, retry logic |
| Risk | HIGH - incomplete reviews unnoticed | LOW - failures block progression |
| User Experience | Terrible - silent failure | Good - clear errors, recovery path |
| Workflow Integrity | Broken | Enforced |

**Current Evidence:**
- ✅ Actual production incident (CORE-023 implementation)
- ✅ Reviews silently failed, workflow proceeded with gaps
- ✅ Context compaction is a known issue (happens regularly)
- ✅ API keys lost after compaction is reproducible

**YAGNI Check:**
- Solving a problem we **actually have** (observed in production)
- Would **NOT** be okay without this for even 1 month (reviews are critical)
- Current solution **fails catastrophically** in practice

**Recommendation:** ✅ **IMPLEMENT IMMEDIATELY** - Critical quality gate

**Reasoning:**
This is a blocker for zero-human-review workflows. Reviews silently failing defeats the entire purpose of the orchestrator. Medium implementation effort but absolutely necessary for production use.

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

**Complexity vs Benefit Tradeoff:**

| Factor | Current (WF-012 State Injection) | Option A (Checkpoint) | Option B (Handover) | Option C (Memory File) | Option D (Short Sessions) |
|--------|----------------------------------|---------------------|-------------------|---------------------|----------------------|
| Complexity | LOW - simple state inject | MEDIUM - detect threshold | HIGH - spawn coordination | MEDIUM - file persistence | LOW - workflow design |
| Context Preservation | Poor (state only) | Good (full checkpoint) | Excellent (full handover) | Good (structured memory) | N/A (avoid compaction) |
| Implementation | Done | Moderate | Complex | Moderate | Low |
| Reliability | Unreliable | Good | Good | Good | Excellent |

**Current Evidence:**
- ✅ User reports workflows derailing after compaction
- ✅ Agent forgets context, abandons workflows
- ✅ #1 cause of workflow abandonment in observation
- ✅ Affects all complex/long-running tasks

**YAGNI Check:**
- Solving a problem we **actually have** (observed repeatedly)
- Would **NOT** be okay without this for even 3 months (blocks complex workflows)
- Current solution (WF-012) **fails in practice** for complex tasks

**Recommendation:** 🔍 **EXPLORATORY** - Research and prototype required

**Reasoning:**
This is a critical problem but the solution is unclear. Multiple approaches exist with different tradeoffs. Need to:
1. Research Claude Code compaction triggers and hooks
2. Prototype simplest option (likely Option A or D)
3. Validate effectiveness before full implementation
4. Consider if Option D (shorter sessions) is sufficient

**Next Steps (in order):**
1. Research Claude Code compaction behavior and available hooks
2. Prototype Option A (checkpoint) or Option D (short sessions)
3. Test with real workflow spanning compaction
4. Evaluate effectiveness and decide on full approach

**Tasks:**
- [ ] Research Claude Code compaction behavior and available hooks
- [ ] Design and plan approach (evaluate options A-D)
- [ ] Prototype and test chosen approach

**Why This Is Critical:**
Without solving compaction, zero-human-review workflows will always fail on complex tasks. The agent simply cannot maintain coherence across long sessions. This is a fundamental blocker for autonomous AI coding.

---

#### CORE-024: Session Transcript Logging with Secret Scrubbing
**Status:** ✅ **RECOMMENDED** - Essential for debugging and learning
**Complexity:** MEDIUM
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

**Complexity vs Benefit Tradeoff:**

| Factor | Current (No Logging) | With Transcript Logging |
|--------|---------------------|------------------------|
| Complexity | None | MEDIUM - scrubbing logic, storage, CLI |
| Debugging Capability | Poor - memory only | Excellent - persistent forensics |
| Pattern Detection | Impossible | Possible (cross-session analysis) |
| Risk | Low | Low (secrets scrubbed) |
| Storage | None | Growing (needs rotation) |

**Current Evidence:**
- ✅ User explicitly requested for debugging
- ✅ WF-023, LEARN-001, CORE-025 all benefit from transcripts
- ✅ Pattern detection needs historical data
- ❌ No current workflow failure forensics capability

**YAGNI Check:**
- Solving a problem we **actually have** (workflow failures with no forensics)
- Would be **okay** without this for 6 months (can debug manually)
- Current solution **works** but makes debugging very difficult

**Recommendation:** ✅ **IMPLEMENT** - High value for debugging and learning

**Reasoning:**
Medium effort with high long-term value. Enables pattern detection, debugging, and feeds into other features (WF-023, LEARN-001). Secret scrubbing is critical but well-understood problem with known patterns.

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
**Status:** ✅ **RECOMMENDED** - Addresses core workflow completion problem
**Complexity:** MEDIUM
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

**Complexity vs Benefit Tradeoff:**

| Factor | Current (No Detection) | With Detection |
|--------|----------------------|----------------|
| Complexity | None | MEDIUM - hooks, state tracking, reminders |
| Workflow Completion | Low (frequent abandonment) | High (active prevention) |
| User Awareness | Poor - silent failures | Good - explicit warnings |
| Auto-Recovery | None | Auto-checkpoint on session end |

**Current Evidence:**
- ✅ User reports workflows not finishing
- ✅ Context compaction causes abandonment (observed)
- ✅ No current mechanism to prevent/detect abandonment
- ✅ LEARN phase frequently skipped (no learnings captured)

**YAGNI Check:**
- Solving a problem we **actually have** (workflows abandoned regularly)
- Would **NOT** be okay without this for 6 months (defeats workflow purpose)
- Current solution **fails** - no enforcement of completion

**Recommendation:** ✅ **IMPLEMENT** - Core workflow reliability feature

**Reasoning:**
Medium effort, high impact on workflow completion rates. Session hooks and state tracking prevent silent abandonment. Complements CORE-025 (compaction survival) but works independently.

**Metrics to Track:**
- Workflow completion rate (completed vs started)
- Average phase reached before abandonment
- Most common abandonment points
- Session count per workflow (high = many restarts)
- Recovery rate (abandoned → resumed → completed)

---

#### WF-024: Risk-Based Multi-AI Phase Reviews
**Status:** ✅ **IMPLEMENT Phase 1** - Plan review for complex projects, defer full system
**Complexity:** MEDIUM (Phase 1: PLAN review) / HIGH (Full system)
**Priority:** HIGH (Phase 1: PLAN review) / Medium (Full risk-based system)
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

**Complexity vs Benefit Tradeoff:**

| Factor | Current (REVIEW phase only) | Basic Phase Reviews | Full Risk-Based System |
|--------|----------------------------|--------------------|----------------------|
| Complexity | LOW - single phase | MEDIUM - add PLAN review | HIGH - risk routing, tiers, config |
| Implementation | Done | Moderate | Large |
| Cost Efficiency | N/A | Same cost, better timing | Optimized (economy tier for low-risk) |
| Catch Rate | Good (late) | Better (earlier) | Best (optimized) |

**Current Evidence:**
- ✅ User feedback: Plan review valuable for complex projects
- ✅ Conceptually sound (catch issues early, prevent wasted implementation)
- ❌ No data on how often bad plans slip through (but logical risk)
- ❌ No data on test design issues yet
- ❌ No evidence that full risk system is needed vs simple "always review PLAN"

**YAGNI Check:**
- **Phase 1 (PLAN review):** Solving a **likely** problem (bad plans → wasted work)
  - Would be **better** with this for complex projects
  - Current solution **works** but wastes time on bad approaches
- **Full risk system:** Solving **hypothetical** optimization problem
  - Would be **completely fine** without tiers/risk routing for 12+ months
  - Premature optimization

**Recommendation:** ✅ **IMPLEMENT Phase 1 (PLAN review)**, ⚠️ **DEFER Phase 2-3** (risk-based system)

**Reasoning:**
User is right - plan reviews for complex projects can prevent hours of wasted implementation on flawed approaches. However, the full risk-based routing system is over-engineered. **Phased approach:**

**Phase 1 (IMPLEMENT NOW):** Simple PLAN review
- Add `orchestrator review-plan` command
- Integrate with `advance` from PLAN phase (optional or configurable)
- 2 external models review plan before human approval
- Simple pass/fail with feedback
- **Especially valuable for complex projects**
- Medium complexity, high value for catching bad approaches early

**Phase 2 (VALIDATE):** Collect data
- Does PLAN review catch real issues in practice?
- What % of plans need revision after review?
- Is there correlation with project complexity?

**Phase 3 (IF NEEDED):** Risk-based optimization
- Only add risk tiers, test review, execute review if data shows need
- May never be needed if simple PLAN review is sufficient

**Implementation Priority:**
Start with Phase 1 - simple, valuable, addresses user's concern about complex projects without over-engineering.

**Tasks for Phase 1 (PLAN review):**
- [ ] Implement `orchestrator review-plan` command
- [ ] Add plan review integration to `advance` from PLAN phase
- [ ] Make plan review optional/configurable (some workflows may not need it)
- [ ] Display AI feedback before human approval gate
- [ ] Support 2-model review (e.g., Gemini + GPT)
- [ ] Track plan review results in workflow log
- [ ] Document in CLAUDE.md with guidance on when to use
- [ ] Test with complex vs simple projects

**Tasks for Phase 2-3 (if data justifies):**
- [ ] Add `risk` field to ChecklistItemDef schema
- [ ] Create ModelTier enum (economy, standard, premium)
- [ ] Add tier-based model selection to ReviewRouter
- [ ] Add test review hook after `write_tests` completion
- [ ] Add risk-based review trigger in `complete` command
- [ ] Add `phase_reviews` configuration section
- [ ] Create economy-tier review prompts (concise, focused)
- [ ] Add `--show-risk` flag to status command
- [ ] Track per-phase review costs

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

**BUT:** Start simple first. Prove the value before building the full system.

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

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Manual LEARN) | With Automated Analysis |
|--------|----------------------|------------------------|
| Complexity | None | MEDIUM - pattern detection, NLP, cross-session analysis |
| Accuracy | Low (agent forgets errors) | High (objective data from logs) |
| Actionability | Vague ("had issues") | Specific (error types, frequencies, time costs) |
| Pattern Detection | None | Cross-session patterns reveal systemic issues |

**Current Evidence:**
- ✅ User requests objective analysis (source of this item)
- ✅ Depends on CORE-024 (session logging) which is highly recommended
- ✅ LEARN phase currently produces vague learnings (observed limitation)
- ❌ No production data yet on actual error patterns (need CORE-024 first)

**YAGNI Check:**
- Solving a problem we **actually have** (vague learnings, forgotten errors)
- Would be **okay** without this for 6-9 months (manual LEARN works, just less effective)
- Current solution **works but suboptimal** - learnings captured but not data-driven

**Recommendation:** ✅ **IMPLEMENT** - After CORE-024 (session logging) is complete

**Reasoning:**
Medium effort, high value for continuous improvement. The key dependency is CORE-024 (session logging with transcript data). Once transcripts are available, pattern detection provides actionable insights that manual reflection cannot. This transforms LEARN from subjective reflection to objective data analysis. However, it's not urgent - manual LEARN phase works, this just makes it significantly better.

**Implementation Order:**
1. CORE-024 (Session Logging) - prerequisite
2. Basic error detection (regex patterns)
3. Time analysis (estimate wasted time)
4. Cross-session patterns
5. Automated suggestions

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

**Complexity vs Benefit Tradeoff:**

| Factor | Current (No Doc Step) | With Doc Update Step |
|--------|----------------------|---------------------|
| Complexity | None | LOW - simple workflow item, basic detection |
| Documentation Quality | Poor (often forgotten) | Good (systematic reminders) |
| User Experience | Outdated docs frustrate users | Up-to-date docs serve users |
| Time Cost | None | ~2-3 min per workflow |

**Current Evidence:**
- ✅ User requests documentation updates (source of this item)
- ✅ CHANGELOG.md and README.md exist in this repo (observed)
- ✅ Documentation drift is common (general dev problem)
- ❌ No data on how often docs are actually forgotten

**YAGNI Check:**
- Solving a problem we **likely have** (doc updates often forgotten)
- Would be **okay** without this for 12+ months (nice-to-have, not critical)
- Current solution **works** - docs can be updated manually

**Recommendation:** ⚠️ **DEFER** - Low priority improvement, implement after higher-value items

**Reasoning:**
Low effort but also low urgency. Documentation updates are important for user-facing projects but not a blocker for core functionality. The workflow item is already implemented (tasks show 2 items complete), so the basic prompt exists. Additional detection logic and warnings are nice-to-haves that can wait until more critical items (like CORE-026, WF-023, CORE-025) are complete. This is a quality-of-life improvement, not a core workflow reliability feature.

**Tasks:**
- [x] Add `update_documentation` item to LEARN phase in workflow.yaml
- [x] Update bundled default workflow
- [ ] Add detection logic for "user-facing change" vs "internal refactor"
- [ ] Add CHANGELOG.md template/format guidance
- [ ] Add auto-detection for missing documentation updates
- [ ] Integrate warning into `commit_and_sync` step
- [ ] Document in CLAUDE.md

---

#### WF-026: Save Review Output to Archive Before Commit
**Status:** Planned
**Complexity:** Low
**Priority:** High - Preserves review evidence
**Source:** User request (2026-01-10) - Review output truncated in CLI, lost after commit

**Problem:**
When running `minds review`, the full output is displayed in CLI but:
1. Gets truncated for long reviews
2. Is lost after committing (review only sees uncommitted changes)
3. No permanent record of what issues were found/addressed

**Proposed Solution:**
In the REVIEW phase, before `commit_and_sync`:
1. Run `minds review --timeout 90 > docs/archive/YYYY-MM-DD_<task-slug>_review.md`
2. Add review output file to the commit
3. Reference review file in workflow completion notes

**Implementation:**
- Add `save_review_output` step to REVIEW phase in workflow.yaml
- Auto-generate filename from workflow task + date
- Include in `commit_and_sync` staged files

**Complexity vs Benefit Tradeoff:**

| Factor | Current (No Archive) | With Review Archive |
|--------|---------------------|---------------------|
| Complexity | None | LOW - simple file redirect + git add |
| Review Evidence | Lost after commit | Permanent archive |
| Debugging | No record of what was found | Full review history |
| Compliance | No audit trail | Complete audit trail |

**Current Evidence:**
- ✅ User experienced this problem (review output truncated/lost)
- ✅ Reviews are critical quality gates (high value to preserve)
- ✅ Archive pattern already used (docs/archive/ exists)
- ✅ Simple implementation (just redirect output to file)

**YAGNI Check:**
- Solving a problem we **actually have** (user hit this issue)
- Would **NOT** be okay without this for long (review evidence is important)
- Current solution **fails** - review output is lost

**Recommendation:** ✅ **IMPLEMENT** - Simple, high-value preservation

**Reasoning:**
Very low effort (literally just `> file.md` and `git add`), high value for traceability and debugging. Review output documents what issues were found and addressed, which is critical for understanding workflow quality over time. This is especially important for zero-human-review workflows where the review output is the only record of quality checks performed. Implementation is trivial, benefit is clear.

**Tasks:**
- [ ] Add `save_review_output` step to REVIEW phase in workflow.yaml
- [ ] Auto-generate filename from workflow task + date
- [ ] Ensure docs/archive/ directory exists
- [ ] Include review file in `commit_and_sync` staged files
- [ ] Document review archive pattern in CLAUDE.md

---


#### WF-028: Enforce Orchestrator Status Check at Session Start
**Status:** ✅ **RECOMMENDED** - Critical learning from PRD-007
**Complexity:** LOW (multiple implementation options)
**Priority:** HIGH - Prevents workflow abandonment
**Source:** PRD-007 learnings (2026-01-11) - Workflow state out of sync after context compaction

**Problem Statement:**
AI agents (especially after context compaction or session resumption) frequently forget to check `orchestrator status` before starting new work, leading to:
1. Abandoned workflows mid-execution
2. Missing quality gates (reviews, testing, verification)
3. Lost learnings (LEARN phase never completed)
4. Work done outside workflow tracking

**Root Cause:**
No enforcement mechanism ensures agents check workflow state before starting work.

**Proposed Solutions** (Pick one or combine):

**Option A: Workflow Phase (HIGHEST IMPACT)**
Add mandatory first phase to ALL workflows:
```yaml
phases:
  - id: "SESSION_SETUP"
    name: "Session Initialization"
    items:
      - id: "check_workflow_status"
        name: "Check Active Workflow State"
        required: true
        notes:
          - "[critical] ALWAYS run 'orchestrator status' as first action"
          - "[critical] If active workflow exists, continue it before new work"
          - "[info] This prevents abandoning workflows mid-execution"
        verification:
          type: "manual_gate"
          description: "Agent must acknowledge current workflow state"
```

**Benefits:**
- Forces conscious decision about existing workflows
- Works across all workflow types
- Visible in `orchestrator status` output

**Option B: Session Start Hook (IMMEDIATE REMINDER)**
Modify `.claude/SessionStart` hook (auto-run on session start):
```bash
#!/bin/bash
# Check for active workflow
if [ -f .workflow_state.json ]; then
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "⚠️  ACTIVE WORKFLOW DETECTED"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  orchestrator status
  echo ""
  echo "Run 'orchestrator status' for details."
  echo "Continue the workflow before starting new work."
fi
```

**Benefits:**
- Immediate visibility on session start
- Works even if agent ignores workflows
- No changes to workflow YAML needed

**Option C: CLAUDE.md Prominent Warning (DOCUMENTATION)**
Add to **top of CLAUDE.md** (highly visible):
```markdown
# ⚠️ CRITICAL: Check Orchestrator Status First

**ALWAYS run this as your FIRST action in ANY session:**
\```bash
orchestrator status
\```

If a workflow is active, **continue it**. Do NOT start new work.

This prevents abandoning quality gates (reviews, tests, learnings).
```

**Benefits:**
- Low implementation cost
- Relies on agent following instructions
- Easy to update

**Recommendation:** ✅ **IMPLEMENT ALL THREE**
- Option A: Long-term solution (workflow enforcement)
- Option B: Immediate guard rail (session hook)
- Option C: Clear documentation (agent awareness)

**Implementation Priority:**
1. Option B (quick win, immediate value)
2. Option C (documentation update)
3. Option A (requires workflow YAML updates, broader impact)

---

#### WF-031: Enforce Marking Fixed Issues as Complete
**Status:** ✅ **RECOMMENDED** - Critical learning from PRD-007
**Complexity:** LOW
**Priority:** HIGH - Prevents incomplete work
**Source:** PRD-007 learnings (2026-01-11) - Agent didn't mark fixed review issues as complete

**Problem Statement:**
AI agents fix issues identified during REVIEW phase but forget to mark them as complete in the orchestrator workflow, leading to:
1. Workflow appears incomplete even when all work is done
2. User must manually verify every fix was made
3. Unable to advance workflow without manually marking items complete
4. Lost tracking of what was actually fixed vs what was skipped

**Root Cause:**
No enforcement mechanism to ensure agents complete the full cycle:
1. Identify issue
2. Fix the issue
3. Mark item as complete in workflow

**Proposed Solutions:**

**Option A: REVIEW Phase Documentation Enhancement**
Add explicit reminder to REVIEW phase items in workflow YAML:
```yaml
items:
  - id: "fix_review_issues"
    name: "Fix All Review Issues"
    required: true
    notes:
      - "[critical] After fixing each issue, mark it complete: orchestrator complete <item_id>"
      - "[critical] Do NOT move on to next phase until ALL fixes are marked complete"
      - "[info] Use 'orchestrator status' to verify all items show ✓"
```

**Option B: Pre-Advance Validation**
Enhance `orchestrator advance` to check for unfixed review issues:
- Scan git diff for TODOs, FIXMEs, review comments
- Check if external review files still exist in `.review_history/`
- Warn if issues found but not all items marked complete
- Require `--force` to bypass check

**Option C: Auto-Complete Detection**
Add `orchestrator detect-completions` command:
```bash
# Analyze git history and mark items that were clearly fixed
orchestrator detect-completions --phase REVIEW

# Preview what would be marked complete
orchestrator detect-completions --dry-run
```

**Recommendation:** ✅ **IMPLEMENT OPTIONS A + B**
- Option A: Immediate documentation fix (prevents future issues)
- Option B: Guard rail to catch missed completions (safety net)
- Option C: Nice-to-have but adds complexity (defer for now)

**Implementation Priority:**
1. Option A (quick documentation update)
2. Option B (validation logic in advance command)

---

#### WF-034: Post-Workflow Self-Assessment & Adherence Validation
**Status:** ✅ **RECOMMENDED** - Critical for dogfooding and continuous improvement
**Complexity:** LOW (checklist) to MEDIUM (automated validation)
**Priority:** HIGH - Ensures workflows are actually followed
**Source:** User feedback (2026-01-11) - Agent completed PRD but didn't use parallel agents or run third-party reviews

**Problem Statement:**
AI agents complete tasks but fail to follow the orchestrator's workflow recommendations:
1. **Parallel agents not used** - PRD says "tasks can be done in parallel" but agent works sequentially
2. **Reviews skipped** - Agent doesn't run third-party model reviews
3. **No systematic feedback capture** - Insights about what went well/poorly are lost
4. **Workflow adherence unmeasured** - No way to validate the orchestrator itself was followed

**Real-World Examples:**

**Example 1 - PRD Implementation (2026-01-11):**
```
Should Have Used Parallel Agents
The PRD explicitly stated: "Each task can be done in parallel by separate agents"
I should have launched 4 agents in parallel. This would have been faster and
followed the orchestrator workflow properly.

No Third-Party Model Reviews
I did not perform multi-model code reviews. For reliability improvements
specifically, it would have been valuable to have other models review the changes.
```

**Example 2 - Phase 2 Implementation (2026-01-11):**
```
Critical Issue: I Didn't Actually Use Multi-Agents Properly

1. I launched only 1 agent instead of 3 parallel agents for:
   - MCP CLI command
   - Slack bot integration
   - Synthesis improvements
2. I assumed work was done without verification
3. No parallel execution - I should have sent a single message with 3 Task tool calls
4. No Third-Party Model Reviews - I did NOT use /review or /minds to get external
   AI perspectives on the implementations

What Could Be Improved:
1. Use Plan Agent First - Should have started with subagent_type="Plan"
2. Launch Agents in Parallel - Send multiple Task calls in a single message
3. Use /review on Completed Work - Run /review to get multi-model code review
4. Verify Agent Output - Don't trust summaries, read the actual files
5. Background Agents - Could have used run_in_background=true
```

**Pattern Identified:**
This is not a one-off issue - **multiple agents across different sessions are consistently failing to use parallel execution and skipping reviews**. This validates the urgent need for WF-034.

**Root Cause:**
- No post-workflow validation that recommendations were followed
- No structured way to capture feedback about workflow effectiveness
- Orchestrator doesn't enforce its own workflow (meta-problem)

**Proposed Solutions:**

**Phase 0: Pre-Execution Planning Guidance (IMMEDIATE, documentation only)**

Add to PLAN phase in workflow.yaml:
```yaml
- id: "parallel_execution_check"
  name: "Assess Parallel Execution Opportunity"
  description: "Before starting implementation, determine if tasks can be parallelized"
  required: true
  notes:
    - "[critical] Are there 2+ independent tasks? Consider parallel agents"
    - "[howto] Launch parallel agents: Send ONE message with MULTIPLE Task tool calls"
    - "[example] Task(description='Fix auth', ...) + Task(description='Fix API', ...) in SAME message"
    - "[plan] Use Plan agent FIRST if implementation approach unclear"
    - "[verify] Will you verify agent output by reading files, not trusting summaries?"
    - "[decision] Document: Will use [sequential/parallel] execution because [reason]"
```

**Phase 1: Self-Assessment Checklist (LOW complexity, immediate value)**

Add to LEARN phase in workflow.yaml:
```yaml
- id: "workflow_adherence_check"
  name: "Workflow Adherence Self-Assessment"
  description: "Validate that orchestrator workflow was followed correctly"
  required: true
  notes:
    - "[check] Did you use parallel agents when PRD/plan recommended it?"
    - "[check] If parallel: Did you launch them in SINGLE message with MULTIPLE Task calls?"
    - "[check] Did you use Plan agent before complex implementations?"
    - "[check] Did you verify agent output by reading files (not trusting summaries)?"
    - "[check] Did you run all 5 third-party model reviews (/review or /minds)?"
    - "[check] Did you use 'orchestrator status' before each action?"
    - "[check] Did you complete all required items (no skips without justification)?"
    - "[check] Did you document learnings and propose roadmap items?"
    - "[feedback] What went well? What challenges? What could improve?"
```

**Phase 2: Automated Validation (MEDIUM complexity)**

Add `orchestrator validate-adherence` command that checks:
```bash
# Analyze workflow log for adherence
orchestrator validate-adherence

OUTPUT:
✓ Plan agent: Used before implementation
✗ Parallel execution: FAIL - Agents launched sequentially (3 separate messages)
✗ Third-party reviews: MISSING - No external model reviews detected
✓ Agent verification: Files read after agent completion (5 verifications)
✓ Status checks: Frequent (23 status checks during workflow)
✓ Required items: All completed (0 unjustified skips)
⚠ Learnings: Brief (3 learnings documented, consider more detail)

ADHERENCE SCORE: 57% (4/7 criteria met)
CRITICAL ISSUES: 2 (parallel execution, reviews)
```

Detection methods:
- **Plan agent**: Check for Task with subagent_type="Plan" before implementation
- **Parallel execution**: Detect multiple Task calls in SINGLE message vs sequential messages
- **Reviews**: Check for `review_completed` events with external models (not DEFERRED)
- **Agent verification**: Count file reads (Read tool) immediately after agent completions
- **Status checks**: Count `orchestrator status` calls in session transcript
- **Required items**: Validate no required items skipped without reason
- **Learnings**: Check length/detail of `document_learnings` notes

**Phase 3: Feedback Capture Template**

Create `orchestrator feedback` command:
```bash
orchestrator feedback --workflow wf_95ec1970

PROMPT:
1. Did you use multi-agents? (yes/no/not-recommended)
2. What went well? (1-2 sentences)
3. What challenges did you encounter? (1-2 sentences)
4. What could be improved? (1-2 sentences)
5. Did you run third-party model reviews? (yes/no/deferred)
6. Additional notes:

OUTPUT → .workflow_feedback.jsonl (structured for analysis)
```

**Phase 4: Workflow Enforcement for Orchestrator Itself (MEDIUM complexity)**

Create `orchestrator-meta.yaml` - a workflow for using the orchestrator:
- Dogfooding: Orchestrator enforces its own usage
- PLAN phase: Check if parallel agents should be used
- REVIEW phase: Enforce third-party model reviews
- VERIFY phase: Validate adherence checklist completed

**Success Criteria:**
- [ ] Adherence checklist added to default workflow LEARN phase
- [ ] `orchestrator validate-adherence` command implemented
- [ ] Adherence score shows % of workflow recommendations followed
- [ ] `orchestrator feedback` command captures structured feedback
- [ ] Feedback stored in `.workflow_feedback.jsonl` for analysis
- [ ] At least 3 dogfooding sessions validate the system works

**Complexity vs Benefit Tradeoff:**

| Factor | Current (No Validation) | With Adherence Validation |
|--------|------------------------|--------------------------|
| Complexity | None | LOW-MEDIUM (checklist → automation) |
| Workflow Quality | Unknown (no measurement) | Measured and improvable |
| Dogfooding | Not validated | Systematically validated |
| Feedback Loop | Ad-hoc (lost insights) | Structured (actionable) |
| Meta-Problem | Orchestrator doesn't follow itself | Self-enforcing |

**Current Evidence:**
- ✅ **TWO independent sessions** with same problem (2026-01-11)
- ✅ User explicitly reported not following workflow recommendations
- ✅ Agent recognized they SHOULD have used parallel agents but didn't (both sessions)
- ✅ No third-party reviews performed when they should have been (both sessions)
- ✅ Agents launched sequentially instead of single message with multiple Tasks
- ✅ Agent output not verified by reading files (assumed work done)
- ✅ Plan agent not used before complex implementations
- ✅ Feedback was captured manually - needs systematic approach

**YAGNI Check:**
- This is **NOT speculative** - we have concrete evidence from **multiple sessions**
- Validates that the orchestrator itself is being used correctly (dogfooding validation)
- Prevents wasted effort (wrong approach) and missed quality checks (skipped reviews)
- Creates feedback loop for continuous workflow improvement
- Pattern is consistent: agents forget to use capabilities they recognize exist

**Recommendation:** ✅ **RECOMMEND** - High priority, phased approach

**Reasoning:**
The orchestrator is designed to enforce workflows, but doesn't enforce its own recommendations. This is a meta-problem: "workflow orchestrator not being orchestrated by workflow". **Two sessions on the same day showed identical problems**, proving this is systematic not accidental. Phase 0 (planning guidance) is documentation-only (~15 min). Phase 1 (checklist) is very low effort (~30 min). Both provide immediate value. Phase 2-4 can be implemented incrementally as dogfooding validates the approach.

**Implementation Priority:**
1. **Phase 0** (IMMEDIATE, 15 min) - Add parallel execution planning guidance to PLAN phase
2. **Phase 1** (Immediate, 30 min) - Add adherence checklist to LEARN phase
3. **Phase 3** (Quick win, 2 hours) - Add `orchestrator feedback` command for structured capture
4. **Phase 2** (Medium-term, 8 hours) - Build automated validation from logs
5. **Phase 4** (Long-term, 16+ hours) - Meta-workflow for dogfooding

**Tasks:**
- [ ] **PHASE 0**: Add `parallel_execution_check` item to PLAN phase in workflow.yaml and src/default_workflow.yaml
- [ ] **PHASE 1**: Add `workflow_adherence_check` item to LEARN phase in workflow.yaml and src/default_workflow.yaml
- [ ] Create `orchestrator feedback` command with structured prompts
- [ ] Store feedback in `.workflow_feedback.jsonl`
- [ ] Implement `orchestrator validate-adherence` command
- [ ] Add adherence detection logic (parallel agents, reviews, status checks)
- [ ] Calculate adherence score
- [ ] Add documentation to CLAUDE.md
- [ ] Dogfood on 3+ real workflows to validate approach
- [ ] (Future) Create orchestrator-meta.yaml for self-enforcement

---

#### CORE-027: Multi-Model API Reliability
**Status:** Planned
**Complexity:** Medium
**Priority:** Medium
**Source:** Approval system review (2026-01-10) - Models failing silently

**Problem:**
During multi-model reviews (`minds review`), models fail inconsistently:
- Grok 4.1 failed after 62s (not timeout - API error?)
- DeepSeek V3.2 failed after 63s
- Gemini 3 Pro failed after 1s (likely rate limit)
- No clear error messages or retry logic

**Observed Failure Modes:**
| Model | Failure Time | Likely Cause |
|-------|--------------|--------------|
| Grok 4.1 | 62s | Unknown API error |
| DeepSeek V3.2 | 63s | Unknown API error |
| Gemini 3 Pro | 1s | Rate limit or auth |

**Proposed Improvements:**
1. Better error reporting - show actual error, not just ✗
2. Retry logic with exponential backoff for transient failures
3. Fallback models when primary fails
4. Health check before review (`minds status --check`)
5. Save raw API responses for debugging

**Note:** This may require changes to the `minds` CLI tool itself.

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Silent Failures) | With Reliability Improvements |
|--------|-------------------------|-------------------------------|
| Complexity | None | MEDIUM - error handling, retry logic, logging |
| Review Success Rate | Low (models fail silently) | High (retries + fallbacks) |
| Debugging | Impossible (no error details) | Easy (actual errors logged) |
| Dependencies | orchestrator only | May need `minds` CLI changes |

**Current Evidence:**
- ✅ User observed multiple model failures (Grok, DeepSeek, Gemini)
- ✅ No clear error messages (just "Failed")
- ✅ Reviews are critical quality gates (failures block workflows)
- ❌ Unknown if failures are transient or permanent

**YAGNI Check:**
- Solving a problem we **actually have** (models failing in production)
- Would **NOT** be okay without this for 3-6 months (reviews must be reliable)
- Current solution **fails silently** - no visibility into why

**Recommendation:** ✅ **IMPLEMENT** - But investigate root causes first (CORE-029, CORE-028)

**Reasoning:**
Medium effort, high value for review reliability. However, this is a symptom item - we should first investigate and fix the root causes (CORE-029 for Gemini rate limits, CORE-028 for fallback chains). Once we understand why models are failing, we can implement targeted reliability improvements. The error logging and health check are quick wins that should be done immediately.

**Implementation Order:**
1. CORE-029 (investigate Gemini rate limits) - understand the problem
2. CORE-028 (implement fallback chain) - solve the problem
3. Better error logging - see what's actually failing
4. Retry logic - handle transient failures
5. Health check - preventive validation

**Tasks:**
- [ ] Add detailed error logging to capture API responses
- [ ] Implement retry logic with exponential backoff
- [ ] Add `minds status --check` health check command
- [ ] Save raw API responses to debug log
- [ ] Distinguish transient vs permanent failures
- [ ] Integrate with CORE-028 fallback chain
- [ ] Document error handling in CLAUDE.md

---

#### CORE-029: Investigate Gemini API Rate Limiting
**Status:** Planned
**Complexity:** Low (Investigation)
**Priority:** Medium
**Source:** User observation (2026-01-11) - Gemini failing with rate limits

**Problem:**
Gemini 3 Pro reviews are failing quickly (~1s) with what appears to be rate limiting:
```
✗ Gemini 3 Pro: Failed (1s)
```

**Questions to Answer:**
1. What are the actual Gemini API rate limits?
2. Are we hitting RPM (requests per minute) or TPM (tokens per minute) limits?
3. Is the API key on free tier vs paid tier?
4. Are multiple orchestrator instances sharing the same key?
5. Is there a way to check current usage/quota?

**Investigation Steps:**
- [ ] Check Gemini API documentation for rate limits by tier
- [ ] Add detailed error logging to capture actual error response
- [ ] Check if error is 429 (rate limit) or something else
- [ ] Determine if this is a free tier limitation
- [ ] Test with delays between requests
- [ ] Check Google Cloud Console for quota usage

**Potential Solutions:**
1. **Upgrade to paid tier** if on free tier
2. **Add request throttling** to stay under limits
3. **Implement backoff/retry** for transient rate limits
4. **Use fallback models** (see CORE-028)
5. **Queue reviews** instead of parallel execution

**Related:** CORE-027 (Multi-Model API Reliability), CORE-028 (Fallback Chain)

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Unknown) | After Investigation |
|--------|------------------|---------------------|
| Complexity | None | LOW - investigation only, no code |
| Understanding | No idea why Gemini fails | Clear understanding of limits |
| Solution Path | Guessing | Targeted fixes possible |
| Time Required | N/A | ~1-2 hours investigation |

**Current Evidence:**
- ✅ Gemini consistently fails after ~1s (observed pattern)
- ✅ Likely rate limit based on failure speed
- ❌ No actual error message captured (need CORE-027 logging first)
- ❌ Unknown if free tier vs paid tier
- ❌ Unknown if shared key across instances

**YAGNI Check:**
- Solving a problem we **actually have** (Gemini failing consistently)
- Would **NOT** be okay without this for 1-3 months (one model consistently broken)
- Current solution **fails** - Gemini reviews don't work

**Recommendation:** 🔍 **INVESTIGATE IMMEDIATELY** - Quick investigation unblocks fixes

**Reasoning:**
Low effort investigation (1-2 hours) that unblocks targeted solutions. This is a prerequisite for fixing Gemini failures - we can't fix what we don't understand. The investigation tasks are concrete and answerable. Should be done before CORE-027 and CORE-028 to inform their implementation.

**Investigation Priority:**
1. Add error logging (CORE-027) to see actual error
2. Check API key tier in Google Cloud Console
3. Review Gemini API documentation for rate limits
4. Test with manual delay between requests
5. Decide on solution (upgrade tier, throttling, or fallback)

**Tasks:**
- [ ] Check Gemini API documentation for rate limits by tier
- [ ] Add detailed error logging to capture actual error response
- [ ] Check if error is 429 (rate limit) or something else
- [ ] Determine if this is a free tier limitation
- [ ] Test with delays between requests
- [ ] Check Google Cloud Console for quota usage

---

#### CORE-028: Review Model Fallback Chain
**Status:** Planned
**Complexity:** Medium
**Priority:** HIGH
**Source:** User request (2026-01-11) - If one AI unavailable, use another

**Problem:**
When a review model fails (rate limit, API error, timeout), the review just fails. No automatic fallback to an alternative model.

**Current Behavior:**
```
Running reviews...
✓ GPT-5.2 Max: Passed (45s)
✗ Gemini 3 Pro: Failed (1s) - Rate limited
✗ Grok 4.1: Failed (62s) - API error
✓ DeepSeek V3.2: Passed (38s)

2/4 reviews completed. Some reviews failed.
```

**Desired Behavior:**
```
Running reviews...
✓ GPT-5.2 Max: Passed (45s)
⟳ Gemini 3 Pro: Rate limited, falling back to Gemini 2.5 Flash...
✓ Gemini 2.5 Flash: Passed (12s)
⟳ Grok 4.1: API error, falling back to Claude 3.5 Sonnet...
✓ Claude 3.5 Sonnet: Passed (28s)
✓ DeepSeek V3.2: Passed (38s)

4/4 reviews completed (2 used fallbacks).
```

**Implementation:**

```yaml
# In workflow.yaml or config
review:
  models:
    - name: gemini-3-pro
      fallbacks: [gemini-2.5-flash, claude-3.5-sonnet]
    - name: grok-4.1
      fallbacks: [grok-3, claude-3.5-sonnet]
    - name: gpt-5.2-max
      fallbacks: [gpt-4o, claude-3.5-sonnet]
    - name: deepseek-v3.2
      fallbacks: [deepseek-v3, claude-3.5-sonnet]

  fallback_policy:
    max_fallback_attempts: 2
    retry_original_after: 300  # seconds
```

**Logic:**
1. Try primary model
2. If fail (rate limit, timeout, API error), try first fallback
3. If fallback fails, try next fallback (up to max_fallback_attempts)
4. Log which model actually ran the review
5. Include fallback info in review report

**Complexity vs Benefit Tradeoff:**

| Factor | Current (No Fallback) | With Fallback Chain |
|--------|----------------------|---------------------|
| Complexity | None | MEDIUM - fallback config, retry logic, model mapping |
| Review Success Rate | ~50% (2/4 models fail) | ~95% (fallbacks rescue failures) |
| Cost | Lower (fewer reviews complete) | Slightly higher (fallback models used) |
| Reliability | Poor (random failures) | Excellent (graceful degradation) |

**Current Evidence:**
- ✅ User observed 50% model failure rate (2 of 4 models failed)
- ✅ User explicitly requested this feature ("If one AI unavailable, use another")
- ✅ Reviews are critical quality gates (failures block workflows)
- ✅ Simple configuration (YAML fallback chains)

**YAGNI Check:**
- Solving a problem we **actually have** (models failing in production, 50% failure rate)
- Would **NOT** be okay without this for even 1 month (reviews must be reliable)
- Current solution **fails critically** - quality gates not enforced when models fail

**Recommendation:** ✅ **IMPLEMENT IMMEDIATELY** - High priority reliability fix

**Reasoning:**
Medium effort, critical value for review reliability. With 50% model failure rate, reviews are not dependable. Fallback chains ensure that review requirements are met even when individual models fail. This is a core reliability feature for zero-human-review workflows. The implementation is straightforward (configuration + retry logic), and the benefit is immediate and measurable. This should be prioritized above most other items except CORE-026 (review failure blocking).

**Implementation Priority:**
1. CORE-029 (investigate Gemini) - understand why models fail
2. CORE-028 (this item) - implement fallback chains
3. CORE-027 (error logging) - visibility into what's happening

**Tasks:**
- [ ] Add fallback chain configuration to review settings
- [ ] Implement fallback logic in ReviewRouter
- [ ] Distinguish retriable errors (rate limit, timeout) from permanent (auth)
- [ ] Log fallback usage for analysis
- [ ] Update review output to show fallback usage
- [ ] Add `--no-fallback` flag to force specific model
- [ ] Document fallback configuration

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
- **Stand-alone, agent-agnostic design**: The orchestrator must work independently of Claude Code, without requiring CLAUDE.md or Claude Code-specific features. It should be usable by any AI agent (Codex, Cursor, Windsurf, etc.) and in any environment (CLI, CI/CD, web). Avoid tight coupling to any specific AI coding assistant.

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

**Complexity vs Benefit Tradeoff:**

| Factor | Current (CLAUDE.md only) | With Context Docs System |
|--------|-------------------------|-------------------------|
| Complexity | None | MEDIUM - injection logic, smart detection, templates |
| Alignment | Poor (agent forgets) | Good (persistent context) |
| Context Survival | Fails after compaction | Survives compaction (re-injected) |
| Review Quality | Generic | Context-aware (knows vision/architecture) |

**Current Evidence:**
- ✅ User discussion requested this (source of item)
- ✅ Context compaction is a known problem (CORE-025)
- ✅ Agents drift from project vision (observed in practice)
- ❌ No data yet on whether context injection prevents drift

**YAGNI Check:**
- Solving a problem we **likely have** (agent alignment, drift from vision)
- Would be **okay** without this for 6-9 months (nice-to-have, not critical)
- Current solution **works** - CLAUDE.md provides some context, agents can read docs

**Recommendation:** ⚠️ **DEFER** - Complement to CORE-025 (compaction survival), not standalone

**Reasoning:**
Medium effort, medium value. This is fundamentally a mitigation for context compaction (CORE-025). Without solving compaction first, context documents get lost too. The value proposition is stronger after CORE-025 is solved - then context documents become the persistent "memory" that survives compaction. CLAUDE.md already provides basic context injection. More structured context docs are valuable but not urgent. Prioritize core reliability items (CORE-026, WF-023, CORE-028) first.

**Implementation Order:**
1. CORE-025 (compaction survival) - prerequisite for persistence
2. Basic North Star injection - prove the concept
3. Architecture + UI Style Guide - expand coverage
4. Smart injection (detect frontend vs backend) - optimize
5. Review integration - enhance review quality

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

#### PRD-008: Zero-Config Workflow Enforcement for Agents
**Status:** ✅ **CRITICAL** - Enables actual dogfooding
**Complexity:** MEDIUM (auto-setup + context injection)
**Priority:** HIGH - Required for PRD-007 to be usable
**Source:** User feedback (2026-01-11) - "Simple prompt shouldn't require 125 pages of docs"

**Problem Statement:**
PRD-007 built a complete Agent Workflow Enforcement System, but using it requires:
1. Manually starting orchestrator server (`python -m src.orchestrator.api`)
2. Manually creating `agent_workflow.yaml` in target repo
3. Manually importing and using Agent SDK
4. Reading 125 pages of documentation to understand how

**This defeats the purpose.** Agents should just say:
```
I want to implement user authentication using workflow enforcement.
```

**Current UX (TOO COMPLEX):**
```
1. Start server: cd workflow-orchestrator && python -m src.orchestrator.api
2. Create agent_workflow.yaml with phases/gates/tools
3. Import AgentClient and write boilerplate
4. Claim task, track progress, submit artifacts
5. Read AGENT_SDK_GUIDE.md, WORKFLOW_SPEC.md, DEPLOYMENT_GUIDE.md
```

**Desired UX (SIMPLE):**
```
User: "I want to implement user auth using workflow enforcement."
Agent: [Auto-detects orchestrator, auto-generates workflow.yaml, auto-uses SDK]
```

**Required Auto-Setup Components:**

| Component | Current | Needed |
|-----------|---------|--------|
| **Server Discovery** | Manual start | Auto-detect running server OR auto-start in background |
| **Workflow YAML** | Manual creation | Auto-generate from task description + repo conventions |
| **Agent SDK Usage** | Manual import/setup | Auto-inject SDK as context for AI agents |
| **Prompt Context** | User must explain | Claude Code reads AGENT_SDK_GUIDE.md automatically |

**Proposed Solution:**

**1. Auto-Detection / Auto-Start**
```python
# In agent context initialization
def ensure_orchestrator_running():
    # Check if server running on localhost:8000
    if not orchestrator_reachable():
        # Start in background: orchestrator serve --daemon
        start_orchestrator_daemon()
    return orchestrator_url
```

**2. Auto-Generate Workflow YAML**
```python
def generate_workflow_yaml(task_description: str, repo_analysis: dict):
    # Analyze repo: tests/, src/, language, conventions
    # Generate appropriate workflow.yaml with:
    # - Phases based on project type
    # - Tools based on repo languages
    # - Gates based on test framework detected
    return workflow_yaml
```

**3. Auto-Inject SDK Context for Claude Code**

Add to Claude Code's session initialization:
```python
# When orchestrator detected in repo or ~/workflow-orchestrator exists:
if orchestrator_available():
    inject_context([
        "docs/AGENT_SDK_GUIDE.md",  # How to use SDK
        "src/agent_sdk/client.py",   # SDK code for reference
    ])
```

**4. Simple Command Pattern with Execution Mode**
```bash
# In any repo - DEFAULT: Sequential (single agent, proven robust)
orchestrator enforce "Implement user authentication"

# OR: Parallel execution with sub-agents (when ready for multi-agent)
orchestrator enforce "Implement user authentication" --parallel

# OR: Explicit sequential (same as default)
orchestrator enforce "Implement user authentication" --sequential

# Auto-generates:
# 1. agent_workflow.yaml (if not exists)
# 2. Starts server (if not running)
# 3. Injects SDK context for agent
# 4. Provides simple prompt to agent
# 5. Configures execution mode (sequential by default)
```

**Execution Modes:**

| Mode | Flag | Description | When to Use |
|------|------|-------------|-------------|
| **Sequential** | (default) or `--sequential` | Single agent works through phases linearly | Default until multi-agent proven robust |
| **Parallel** | `--parallel` | Spawns sub-agents for parallelizable work | After PRD-004, PRD-007, PRD-014 validated |

**Sequential Mode (Default):**
- Single Claude Code agent
- Works through PLAN → TDD → IMPL → REVIEW → VERIFY sequentially
- Proven workflow (current orchestrator behavior)
- Lower complexity, easier debugging
- **Recommended until parallel agent coordination is battle-tested**

**Parallel Mode (Opt-in):**
- Spawns multiple agents via `orchestrator prd spawn`
- Agents coordinate through orchestrator server
- State management prevents conflicts
- Approval gates for coordination decisions
- **Only use after dogfooding validates robustness**

**Default Rationale:**
Sequential mode is default because:
- Multi-agent coordination is new (PRD-007 just completed)
- File conflicts not yet solved (PRD-014 exploratory)
- Spawning stability needs validation (PRD-004 recently fixed)
- Single-agent workflow is proven and reliable

**When to Switch Default:**
After dogfooding shows:
- ✅ Multi-agent spawning stable (no crashes, cleanup works)
- ✅ State coordination prevents race conditions
- ✅ File conflicts resolved or rare
- ✅ Approval gates handle coordination well
- ✅ Performance benefit clear (>30% faster)

**Configuration:**
```yaml
# orchestrator.yaml
execution:
  default_mode: "sequential"  # or "parallel" when proven
  allow_parallel: true         # Can users opt-in to --parallel?
```

**Simple Prompt for Agents:**
```
Task: Implement user authentication

The workflow orchestrator is running and agent_workflow.yaml has been created.
Use the Agent SDK (src.agent_sdk.client.AgentClient) to:
1. Claim this task
2. Follow the enforced workflow phases
3. Submit artifacts at gates
4. Track progress through completion

The SDK is already imported and ready to use.
```

**Integration with PRD-007:**
This makes PRD-007 actually usable. Without this, PRD-007 is "technically complete" but requires too much manual setup for anyone to actually use it.

**Files to Create:**
- `src/orchestrator/auto_setup.py` - Auto-detection, auto-start, auto-generation
- `src/orchestrator/workflow_generator.py` - Generate workflow.yaml from task + repo
- `src/cli.py` - Add `orchestrator enforce <task>` command
- `.claude/agent_sdk_context.md` - Auto-injected context for Claude Code sessions

**Files to Modify:**
- Claude Code session initialization (if we control it)
- OR: Add to CLAUDE.md with instructions for agent to read SDK guide

**Success Criteria:**
- Agent can use workflow enforcement with single simple prompt
- No manual server startup required
- No manual YAML creation required
- No manual SDK setup required
- Works in any repo with one command: `orchestrator enforce "task"`

**Dogfooding Test:**
```
# In a different repo
$ orchestrator enforce "Add rate limiting to API"

✓ Orchestrator running on localhost:8000
✓ Generated agent_workflow.yaml (5 phases, 3 gates)
✓ Agent SDK context injected
✓ Task ready - tell your agent: "Start the rate limiting task"
```

**Recommendation:** ✅ **IMPLEMENT IMMEDIATELY** - PRD-007 is not truly "complete" without this UX layer.

---


#### PRD-007-E1: Multi-Instance Architecture Package (Redis + Distributed Locks + Circuit Breaker Coordination)
**Status:** 🔍 **EXPLORATORY** - Requires complexity/benefit analysis before implementation
**Complexity:** VERY HIGH (complete architectural redesign)
**Priority:** Low (no evidence of need)
**Source:** PRD-007 learnings + tradeoff analysis (2026-01-11)
**Depends On:** PRD-007 (Completed)
**Includes:** Former E1 (Redis state), E4 (distributed locks), E5 (circuit breaker coordination)

⚠️ **CRITICAL:** These three items form an "all or nothing" package. Implementing E1 alone without E4/E5 creates data corruption risk in multi-instance scenarios.

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Single-Instance) | This PRD (Multi-Instance) |
|--------|--------------------------|---------------------------|
| **Complexity** | LOW - JSON file, thread locks | VERY HIGH - Redis cluster, distributed protocols |
| **Operational Overhead** | Minimal - no dependencies | High - Redis ops, backups, monitoring, troubleshooting |
| **Scale Limit** | ~1000 concurrent tasks | Unlimited (horizontal scaling) |
| **Failure Modes** | Simple - file corruption, deadlock | Complex - split brain, network partitions, Redis down |
| **Testing** | Easy - single process | Hard - distributed system race conditions |
| **Cost** | $0/month extra | Redis hosting + operational time |

**Current Evidence for Need:**
- ❌ No production deployment exists yet
- ❌ No data on actual concurrent task volume
- ❌ No observed bottleneck at single-instance scale
- ❌ No user requests for multi-instance or HA

**What Changes Required:**
1. Replace JSON state with Redis (sorted sets, hashes, pub/sub)
2. Replace `threading.Lock` with Redis distributed locks (redlock algorithm)
3. Share circuit breaker state across instances
4. Add Redis cluster deployment (3+ nodes for HA)
5. Implement connection pooling, failover, retry logic
6. Add distributed system tests (network partitions, race conditions)

**Recommendation:** ⚠️ **DEFER - Apply YAGNI Principle**
- Current architecture is production-ready for foreseeable scale
- No evidence shows need for >100 concurrent tasks, let alone >1000
- Premature optimization adds significant operational burden
- **Revisit only when:** Production shows sustained >500 concurrent tasks OR user explicitly requires multi-instance HA

---

#### PRD-007-E2: Persistent Event Store
**Status:** 🔍 **DEFER** - Wait for user need
**Complexity:** Medium
**Priority:** Low (no current use case)
**Source:** PRD-007 learnings + tradeoff analysis (2026-01-11)
**Depends On:** PRD-007 (Completed)

**Complexity vs Benefit Tradeoff:**

| Factor | Current (In-Memory) | This PRD (Persistent) |
|--------|---------------------|----------------------|
| **Complexity** | LOW - Python list | MEDIUM - SQLite schema, migrations, queries |
| **Storage** | Minimal (cleared on restart) | Growing disk usage (needs retention policy) |
| **Query Speed** | Instant (in-memory) | Slower (disk I/O) |
| **Debugging Value** | Good (active session) | Better (cross-restart forensics) |

**Current Evidence for Need:**
- ❌ No user reports needing event history after restart
- ❌ In-memory events sufficient for debugging active issues
- ❌ No compliance requirement for event retention

**Recommendation:** ⚠️ **DEFER** - Wait for actual user request. Current in-memory store works for all known use cases.

**Reconsider when:** User explicitly requests cross-restart event analysis OR compliance requires event audit trail.

---

#### PRD-007-E3: Prometheus Metrics Endpoint
**Status:** ✅ **RECOMMENDED** - Low effort, high value for production
**Complexity:** LOW (well-established pattern)
**Priority:** Medium-High (standard practice for production services)
**Source:** PRD-007 learnings + tradeoff analysis (2026-01-11)
**Depends On:** PRD-007 (Completed)

**Complexity vs Benefit Tradeoff:**

| Factor | Cost | Benefit |
|--------|------|---------|
| **Implementation** | 2-3 hours (prometheus_client library + decorators) | Standard monitoring practice |
| **Operational** | Prometheus server (can use existing) | Alerting on circuit breakers, latency spikes |
| **Maintenance** | LOW - stable library | Performance regression detection |

**Current Evidence for Need:**
- ✅ Production services should have metrics
- ✅ Circuit breaker state visibility essential
- ✅ Low implementation cost
- ✅ Enables proactive issue detection

**Metrics to Expose:**
- Task completion rate (gauge)
- Phase transition latency (histogram)
- Circuit breaker state (gauge: 0=CLOSED, 1=OPEN, 2=HALF_OPEN)
- Retry counts by operation (counter)
- Event bus throughput (counter)
- API request latency percentiles (histogram)

**Recommendation:** ✅ **IMPLEMENT** - This is a best practice with high ROI. Should be added before first production deployment.

---

#### ~~PRD-007-E4: Distributed Locking Support~~
#### ~~PRD-007-E5: Circuit Breaker State Sharing~~

**Status:** ❌ **MERGED INTO PRD-007-E1** (see above)
**Reason:** These cannot be implemented independently. They are part of the multi-instance architecture package and have no value without it.

---

#### PRD-014: File Conflict Management for Parallel Agents
**Status:** Exploration Needed
**Complexity:** TBD
**Priority:** Medium (may not be a real problem)
**Source:** User question (2026-01-11) - How do we handle two agents working on the same file?

**Question:**
How should we manage when two spawned PRD agents (or two manual Claude Code instances) are working on the same file? Is this even a problem that needs solving?

**Scenarios to Consider:**
1. Two spawned PRD agents assigned tasks that touch the same file
2. User running two Claude Code instances manually in same repo
3. Agent editing file while user also editing

**Is This Actually a Problem?**

It's unclear if this needs a solution. Consider:
- Git already handles merges - maybe that's sufficient?
- Good task decomposition may naturally avoid overlaps
- Conflicts might be rare in practice
- Existing merge conflict resolution (CORE-023) handles post-hoc conflicts

**If It Is a Problem, Potential Approaches:**

| Approach | Description |
|----------|-------------|
| **Do nothing** | Rely on git merge + conflict resolution |
| **Task decomposition** | Design tasks to not overlap (prevention) |
| **File locks (OS-level)** | flock or similar |
| **Advisory locks (app-level)** | Orchestrator-managed claims |
| **Optimistic locking** | Version check on save, merge if needed |
| **Real-time sync (CRDT)** | Collaborative editing |

**Open Questions:**
1. How often do parallel agents actually touch the same file?
2. When they do, how bad are the resulting conflicts?
3. Is git merge + human resolution sufficient?
4. Would better task decomposition eliminate the problem?
5. Is the complexity of a locking solution worth it?

**Next Steps:**
- [ ] Observe: Track how often file conflicts occur in practice
- [ ] Assess: Evaluate severity when they do occur
- [ ] Decide: Is this worth solving, or is git merge enough?
- [ ] If needed: Design solution based on findings

---

#### PRD-016: Auto-Spawn Review Agents
**Status:** Planned
**Complexity:** Medium
**Priority:** High
**Depends On:** PRD-007 (Agent Workflow Enforcement)

**Problem:** Reviews still require manual orchestration to start.

**Solution:** Orchestrator auto-spawns review agents when task transitions IMPL → REVIEW.

**Implementation:**
- Detect IMPL → REVIEW transition trigger in enforcement engine
- Read `auto_spawn` section from agent_workflow.yaml
- Spawn parallel review agents (security, quality, consistency, holistic, vibe_coding)
- Wait for all reviews to complete before allowing REVIEW → COMPLETE transition
- Consolidate review results into single review_report artifact

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Manual Review) | With Auto-Spawn |
|--------|------------------------|-----------------|
| Complexity | None | MEDIUM - spawn coordination, result consolidation |
| Review Coverage | Manual (often forgotten) | Automatic (always runs) |
| Parallelization | Sequential if done | Parallel (faster) |
| Dependencies | PRD-007 must be solid | Depends on PRD-007 stability |

**Current Evidence:**
- ❌ PRD-007 just completed (not validated in production)
- ❌ No evidence manual review is a bottleneck
- ❌ Multi-agent spawning not yet proven stable
- ❌ No user requests for auto-review spawning

**YAGNI Check:**
- Solving a **hypothetical** problem (manual review burden)
- Would be **completely fine** without this for 12+ months (manual review works)
- Current solution **works** - `minds review` is simple and reliable

**Recommendation:** ⚠️ **DEFER** - Automation before validation is premature

**Reasoning:**
Medium effort, but built on unproven foundations. PRD-007 just completed and hasn't been battle-tested. Multi-agent spawning (PRD-004) recently had stability issues. Auto-spawning reviews adds complexity without clear benefit - current `minds review` command is simple and works well. This is automation for automation's sake. Wait until manual review becomes a clear bottleneck (it won't) or PRD-007 is proven rock-solid in production.

**Reconsider when:**
- PRD-007 proven stable in production (6+ months)
- Manual review coordination becomes actual pain point
- Multi-agent spawning demonstrably robust

**Success Criteria:**
- [ ] Reviews auto-spawn on IMPL → REVIEW transition
- [ ] All 5 review models run in parallel
- [ ] Consolidated review report generated
- [ ] Agent blocked until all reviews complete

---

#### PRD-009: Monitoring & Metrics Export
**Status:** Planned
**Complexity:** Low
**Priority:** Medium
**Depends On:** PRD-007 (Agent Workflow Enforcement)

**Problem:** No visibility into enforcement effectiveness.

**Solution:** Export metrics defined in agent_workflow.yaml monitoring section.

**Metrics to Track:**
- phase_transition_time (how long in each phase)
- gate_pass_rate (% of transitions that pass gates)
- gate_block_rate (% of transitions blocked)
- tool_usage_by_phase (which tools used where)
- artifact_validation_failures (what's failing validation)

**Export Format:** JSONL to `.orchestrator/metrics.jsonl`

**Alerting:**
- Alert if gate_block_rate > 50% (agents struggling)
- Alert if task_stuck_in_phase > 2h (needs human intervention)

**Complexity vs Benefit Tradeoff:**

| Factor | Current (No Metrics) | With Metrics Export |
|--------|---------------------|---------------------|
| Complexity | None | LOW - event tracking, JSONL export |
| Visibility | None | High (measurable effectiveness) |
| Debugging | Hard (guess what went wrong) | Easy (data-driven analysis) |
| Optimization | Impossible | Data-driven improvements |

**Current Evidence:**
- ❌ PRD-007 just completed (no production use yet)
- ❌ No metrics = no evidence workflow enforcement helps or hurts
- ❌ No user requests for metrics
- ❌ No operational deployment to monitor

**YAGNI Check:**
- Solving a **hypothetical** problem (lack of visibility)
- Would be **okay** without this for 3-6 months (can dogfood without metrics first)
- Current solution **works** - no metrics, but also no production use

**Recommendation:** ⚠️ **DEFER** - Validate PRD-007 works first, then add metrics

**Reasoning:**
Low effort, but premature. Metrics are valuable when you have a running system to optimize. PRD-007 just completed and hasn't been used in production yet. First step: dogfood PRD-007 to prove it works. Second step: identify what metrics would actually be valuable based on real usage. Third step: implement metrics. Adding metrics now is measuring something that doesn't exist yet. Wait 3-6 months of production use, then add metrics based on actual questions that arise.

**Reconsider when:**
- PRD-007 in production for 3+ months
- Questions arise like "Why do tasks get stuck?" or "Which gates fail most?"
- Need to optimize based on data, not guesses

**Success Criteria:**
- [ ] Metrics exported to .orchestrator/metrics.jsonl
- [ ] Dashboard can read metrics (optional: Grafana/Prometheus)
- [ ] Alerts trigger on thresholds

---

#### PRD-010: Recovery & Failure Handling
**Status:** Planned
**Complexity:** High
**Priority:** High
**Depends On:** PRD-007 (Agent Workflow Enforcement)

**Problem:** Agent/orchestrator crashes leave tasks in inconsistent state.

**Solution:** Implement recovery strategies from agent_workflow.yaml.

**Agent Crash Handling:**
- Detect when agent stops sending heartbeats
- Retry task up to 3 times with 60s backoff
- If retries exhausted, escalate to human

**Orchestrator Crash Handling:**
- Checkpoint state every 5 minutes to `.orchestrator/checkpoints/`
- On restart, resume from last checkpoint
- Replay event log to rebuild in-memory state

**Gate Timeout Handling:**
- If gate approval times out, escalate to human
- Preserve all state (don't lose progress)
- Allow human to approve/reject/retry

**Complexity vs Benefit Tradeoff:**

| Factor | Current (No Recovery) | With Recovery System |
|--------|----------------------|---------------------|
| Complexity | None | HIGH - checkpoints, replay, retry, escalation |
| Crash Tolerance | None (data loss) | High (recovers gracefully) |
| Implementation | N/A | Complex state management |
| Testing | Easy | Hard (simulate crash scenarios) |

**Current Evidence:**
- ❌ PRD-007 just completed (no production crashes yet)
- ❌ Unknown if crashes are frequent or rare
- ❌ Unknown if current JSON state survives crashes
- ❌ No user reports of crash-related data loss

**YAGNI Check:**
- Solving a **hypothetical** problem (crash recovery)
- Would be **okay** without this for 6-9 months (crashes may be rare)
- Current solution **unknown** - need to observe crash behavior first

**Recommendation:** ⚠️ **DEFER** - Observe crash patterns before building complex recovery

**Reasoning:**
High effort for unknown problem. PRD-007 just completed - we don't know if crashes are even a real issue. JSON state files may survive crashes fine (they're written atomically). Complex recovery systems (checkpointing, replay, retries) add significant complexity and testing burden. Better approach: ship PRD-007, observe actual crash behavior and impact, then decide if recovery is needed. If crashes are rare and JSON state survives, this entire system is unnecessary.

**Simpler Alternative:**
- JSON state with atomic writes (may already survive crashes)
- Manual recovery: restart orchestrator, resume from state file
- Wait for evidence of crash frequency before building automation

**Reconsider when:**
- Crashes observed in production (>1 per week)
- Data loss occurs (JSON state corrupted)
- Manual recovery becomes actual burden

**Success Criteria:**
- [ ] Orchestrator survives restart without data loss
- [ ] Agent crashes trigger automatic retry
- [ ] Gate timeouts escalate to human
- [ ] Zero data loss on crash

---

#### PRD-015: Cloud-Based Development / Agent Spawning
**Status:** Exploration Needed
**Complexity:** TBD (depends on approach)
**Priority:** HIGH - Local spawning exhausts laptop resources
**Source:** User observation (2026-01-11) - Too much memory/compute on laptop

**Problem:**
Spawning multiple parallel agents locally consumes significant resources:
- Each Claude Code instance uses ~500MB-1GB RAM
- Multiple tmux sessions with active agents
- CPU spikes during concurrent operations
- Laptop becomes sluggish with 3+ agents

**Question:** What's the best way to handle resource-intensive parallel agent work?

**Potential Approaches:**

| Approach | Description | Complexity |
|----------|-------------|------------|
| **A. Cloud Dev Server** | Do all development on a scalable cloud VM (e.g., EC2, GCP) that can spin up/down capacity as needed | Low |
| **B. Remote Agent Spawning** | Keep orchestrator local, spawn agents in cloud (Codespaces, Modal) | High |
| **C. Hybrid** | Local for interactive, cloud for batch/parallel | Medium |
| **D. Resource Limits** | Limit concurrent local agents, queue the rest | Low |

**Option A: Cloud Dev Server (Simplest?)**
- Run entire dev environment on a cloud VM
- Scale VM size based on workload
- No architecture changes needed
- Orchestrator + agents all run on same (beefier) machine
- Examples: EC2 with auto-scaling, Google Cloud Workstations, Gitpod

**Option B: Remote Agent Spawning**
- Orchestrator stays local
- Agents spawn in cloud environments
- Requires coordination layer, credential passing, result syncing
- More complex but keeps local machine light

**Option C: Hybrid**
- Use local for 1-2 interactive agents
- Offload batch work to cloud
- Best of both worlds but more complex to manage

**Option D: Resource Limits**
- Cap concurrent agents (e.g., max 2 local)
- Queue additional tasks
- Simple but slower throughput

**Open Questions:**
1. What's the actual resource usage per agent? (need to measure)
2. Is latency acceptable for cloud-based development?
3. What are the cost implications of each approach?
4. How does credential/secret management work across approaches?
5. Which cloud providers offer the best dev experience?

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Local Only) | Option A (Cloud Server) | Option D (Resource Limits) |
|--------|---------------------|------------------------|---------------------------|
| Complexity | None | LOW - just use cloud VM | LOW - add agent queue |
| Cost | $0/month | $50-200/month | $0/month |
| Resource Limits | 2-3 agents max | 10+ agents easily | 2-3 agents, queue rest |
| Latency | None | Slight (network) | None |

**Current Evidence:**
- ✅ User observed laptop sluggishness with 3+ agents
- ✅ Multi-agent spawning is a real use case (PRD execution)
- ❌ No measurement of actual resource usage per agent
- ❌ Unknown how often >3 parallel agents are actually needed

**YAGNI Check:**
- Solving a problem we **actually have** (laptop resource exhaustion)
- Would **NOT** be okay without this if using multi-agent frequently
- Current solution **fails** with >3 agents

**Recommendation:** 🔍 **INVESTIGATE Option D first**, then cloud if needed

**Reasoning:**
Real problem, but solution unclear. Option D (resource limits + queuing) is simplest and may be sufficient - most workflows don't need >3 parallel agents. Option A (cloud dev server) is next simplest but adds cost and latency. Option B (remote spawning) is complex overkill. Priority: 1) Measure actual resource usage, 2) Implement Option D (5-10 agents max), 3) If still hitting limits, consider cloud. This is a real operational constraint, not YAGNI, but start with simplest solution.

**Implementation Priority:**
1. Measure resource usage per agent (1-2 hours)
2. Implement Option D - queue-based limiting (LOW effort)
3. If queuing is too slow, evaluate Option A (cloud server)

**Next Steps:**
- [ ] Measure actual resource usage per agent
- [ ] Research cloud dev environments (Codespaces, Gitpod, EC2, etc.)
- [ ] Estimate costs for each approach
- [ ] Prototype simplest option (likely A or D)
- [ ] Document findings and recommendation

---

#### PRD-011: Orchestrator Web UI
**Status:** Design Phase Needed
**Complexity:** TBD (depends on scope)
**Priority:** Low
**Depends On:** PRD-007, PRD-009 (Monitoring) - for data to display
**Source:** User request (2026-01-11) - Visual interface for orchestrator management

**Problem:**
CLI-only interface has limitations for visibility and control when managing multiple agents and complex workflows.

**What's Needed First: Design Phase**

Before building anything, need to define:

1. **Functionality** - What should the UI actually do?
   - What are the core use cases?
   - What problems is it solving that CLI can't?
   - What's MVP vs nice-to-have?

2. **UX** - How should users interact with it?
   - What workflows does it support?
   - What's the information hierarchy?
   - How does it complement (not replace) CLI?

3. **UI** - What should it look like?
   - Wireframes / mockups
   - Visual design system
   - Responsive requirements?

**Initial Ideas (to explore in design phase):**
- View files and changes
- Monitor sub-agents
- Understand skips and decisions
- Provide guidance to agents
- Look at learnings

**Open Questions:**
1. Who is the primary user? (Developer? Team lead? Both?)
2. Is this a "dashboard" (read-mostly) or "control panel" (interactive)?
3. Web app, desktop app, or terminal UI (Textual)?
4. How much real-time updating is needed?
5. Should it work on mobile?
6. What data is already available via CLI that just needs visualization?

**Design Phase Tasks:**
- [ ] Define primary use cases and user personas
- [ ] List must-have vs nice-to-have features
- [ ] Create low-fidelity wireframes
- [ ] Get user feedback on wireframes
- [ ] Define MVP scope
- [ ] Choose tech stack based on requirements
- [ ] Create detailed design document

**Implementation:** TBD after design phase

**Complexity vs Benefit Tradeoff:**

| Factor | Current (CLI Only) | With Web UI |
|--------|-------------------|-------------|
| Complexity | None | HIGH - full web app, frontend + backend |
| Visibility | Good (CLI output) | Better (visual dashboard) |
| Learning Curve | Low (CLI commands) | Lower (visual interface) |
| Maintenance | Low | High (UI bugs, browser compat) |

**Current Evidence:**
- ✅ User requested this
- ❌ No evidence CLI is actually a bottleneck
- ❌ PRD-007 and PRD-009 don't exist yet (no data to show)
- ❌ Unknown what specific problems UI would solve

**YAGNI Check:**
- Solving **hypothetical** UX problems (CLI may be fine)
- Would be **completely fine** without this for 12+ months (CLI works)
- Current solution **works** - CLI is simple and effective

**Recommendation:** ⚠️ **DEFER INDEFINITELY** - CLI-first is a strength, not weakness

**Reasoning:**
High effort, unclear benefit. CLI tools have lower maintenance, better scriptability, and clearer mental models. Web UIs add complexity (frontend bugs, browser compatibility, responsive design) without clear value. CLAUDE.md explicitly states "CLI-first" as a design principle. User request for UI is not evidence of need - need to validate CLI is actually blocking workflows. Modern CLI tools (rich, textual) can be beautiful too. Unless usage data shows CLI is genuinely painful, this is solution looking for problem.

**Reconsider if:**
- Team size grows beyond 5 people (need shared visibility)
- Non-technical stakeholders need access
- Clear evidence CLI blocks specific workflows

---

#### PRD-012: A/B Testing Workflows
**Status:** Planned
**Complexity:** High
**Priority:** Low

**Problem:** Don't know if workflow is optimal.

**Solution:** Support multiple workflow definitions, randomly assign agents, compare metrics.

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Single Workflow) | With A/B Testing |
|--------|--------------------------|------------------|
| Complexity | None | HIGH - variant management, random assignment, statistical analysis |
| Optimization | Manual/intuitive | Data-driven |
| Sample Size Needed | N/A | Large (hundreds of runs) |
| Prerequisites | None | PRD-007 + PRD-009 (metrics) |

**Current Evidence:**
- ❌ PRD-007 not validated in production yet
- ❌ No baseline workflow to optimize
- ❌ No metrics to compare (PRD-009 doesn't exist)
- ❌ No evidence current workflow is suboptimal

**YAGNI Check:**
- Solving **hypothetical** optimization problem
- Would be **completely fine** without this for years
- Current solution **unknown** - workflow not proven yet

**Recommendation:** ⚠️ **DEFER INDEFINITELY** - Premature optimization is root of all evil

**Reasoning:**
Classic premature optimization. Can't A/B test what doesn't exist. PRD-007 needs 6-12 months production use before optimization makes sense. Even then, manual workflow iteration based on observation is likely sufficient. A/B testing requires statistical rigor, large sample sizes, and careful variant design - huge investment for unclear payoff. This is enterprise-scale thinking for a tool that hasn't proven core value yet.

**Reconsider if:**
- Workflow in production >1 year
- Hundreds of workflow runs per week
- Clear hypothesis about what to optimize

---

#### PRD-013: ML-Based Gate Optimization
**Status:** Planned
**Complexity:** Very High
**Priority:** Low

**Problem:** Gates may be too strict or too lenient.

**Solution:** Machine learning model learns from historical gate pass/fail decisions, suggests optimizations.

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Manual Gates) | With ML Optimization |
|--------|----------------------|---------------------|
| Complexity | None | VERY HIGH - ML pipeline, feature engineering, training, deployment |
| Data Requirements | None | Thousands of gate decisions |
| Maintenance | Low | High (model retraining, drift detection) |
| Interpretability | High (rules explicit) | Low (black box) |

**Current Evidence:**
- ❌ No gates exist yet (PRD-007 just completed)
- ❌ No historical data (need years of production use)
- ❌ No evidence gates are misconfigured
- ❌ No user complaints about gate strictness

**YAGNI Check:**
- Solving **hypothetical** optimization problem
- Would be **completely fine** without this for years (decades?)
- Current solution **doesn't exist yet** to optimize

**Recommendation:** ⚠️ **DEFER INDEFINITELY** - ML is massive overkill

**Reasoning:**
This is absurdly premature. PRD-007 gates don't exist in production. Even if they did, manual tuning based on observation is sufficient for years. ML requires thousands of samples, careful feature engineering, model maintenance, and addresses a problem that likely doesn't exist. Gates are simple boolean rules - if they're wrong, just change the YAML. This is "let's use ML because it sounds cool" not "we have a problem that requires ML." Hard pass.

**Simpler Alternative:**
- Use manual gate tuning based on observation
- Add logging to see which gates fail most often
- Adjust thresholds in YAML based on data
- Never build this ML system

---

### Critical - Agent Independence

#### CORE-030: Audit and Remove Claude Code Dependencies
**Status:** Planned
**Complexity:** LOW (audit) to MEDIUM (if refactoring needed)
**Priority:** HIGH - Core architectural principle
**Source:** User feedback (2026-01-11) - "I'm nervous about ever including things in Claude.md as I want this to be a stand alone program which others can use"

**Problem Statement:**
The orchestrator currently has implicit dependencies on Claude Code environment:
1. **CLAUDE.md documentation** - Contains orchestrator usage instructions
2. **Installation via Claude Code session hooks** - install.sh assumes Claude Code
3. **CLI integration examples** - Documented for Claude Code specifically
4. **Happy integration** - Mobile access assumes Claude Code + Happy

**Real-World Impact:**
- Codex, Cursor, Windsurf, or other AI agents cannot easily adopt the orchestrator
- CI/CD pipelines may have Claude Code assumptions
- Documentation is Claude Code-centric rather than tool-agnostic
- Users may be locked into Claude Code ecosystem

**Non-Negotiable Principle:**
> The orchestrator must work independently of Claude Code, without requiring CLAUDE.md or Claude Code-specific features. It should be usable by any AI agent (Codex, Cursor, Windsurf, etc.) and in any environment (CLI, CI/CD, web).

**Proposed Solution:**

**Phase 1: Audit** (1-2 hours)
1. Grep codebase for "claude", "CLAUDE", "happy", "Happy" references
2. Document all Claude Code-specific features/assumptions
3. Identify which are:
   - **Essential to keep** (e.g., agent SDK is agent-agnostic)
   - **Can be generalized** (e.g., "AI agent" instead of "Claude Code")
   - **Should be removed** (e.g., tight coupling to Happy)

**Phase 2: Refactor** (if needed, 4-8 hours)
1. Move Claude Code-specific docs from CLAUDE.md → separate `docs/integrations/claude-code.md`
2. Make README.md agent-agnostic (works for any AI agent)
3. Ensure CLI commands work standalone (no Claude Code assumptions)
4. Update installation to work without session hooks (pure pip install)
5. Add integration guides for other agents: `docs/integrations/cursor.md`, `docs/integrations/codex.md`

**Phase 3: Testing** (2-4 hours)
1. Test orchestrator in vanilla terminal (no Claude Code)
2. Test with pure Python environment (no AI agent)
3. Test CI/CD usage (GitHub Actions, GitLab CI)
4. Verify all CLI commands work standalone

**Expected Findings:**
- Most code is already agent-agnostic (core functionality doesn't know about Claude Code)
- Documentation is the main culprit (assumes Claude Code context)
- Installation script may need --standalone flag
- Agent SDK is already generic (good!)

**Success Criteria:**
- [ ] All code works in vanilla terminal (no AI agent)
- [ ] README.md mentions zero AI agent brands
- [ ] Installation: `pip install workflow-orchestrator` works standalone
- [ ] CLAUDE.md becomes `docs/integrations/claude-code.md` (optional integration guide)
- [ ] New doc: `docs/integrations/README.md` explains how to integrate with any agent

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Claude Code-centric) | After Refactor (Agent-agnostic) |
|--------|-------------------------------|--------------------------------|
| Complexity | LOW - existing code | LOW - mostly docs changes |
| Adoption | Claude Code users only | Any AI agent |
| Maintenance | Coupled to Claude Code ecosystem | Independent evolution |
| Testing | Claude Code environment | Any environment |
| CI/CD | Requires workarounds | Native support |

**Current Evidence:**
- ✅ User explicitly concerned about Claude Code lock-in
- ✅ Project goal: "stand alone program which others can use"
- ✅ Future goal: "runnable by other agents like Codex"
- ✅ Aligns with architectural principle

**YAGNI Check:**
- This is **NOT speculative** - it's enforcing existing architectural principle
- Validates that current implementation matches stated goals
- Prevents accumulation of Claude Code-specific assumptions

**Recommendation:** ✅ **RECOMMEND** - High priority, low effort, core principle

**Reasoning:**
This isn't feature creep - it's ensuring the project adheres to its stated goal of being a standalone, agent-agnostic tool. The audit phase is very low effort (1-2 hours) and will reveal if any refactoring is needed. Most likely, the code is already independent and only documentation needs updating. This should be done sooner rather than later to prevent Claude Code assumptions from accumulating.

**Tasks:**
- [ ] Audit: Grep for "claude", "CLAUDE", "happy", "Happy" in codebase
- [ ] Audit: List all Claude Code-specific assumptions
- [ ] Refactor: Move CLAUDE.md → `docs/integrations/claude-code.md`
- [ ] Refactor: Make README.md agent-agnostic
- [ ] Refactor: Add `docs/integrations/README.md` (integration guide template)
- [ ] Test: Run orchestrator in vanilla terminal (no AI agent)
- [ ] Test: Run in CI/CD environment
- [ ] Document: Add examples for Cursor, Codex, Windsurf integrations

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

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Inline Only) | With File Support |
|--------|----------------------|------------------|
| Complexity | None | LOW - read file, split lines |
| Usability | Awkward for many constraints | Easy (edit file) |
| Reusability | None | High (reuse file) |
| Effort | ~30 min implementation | ~30 min implementation |

**Current Evidence:**
- ❌ No user reports of constraints being unwieldy
- ❌ No evidence multiple constraints are common
- ❌ Inline constraints work fine for known use cases
- ✅ Very low implementation cost

**YAGNI Check:**
- Solving a **hypothetical** usability problem
- Would be **completely fine** without this for 12+ months
- Current solution **works** - inline constraints are simple

**Recommendation:** ⚠️ **DEFER** - Wait for user pain point

**Reasoning:**
Very low effort (~30 min), but also unclear need. Inline `--constraints` flags work fine for 1-3 constraints. If users commonly need 5-10 constraints, this becomes valuable. But no evidence of that yet. This is a nice-to-have convenience feature, not a core capability. Implement when users actually complain about inline constraints being awkward, not before.

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

**Complexity vs Benefit Tradeoff:**

| Factor | Current (File Backend) | With DB Backends |
|--------|----------------------|------------------|
| Complexity | LOW - simple JSON files | MEDIUM - DB schema, migrations, connections |
| Multi-Node | No | Yes (PostgreSQL) |
| Querying | Parse all files | SQL queries |
| Team Use | Copy files manually | Shared database |

**Current Evidence:**
- ❌ No multi-node deployment exists
- ❌ No team collaboration use case observed
- ❌ No reports of checkpoint querying being slow
- ❌ File backend works fine for current use

**YAGNI Check:**
- Solving **hypothetical** scaling problem
- Would be **completely fine** without this for 12+ months
- Current solution **works** - files are simple and reliable

**Recommendation:** ⚠️ **DEFER** - Wait for team/multi-node need

**Reasoning:**
Medium effort for unclear benefit. Checkpoints are infrequent (manual save points), not high-throughput data. File backend is simple, reliable, and git-friendly (can commit checkpoints). Database adds operational complexity (backups, migrations, connection management) without solving an actual problem. If orchestrator becomes a team tool with shared state, then PostgreSQL makes sense. But that's a big "if" that hasn't materialized yet.

**Reconsider when:**
- Team size >3 people sharing checkpoints
- Multi-node deployment actually needed
- Checkpoint querying becomes bottleneck (unlikely)

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

**Complexity vs Benefit Tradeoff:**

| Factor | Current (No Cache) | With Caching |
|--------|-------------------|--------------|
| Complexity | None | LOW - simple TTL cache |
| Speed | Subprocess/HTTP each time | Instant (cached) |
| Freshness | Always current | 5-min stale |
| Value | N/A | Only matters if availability checks are slow |

**Current Evidence:**
- ❌ No measurement of availability check latency
- ❌ No user complaints about slowness
- ❌ Provider selection happens infrequently (once per workflow)
- ❌ Unknown if subprocess spawn is actually slow

**YAGNI Check:**
- Solving **hypothetical** performance problem
- Would be **completely fine** without this for 12+ months
- Current solution **works** - no observed slowness

**Recommendation:** ⚠️ **DEFER** - Measure first, optimize if needed

**Reasoning:**
Low effort, but solving imaginary problem. Provider availability checks happen once per workflow start - not in a hot loop. Even if subprocess spawn takes 50ms, that's imperceptible to users. Caching adds complexity (TTL management, invalidation, stale data) for unclear benefit. This is textbook premature optimization. If profiling shows availability checks are actually slow, then cache. But don't assume.

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

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Built-in Only) | With Plugin System |
|--------|------------------------|-------------------|
| Complexity | LOW - providers in core | HIGH - entry points, validation, docs |
| Extensibility | Modify core code | External packages |
| Maintenance | Orchestrator team | Community |
| Use Case | Core providers only | Custom/niche providers |

**Current Evidence:**
- ❌ No user requests for custom providers
- ❌ No evidence built-in providers are insufficient
- ❌ No ecosystem of external providers exists
- ❌ No community contributions yet

**YAGNI Check:**
- Solving **hypothetical** extensibility need
- Would be **completely fine** without this for years
- Current solution **works** - add providers to core if needed

**Recommendation:** ⚠️ **DEFER INDEFINITELY** - Build when ecosystem demands

**Reasoning:**
High effort for imaginary need. Plugin systems are valuable when there's an ecosystem of external contributors. But orchestrator doesn't have that - it's a single-user tool. If someone needs a custom provider, they can fork or PR. Building plugin infrastructure before there are plugins is premature. Wait until multiple external contributors actually want to add providers, then build the system.

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

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Plaintext) | With Encryption |
|--------|---------------------|----------------|
| Complexity | None | HIGH - encryption lib, key mgmt, recovery |
| Security | Checkpoints readable | Checkpoints encrypted |
| Use Case | Development checkpoints | Sensitive proprietary work |
| Risk | Secrets may leak in checkpoints | Secrets protected |

**Current Evidence:**
- ❌ No reports of secrets in checkpoints
- ❌ No compliance requirement for encrypted checkpoints
- ❌ Checkpoints are developer-local (not shared)
- ✅ Secrets already handled by SOPS (separate system)

**YAGNI Check:**
- Solving **hypothetical** security problem
- Would be **completely fine** without this for years
- Current solution **works** - secrets handled separately

**Recommendation:** ⚠️ **DEFER INDEFINITELY** - No evidence of need

**Reasoning:**
High effort for unclear threat model. Checkpoints are local dev artifacts, not shared data. If they contain secrets, that's a bug in checkpoint creation (should scrub secrets). Encryption adds key management complexity, recovery challenges, and doesn't solve root cause. Better approach: ensure checkpoints never contain secrets (validation/scrubbing) rather than encrypt them. Only consider if compliance requires encrypted-at-rest for all local dev artifacts.

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

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Single Agent) | Original (Distributed) | Revised (PRD-001) |
|--------|----------------------|----------------------|------------------|
| Complexity | LOW | VERY HIGH - full distributed system | MEDIUM - session mgmt |
| Coordination | None needed | Item locking, claiming | Session registry |
| Merge Handling | Simple | Complex conflict resolution | Wave resolver |
| User Control | Full | Limited | Maintained |

**Current Evidence:**
- ✅ PRD-001 (Claude Squad) completed and simpler
- ✅ Original approach was over-engineered
- ✅ Session-based approach proven effective
- ❌ No evidence full distributed system needed

**YAGNI Check:**
- Original problem **over-solved** by distributed system design
- Current PRD-001 approach **sufficient** for known use cases
- Full distributed coordination **not needed**

**Recommendation:** ✅ **SUPERSEDED by PRD-001** - Simpler approach won

**Reasoning:**
This item is effectively complete via PRD-001's simpler approach. The original distributed workflow vision (item locking, claiming, central coordination) was over-engineered. Claude Squad + session management + wave-based merging solves the actual problem (parallel agent work) without distributed systems complexity. This is a great example of reconsidering and simplifying. Mark as superseded, not deferred.

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

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Manual Visual Testing) | With CI/CD |
|--------|---------------------------------|------------|
| Complexity | None | MEDIUM - GitHub Actions, preview deploy, screenshot compare |
| Coverage | Manual (often skipped) | Automated (every PR) |
| Feedback Speed | Slow (manual test) | Fast (automated) |
| Prerequisites | Visual verification system | Visual verification system + CI setup |

**Current Evidence:**
- ❌ No visual verification system exists yet (VV-001, VV-002, VV-003 not implemented)
- ❌ No preview/staging deployment setup
- ❌ No evidence manual visual testing is bottleneck
- ❌ Visual testing may not be core to orchestrator (CLI tool)

**YAGNI Check:**
- Solving **hypothetical** CI problem for **nonexistent** visual testing
- Would be **completely fine** without this for years
- Current solution **doesn't exist** - building automation before feature

**Recommendation:** ⚠️ **DEFER** - Build visual verification first, automate later

**Reasoning:**
Classic cart-before-horse. Can't automate visual testing that doesn't exist. VV-001 through VV-004 need to be implemented and proven valuable first. Only then does CI integration make sense. Also, orchestrator is primarily a CLI tool - visual testing may not even be relevant except for hypothetical web UI (PRD-011, also deferred). This is automation looking for a feature to automate.

**Reconsider when:**
- Visual verification system exists and is used regularly
- Manual visual testing becomes bottleneck
- Web UI (PRD-011) actually gets built and needs testing

---

### Low Priority

#### CONTEXT-002: RAG/Retrieval for Knowledge Management
**Status:** Exploration
**Complexity:** High
**Priority:** Low (exploratory)
**Source:** User discussion - Managing complex processes beyond context window limits

**Description:** Explore using RAG (Retrieval-Augmented Generation) to provide semantic search over learnings, PRDs, past decisions, and project knowledge. This could complement the handoff system (CORE-025) for longer-term knowledge management.

**Problem Space:**
Context windows have hard limits. Even with handoff/checkpoints, some information is lost or inaccessible:
- "How did we solve this problem 3 months ago?"
- "What were the tradeoffs we considered for X?"
- "Which PRDs are relevant to this new feature?"
- "What patterns have we learned across all projects?"

**Potential Use Cases:**

| Use Case | Description | Value |
|----------|-------------|-------|
| **Learning Retrieval** | Semantic search over LEARNINGS.md across sessions | Avoid repeating mistakes |
| **PRD Context** | Auto-inject relevant PRD sections during PLAN | Better planning decisions |
| **Decision History** | Surface past architectural decisions | Consistency |
| **Cross-Project Knowledge** | Shared index across repos | Scale learnings |
| **Review Context** | Provide reviewers with relevant past issues | Better reviews |

**Comparison with Handoff (CORE-025):**

| Aspect | Handoff | RAG |
|--------|---------|-----|
| Purpose | Survive context compaction | Query past knowledge |
| Timing | Session boundaries | Any time |
| Scope | Current task state | All historical knowledge |
| Complexity | Low | High |
| Infrastructure | Files only | Vector DB + embeddings |

**Recommendation:** These are complementary. Handoff solves the immediate problem (context compaction kills workflows). RAG is a longer-term enhancement for knowledge management.

**Open Questions:**
- What embedding model? (OpenAI, local, etc.)
- Vector DB? (Chroma, Pinecone, pgvector, local files?)
- Index scope? (per-project, per-user, shared?)
- How to handle updates? (re-index on commit?)
- Cost vs benefit for small projects?
- Privacy implications of indexing code/decisions?

**Potential Architecture:**
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  LEARNINGS.md   │     │   PRDs/docs/    │     │  Session logs   │
│  ROADMAP.md     │────▶│   CLAUDE.md     │────▶│  (scrubbed)     │
│  Decisions      │     │   Architecture  │     │                 │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 ▼
                    ┌─────────────────────┐
                    │   Embedding Model   │
                    │   (chunk + embed)   │
                    └──────────┬──────────┘
                               ▼
                    ┌─────────────────────┐
                    │    Vector Store     │
                    │  (local or remote)  │
                    └──────────┬──────────┘
                               ▼
                    ┌─────────────────────┐
                    │   Query Interface   │
                    │  orchestrator query │
                    └─────────────────────┘
```

**CLI Concept:**
```bash
# Search learnings
orchestrator query "authentication timeout issues"

# Get context for planning
orchestrator plan-context "add rate limiting"

# Find relevant PRDs
orchestrator prd search "user notifications"
```

**Tasks (if pursued):**
- [ ] Research: Evaluate embedding models (cost, quality, local vs API)
- [ ] Research: Evaluate vector stores (Chroma, pgvector, file-based)
- [ ] Design: Define what gets indexed and when
- [ ] Design: Define privacy/security boundaries
- [ ] Prototype: Index LEARNINGS.md + query interface
- [ ] Evaluate: Is the complexity worth it for typical use cases?

**Decision Point:** This item is exploratory. Before implementing, need to validate that:
1. The use cases are real (not hypothetical)
2. Simpler solutions (grep, ctrl+f) aren't sufficient
3. The infrastructure cost is justified

---

#### WF-035: Zero-Human Mode - Remove Manual Gate Blockers
**Status:** ✅ **RECOMMEND** - Critical for autonomous AI workflows
**Complexity:** MEDIUM (config system + gate logic + test automation)
**Priority:** HIGH - Blocks fully autonomous operation
**Source:** Session analysis (2026-01-11) - Manual gates incompatible with zero-human review workflows

**Problem Statement:**
The workflow is designed for zero-human code review (5 AI models replace human judgment), but contains manual gates that block autonomous operation:

1. **PLAN phase:** `user_approval` manual gate blocks workflow start
2. **VERIFY phase:** `manual_smoke_test` requires human intervention
3. **VERIFY phase:** Visual regression test underspecified (no tooling guidance)
4. **REVIEW phase:** Single missing API key blocks entire workflow (brittle)
5. **No supervision mode config:** Can't distinguish autonomous vs supervised workflows

**Current Blocking Flow:**
```
PLAN → [MANUAL GATE: user_approval] → EXECUTE → REVIEW → [MANUAL GATE: manual_smoke_test] → LEARN
        ↑ Blocks autonomous start                          ↑ Blocks autonomous completion
```

**Real-World Impact:**
- Zero-human workflows cannot complete without human intervention
- Agent must wait indefinitely at manual gates
- Visual regression tests fail because agents don't know what tooling to use
- Missing any of 3 API keys (GEMINI, OPENAI, XAI) blocks entire workflow
- No way to configure "supervised" vs "autonomous" operation modes

**Design Philosophy - Why Gold-Plating is Justified:**

In traditional CI/CD: `AI implements → Human reviews → Merge`

In zero-human workflow: `AI implements → ??? → Merge`

**The 5-model review and test redundancy aren't overkill - they're replacing human judgment.** Multi-model reviews are essential safety infrastructure. Test redundancy (EXECUTE + VERIFY) is defense-in-depth (post-review regression checks).

However, manual gates defeat the entire zero-human premise.

**Proposed Solution:**

**Phase 1: Supervision Mode Configuration**

Add `supervision_mode` setting to workflow.yaml:

```yaml
settings:
  # Supervision mode: how much human oversight is required
  # - zero_human: Fully autonomous, skip manual gates with warning
  # - supervised: Require human approval at manual gates (traditional)
  # - hybrid: Risk-based gates with timeout fallback
  supervision_mode: "zero_human"  # or "supervised" or "hybrid"

  # Hybrid mode settings (only used if supervision_mode: hybrid)
  hybrid_mode:
    gate_timeout: 300  # 5 minutes - auto-skip after timeout
    auto_approve_if:
      - risk_level: "low"
      - files_changed: "<= 5"
      - no_breaking_changes: true
    require_human_if:
      - risk_level: "high"
      - touches_auth: true
      - database_migrations: true
```

**Phase 2: Automated Smoke Testing**

Add smoke test command to settings (like `test_command`):

```yaml
settings:
  # Smoke test command - lightweight runtime verification
  # Examples:
  #   Web: "playwright test tests/smoke/"
  #   CLI: "myapp --version && myapp validate"
  #   API: "curl http://localhost:8000/health"
  smoke_test_command: "pytest tests/smoke/ -v --tb=short"
```

Update VERIFY phase:

```yaml
- id: "automated_smoke_test"
  name: "Automated Smoke Test"
  description: "Run automated smoke test suite to verify core functionality works"
  verification:
    type: "command"
    command: "{{smoke_test_command}}"
    expect_exit_code: 0
  skip_conditions: ["no_smoke_tests_defined"]
  notes:
    - "[zero-human] Replaces manual smoke test with automation"
    - "[web] Use Playwright: playwright test tests/smoke/"
    - "[cli] Test core commands: myapp --version && myapp run --dry-run"
    - "[api] Test health endpoints: curl localhost:8000/health"
```

**Phase 3: Visual Regression Test Tooling**

Specify Playwright as standard tooling:

```yaml
- id: "visual_regression_test"
  name: "Visual Regression Test (Playwright)"
  description: "Automated visual regression testing using Playwright screenshots"
  verification:
    type: "command"
    command: "playwright test --grep @visual"
  skip_conditions: ["no_ui_changes", "backend_only", "api_only"]
  notes:
    - "[tool] Uses Playwright for screenshot capture and comparison"
    - "[baseline] First run: playwright test --update-snapshots"
    - "[compare] Subsequent runs compare to baseline in tests/screenshots/"
    - "[ci] In CI mode, never update snapshots (fail on mismatch)"
    - "[threshold] Configure pixel diff threshold in playwright.config.ts"
    - "[setup] Guide: https://playwright.dev/docs/test-snapshots"
```

**Phase 4: Review Fallback & Graceful Degradation**

Add minimum review threshold and fallback models:

```yaml
settings:
  reviews:
    enabled: true
    minimum_required: 3  # At least 3 of 5 must succeed

    # Fallback chain when primary models unavailable
    fallbacks:
      codex:
        - "openai/gpt-5.1"           # OpenRouter fallback
        - "anthropic/claude-opus-4"  # Secondary fallback
      gemini:
        - "google/gemini-3-pro"      # OpenRouter fallback
        - "anthropic/claude-opus-4"  # Secondary fallback
      grok:
        - "x-ai/grok-4.1"            # OpenRouter fallback
        - "anthropic/claude-opus-4"  # Secondary fallback

    # Behavior when minimum not met
    on_insufficient_reviews:
      action: "warn"  # or "block"
      message: "Only {count} of {minimum} reviews completed. Proceeding with warning."
```

**Phase 5: Gate Skipping Logic**

Update manual gates to respect supervision mode:

```yaml
# PLAN phase
- id: "user_approval"
  name: "Get User Approval"
  description: "User must approve the plan before execution (skipped in zero_human mode)"
  verification:
    type: "manual_gate"
    skip_if_supervision_mode: ["zero_human"]
    auto_approve_after: 300  # 5 min (hybrid mode only)
  notes:
    - "[zero-human] Auto-skipped with warning logged"
    - "[supervised] Requires explicit approval"
    - "[hybrid] Auto-approves after timeout for low-risk changes"
```

**Implementation Tasks:**

**Phase 1: Configuration (2 hours)** - COMPLETE (v2.8.0)
- [x] Add `supervision_mode` to workflow schema
- [x] Add validation for supervision_mode values
- [x] Update StateManager to read supervision_mode setting (WorkflowEngine.settings property)
- [ ] **REMAINING: Add `--supervision-mode` CLI flag for overrides**

**Phase 2: Gate Logic (3 hours)** - MOSTLY COMPLETE (v2.8.0)
- [x] Update manual gate handler to check supervision_mode
- [x] Log warnings when gates are auto-skipped
- [ ] **REMAINING: Implement timeout logic for hybrid mode** (currently conservative - blocks like supervised)
- [ ] **REMAINING: Add risk-based auto-approval for hybrid mode**

**Phase 3: Smoke Test Framework (2 hours)** - PARTIALLY COMPLETE
- [x] Add `smoke_test_command` to settings schema (v2.8.0)
- [ ] **REMAINING: Update VERIFY phase: replace manual_smoke_test with automated_smoke_test**
- [ ] **REMAINING: Add example smoke tests to tests/smoke/ directory**
- [ ] **REMAINING: Document smoke test patterns (web/CLI/API) in notes**

**Phase 4: Visual Testing Docs (1 hour)** - MOSTLY COMPLETE
- [x] Update visual_regression_test with Playwright guidance (workflow.yaml)
- [x] Add detailed notes: baseline workflow, CI behavior, threshold config (workflow.yaml)
- [ ] **REMAINING: Create docs/VISUAL_TESTING.md guide**
- [ ] **REMAINING: Add example Playwright visual test to tests/**

**Phase 5: Review Fallbacks (4 hours)** - PARTIALLY COMPLETE (v2.8.0-v2.8.1)
- [x] Add `minimum_required` and `fallbacks` to review config schema (v2.8.0)
- [x] Track which models were used (primary vs fallback) in logs (v2.8.1 - ReviewResult.was_fallback)
- [x] Add ReviewThresholdError exception for block mode (v2.8.1)
- [ ] **REMAINING: Implement fallback chain logic in api_executor.py** (try primary → fallback1 → fallback2)
- [ ] **REMAINING: Add minimum_required threshold check in ReviewRouter.execute_all_reviews()**
- [ ] **REMAINING: Wire on_insufficient_reviews behavior (warn logs warning, block raises ReviewThresholdError)**

**Phase 6: Integration & Testing (4 hours)** - PARTIALLY COMPLETE
- [x] Update both workflow.yaml and src/default_workflow.yaml (v2.8.0)
- [x] Add tests for supervision_mode logic (v2.8.0 - 34 tests)
- [x] Add tests for review fallback schema/fields (v2.8.1 - 16 tests)
- [ ] **REMAINING: Add tests for fallback chain execution logic**
- [x] Dogfood: Run full workflow in zero_human mode (ongoing)
- [x] Update CLAUDE.md with supervision_mode usage (v2.8.0)

**Complexity vs Benefit Tradeoff:**

| Factor | Current (Manual Gates) | With Zero-Human Mode |
|--------|------------------------|---------------------|
| Complexity | LOW (manual gates simple) | MEDIUM (config + logic + fallbacks) |
| Autonomous Operation | ❌ Blocked by gates | ✅ Fully autonomous |
| Supervision Flexibility | ❌ One-size-fits-all | ✅ Three modes (zero/supervised/hybrid) |
| Review Reliability | ❌ Single point of failure (API keys) | ✅ Graceful degradation (fallbacks) |
| Visual Test Guidance | ❌ Vague ("capture screenshots") | ✅ Specific (Playwright + workflow) |
| Smoke Test Automation | ❌ Manual gate | ✅ Automated command |

**Current Evidence:**
- ✅ Multi-model review justified (replaces human judgment in zero-human workflows)
- ✅ Test redundancy justified (post-review regression checks are defense-in-depth)
- ✅ Manual gates block autonomous operation (fundamental incompatibility)
- ✅ API key brittleness is single point of failure (any missing key blocks workflow)
- ✅ Visual test underspecification prevents agent execution
- ✅ Zero-human workflow is the stated design goal (not traditional CI/CD)

**YAGNI Check:**
- Solving a problem we **actually have** (manual gates block stated use case)
- Would **NOT** be okay without this (zero-human workflows are core value prop)
- Current solution **fails by design** (manual gates defeat zero-human premise)
- Gold-plating (5 models, test redundancy) is **justified** in zero-human context

**Recommendation:** ✅ **IMPLEMENT** - High priority, phased approach

**Reasoning:**
The workflow is explicitly designed for zero-human code review with 5 AI models replacing human judgment. The multi-model reviews and test redundancy are essential safety infrastructure, not overkill. However, manual gates create a fundamental contradiction: "zero-human workflow that requires humans." This must be fixed for the orchestrator to deliver on its core value proposition. The implementation is medium complexity (config system + gate logic + fallback chains) but high value (enables autonomous operation). Phased approach allows incremental delivery.

**Success Criteria:**
- [ ] Workflow completes end-to-end in `supervision_mode: zero_human` without human intervention
- [ ] Missing API keys trigger fallback models (workflow continues, not blocked)
- [ ] Smoke tests run automatically in VERIFY phase
- [ ] Visual regression tests have clear Playwright guidance
- [ ] At least 3 dogfooding sessions validate autonomous operation
- [ ] All three supervision modes (zero_human, supervised, hybrid) tested

**Non-Goals (Explicitly Out of Scope):**
- Production deployment phases (covered in WF-036)
- Multi-environment management (staging/prod)
- Health checks and rollback automation
- Observability and monitoring integration

---

#### WF-036: Production Deployment Readiness
**Status:** ⚠️ **DEFER** - Future enhancement, not blocking current work
**Complexity:** HIGH (multi-environment, deployment, rollback, health checks)
**Priority:** LOW (deferred until production deployment needed)
**Source:** Session analysis (2026-01-11) - Prepare for production code workflows

**Problem Statement:**
The workflow currently stops at "commit to main" with no deployment capabilities. For production code, this is insufficient:

1. **No deployment phases** - Workflow ends after commit (no staging, no production deploy)
2. **No environment management** - Cannot deploy to staging, QA, or production environments
3. **No health checks** - Cannot verify deployment succeeded
4. **No rollback automation** - If deploy fails, manual intervention required
5. **No observability** - No monitoring, alerting, or deployment tracking

**Comparison to Industry CI/CD:**

| Feature | Orchestrator (Current) | Industry CI/CD | Gap |
|---------|----------------------|----------------|-----|
| **Build artifacts** | ❌ None | ✅ Docker images, packages | Need artifact versioning |
| **Environment progression** | ❌ Just commit | ✅ Dev→Staging→Prod | Need multi-env support |
| **Deployment** | ❌ None | ✅ K8s, VPS, cloud | Need deploy phase |
| **Health checks** | ❌ None | ✅ Automated | Need verification |
| **Rollback** | ❌ Manual | ✅ Auto on failure | Need rollback automation |
| **Observability** | ❌ None | ✅ Metrics, logs, traces | Need monitoring hooks |
| **Planning** | ✅ Built-in | ❌ External | Orchestrator advantage |
| **AI Review** | ✅ 5 models | ❌ Human only | Orchestrator advantage |
| **Learning Loop** | ✅ Systematic | ❌ Ad-hoc | Orchestrator advantage |

**Key Insight:**
Industry CI/CD is more mature for deployment, but orchestrator is better for development (planning, AI review, learning). **The solution is integration, not replacement.**

**Proposed Solution:**

**Phase 1: Deployment Phase Structure**

Add two new phases after VERIFY:

```yaml
# Phase 5: DEPLOY_STAGING
- id: "DEPLOY_STAGING"
  name: "Deploy to Staging Environment"
  description: "Deploy to staging for integration testing and smoke tests"
  items:
    - id: "build_artifacts"
      name: "Build Deployment Artifacts"
      description: "Build Docker images, packages, or binaries for deployment"
      verification:
        type: "command"
        command: "{{build_command}}"
        expect_exit_code: 0

    - id: "deploy_staging"
      name: "Deploy to Staging"
      description: "Deploy to staging environment using configured deployment method"
      verification:
        type: "command"
        command: "{{deploy_staging_command}}"
        expect_exit_code: 0
      notes:
        - "[k8s] kubectl apply -f k8s/staging/"
        - "[docker] docker-compose -f docker-compose.staging.yml up -d"
        - "[vps] rsync + systemctl restart"

    - id: "staging_health_check"
      name: "Staging Health Check"
      description: "Verify staging deployment is healthy"
      verification:
        type: "command"
        command: "{{health_check_command}}"
        expect_exit_code: 0
        retry: 3
        retry_delay: 10
      notes:
        - "[web] curl https://staging.example.com/health"
        - "[api] curl https://api-staging.example.com/v1/health"

    - id: "staging_smoke_tests"
      name: "Staging Smoke Tests"
      description: "Run smoke tests against staging environment"
      verification:
        type: "command"
        command: "ENVIRONMENT=staging {{smoke_test_command}}"
        expect_exit_code: 0

# Phase 6: DEPLOY_PRODUCTION
- id: "DEPLOY_PRODUCTION"
  name: "Deploy to Production"
  description: "Deploy to production with health checks and rollback capability"
  items:
    - id: "production_approval"
      name: "Production Deployment Approval"
      description: "Human approval required before production deployment"
      verification:
        type: "manual_gate"
        skip_if_supervision_mode: []  # Never skip for production
      notes:
        - "[critical] Always requires human approval, even in zero_human mode"
        - "[review] Review staging test results before approving"

    - id: "deploy_production"
      name: "Deploy to Production"
      description: "Deploy using blue/green or canary strategy"
      verification:
        type: "command"
        command: "{{deploy_production_command}}"
        expect_exit_code: 0
      notes:
        - "[strategy] Blue/green: zero-downtime switchover"
        - "[strategy] Canary: gradual rollout (5% → 50% → 100%)"
        - "[k8s] kubectl apply -f k8s/production/"

    - id: "production_health_check"
      name: "Production Health Check"
      description: "Verify production deployment is healthy"
      verification:
        type: "command"
        command: "{{health_check_command}}"
        expect_exit_code: 0
        retry: 5
        retry_delay: 30
        on_failure: "trigger_rollback"
      notes:
        - "[critical] Failure triggers automatic rollback"
        - "[metrics] Check response time, error rate, p95 latency"

    - id: "production_smoke_tests"
      name: "Production Smoke Tests"
      description: "Run smoke tests against production"
      verification:
        type: "command"
        command: "ENVIRONMENT=production {{smoke_test_command}}"
        expect_exit_code: 0
        on_failure: "trigger_rollback"

    - id: "monitor_deployment"
      name: "Monitor Deployment"
      description: "Watch metrics for 5 minutes, rollback on anomalies"
      verification:
        type: "command"
        command: "{{monitor_command}}"
        timeout: 300
        on_failure: "trigger_rollback"
      notes:
        - "[metrics] Watch error rate, latency, throughput"
        - "[alerts] Set up alerts for anomalies"
        - "[duration] Monitor for 5 min post-deploy"
```

**Phase 2: Environment Configuration**

```yaml
settings:
  # Environment-specific configuration
  environments:
    staging:
      url: "https://staging.example.com"
      deploy_command: "kubectl apply -f k8s/staging/"
      health_check_url: "https://staging.example.com/health"

    production:
      url: "https://example.com"
      deploy_command: "kubectl apply -f k8s/production/"
      health_check_url: "https://example.com/health"
      deployment_strategy: "blue_green"  # or "canary"
      rollback_on_failure: true

  # Deployment settings
  deployment:
    artifact_type: "docker"  # or "binary", "package"
    build_command: "docker build -t myapp:{{version}} ."
    health_check_command: "curl -f {{env.health_check_url}}"
    monitor_command: "scripts/monitor_deployment.sh"
    rollback_command: "kubectl rollout undo deployment/myapp"
```

**Phase 3: Rollback Automation**

Add rollback capability:

```bash
# Automatic rollback on health check failure
orchestrator verify-deployment --environment production
  ↓
  [Health check fails]
  ↓
  [Trigger rollback]
  ↓
  [Verify rollback succeeded]
  ↓
  [Alert user]

# Manual rollback command
orchestrator rollback --environment production --to-version v1.2.3
```

**Phase 4: Integration with Existing CI/CD**

**Hybrid Approach (Recommended):**

```yaml
# Use orchestrator for development, CI/CD for deployment
PLAN (orchestrator) →
EXECUTE (orchestrator) →
REVIEW (orchestrator AI) →
VERIFY (orchestrator) →
COMMIT →
[GitHub Actions triggers] →
BUILD (GitHub Actions) →
DEPLOY_STAGING (GitHub Actions) →
DEPLOY_PRODUCTION (GitHub Actions) →
LEARN (orchestrator)
```

**Full Orchestrator Approach:**
```yaml
# Orchestrator handles everything
PLAN → EXECUTE → REVIEW → VERIFY →
DEPLOY_STAGING → DEPLOY_PRODUCTION → LEARN
```

**When to Use Which:**
- **Hybrid:** You have existing CI/CD (GitHub Actions, GitLab CI)
- **Full:** Green field project or orchestrator-native deployment preferred

**Implementation Tasks:**

**Phase 1: Deployment Phases (8 hours)**
- [ ] Add DEPLOY_STAGING phase to workflow schema
- [ ] Add DEPLOY_PRODUCTION phase to workflow schema
- [ ] Add environment configuration to settings
- [ ] Update StateManager to support deployment phases

**Phase 2: Health Checks & Retry Logic (4 hours)**
- [ ] Implement retry logic for verification commands
- [ ] Add `on_failure` handlers (trigger_rollback)
- [ ] Implement health check verification with retries
- [ ] Add timeout support for long-running verifications

**Phase 3: Rollback Automation (6 hours)**
- [ ] Implement `orchestrator rollback` command
- [ ] Add rollback_command to settings
- [ ] Implement automatic rollback on health check failure
- [ ] Add rollback verification (ensure rollback succeeded)
- [ ] Add alerting/notification on rollback

**Phase 4: Artifact Management (4 hours)**
- [ ] Add artifact versioning (semantic versioning)
- [ ] Track deployed versions per environment
- [ ] Add `orchestrator deployments list` command
- [ ] Store deployment history in state

**Phase 5: Monitoring Integration (4 hours)**
- [ ] Add monitor_command support
- [ ] Implement post-deploy monitoring window
- [ ] Add metrics threshold checking
- [ ] Integrate with monitoring systems (Prometheus, Datadog)

**Phase 6: Documentation & Examples (4 hours)**
- [ ] Create docs/DEPLOYMENT.md guide
- [ ] Add example deployment configs (K8s, Docker, VPS)
- [ ] Add example health check scripts
- [ ] Add example rollback scripts
- [ ] Document hybrid vs full orchestrator approaches

**Complexity vs Benefit Tradeoff:**

| Factor | Current (No Deployment) | With Deployment Phases |
|--------|------------------------|----------------------|
| Complexity | LOW (stops at commit) | HIGH (multi-env, health checks, rollback) |
| Production Readiness | ❌ Not suitable | ✅ Production-ready |
| Deployment Safety | ⚠️ Manual, error-prone | ✅ Automated, verified |
| Rollback Capability | ❌ Manual git revert | ✅ Automated rollback |
| Environment Management | ❌ None | ✅ Staging → Production |
| Implementation Effort | N/A | 30+ hours |

**Current Evidence:**
- ❌ User stated "not deploying to production yet"
- ❌ No production deployment requirements identified
- ❌ Current workflow (commit to main) works for current use case
- ✅ Industry CI/CD has mature deployment patterns (can learn from)
- ⚠️ Good to design now, implement later

**YAGNI Check:**
- **NOT** solving a problem we currently have
- **Would be completely fine** without this for 6-12+ months
- Current solution (commit to main) **works fine** for current use case
- Premature implementation would be over-engineering

**Recommendation:** ⚠️ **DEFER** - Design documented, implement when needed

**Reasoning:**
User explicitly stated "not deploying to production yet" and asked to put this on roadmap "for later." The design is valuable to document now (so we know what production-ready looks like), but implementation should wait until there's an actual production deployment need. This is 30+ hours of engineering work that would deliver zero value today. The orchestrator's current strengths (planning, AI review, learning) don't depend on deployment phases. When production deployment is needed, this design provides a clear implementation path.

**Trigger Conditions for Implementation:**
- User has production environment requiring deployment
- Current "commit to main" workflow becomes insufficient
- User requests deployment phase implementation
- At least 6 months of successful non-production usage

**Success Criteria (When Implemented):**
- [ ] Deploy to staging, run tests, deploy to production in single workflow
- [ ] Automatic rollback on health check failure
- [ ] Environment-specific configuration (staging vs production)
- [ ] Deployment history tracking
- [ ] Integration with existing CI/CD (hybrid mode)
- [ ] Blue/green or canary deployment support

**Non-Goals (Even When Implemented):**
- Multi-region deployment
- Auto-scaling configuration
- Infrastructure-as-code generation
- Cost optimization
- Performance monitoring (beyond health checks)

---

