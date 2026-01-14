# CORE-026-E1 & E2 Risk Analysis

## Risk Assessment

### E1: Wire Error Classification in Executors

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Breaking existing error handling | MEDIUM | LOW | Tests verify current behavior preserved |
| Missing error patterns | LOW | MEDIUM | Start with common patterns, extend later |
| Exception type detection | LOW | LOW | Use hasattr() checks for safe introspection |

**Overall Risk: LOW** - Adding error_type is additive, default NONE maintains backward compat.

### E2: Ping Validation

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Rate limiting on ping | LOW | MEDIUM | Use lightweight /models endpoint |
| Increased latency | LOW | HIGH | ping=False by default, opt-in only |
| API endpoint changes | LOW | LOW | Standard endpoints, well-documented |
| Network errors on ping | LOW | MEDIUM | Catch exceptions, return clear error |

**Overall Risk: LOW** - Opt-in feature with defensive error handling.

## Impact Assessment

### Positive Impacts
- E1: Error_type field becomes useful for debugging and retry logic
- E2: Can detect expired/revoked keys before running full review

### Negative Impacts
- E2: Slight latency increase when ping=True (mitigated by opt-in)

## Rollback Strategy

Both changes are additive:
- E1: error_type defaults to NONE, existing code works unchanged
- E2: ping defaults to False, existing behavior unchanged

Rollback: Simply revert the commit. No data migration needed.

## Security Considerations

- E1: Error messages already sanitized (_sanitize_error)
- E2: API keys not logged, only used in HTTP headers
- Ping endpoints return model lists, no sensitive data exposed

## Dependencies

No new dependencies required. Uses existing:
- requests (already used by api_executor)
- urllib.request (already used by cli_executor for grok)
