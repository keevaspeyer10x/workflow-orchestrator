# Risk Analysis: Issue #61 - CLI Non-Interactive Mode Fix

## Risk Assessment

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Breaking existing interactive behavior | Medium | Low | Test both modes explicitly |
| `CI` env var false positives | Low | Low | CI is standard; document behavior |
| Missing `input()` locations | Medium | Low | Grep for all `input(` in cli.py |
| Regression in `--yes` flag handling | Medium | Low | Existing tests should catch |

## Impact Analysis

### Files Changed
- `src/cli.py` - Add helpers, modify 4 functions

### Functions Modified
1. `cmd_advance()` - Critical path for workflow advancement
2. `cmd_init()` - Used once per project setup
3. `cmd_resolve()` - Conflict resolution (less frequent)
4. `cmd_workflow_cleanup()` - Maintenance command

### Backward Compatibility
- **Preserved**: All existing flags (`--yes`, `--force`) continue to work
- **New behavior**: Non-interactive mode now fails fast instead of hanging
- **Breaking**: Scripts relying on stdin input will fail (expected - this is the fix)

## Rollback Plan

If issues arise:
1. Revert the commit
2. All changes are in a single file (`src/cli.py`)
3. No database or state changes

## Security Considerations

- **No new attack surface**: Changes are defensive (fail-fast)
- **No secrets handling changes**: N/A
- **No network calls added**: N/A

## Testing Requirements

- Must test both interactive and non-interactive modes
- Must verify `--yes` flag works in non-interactive mode
- Must verify graceful error messages
