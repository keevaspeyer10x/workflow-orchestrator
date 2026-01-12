# Implementation Plan: CORE-024 & WF-034

## Overview

Implementing two high-priority roadmap items:
- **CORE-024**: Session Transcript Logging with Secret Scrubbing
- **WF-034**: Post-Workflow Self-Assessment & Adherence Validation

**Execution Strategy:** Parallel (2 agents) + Sequential (Phase 2)

**Parallel Execution Decision:**
- **Agent 1:** CORE-024 (full implementation) - 4-6 hours
- **Agent 2:** WF-034 Phase 0+1+3+4 (excluding validation) - 3-4 hours
- **Sequential:** WF-034 Phase 2 (validation) after CORE-024 complete - 2-3 hours
- **Time Savings:** 30-40% reduction (4-5 hours saved vs sequential)

**Rationale:**
- CORE-024 and WF-034 Phase 0+1+3+4 are independent (separate code paths, no shared files)
- Session log format specified in this plan (both agents work from same spec)
- Only WF-034 Phase 2 depends on CORE-024 (needs session transcripts for validation)
- Low coordination overhead, high time savings
- Minimal conflict risk (Phase 0+1 touch workflow.yaml only, Phase 3+4 are new files)

---

## CORE-024: Session Transcript Logging

### Goal
Automatically log all orchestrator session transcripts with secret scrubbing to enable debugging and pattern analysis.

### User Decisions
- **Scope:** Full implementation (basic logging + analysis commands)
- **Storage:** `.orchestrator/sessions/` directory
- **Secret Scrubbing:** Hybrid approach (pattern-based + secrets manager integration)

### Architecture

```
src/
  session_logger.py          # New: Core logging & scrubbing logic
  secrets.py                 # Existing: Extend for scrubbing integration
  cli.py                     # Extend: Add session commands

.orchestrator/
  sessions/                  # New: Session transcript storage
    2026-01-12_14-32-15_core-024-wf-034.log
    2026-01-12_16-45-22_bugfix.log
```

### Components

#### 1. Session Logger (`src/session_logger.py`)
**Responsibilities:**
- Capture session transcripts (commands, outputs, errors)
- Apply secret scrubbing before writing to disk
- Provide session metadata (start time, end time, duration, workflow ID)
- Support session naming from task description

**Key Classes:**
```python
class SessionLogger:
    """Manages session transcript logging with automatic secret scrubbing."""

    def __init__(self, session_dir: Path, secrets_manager: SecretsManager)
    def start_session(self, task_description: str) -> SessionContext
    def log_event(self, event_type: str, data: dict)
    def end_session(self, status: str)

class SessionContext:
    """Tracks current session state."""
    session_id: str
    task_description: str
    start_time: datetime
    log_file: Path
```

**Secret Scrubbing Strategy:**
1. **Pattern-based** (regex for common patterns):
   - API keys: `[A-Za-z0-9_-]{32,}`
   - Tokens: `Bearer [A-Za-z0-9._-]+`
   - URLs with credentials: `https://user:pass@...`
   - Common env var patterns: `API_KEY=...`, `TOKEN=...`, `SECRET=...`

2. **SecretsManager integration**:
   - Query known secrets from secrets sources
   - Scrub exact matches
   - Redact format: `[REDACTED:SECRET_NAME]`

3. **Safe by default**:
   - Scrub before writing (never write secrets to disk)
   - Log scrubbing stats (X secrets redacted)

#### 2. Session Commands (extend `src/cli.py`)

**New commands:**
```bash
# List all sessions
orchestrator sessions list [--last N] [--workflow WORKFLOW_ID]

# View a session transcript
orchestrator sessions view <session_id>

# Analyze session patterns (FULL IMPLEMENTATION)
orchestrator sessions analyze [--last N] [--days DAYS]
  - Workflow completion rate
  - Most common failure points
  - Average session duration
  - Error frequency by type
  - Phase completion statistics
```

**Session Analysis Output:**
```
Session Analysis (Last 30 days)
================================
Total Sessions: 45
Workflow Completion Rate: 67% (30/45)

Most Common Failure Point: REVIEW phase (18 failures)
  - Context compaction: 12 sessions
  - Review API errors: 4 sessions
  - Manual abandonment: 2 sessions

Average Session Duration: 45 minutes
  - PLAN: 8 min
  - EXECUTE: 22 min
  - REVIEW: 10 min
  - VERIFY: 3 min
  - LEARN: 2 min

Top Errors:
  1. Review API timeout (15 occurrences)
  2. Git conflict resolution failed (8 occurrences)
  3. Test execution timeout (5 occurrences)
```

#### 3. Integration Points

**Engine Integration (`src/engine.py`):**
- Initialize SessionLogger on workflow start
- Log workflow events (phase transitions, item completions, errors)
- End session on workflow finish/abandon

**CLI Integration:**
- Capture all command invocations
- Log command outputs
- Track user interactions

### Implementation Steps

1. **Create SessionLogger** (`src/session_logger.py`)
   - Implement SessionLogger class
   - Implement secret scrubbing (pattern-based + SecretsManager)
   - Add session metadata tracking
   - Write comprehensive unit tests

2. **Extend SecretsManager** (`src/secrets.py`)
   - Add `get_all_secret_values()` method for scrubbing
   - Add secret name resolution (value → name mapping)

3. **Add Session Commands** (`src/cli.py`)
   - `sessions list` - List all sessions with metadata
   - `sessions view` - Display a session transcript
   - `sessions analyze` - Analyze session patterns and statistics
   - Add command parsers and help text

4. **Integrate with WorkflowEngine** (`src/engine.py`)
   - Initialize SessionLogger on workflow start
   - Log workflow events (phase changes, completions, errors)
   - End session on finish/abandon

5. **Add Session Analysis** (`src/session_logger.py`)
   ```python
   class SessionAnalyzer:
       """Analyzes session patterns and generates statistics."""

       def analyze_sessions(sessions: List[SessionContext]) -> AnalysisReport
       def completion_rate(sessions) -> float
       def failure_points(sessions) -> Dict[str, int]
       def duration_stats(sessions) -> DurationStats
       def error_frequency(sessions) -> List[Tuple[str, int]]
   ```

6. **Update .gitignore**
   - Add `.orchestrator/sessions/` to gitignore
   - Update CLAUDE.md with session logging documentation

### Testing Strategy

**Unit Tests:**
- Secret scrubbing accuracy (pattern-based and SecretsManager-based)
- Session file creation and naming
- Metadata tracking
- Command parsing

**Integration Tests:**
- Full workflow run with session logging enabled
- Session analysis on sample data
- Multi-session tracking

**Manual Tests:**
- Verify no secrets in session logs
- Check session analysis output accuracy
- Validate session listing and viewing

---

## WF-034: Post-Workflow Self-Assessment

### Goal
Ensure AI agents follow orchestrator workflow recommendations through planning guidance, self-assessment checklists, and automated validation.

### User Decisions
- **Scope:** All 4 phases (full implementation)
- **Automation:** Include automated adherence validation

### Architecture

```
workflow.yaml               # Extend: Add Phase 0 + Phase 1 items
src/
  adherence_validator.py    # New: Phase 2 automated validation
  feedback_capture.py       # New: Phase 3 feedback system
cli.py                      # Extend: Add validation commands
```

### Phases

#### Phase 0: Pre-Execution Planning Guidance
**Implementation:** Extend `workflow.yaml` PLAN phase

Add new required item:
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

**Result:** Agents see explicit guidance BEFORE implementation, preventing sequential execution mistakes.

#### Phase 1: Self-Assessment Checklist
**Implementation:** Extend `workflow.yaml` LEARN phase

Add new required item:
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

**Result:** Agents explicitly validate adherence at end of workflow.

#### Phase 2: Automated Validation
**Implementation:** New module `src/adherence_validator.py`

**Command:**
```bash
orchestrator validate-adherence [--workflow WORKFLOW_ID]
```

**Validation Checks:**
1. **Plan agent usage** - Detect Task calls with `subagent_type="Plan"` before implementation phases
2. **Parallel execution** - Detect multiple Task calls in SINGLE message (good) vs sequential messages (bad)
3. **Third-party reviews** - Check for review_completed events with external models (not DEFERRED)
4. **Agent verification** - Count Read tool calls immediately after Task completions
5. **Status checks** - Count `orchestrator status` calls frequency
6. **Required items** - Validate no required items skipped without reason
7. **Learnings detail** - Check length/detail of `document_learnings` notes

**Key Classes:**
```python
class AdherenceValidator:
    """Validates workflow adherence using session transcripts."""

    def __init__(self, session_logger: SessionLogger, workflow_log: Path)
    def validate(self, workflow_id: str) -> AdherenceReport
    def check_plan_agent_usage() -> bool
    def check_parallel_execution() -> ParallelExecutionResult
    def check_reviews() -> ReviewAdherenceResult
    def check_agent_verification() -> VerificationResult
    def check_status_frequency() -> StatusCheckResult
    def check_required_items() -> RequiredItemsResult
    def check_learnings_detail() -> LearningsResult

class AdherenceReport:
    """Report of adherence validation results."""
    workflow_id: str
    score: float  # 0.0-1.0
    checks: Dict[str, CheckResult]
    critical_issues: List[str]
    warnings: List[str]
    recommendations: List[str]
```

**Output Format:**
```
Workflow Adherence Validation
==============================
Workflow: wf_95ec1970
Task: Implement PRD-007 parallel agents

✓ Plan agent: Used before implementation
✗ Parallel execution: FAIL - Agents launched sequentially (3 separate messages)
✗ Third-party reviews: MISSING - No external model reviews detected
✓ Agent verification: Files read after agent completion (5 verifications)
✓ Status checks: Frequent (23 status checks during workflow)
✓ Required items: All completed (0 unjustified skips)
⚠ Learnings: Brief (3 learnings documented, consider more detail)

ADHERENCE SCORE: 57% (4/7 criteria met)
CRITICAL ISSUES: 2 (parallel execution, reviews)

Recommendations:
1. Launch parallel agents in SINGLE message with MULTIPLE Task calls
2. Run third-party model reviews for code quality validation
3. Add more detailed learnings in LEARN phase
```

#### Phase 3: Feedback Capture Template
**Implementation:** New module `src/feedback_capture.py`

**Command:**
```bash
orchestrator feedback [--workflow WORKFLOW_ID] [--interactive]
```

**Structured Feedback Questions:**
1. Did you use multi-agents? (yes/no/not-recommended)
2. What went well? (1-2 sentences)
3. What challenges did you encounter? (1-2 sentences)
4. What could be improved? (1-2 sentences)
5. Did you run third-party model reviews? (yes/no/deferred)
6. Additional notes

**Output:** Append to `.workflow_feedback.jsonl` (structured for analysis)

**Feedback Schema:**
```json
{
  "workflow_id": "wf_95ec1970",
  "task": "Implement PRD-007",
  "timestamp": "2026-01-12T14:30:00Z",
  "multi_agents_used": true,
  "what_went_well": "Parallel execution reduced time by 60%",
  "challenges": "Coordination overhead between agents",
  "improvements": "Better task decomposition in PLAN phase",
  "reviews_performed": true,
  "notes": "First time using multi-agents successfully"
}
```

**Integration with Analysis:**
- Session analyzer can correlate feedback with adherence scores
- Pattern detection: workflows with high adherence → better feedback
- Roadmap suggestions from common improvement themes

#### Phase 4: Workflow Enforcement for Orchestrator Itself
**Implementation:** New workflow template `orchestrator-meta.yaml`

**Concept:** Dogfooding - Orchestrator enforces its own usage

**Structure:**
```yaml
name: "Orchestrator Meta-Workflow"
description: "Enforce orchestrator best practices when using orchestrator"

phases:
  - id: "PLAN"
    items:
      - id: "check_parallel_opportunity"
        name: "Assess if tasks can be parallelized"
        required: true
        validation:
          enforce: true  # Block advancement if not completed

  - id: "REVIEW"
    items:
      - id: "third_party_reviews"
        name: "Run multi-model code reviews"
        required: true
        validation:
          enforce: true

  - id: "VERIFY"
    items:
      - id: "validate_adherence"
        name: "Run adherence validation"
        required: true
        command: "orchestrator validate-adherence"
```

**Usage:**
```bash
# Use meta-workflow for orchestrator development
orchestrator start "Implement CORE-024" --workflow orchestrator-meta.yaml
```

**Result:** When working on orchestrator itself, the tool enforces its own best practices.

### Implementation Steps

1. **Phase 0: Update workflow.yaml**
   - Add `parallel_execution_check` item to PLAN phase
   - Update bundled `src/default_workflow.yaml`
   - Document in CLAUDE.md

2. **Phase 1: Update workflow.yaml**
   - Add `workflow_adherence_check` item to LEARN phase
   - Update bundled `src/default_workflow.yaml`

3. **Phase 2: Implement AdherenceValidator**
   - Create `src/adherence_validator.py`
   - Implement validation checks (7 criteria)
   - Add `validate-adherence` command to CLI
   - Integrate with session transcripts (depends on CORE-024)
   - Write comprehensive tests

4. **Phase 3: Implement FeedbackCapture**
   - Create `src/feedback_capture.py`
   - Add `feedback` command to CLI
   - Implement interactive prompts
   - Define feedback schema
   - Write to `.workflow_feedback.jsonl`

5. **Phase 4: Create Meta-Workflow**
   - Create `orchestrator-meta.yaml` template
   - Add enforcement validation hooks
   - Document usage in CLAUDE.md
   - Test dogfooding scenario

6. **Integration**
   - Link Phase 2 (validation) with LEARN phase
   - Auto-run `validate-adherence` at workflow completion
   - Include adherence score in workflow summary

### Testing Strategy

**Phase 0 & 1 Testing:**
- Manual verification that new items appear in workflow
- Test agent responses to planning guidance

**Phase 2 Testing:**
- Unit tests for each validation check
- Integration test with mock session transcripts
- Test adherence score calculation
- Test output formatting

**Phase 3 Testing:**
- Unit tests for feedback capture
- Integration test for JSONL writing
- Test interactive prompts
- Validate feedback schema

**Phase 4 Testing:**
- Full dogfooding test (use orchestrator-meta.yaml for a real task)
- Validate enforcement blocks advancement
- Test meta-workflow completion

---

## Integration Between CORE-024 and WF-034

**Dependencies:**
- WF-034 Phase 2 (AdherenceValidator) reads session transcripts from CORE-024
- Validation checks parse session logs for Tool use patterns
- Feedback capture can reference session metadata

**Shared Data:**
- Session transcripts contain tool usage patterns
- Workflow logs contain event sequences
- Both feed into learning and improvement cycles

**Implementation Order:**
1. CORE-024 complete → Session transcripts available
2. WF-034 Phase 0-1 → Immediate value (checklists)
3. WF-034 Phase 2 → Uses CORE-024 transcripts for validation
4. WF-034 Phase 3-4 → Full feedback and enforcement system

---

## Success Criteria

### CORE-024 Success Criteria
- [ ] Session transcripts logged to `.orchestrator/sessions/`
- [ ] No secrets appear in session logs (verified by test suite)
- [ ] `orchestrator sessions list` shows all sessions
- [ ] `orchestrator sessions view <id>` displays transcript
- [ ] `orchestrator sessions analyze` generates statistics
- [ ] Session analysis accurately reports completion rates and failure points
- [ ] Session logging adds <5% overhead to workflow execution time

### WF-034 Success Criteria
- [ ] Phase 0: `parallel_execution_check` item appears in PLAN phase
- [ ] Phase 1: `workflow_adherence_check` item appears in LEARN phase
- [ ] Phase 2: `orchestrator validate-adherence` command works
- [ ] Phase 2: Validation correctly detects parallel execution patterns
- [ ] Phase 2: Validation correctly detects missing reviews
- [ ] Phase 3: `orchestrator feedback` captures structured feedback
- [ ] Phase 4: `orchestrator-meta.yaml` enforces orchestrator best practices
- [ ] Adherence validation adds <10% overhead to workflow completion time

### Integration Success Criteria
- [ ] AdherenceValidator can parse session transcripts from CORE-024
- [ ] Validation checks accurately detect tool usage patterns
- [ ] Feedback capture references session metadata
- [ ] Full workflow: start → log → validate → feedback → improve

---

## Timeline Estimate

**CORE-024:** 4-6 hours
- SessionLogger implementation: 2 hours
- Secret scrubbing: 1 hour
- CLI commands: 1 hour
- Session analysis: 1 hour
- Testing: 1 hour

**WF-034:** 6-8 hours
- Phase 0+1 (workflow.yaml): 1 hour
- Phase 2 (AdherenceValidator): 2-3 hours
- Phase 3 (FeedbackCapture): 1-2 hours
- Phase 4 (Meta-workflow): 1 hour
- Testing: 2 hours

**Total:** 10-14 hours

---

## Files to Create/Modify

### New Files
- `src/session_logger.py` - Session logging and scrubbing
- `src/adherence_validator.py` - Workflow adherence validation
- `src/feedback_capture.py` - Structured feedback capture
- `orchestrator-meta.yaml` - Meta-workflow for dogfooding
- `tests/test_session_logger.py` - SessionLogger tests
- `tests/test_adherence_validator.py` - AdherenceValidator tests
- `tests/test_feedback_capture.py` - FeedbackCapture tests

### Modified Files
- `src/cli.py` - Add session and validation commands
- `src/engine.py` - Integrate SessionLogger
- `src/secrets.py` - Extend for scrubbing support
- `workflow.yaml` - Add Phase 0+1 items (project-specific, if exists)
- `src/default_workflow.yaml` - Add Phase 0+1 items (bundled template)
- `.gitignore` - Add `.orchestrator/sessions/`
- `CLAUDE.md` - Document new features

---

## Risk Mitigation

See risk_analysis.md for detailed risk assessment and mitigation strategies.
