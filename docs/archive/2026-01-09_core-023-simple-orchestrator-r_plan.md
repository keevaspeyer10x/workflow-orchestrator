# Process Compliance Fixes Implementation Plan

## Goal
Implement guardrails to ensure the orchestrator workflow is followed correctly, preventing AI agents from bypassing phases, skipping reviews, or working outside the established process.

## Problem Statement
During testing, the orchestrator was observed "not following instructions" due to:
1. **Context compaction** - AI loses awareness of active workflow when context is compacted
2. **Phase bypass** - Code written during non-EXECUTE phases
3. **Review bypass** - Workflows completed without required external reviews
4. **Process drift** - Significant work done with no workflow active

## Items to Implement

| ID | Name | Priority | Approach |
|----|------|----------|----------|
| WF-012 | Workflow State Injection After Context Compaction | Critical | Behavioral + Hook |
| WF-013 | Block Implementation Code Without Active Workflow Phase | Critical | Behavioral |
| WF-014 | Block Workflow Finish Without Required Reviews | High | Code |
| WF-015 | Detect and Warn on Work Outside Active Workflow | High | Hook + Code |

## Detailed Design

### WF-012: Workflow State Injection After Context Compaction

**Challenge:** Claude Code doesn't have a "context compaction" hook. The compaction happens automatically and invisibly.

**Solution:** Multi-layered defense:

1. **Enhanced CLAUDE.md Instructions**
   - Add prominent "ALWAYS CHECK" section at the top
   - Instruction: Before ANY code change, run `orchestrator status`
   - Instruction: If workflow is active, verify you're in the correct phase
   - Add visual reminder pattern the AI can recognize

2. **Session Start Hook Enhancement**
   - Modify `.claude/hooks/session-start.sh` to inject workflow state
   - Print prominent banner if workflow is active
   - Set environment variable `WORKFLOW_ACTIVE=true` for downstream detection

3. **New Command: `orchestrator context-reminder`**
   - Returns a compact status suitable for re-injection
   - Designed to be called periodically during long sessions
   - Format optimized for AI parsing

**Files to Modify:**
- `CLAUDE.md` - Add process compliance section at top
- `.claude/hooks/session-start.sh` - Add workflow state injection
- `src/cli.py` - Add `context-reminder` command

---

### WF-013: Block Implementation Code Without Active Workflow Phase

**Challenge:** The orchestrator CLI can't literally "block" code writing - it's not in the code path.

**Solution:** Behavioral enforcement via CLAUDE.md:

1. **Clear Behavioral Rule in CLAUDE.md**
   ```
   CRITICAL RULE: Phase-Aware Development

   IF an orchestrator workflow is active:
     IF current phase is NOT "EXECUTE":
       DO NOT write implementation code
       INSTEAD: Complete current phase items first

   Allowed actions by phase:
   - PLAN: Reading, planning, documenting only
   - EXECUTE: Writing code and tests
   - REVIEW: Running reviews, NOT fixing code
   - VERIFY: Running tests, verifying (no new code)
   - LEARN: Documenting learnings only
   ```

2. **Pre-Write Verification Command**
   - New command: `orchestrator verify-write-allowed`
   - Returns success if in EXECUTE phase or no workflow
   - Returns error with explanation if wrong phase
   - AI is instructed to call this before file writes

**Files to Modify:**
- `CLAUDE.md` - Add phase-aware development rules
- `src/cli.py` - Add `verify-write-allowed` command

---

### WF-014: Block Workflow Finish Without Required Reviews

**Challenge:** Workflows can be completed without external reviews actually running.

**Solution:** Enforcement in `cmd_finish()`:

1. **Review Completion Tracking**
   - Check workflow log for `REVIEW_COMPLETED` events
   - Identify which review types were actually executed
   - Compare against required review types

2. **Blocking Logic**
   ```python
   def validate_reviews_completed(engine) -> tuple[bool, list[str]]:
       """Check if required reviews were completed."""
       required = {"security", "quality"}  # Minimum required
       completed = set()

       for event in engine.get_events():
           if event.event_type == EventType.REVIEW_COMPLETED:
               review_type = event.details.get("review_type")
               if review_type:
                   completed.add(review_type)

       missing = required - completed
       return len(missing) == 0, list(missing)
   ```

3. **Override Flag**
   - Add `--skip-review-check` flag with required `--reason`
   - Logs the skip with reason for audit trail
   - Prints prominent warning about bypassing

**Files to Modify:**
- `src/cli.py` - Add review validation to `cmd_finish()`
- `src/engine.py` - Add `get_completed_reviews()` method

---

### WF-015: Detect and Warn on Work Outside Active Workflow

**Challenge:** Detecting "significant work" without blocking legitimate quick fixes.

**Solution:** Git pre-commit hook + workflow integration:

1. **Pre-Commit Hook Script**
   Create `.claude/hooks/pre-commit-workflow-check.sh`:
   ```bash
   #!/bin/bash
   # Check if significant changes are being committed without workflow

   # Count changed lines
   LINES_CHANGED=$(git diff --cached --numstat | awk '{ added += $1; deleted += $2 } END { print added + deleted }')

   # Check workflow status
   WORKFLOW_ACTIVE=$(orchestrator status --json 2>/dev/null | jq -r '.active // false')

   if [ "$LINES_CHANGED" -gt 50 ] && [ "$WORKFLOW_ACTIVE" != "true" ]; then
       echo "⚠️  WARNING: Committing significant changes without an active workflow"
       echo "   Lines changed: $LINES_CHANGED"
       echo ""
       echo "   Consider starting a workflow for tracked development:"
       echo "   orchestrator start \"Description of your task\""
       echo ""
       echo "   To proceed anyway, use: git commit --no-verify"
   fi
   ```

2. **Status Command Enhancement**
   - Add `--json` flag for machine-readable output
   - Include `active: true/false` field

3. **CLAUDE.md Behavioral Rule**
   - Add instruction to start workflow for any non-trivial task
   - Define "non-trivial": >3 files or >50 lines changed

**Files to Modify:**
- `.claude/hooks/pre-commit-workflow-check.sh` (new)
- `src/cli.py` - Add `--json` flag to status command

---

## Implementation Order

1. **WF-014** (Block finish without reviews) - Pure code change, lowest risk
2. **WF-012** (Context injection) - CLAUDE.md + hook changes
3. **WF-013** (Phase blocking) - CLAUDE.md + new command
4. **WF-015** (Work detection) - Hook + status enhancement

## Files Summary

| File | Changes |
|------|---------|
| `src/cli.py` | Add `context-reminder`, `verify-write-allowed` commands; Add `--json` to status; Add review validation to finish |
| `src/engine.py` | Add `get_completed_reviews()` method |
| `CLAUDE.md` | Add Process Compliance section with behavioral rules |
| `.claude/hooks/session-start.sh` | Enhance with workflow state injection |
| `.claude/hooks/pre-commit-workflow-check.sh` | New hook for work detection |
| `.claude/settings.json` | Register pre-commit hook (if using Claude Code hooks) |

## Testing Strategy

1. **Unit Tests**
   - `test_review_validation()` - Verify finish blocks without reviews
   - `test_verify_write_allowed()` - Phase checking logic
   - `test_context_reminder()` - Command output format

2. **Integration Tests**
   - Complete workflow with all reviews → should succeed
   - Complete workflow without reviews → should block
   - Try finish with `--skip-review-check` → should succeed with warning

3. **Manual Testing**
   - Start workflow, try to write code in PLAN phase
   - Simulate context compaction, verify reminder works
   - Make significant commits without workflow, verify warning

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| False positives blocking legitimate work | Medium | Medium | Override flags with logged reasons |
| Behavioral rules not followed by AI | Medium | High | Multiple enforcement layers |
| Session hook slowdown | Low | Low | Keep hook fast (<2s) |
| Breaking existing workflows | Low | High | Backward compatible, opt-in strictness |

## Success Criteria

1. `orchestrator finish` blocks without completed reviews (unless `--skip-review-check`)
2. `orchestrator verify-write-allowed` returns correct phase status
3. `orchestrator context-reminder` outputs compact status
4. Pre-commit hook warns on significant uncommitted work without workflow
5. CLAUDE.md contains clear behavioral rules
6. All existing tests still pass
