# Risk Analysis: CORE-010 & CORE-011

## Summary

**Overall Risk Level: LOW**

These features are additive enhancements to CLI output. No breaking changes to existing functionality or data structures.

## Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing CLI output parsing | Low | Medium | Changes are additive; existing success/error indicators (✓, ✗) unchanged |
| Performance degradation | Low | Low | Summary is O(n) where n = total items; typical workflows have <50 items |
| Duration calculation edge cases | Medium | Low | Handle None start/end times gracefully; show "N/A" if unavailable |
| Confusing output for new users | Low | Low | Clear visual separators and headers improve readability |

## Detailed Analysis

### 1. CLI Output Changes

**Risk**: Scripts or users parsing CLI output may break

**Analysis**:
- `cmd_skip` currently outputs: `"✓ {message}"`
- New output adds lines BEFORE the success message
- Success indicator remains unchanged
- Low likelihood of breaking existing usage

**Mitigation**: Keep existing success/error format; add new content as additional context

### 2. Engine Method Additions

**Risk**: New methods could affect existing functionality

**Analysis**:
- All new methods are pure getters (read-only)
- No modification to state or side effects
- Return empty/None values if data unavailable
- Zero risk to existing functionality

### 3. Duration Calculation

**Risk**: Edge cases in datetime handling

**Analysis**:
- `started_at` or `completed_at` may be None
- Timezone handling could vary
- Need graceful fallback

**Mitigation**:
- Check for None before calculation
- Use UTC consistently (already the case in schema)
- Show "Duration: N/A" if times unavailable

## Security Considerations

- No new user input handling beyond existing validation
- No file system operations beyond existing state access
- No network operations
- No privilege escalation risks

## Rollback Plan

If issues arise:
1. Changes are isolated to CLI output only
2. Revert commits that modify `cmd_skip`, `cmd_advance`, `cmd_finish`
3. Engine methods are additive and can remain (unused)

## Conclusion

This is a low-risk change. The features add visibility without modifying core workflow logic or data structures.
