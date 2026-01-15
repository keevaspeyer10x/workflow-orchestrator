# Plan: Fix Issues #67 and #68

## Issue #67: Default test_command fails on non-npm projects
**Root cause:** When no project type is detected, `get_project_commands()` returns `None` for test_command, so the default `npm run build` from workflow.yaml is used.

**Fix location:** `src/cli.py` lines 482-486

**Fix:** Add else clause to set `test_command: "true"` when no project detected:
```python
if detected_commands.get("test_command") and "test_command" not in settings_overrides:
    settings_overrides["test_command"] = detected_commands["test_command"]
elif not detected_commands.get("test_command") and "test_command" not in settings_overrides:
    # No project type detected - use no-op to avoid npm errors
    settings_overrides["test_command"] = "true"
```

## Issue #68: subprocess not imported in cmd_finish
**Root cause:** Line 1783 uses `subprocess.run()` but subprocess is not imported in that function scope.

**Fix location:** `src/cli.py` around line 1780

**Fix:** Add `import subprocess` before the subprocess.run() call, matching pattern used elsewhere in the file.

## Execution
- Sequential: Both fixes are in the same file, low complexity
- No parallel agents needed
