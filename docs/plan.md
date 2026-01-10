# Plan: Parallel Agent Approval System

## Overview
Implement SQLite-backed approval queue for coordinating parallel AI agents that need human approval at workflow gates.

## Architecture (from multi-model review consensus)

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR CONTROL PLANE                   │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────┐    ┌─────────┐    ┌─────────┐                     │
│  │ Agent 1 │    │ Agent 2 │    │ Agent N │                     │
│  │ (tmux)  │    │ (tmux)  │    │ (tmux)  │                     │
│  └────┬────┘    └────┬────┘    └────┬────┘                     │
│       │              │              │                           │
│       └──────────────┴──────────────┘                           │
│                      │                                          │
│                      ▼                                          │
│          ┌───────────────────────┐                             │
│          │   SQLite Queue        │                             │
│          │   (WAL mode)          │                             │
│          └───────────┬───────────┘                             │
│                      │                                          │
│                      ▼                                          │
│          ┌───────────────────────┐                             │
│          │  orchestrator pending │  ◄── User checks this       │
│          │  orchestrator review  │  ◄── User approves here     │
│          └───────────────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Steps

### 1. ApprovalQueue (src/approval_queue.py) ✅ DONE
- SQLite with WAL mode for concurrent access
- State machine: PENDING → APPROVED|REJECTED → CONSUMED
- Heartbeat tracking for stuck agents
- Methods: submit(), check(), consume(), decide(), pending()

### 2. ApprovalGate (src/approval_gate.py)
- Agent-side interface for requesting approval
- Polling with exponential backoff (2s → 10s → 30s)
- Auto-approval rules by risk level
- Timeout handling (default 30 min)
- tmux notification on gate hit

### 3. CLI Commands (src/cli.py)
- `orchestrator pending` - List all waiting agents
- `orchestrator review` - Batch approval interface
- `orchestrator approve <id>` - Approve single request
- `orchestrator reject <id>` - Reject single request

### 4. Auto-Approval Rules
| Risk Level | Auto-Approve | Examples |
|------------|--------------|----------|
| LOW | ✅ Always | Read files, run tests, lint, PLAN phase |
| MEDIUM | ⚠️ With logging | Create files, small edits (<100 lines) |
| HIGH | ❌ Human review | >100 lines, configs, deps |
| CRITICAL | 🚫 Never | rm -rf, force push, prod deploy |

### 5. Integration with TmuxAdapter
- Agents use ApprovalGate when hitting workflow gates
- Pending command shows tmux session info
- Review command can attach to agent session

## Files to Create/Modify
- `src/approval_queue.py` ✅ DONE
- `src/approval_gate.py` (new)
- `src/cli.py` (add pending, review commands)
- `tests/test_approval_queue.py` (new)
- `tests/test_approval_gate.py` (new)

## Success Criteria
1. Agents can submit approval requests and poll for decisions
2. User can see all pending approvals with `orchestrator pending`
3. User can batch approve/reject with `orchestrator review`
4. Stale agents are detected and expired after timeout
5. All tests pass
