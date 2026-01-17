# V4.2 Phase 4: Chat Mode Risk Analysis

## Risk Assessment

### Risk 1: Lossy Summarization Corrupts Session State
**Severity**: High
**Probability**: Medium
**Impact**: Users lose critical context, decisions, or code references

**Mitigation**:
- SummaryValidator performs deterministic validation before accepting summaries
- If validation fails, fallback to truncation (preserves recent + pinned)
- Pinned messages are NEVER summarized
- Last 20 messages always preserved

**Residual Risk**: Regex-based extraction may miss domain-specific entities
**Monitoring**: Log validation failures and fallback counts

### Risk 2: Event Store Corruption Prevents Recovery
**Severity**: Critical
**Probability**: Low
**Impact**: Session cannot be recovered, all history lost

**Mitigation**:
- Use SQLite WAL mode for crash safety
- Checkpoints every 20 messages provide recovery points
- Event append uses optimistic concurrency control
- Test crash recovery explicitly

**Residual Risk**: Hardware failure during write
**Monitoring**: Verify checkpoint count on session load

### Risk 3: Budget Exhaustion Mid-Conversation
**Severity**: Medium
**Probability**: Medium
**Impact**: Session stops responding, user frustrated

**Mitigation**:
- Pre-check budget before LLM calls
- Graceful error message explaining budget status
- `/status` command shows remaining budget
- Summarization reduces context size, saving tokens

**Residual Risk**: Long responses may exceed reservation
**Monitoring**: Log budget overruns

### Risk 4: Meta-command Injection
**Severity**: Medium
**Probability**: Low
**Impact**: Unintended command execution

**Mitigation**:
- Commands only parsed at message start
- Command names are fixed allowlist
- Arguments validated before execution
- Commands don't execute shell operations

**Residual Risk**: None identified
**Monitoring**: Log all command executions

### Risk 5: Recursive Summarization Loops
**Severity**: Medium
**Probability**: Low
**Impact**: Infinite loop consuming tokens

**Mitigation**:
- Summarization only triggers above 70% threshold
- Summary itself is not re-summarized (marked as SYSTEM)
- Maximum one summarization pass per prepare_context call
- Budget reservation prevents runaway spending

**Residual Risk**: None with current design
**Monitoring**: Log summarization trigger counts

## Risk Matrix

| Risk | Severity | Probability | Score | Mitigation Status |
|------|----------|-------------|-------|-------------------|
| Lossy Summarization | High | Medium | 6 | Designed |
| Event Store Corruption | Critical | Low | 6 | Uses Phase 1 |
| Budget Exhaustion | Medium | Medium | 4 | Uses Phase 2/3 |
| Meta-command Injection | Medium | Low | 2 | Designed |
| Recursive Summarization | Medium | Low | 2 | Designed |

## Dependencies

| Dependency | Risk if Missing | Fallback |
|------------|-----------------|----------|
| SQLiteAsyncEventStore | No persistence | In-memory only |
| TokenCounter | Inaccurate budgets | Estimation |
| LLMCallWrapper | No LLM calls | N/A (critical) |
| CheckpointStore | No crash recovery | Replay all events |
