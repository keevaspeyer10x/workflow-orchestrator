# Code Review: PRD-005 (Commit 054a349)

## 🛑 Critical Issues

### 1. Auto-Approvals Are Not Persisted to Database
**Severity:** High
**Location:** `src/approval_gate.py` vs `src/cli.py`

The CLI command `orchestrator approval summary` fetches data from the SQLite database (`ApprovalQueue`), but the `ApprovalGate` only logs auto-approvals **in-memory** within the agent's process.

**Current Flow:**
1. Agent calls `gate.request_approval(...)`.
2. `ApprovalGate` determines `_should_auto_approve` is True.
3. It logs to `self._decision_log` (local list).
4. It returns `WaitResult.AUTO_APPROVED`.
5. **The request is never submitted to the DB.**

**Result:**
The `orchestrator approval summary` command will **never** show auto-approved operations from agents, rendering the "transparency" feature non-functional across processes.

**Fix Recommendation:**
Modify `ApprovalGate.request_approval` to submit the request to the queue and immediately mark it as `auto_approved`.

```python
# src/approval_gate.py

if self._should_auto_approve(risk_level, phase):
    rationale = self._generate_rationale(...)
    
    # FIX: Persist to DB so CLI can see it
    request = ApprovalRequest.create(
        self.agent_id, phase, operation, risk_level, context
    )
    request_id = self.queue.submit(request)
    self.queue.mark_auto_approved(request_id, rationale)
    
    # ... existing logging ...
    return WaitResult.AUTO_APPROVED
```

## ⚠️ Concerns & Observations

### 2. Test Coverage Gap
**Severity:** Medium
**Location:** `tests/test_approval_gate.py`

The tests pass because they isolate components:
- `TestApprovalGateDecisionLogging` checks the **in-memory** log.
- `TestApprovalQueueDecisionSummary` checks the **database** summary (by manually seeding data).
- There is no integration test verifying that an `ApprovalGate.request_approval` call actually results in a visible record in `ApprovalQueue.decision_summary`.

### 3. Unused Code (Planned)
**Severity:** Low
**Location:** `src/prd/tmux_adapter.py`

The function `generate_approval_gate_instructions` is implemented but not called.
*Context:* This is acknowledged in `ROADMAP.md` as part of PRD-006, but currently it's dead code.

### 4. `mark_auto_approved` Logic
**Severity:** Low
**Location:** `src/approval_queue.py`

The SQL query updates a record `WHERE status = 'pending'`. If you implement the fix above, ensure the record is in the 'pending' state when `mark_auto_approved` is called, or allow updating from the initial state.

## 💡 Suggestions

1.  **Refactor `submit()`:** Consider allowing `ApprovalQueue.submit(request, initial_status='pending')` to avoid two DB round-trips (insert pending -> update to auto_approved).
2.  **CLI Watch formatting:** The `watch` command output is good, but consider adding a timestamp to the "NEW APPROVAL REQUEST" header.

## Conclusion
The feature is **incomplete** due to the persistence issue. The transparency logging will not work as described in the PR/docs until auto-approvals are written to the SQLite database.
