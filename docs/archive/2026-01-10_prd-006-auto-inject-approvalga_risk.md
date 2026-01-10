# PRD-005 Risk Analysis: Integrate ApprovalGate with TmuxAdapter

## Risk Assessment

### Risk 1: Agent Ignores Approval Gate
**Severity:** Medium
**Likelihood:** Low
**Impact:** Agent proceeds without human approval

**Mitigation:**
- Inject approval gate instructions prominently in agent prompt
- Include sample code in prompt for easy copy-paste
- Add pre-flight check: verify gate is initialized

### Risk 2: Database Contention
**Severity:** Low
**Likelihood:** Low
**Impact:** Multiple agents hitting same SQLite file

**Mitigation:**
- Already using WAL mode with busy_timeout=5000ms
- Each request has unique ID, no shared state conflicts
- Existing implementation handles concurrent access

### Risk 3: Deadlock - Agent Waits Forever
**Severity:** Medium
**Likelihood:** Medium
**Impact:** Agent stalls if human doesn't respond

**Mitigation:**
- Already implemented: 30-minute default timeout
- Watch command provides notifications
- Timeout returns `WaitResult.TIMEOUT` for graceful handling

### Risk 4: Over-Notification Fatigue
**Severity:** Low
**Likelihood:** Medium
**Impact:** User ignores notifications due to frequency

**Mitigation:**
- Risk-based auto-approval reduces noise (low/medium auto-approve)
- Group notifications in watch command
- Provide clear context so decisions are quick

### Risk 5: Auto-Approval Masks Risky Operations
**Severity:** High
**Likelihood:** Low
**Impact:** Agent does something risky without human review

**Mitigation:**
- Decision transparency: log ALL auto-approvals with rationale
- Summary at end shows what was auto-approved
- Conservative defaults: only LOW always auto-approves
- MEDIUM requires logging, HIGH/CRITICAL never auto-approve

## Impact Analysis

### Positive Impacts
1. **Efficiency**: Low-risk operations don't require human intervention
2. **Safety**: High-risk operations always pause for review
3. **Transparency**: Full audit trail of all decisions

### Potential Negative Impacts
1. **Complexity**: Agents need to understand approval system
2. **Latency**: HIGH/CRITICAL operations wait for human (by design)

## Rollback Strategy
1. Agents can run without gate (existing behavior)
2. Prompt injection is additive, not breaking
3. Watch command is optional
4. All changes are backwards compatible
