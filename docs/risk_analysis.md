# Issue #58: Risk Analysis

## Overall Risk: MEDIUM

Adding fallback logic changes review execution behavior. Risk is medium because:
- Changes core review path
- Must correctly classify transient vs permanent errors
- Could mask issues if fallback hides real problems

## Detailed Risks

### 1. Incorrect Error Classification
**Risk**: Permanent errors classified as transient, causing wasted retries
**Likelihood**: Medium
**Impact**: Low (just slower failure)
**Mitigation**: Port proven logic from multiminds, comprehensive tests

### 2. Infinite Retry Loop
**Risk**: Bug causes endless retries
**Likelihood**: Low
**Impact**: High (hangs workflow)
**Mitigation**:
- Hard limit on max_fallback_attempts (default: 2)
- Total timeout on retry loop
- Tests for loop termination

### 3. Fallback Masks Real Issues
**Risk**: Fallback succeeds but masks that primary model has persistent issue
**Likelihood**: Medium
**Impact**: Low
**Mitigation**:
- Log fallback usage clearly
- Show in output which reviews used fallback
- `was_fallback` and `fallback_reason` fields preserved

### 4. Cost Implications
**Risk**: Fallback to more expensive model increases costs
**Likelihood**: Medium
**Impact**: Low
**Mitigation**:
- Configure fallback chains to use cheaper alternatives first
- Log cost of fallback operations
- `--no-fallback` flag for cost-sensitive users

### 5. Breaking Existing Behavior
**Risk**: Changes break existing review functionality
**Likelihood**: Low
**Impact**: High
**Mitigation**:
- Fallback is opt-in behavior (enabled by default but configurable)
- All existing tests must pass
- Run full review suite after implementation

## Security Considerations

- No new API keys exposed
- Error messages already sanitized (from #34)
- Fallback doesn't bypass authentication

## Rollback Plan

If issues arise:
1. Set `max_fallback_attempts: 0` to disable fallbacks
2. Use `--no-fallback` flag per invocation
3. Revert to pre-fallback code (single commit)

## Conclusion

**Recommendation: PROCEED**

Risk is acceptable because:
- Multiminds implementation is proven and tested
- Existing error classification infrastructure from #34
- Fallback can be disabled if issues arise
- Improves reliability in common failure scenarios (rate limits)
