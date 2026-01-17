# Risk Analysis: CLI Scanner Integration

## Risk Matrix

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Scanner slows cmd_finish | LOW | LOW | Non-blocking, <1s typical |
| Scanner error blocks workflow | MEDIUM | LOW | Try/except, log warning only |
| Healing not configured | LOW | MEDIUM | Graceful skip if no client |
| Crash recovery false positive | LOW | LOW | Session state tracking |

## Detailed Analysis

### 1. Performance Impact

**Risk**: Scanner adds latency to cmd_finish.

**Mitigation**:
- Incremental scanning (hash-based skip)
- Typical scan: <1s for most repos
- Non-blocking: errors logged, not raised

### 2. Error Handling

**Risk**: Scanner error could block workflow completion.

**Mitigation**:
- All scanner calls wrapped in try/except
- Errors logged at warning level
- Workflow continues regardless

### 3. Configuration

**Risk**: Healing not configured in environment.

**Mitigation**:
- Check healing_enabled() before scanner calls
- Gracefully skip if no Supabase config
- No error messages for expected missing config

## Rollback Plan

If issues found:
1. Set `ORCHESTRATOR_SKIP_SCAN=1` to disable
2. Or remove scanner calls from cmd_finish/cmd_start
3. No database changes to revert
