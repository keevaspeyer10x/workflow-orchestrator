# PRD-005: Integrate ApprovalGate with TmuxAdapter

## Overview
Enable spawned parallel agents to automatically pause at workflow gates and wait for human approval, with risk-based auto-approval and full transparency.

## Implementation Plan

### Phase 1: Enhance ApprovalGate Logging (approval_gate.py)

1. **Add auto-approval logging with transparency**
   - When auto-approving, log: operation, risk level, phase, rationale
   - Store auto-approval records in queue (new status: `auto_approved`)
   - Include risk explanation in each logged decision

2. **Track all decisions for end-of-session summary**
   - New method: `gate.get_decision_log()` returns all decisions
   - Format decisions with risk rationale for human review

### Phase 2: Inject ApprovalGate into TmuxAdapter (tmux_adapter.py)

1. **Modify spawn_agent() to inject gate initialization**
   - Add gate setup instructions to agent prompts
   - Pass db_path so agents use same approval queue
   - Include agent_id for tracking

2. **Generate approval-aware prompt template**
   - Add instructions for when to call `request_approval()`
   - Define risk classification guidelines
   - Include sample approval request code

### Phase 3: Add CLI Watch Command (cli.py)

1. **New `orchestrator approval watch` command**
   - Poll queue for pending requests
   - Print new requests with context
   - Trigger tmux bell for Happy notifications
   - Option to auto-approve-all with timeout

2. **Enhance pending display**
   - Show time waiting
   - Show risk level with color
   - Quick-approve keyboard shortcut hint

### Phase 4: Add Decision Summary

1. **New method in ApprovalQueue: `decision_summary()`**
   - Return all decisions from session
   - Group by: human-approved, auto-approved, rejected

2. **Display summary at workflow end**
   - List auto-approved items with risk rationale
   - Highlight any high-risk auto-approvals (shouldn't happen)

## Files to Modify

| File | Changes |
|------|---------|
| `src/approval_gate.py` | Add transparency logging, decision tracking |
| `src/approval_queue.py` | Add `auto_approved` status, decision summary |
| `src/prd/tmux_adapter.py` | Inject gate setup into prompts |
| `src/cli.py` | Add `approval watch` command |

## Dependencies
- ApprovalQueue (v2.4.0) - exists
- TmuxAdapter (v2.3.0) - exists
- tmux for bell notifications

## Testing Strategy
- Unit tests for auto-approval logging
- Integration test: spawn agent, verify gate pauses
- Manual test: watch command with tmux bell
