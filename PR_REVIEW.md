# Code Review: Orchestrator Feedback (WF-034 Phase 3a)

## Summary
The changes implement **WF-034 Phase 3a: Orchestrator Feedback**, introducing a mechanism to capture and review workflow metrics, errors, and qualitative feedback. This includes new CLI commands (`orchestrator feedback capture/review`), a local storage mechanism (`.workflow_feedback.jsonl`), and documentation updates.

**Changes Reviewed:**
- `src/cli.py`: +414 lines (Feedback commands implementation)
- `README.md`: Usage instructions
- `docs/plan.md` & `ROADMAP.md`: Planning and documentation updates

## 🛑 Critical Issues

### 1. Broken Learning Capture (Bug)
**Severity:** High
**Location:** `src/cli.py` in `cmd_feedback_capture` (line ~4027)

The code attempts to extract learning notes from `document_learnings` events by accessing `notes` at the top level of the event object. However, `src/engine.py` logs item completion notes inside the `details` dictionary.

**Current Code:**
```python
if event.get('item_id') == 'document_learnings' and event_type == 'item_completed':
    notes = event.get('notes', '')  # BUG: 'notes' is not a top-level field
    if notes:
        learnings_notes.append(notes)
```

**Expected Structure (from `src/engine.py`):**
```python
self.log_event(WorkflowEvent(
    ...,
    details={"notes": notes, ...}
))
```

**Fix:**
Change the extraction logic to look in `details`:
```python
notes = event.get('details', {}).get('notes', '')
```
Without this fix, the "Learnings" section in the feedback review will always be empty for auto-captured workflows.

### 2. Missing Unit Tests
**Severity:** High
**Location:** `tests/`

The feature adds significant logic to `src/cli.py` (parsing logs, calculating statistics, heuristic suggestions), but **no new unit tests** were added. The diff shows changes to `tests/test_cases.md` (manual tests), but automated regression testing is missing.

**Recommendation:**
Add `tests/test_cli_feedback.py` to verify:
- Log parsing logic (especially the bug above).
- Statistics calculation (e.g., handling empty logs).
- Interactive mode inputs.

## ⚠️ Concerns & Observations

### 3. Date Handling
**Severity:** Low
**Location:** `src/cli.py`

The code uses `datetime.utcnow()` in several places, which is deprecated in newer Python versions and can lead to timezone confusion (naive vs aware).
- **Issue:** `datetime.utcnow().isoformat() + 'Z'` is a manual way to construct ISO strings.
- **Recommendation:** Use `datetime.now(timezone.utc)` for consistent, timezone-aware objects.

### 4. Hardcoded Heuristics
**Severity:** Low
**Location:** `src/cli.py` (`cmd_feedback_review`)

The pattern detection uses hardcoded thresholds (e.g., `< 30%` parallel usage, `< 50%` reviews).
- **Observation:** This is acceptable for a "Phase 3a" prototype but might be too noisy for some teams.
- **Suggestion:** Consider moving these thresholds to constants or configuration in the future.

## 💡 Questions
1.  **Log File Consistency:** The auto-capture relies entirely on `.workflow_log.jsonl`. If a user runs `orchestrator clean` or deletes logs, this data is lost. Is this ephemeral nature intentional for Phase 3a?
2.  **Privacy:** The tool captures the git remote URL (`repo`). While stored locally in `.workflow_feedback.jsonl`, users should be aware if this file is ever intended to be shared or synced in Phase 3b.

## Conclusion
The implementation is solid for a "Phase 3a" MVP, providing immediate value for self-reflection. However, the **learning capture bug** needs to be fixed before merging, as it renders a key part of the "auto-capture" feature non-functional. Unit tests are strongly recommended to prevent future regressions in the log parsing logic.
