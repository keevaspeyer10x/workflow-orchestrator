# Issue #61: Fix CLI Hanging in Non-Interactive Mode

## Problem Statement

Orchestrator CLI commands (`orchestrator advance`, `orchestrator complete`) hang indefinitely when run from non-interactive shells (Claude Code, CI/CD, scripts) because `input()` blocks waiting for stdin that never comes.

## Root Cause

`input()` calls in `src/cli.py` block in non-interactive mode. When stdin is not connected to a terminal (e.g., when spawned by Claude Code or running in CI), `input()` waits forever.

## Solution Design

### Pattern: Detect and Fail-Fast

```python
def is_interactive():
    """Check if running in an interactive terminal."""
    return sys.stdin.isatty() and sys.stdout.isatty() and not os.environ.get('CI')

def confirm(prompt: str, default: bool = False, yes_flag: bool = False) -> bool:
    """Prompt user for confirmation with non-interactive fallback.

    Args:
        prompt: The question to ask
        default: Default answer if non-interactive
        yes_flag: If True, skip prompt and return True (--yes flag)

    Returns:
        True if confirmed, False otherwise
    """
    if yes_flag:
        return True
    if not is_interactive():
        hint = prompt.split('[')[0].strip()  # Extract question part
        print(f"ERROR: {hint} - Cannot prompt in non-interactive mode.")
        print("Use --yes flag to auto-confirm, or run interactively.")
        sys.exit(1)
    response = input(prompt)
    return response.lower() in ['y', 'yes']
```

### Locations to Fix

| Location | Function | Line | Current Behavior | Fix |
|----------|----------|------|------------------|-----|
| **PRIORITY** | `cmd_advance` | ~1265 | `input("Critical issues found...")` | Use `confirm()` |
| Medium | `cmd_init` | ~490 | `input("Overwrite?...")` | Use `confirm()` with `--force` flag |
| Medium | `cmd_resolve` | ~808, ~831 | `input("Enter choice...")` | Fail-fast with strategy suggestion |
| Low | `cmd_workflow_cleanup` | ~5053 | `input("Remove these?...")` | Use `confirm()` with `--yes` flag |
| N/A | `cmd_feedback_capture` | ~5129-5146 | Already gated by `is_interactive` flag | No change needed |

## Implementation Steps

1. **Add helper functions** near top of `cli.py` (after imports, ~line 100):
   - `is_interactive()` - detect terminal mode
   - `confirm()` - reusable confirmation with fail-fast

2. **Fix `cmd_advance`** (line ~1265):
   - Replace direct `input()` with `confirm()`
   - Leverage existing `--yes` flag

3. **Fix `cmd_init`** (line ~490):
   - Use `confirm()` with existing `--force` flag
   - `--force` bypasses confirmation

4. **Fix `cmd_resolve`** (lines ~808, ~831):
   - In non-interactive mode, fail with clear error
   - Suggest: "Use `--strategy ours` or `--strategy theirs`"

5. **Fix `cmd_workflow_cleanup`** (line ~5053):
   - Use `confirm()` with existing `--yes`/`-y` flag
   - Already has `skip_confirm` parameter

## Parallel Execution Decision

**Sequential execution** - This is a single-file fix with interdependent changes. Each fix uses the same helper functions added in step 1. No benefit from parallelization.

## Testing Strategy

1. Unit tests for `is_interactive()` helper
2. Unit tests for `confirm()` helper
3. Integration tests simulating non-interactive mode
4. Verify existing `--yes` flags work correctly
