# CORE-026: Risk Analysis

## Risk Assessment

### High Impact Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **API ping adds latency** | High | Medium | Use lightweight endpoints (list models), 5s timeout, cache validation for session |
| **False positives block valid reviews** | Medium | High | Validate key presence + format only, not full auth; keep `--skip-review-check` escape hatch |
| **Breaking existing workflows** | Low | High | `required_reviews` defaults to empty list (backward compatible); existing workflows continue working |

### Medium Impact Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Over-blocking frustrated users** | Medium | Medium | Clear recovery instructions, `--skip-review-check --reason` escape hatch, `orchestrator review retry` command |
| **Retry loops on permanent failures** | Low | Medium | Max 3 retries, classify errors (transient vs permanent), skip permanent failures |
| **Schema migration complexity** | Low | Medium | `required_reviews` is additive field, no migration needed for existing state files |

### Low Impact Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **API changes break ping logic** | Low | Low | Abstract ping per provider, easy to update individual endpoints |
| **Error classification wrong** | Medium | Low | Log all errors with full context, improve classification over time |

## Backward Compatibility

### What Changes
- New `required_reviews` field in workflow.yaml phases
- New `ReviewErrorType` enum in ReviewResult
- New `orchestrator review retry` command
- Updated error messages with recovery instructions

### What Stays Compatible
- Existing workflow.yaml files work (required_reviews defaults to empty)
- Existing `--skip-review-check` flag still works
- Review completion events unchanged (REVIEW_COMPLETED)
- State file format unchanged

## Rollback Plan

If issues arise after deployment:

1. **Immediate**: Users can use `--skip-review-check --reason "..."` to bypass validation
2. **Quick fix**: Remove validation calls, revert to current behavior
3. **Full rollback**: Git revert the commits

## Dependencies

- No new external dependencies
- Uses existing API clients (no new libraries)
- No database changes
- No state file format changes

## Security Considerations

- API keys never logged (existing sanitization continues)
- Recovery instructions don't expose key values
- Ping endpoints are read-only (list models, not create/modify)
- No new attack surface introduced
