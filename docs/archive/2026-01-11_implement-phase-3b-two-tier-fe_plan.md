# Implementation Plan: orchestrator feedback Command

## Overview
Implement WF-034 Phase 3a - simplified feedback system (ship fast, iterate later).

**Phase 3a (NOW):** Single-file feedback capture + basic review
**Phase 3b (LATER):** Split tool/process feedback + sync functionality

This implements the core telemetry loop quickly, then iterates based on real usage.

## Phase 3a Scope (Current Implementation)

**What We're Building:**
- ✅ `orchestrator feedback --auto` - Capture combined feedback (tool + process in one entry)
- ✅ `orchestrator feedback --interactive` - Prompt questions
- ✅ `orchestrator feedback review` - Show patterns and suggest roadmap items
- ✅ Single file: `.workflow_feedback.jsonl`
- ✅ Basic pattern detection (repeated errors, skipped items, learnings)

**What We're Deferring (Phase 3b):**
- ⏸️ Separate tool vs process feedback files
- ⏸️ Anonymization for tool feedback
- ⏸️ `orchestrator feedback sync` - Upload to central repo
- ⏸️ Comprehensive test coverage (manual testing for now)

## Two Types of Feedback (Phase 3b - Future)

### Tool Feedback (About Orchestrator Itself)
**Purpose:** Help orchestrator maintainers improve the tool
**Questions:**
- Did Phase 0 parallel execution check help?
- Were workflow instructions clear?
- Did reviews work correctly?
- Which items are always skipped? (maybe remove them)
- Did orchestrator commands fail/error?

**Storage:** `.workflow_tool_feedback.jsonl` (anonymized, optionally shared)
**Target audience:** Orchestrator maintainers (you)

### Process Feedback (About User's Project/Workflow)
**Purpose:** Help users improve their own workflow
**Questions:**
- What went well in YOUR project?
- What challenges in YOUR codebase?
- Project-specific learnings
- Custom items you added to workflow

**Storage:** `.workflow_process_feedback.jsonl` (stays local, private)
**Target audience:** Repo users (their own use)

## Objectives
1. Add `orchestrator feedback` CLI command with two modes: `--tool` and `--process`
2. Support automatic mode (infer from logs) and interactive mode (prompt user)
3. Save tool feedback to `.workflow_tool_feedback.jsonl` (anonymized, shareable)
4. Save process feedback to `.workflow_process_feedback.jsonl` (local, private)
5. Add `orchestrator feedback review` to analyze both types
6. Add `orchestrator feedback sync` to upload anonymized tool feedback to central repo
7. Respect `ORCHESTRATOR_SKIP_FEEDBACK=1` opt-out

## Telemetry Pattern (Standard Observability)
Following standard patterns from Sentry, DataDog, etc:
- **Collection**: Each workflow emits feedback event
- **Storage**: `.workflow_feedback.jsonl` (append-only log, like metrics DB)
- **Analysis**: Query recent feedback, identify patterns
- **Action**: Auto-suggest roadmap items based on learnings/errors

**Design Decision: Local JSONL vs External Service (Sentry)**
- **Choice**: Local JSONL files
- **Rationale**:
  - No external dependencies, works offline
  - Privacy-safe (data never leaves machine)
  - Low volume (1 event/workflow, not thousands/sec)
  - Manual review workflow (not real-time monitoring)
  - Easy aggregation (`cat */.workflow_feedback.jsonl | jq`)
  - Similar to GitHub Copilot/VS Code telemetry approach
- **External services like Sentry** are overkill for this use case (low volume, manual review, privacy concerns)

## Implementation Steps

### 1. Add CLI Command Parsers (src/cli.py)
**feedback capture:**
- `orchestrator feedback --tool` - Capture tool feedback (about orchestrator)
- `orchestrator feedback --process` - Capture process feedback (about user's project)
- Default: captures BOTH in auto mode
- Flags: `--auto` (default from workflow), `--interactive`

**feedback review:**
- `orchestrator feedback review --tool` - Review tool feedback patterns
- `orchestrator feedback review --process` - Review process feedback patterns
- Default: shows both

**feedback sync:**
- `orchestrator feedback sync` - Upload anonymized tool feedback to central repo
- Only uploads tool feedback (never process feedback - privacy!)
- Opt-in via `orchestrator config set feedback_sync true`

### 2. Implement cmd_feedback() Function
**Auto Mode (captures BOTH tool and process feedback):**
- Check `ORCHESTRATOR_SKIP_FEEDBACK` env var - exit if set
- Read `.workflow_state.json` for current workflow ID and items
- Read `.workflow_log.jsonl` for workflow events

**Tool Feedback (about orchestrator itself):**
- Phase 0 guidance used? (parallel_execution_check completed)
- Reviews worked? (review_completed with external models, no errors)
- Orchestrator commands failed? (error events with orchestrator in stack trace)
- Items always skipped? (track skip patterns across workflows)
- Workflow phase timings (is PLAN too long? REVIEW too short?)
- Tool version (for compatibility tracking)

**Process Feedback (about user's project):**
- Parallel agents used? (user chose to use them)
- Project-specific errors? (errors NOT from orchestrator)
- Learnings documented? (extract from `document_learnings` notes)
- What went well / challenges? (from interactive mode or learnings)
- Custom workflow items added? (compare to default_workflow.yaml)

- Save to TWO files: `.workflow_tool_feedback.jsonl` + `.workflow_process_feedback.jsonl`

**Interactive Mode:**
- Prompt TWO sets of questions (tool + process)

**Tool Questions (about orchestrator):**
  1. Were Phase 0 parallel execution prompts helpful? (yes/no/didn't-see)
  2. Did third-party reviews work correctly? (yes/no/skipped)
  3. Which workflow items were confusing or unclear? (list or none)
  4. Did any orchestrator commands fail? (yes/no)
  5. Suggestions for improving the tool? (optional)

**Process Questions (about YOUR project):**
  1. Did you use multi-agents? (yes/no/not-applicable)
  2. What went well in this workflow? (1-2 sentences)
  3. What challenges did you face? (1-2 sentences)
  4. What did you learn? (1-2 sentences)
  5. Project-specific improvements? (optional)

### 3. Feedback Entry Formats

**Tool Feedback (.workflow_tool_feedback.jsonl) - ANONYMIZED:**
```json
{
  "timestamp": "2026-01-11T10:30:00Z",
  "workflow_id_hash": "abc123...",
  "orchestrator_version": "2.6.0",
  "repo_type": "python",
  "duration_seconds": 1234,
  "phases": {
    "PLAN": 300,
    "EXECUTE": 600,
    "REVIEW": 200,
    "VERIFY": 100,
    "LEARN": 34
  },
  "phase0_guidance_used": true,
  "reviews_worked": true,
  "orchestrator_errors": ["orchestrator prd spawn: command not found"],
  "items_skipped": ["visual_tests", "update_knowledge_base"],
  "items_skipped_pct": 0.15,
  "confusing_items": [],
  "tool_suggestions": "Phase 0 was helpful",
  "mode": "auto"
}
```

**Process Feedback (.workflow_process_feedback.jsonl) - PRIVATE:**
```json
{
  "timestamp": "2026-01-11T10:30:00Z",
  "workflow_id": "wf_xxx",
  "repo": "github.com/user/my-api",
  "task": "Add user authentication",
  "parallel_agents_used": true,
  "project_errors": ["Connection timeout to test DB", "Terraform state locked"],
  "learnings": "Incremental migrations work better. Feature flags reduced risk.",
  "what_went_well": "TDD approach caught edge cases early",
  "challenges": "Docker build cache issues slowed iteration",
  "improvements": "Add DB health check to PLAN phase",
  "custom_workflow_items": ["terraform_plan", "db_migration_check"],
  "mode": "auto"
}
```

**Key Differences:**
- Tool feedback: NO repo name, NO task description, workflow_id HASHED (anonymized)
- Process feedback: Full context, stays local, never uploaded

### 4. Implement cmd_feedback_review() Function
**Purpose:** Analyze collected feedback and suggest improvements

**Usage:**
```bash
orchestrator feedback review              # Show recent feedback (last 7 days)
orchestrator feedback review --days 30    # Last 30 days
orchestrator feedback review --all        # All feedback
orchestrator feedback review --suggest    # Auto-suggest roadmap items
```

**Analysis Logic:**
- Read all feedback entries from `.workflow_feedback.jsonl`
- Filter by date range (default: last 7 days)
- Identify patterns:
  - **Repeated errors**: Same error in 2+ workflows → suggest fix
  - **Common challenges**: Similar challenge text → investigate
  - **Skipped items**: Item skipped in 80%+ of workflows → consider removing or making optional
  - **Missing reviews**: Reviews skipped in 50%+ → add reminder/enforcement
  - **Missing parallel agents**: Could have used parallel but didn't → better guidance needed

**Output Format:**
```
Feedback Review (last 7 days, 5 workflows)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PATTERNS DETECTED:
⚠ Parallel agents rarely used (1 of 5 workflows, 20%)
   → Suggestion: Improve Phase 0 guidance in workflow.yaml

⚠ Common error: "ModuleNotFoundError: pytest_asyncio" (3 occurrences)
   → Suggestion: Add to roadmap: "Add dependency check to PLAN phase"

✓ Reviews performed consistently (4 of 5 workflows, 80%)

COMMON CHALLENGES:
  • "Mock setup tricky" (mentioned in 2 workflows)
  • "Test timeout issues" (mentioned in 2 workflows)

LEARNINGS SUMMARY:
  • TDD approach effective (mentioned positively in 4 workflows)
  • Phase timings: avg PLAN=15min, EXECUTE=45min, REVIEW=10min

--suggest flag: Add 2 items to ROADMAP.md? (y/n)
```

**Suggest Mode (`--suggest`):**
- Generates roadmap item drafts based on patterns
- Prompts user to approve adding to ROADMAP.md
- Uses standard WF-XXX format

### 5. Implement cmd_feedback_sync() Function
**Purpose:** Upload anonymized tool feedback to central orchestrator repo

**Usage:**
```bash
# One-time opt-in
orchestrator config set feedback_sync true

# Manual sync
orchestrator feedback sync

# Check sync status
orchestrator feedback sync --status
```

**Implementation:**
- Read `.workflow_tool_feedback.jsonl`
- Filter: only entries not yet synced (track sync timestamps)
- Verify anonymization (no repo names, task descriptions, code)
- POST to central endpoint: `https://feedback.workflow-orchestrator.dev/submit`
- OR fallback: Create GitHub Gist in orchestrator repo
- Mark entries as synced (add `synced_at` timestamp)

**Central Storage (for you, orchestrator maintainer):**
- Simple HTTP endpoint or GitHub Gists
- Aggregates tool feedback from all users
- You run: `orchestrator feedback review --tool --all-users` (special command)
- Shows patterns across ALL orchestrator installations:
  - "Phase 0 guidance helpful: 85% of users"
  - "Common orchestrator error: 'prd spawn failed' (42 users)"
  - "visual_tests skipped by 90% of users → consider removing"

**Privacy Safeguards:**
- Only tool feedback synced (NEVER process feedback)
- **Default: opt-in enabled** (since currently single user - orchestrator developer)
- Future: Change to opt-out when tool has more users
- All data anonymized before upload
- Users can inspect what will be uploaded: `orchestrator feedback sync --dry-run`
- Users can disable: `orchestrator config set feedback_sync false`

### 6. Helper Functions

**Capture (cmd_feedback):**
- `get_workflow_state()` - read current workflow and items
- `analyze_workflow_logs()` - infer from logs
- `extract_tool_feedback()` - parse orchestrator-specific data (phase timings, items skipped, errors)
- `extract_process_feedback()` - parse project-specific data (learnings, challenges, custom items)
- `anonymize_tool_feedback()` - hash workflow_id, remove repo/task, detect repo_type only
- `get_repo_type()` - detect python/javascript/go/rust (for tool feedback)
- `save_tool_feedback()` - append to .workflow_tool_feedback.jsonl
- `save_process_feedback()` - append to .workflow_process_feedback.jsonl

**Review (cmd_feedback_review):**
- `load_feedback()` - read tool and/or process feedback
- `filter_by_date()` - filter entries by date range
- `detect_tool_patterns()` - items always skipped, orchestrator errors, phase timing issues
- `detect_process_patterns()` - repeated project errors, common challenges
- `calculate_stats()` - usage percentages
- `generate_suggestions()` - create roadmap item drafts
- `add_to_roadmap()` - append suggestions with user approval

**Sync (cmd_feedback_sync):**
- `load_unsynced_tool_feedback()` - read tool feedback not yet uploaded
- `verify_anonymization()` - double-check no PII/code in payload
- `post_to_central()` - HTTP POST or GitHub Gist
- `mark_as_synced()` - update entries with synced_at timestamp

### 6. Error Handling
- Graceful if .workflow_state.json missing (no active workflow)
- Warn if ORCHESTRATOR_SKIP_FEEDBACK set
- Continue workflow even if feedback fails

## Files to Modify
- `src/cli.py` - add command parsers and cmd_feedback(), cmd_feedback_review()
- No new files needed (commands in cli.py)

## Testing Strategy

**Capture Command:**
- Manual test: `orchestrator feedback --auto`
- Manual test: `orchestrator feedback --interactive`
- Verify JSON format in .workflow_feedback.jsonl
- Test opt-out: `ORCHESTRATOR_SKIP_FEEDBACK=1 orchestrator feedback`
- Verify errors/skips/learnings extraction

**Review Command:**
- Manual test: `orchestrator feedback review` (last 7 days)
- Manual test: `orchestrator feedback review --days 30`
- Manual test: `orchestrator feedback review --all`
- Manual test: `orchestrator feedback review --suggest` (roadmap suggestions)
- Verify pattern detection (repeated errors, common challenges)
- Verify stats calculation (parallel agents %, reviews %)

## Success Criteria

**Capture:**
✓ Command runs without errors
✓ Auto mode infers from logs correctly (parallel agents, reviews, errors, skips, learnings)
✓ Interactive mode prompts and saves responses
✓ Feedback saved to .workflow_feedback.jsonl
✓ Opt-out via env var works
✓ Integrates with workflow LEARN phase item

**Review:**
✓ Reads and parses .workflow_feedback.jsonl correctly
✓ Filters by date range (default 7 days)
✓ Detects patterns (repeated errors, common challenges)
✓ Calculates usage stats (parallel agents %, reviews %)
✓ Generates roadmap suggestions from patterns
✓ Can add suggestions to ROADMAP.md with approval
