# Code Review: V3 Pre-Implementation Checklist

**Verdict: Changes Requested**

The shift to the V3 pre-implementation plan is clear, and the documentation updates (`docs/plan.md`, `ROLLBACK.md`) are solid. However, the code changes in `src/cli.py` introduce dead code and potential logic confusion that should be addressed before merging.

## 1. Dead Code in `src/cli.py`
The functions `is_llm_mode()` and `_emergency_override_active()` are defined but **never called**. 
- **Risk**: Committing dead code creates technical debt and confusion about intended usage.
- **Action**: Wire these functions into the application logic (e.g., within `is_interactive()` or as a guard in `cmd_start`/`main`) or remove them until the implementation phase.

## 2. Magic Strings
In `_emergency_override_active()`:
```python
return os.environ.get('ORCHESTRATOR_EMERGENCY_OVERRIDE') == 'human-override-v3'
```
- **Concern**: `'human-override-v3'` is a magic string buried in the function.
- **Action**: Extract this to a constant at the module level (e.g., `EMERGENCY_OVERRIDE_VALUE = 'human-override-v3'`) for better maintainability and visibility.

## 3. Ambiguous Mode Detection Logic
```python
def is_llm_mode() -> bool:
    if os.environ.get('CLAUDECODE') == '1':
        return True
    if not sys.stdin.isatty():
        return True  # <--- Overlaps with is_interactive() check
    return False
```
- **Concern**: `!sys.stdin.isatty()` is used in `is_interactive()` to return `False`, and here to return `True`. While semantically consistent (not tty = not interactive = llm mode?), it assumes *all* non-TTY usage is "LLM mode", which might not be true (e.g., CI pipelines, piped scripts).
- **Question**: Should `is_llm_mode()` explicitly exclude CI environments? `is_interactive()` already checks for `CI` and `GITHUB_ACTIONS`.

## 4. Documentation & Plan
- **ROLLBACK.md**: Clear and concise. Good job.
- **docs/plan.md**: The sequential checklist is well-structured.
- **State Files**: The updates to `.orchestrator/state.json` and `.orchestrator/audit.jsonl` are acceptable as runtime artifacts.

## Summary
The documentation and plan are approved. Please fix the `src/cli.py` issues:
1.  Connect the new functions to the logic OR remove them.
2.  Refactor the magic string.
3.  Clarify the `is_llm_mode` logic regarding non-LLM automation (CI).