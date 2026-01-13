# Test Cases: orchestrator feedback Command

## Manual Tests (Core Functionality)

### TC1: Auto Mode - Happy Path
**Given:** Completed workflow with parallel agents, reviews, some errors, skipped items, and learnings
**When:** Run `orchestrator feedback --auto`
**Then:**
- Feedback entry created in .workflow_feedback.jsonl
- Entry includes: workflow_id, duration, parallel_agents_used=true, reviews_performed=true
- Entry includes: errors_count, errors_summary (array), items_skipped_count, items_skipped_reasons (array)
- Entry includes: learnings (extracted from document_learnings notes)
- Exit code 0

### TC2: Interactive Mode
**Given:** Completed workflow
**When:** Run `orchestrator feedback --interactive`
**Then:**
- Prompts 5 questions sequentially
- Saves user responses to .workflow_feedback.jsonl
- Exit code 0

### TC3: Opt-Out
**Given:** ORCHESTRATOR_SKIP_FEEDBACK=1 set
**When:** Run `orchestrator feedback --auto`
**Then:**
- Prints "Feedback capture disabled" message
- NO entry added to .workflow_feedback.jsonl
- Exit code 0

### TC4: No Active Workflow
**Given:** No .workflow_state.json exists
**When:** Run `orchestrator feedback --auto`
**Then:**
- Warning printed: "No active workflow found"
- Still attempts to create feedback entry with minimal data
- Exit code 0 (non-fatal)

### TC5: Workflow Integration
**Given:** In LEARN phase with capture_workflow_feedback item
**When:** Item executes (calls `orchestrator feedback --auto`)
**Then:**
- Feedback captured automatically
- User sees no prompts
- Workflow continues to next item

### TC5A: Error/Skip/Learning Extraction
**Given:** Workflow with:
- 2 error events in logs (test failure, linting error)
- 3 skipped items (visual_tests, update_knowledge_base, optional_step)
- document_learnings completed with notes "TDD worked well. Mock setup tricky."
**When:** Run `orchestrator feedback --auto`
**Then:**
- errors_count = 2
- errors_summary contains both error descriptions
- items_skipped_count = 3
- items_skipped_reasons contains all 3 skip reasons
- learnings = "TDD worked well. Mock setup tricky."
- Exit code 0

## Edge Cases

### TC6: Malformed Log File
**Given:** .workflow_log.jsonl has invalid JSON line
**When:** Run `orchestrator feedback --auto`
**Then:**
- Skips malformed lines gracefully
- Creates feedback entry with partial data
- Logs warning
- Exit code 0

### TC7: No Git Remote
**Given:** Not in a git repository
**When:** Run `orchestrator feedback --auto`
**Then:**
- Uses "unknown" as repo identifier
- Feedback still saved
- Exit code 0

### TC8: File Write Permission Error
**Given:** .workflow_feedback.jsonl is read-only
**When:** Run `orchestrator feedback --auto`
**Then:**
- Prints error message
- Exit code 1
- Does NOT crash workflow

## JSON Format Validation

### TC9: Verify JSON Structure
**When:** Feedback entry created
**Then:** Entry has required fields:
- timestamp (ISO 8601)
- workflow_id
- repo
- duration_seconds
- parallel_agents_used (boolean)
- reviews_performed (boolean)
- errors_count (integer)
- errors_summary (array of strings)
- items_skipped_count (integer)
- items_skipped_reasons (array of strings)
- learnings (string, extracted from notes)
- mode ("auto" or "interactive")

### TC10: Multiple Feedback Entries
**Given:** .workflow_feedback.jsonl has existing entries
**When:** New feedback captured
**Then:**
- Appends new entry (doesn't overwrite)
- Each line is valid JSON
- File remains valid JSONL format

## Cross-Repo Aggregation

### TC11: Different Repos
**Given:** Run workflows in repo A, then repo B
**When:** Check .workflow_feedback.jsonl in each repo
**Then:**
- Each repo has its own feedback file
- Repo identifiers differ correctly
- No cross-contamination

## Performance

### TC12: Auto Mode Speed
**When:** Run `orchestrator feedback --auto` on large workflow (100+ log entries)
**Then:** Completes in < 2 seconds

## Feedback Review Command Tests

### TC13: Review - Show Recent Feedback
**Given:** 10 feedback entries in .workflow_feedback.jsonl (5 from last week, 5 from last month)
**When:** Run `orchestrator feedback review`
**Then:**
- Shows 5 entries (default: last 7 days)
- Displays summary statistics
- Exit code 0

### TC14: Review - Custom Date Range
**Given:** Feedback entries spanning 60 days
**When:** Run `orchestrator feedback review --days 30`
**Then:**
- Shows only entries from last 30 days
- Exit code 0

### TC15: Review - Pattern Detection (Repeated Errors)
**Given:** 3 workflows with error "ModuleNotFoundError: pytest_asyncio"
**When:** Run `orchestrator feedback review`
**Then:**
- Detects pattern: "Common error (3 occurrences)"
- Suggests roadmap item to fix
- Exit code 0

### TC16: Review - Pattern Detection (Low Parallel Agent Usage)
**Given:** 5 workflows, only 1 used parallel agents
**When:** Run `orchestrator feedback review`
**Then:**
- Shows: "⚠ Parallel agents rarely used (1 of 5, 20%)"
- Suggests improving Phase 0 guidance
- Exit code 0

### TC17: Review - Suggest Mode
**Given:** Patterns detected in feedback (repeated error, common challenge)
**When:** Run `orchestrator feedback review --suggest`
**Then:**
- Generates 2 roadmap item drafts
- Prompts: "Add 2 items to ROADMAP.md? (y/n)"
- If yes: appends to ROADMAP.md with WF-XXX format
- Exit code 0

### TC18: Review - No Feedback File
**Given:** .workflow_feedback.jsonl doesn't exist
**When:** Run `orchestrator feedback review`
**Then:**
- Prints: "No feedback data found. Run workflows to collect feedback."
- Exit code 0 (non-fatal)

### TC19: Review - Empty Feedback File
**Given:** .workflow_feedback.jsonl exists but is empty
**When:** Run `orchestrator feedback review`
**Then:**
- Prints: "No feedback entries found"
- Exit code 0

### TC20: Review - Stats Calculation
**Given:** 10 workflows: 8 with reviews, 3 with parallel agents
**When:** Run `orchestrator feedback review --all`
**Then:**
- Shows: "✓ Reviews performed: 8 of 10 (80%)"
- Shows: "⚠ Parallel agents used: 3 of 10 (30%)"
- Exit code 0

### TC21: Review - Common Challenges Aggregation
**Given:** 3 workflows mention "Mock setup tricky", 2 mention "Test timeouts"
**When:** Run `orchestrator feedback review`
**Then:**
- COMMON CHALLENGES section lists both
- Shows occurrence count for each
- Exit code 0

## Test Coverage Goals
- ✓ Happy path (auto and interactive)
- ✓ Opt-out mechanism
- ✓ Error handling (no workflow, malformed logs, file permissions)
- ✓ JSON format correctness
- ✓ Workflow integration
- ✓ Performance acceptable
