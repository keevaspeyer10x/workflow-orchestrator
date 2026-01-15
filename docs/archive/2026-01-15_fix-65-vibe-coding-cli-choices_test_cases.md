# Test Cases: Issue #61 - CLI Non-Interactive Mode Fix

## Unit Tests

### TC-001: `is_interactive()` returns True in terminal
- **Setup**: Mock `sys.stdin.isatty()` = True, `sys.stdout.isatty()` = True, no CI env
- **Expected**: Returns `True`

### TC-002: `is_interactive()` returns False without tty
- **Setup**: Mock `sys.stdin.isatty()` = False
- **Expected**: Returns `False`

### TC-003: `is_interactive()` returns False with CI env
- **Setup**: Set `CI=true` environment variable
- **Expected**: Returns `False`

### TC-004: `confirm()` with `yes_flag=True` skips prompt
- **Setup**: Call `confirm("Question?", yes_flag=True)`
- **Expected**: Returns `True` without calling `input()`

### TC-005: `confirm()` exits in non-interactive mode
- **Setup**: Mock non-interactive, call `confirm("Question?")`
- **Expected**: Calls `sys.exit(1)` with error message

### TC-006: `confirm()` prompts in interactive mode
- **Setup**: Mock interactive, mock `input()` returning "y"
- **Expected**: Returns `True`

## Integration Tests

### TC-007: `orchestrator advance --yes` in non-interactive mode
- **Setup**: Create workflow at blocking phase, simulate non-interactive
- **Command**: `orchestrator advance --yes`
- **Expected**: Advances without hanging

### TC-008: `orchestrator advance` without `--yes` in non-interactive mode
- **Setup**: Workflow at blocking phase with critique issues, non-interactive
- **Command**: `orchestrator advance`
- **Expected**: Exit code 1, error message about non-interactive mode

### TC-009: `orchestrator init --force` in non-interactive mode
- **Setup**: Existing `workflow.yaml`, non-interactive
- **Command**: `orchestrator init --force`
- **Expected**: Overwrites without prompting

### TC-010: `orchestrator init` without `--force` in non-interactive mode
- **Setup**: Existing `workflow.yaml`, non-interactive
- **Command**: `orchestrator init`
- **Expected**: Exit code 1, error message suggesting `--force`

### TC-011: `orchestrator resolve` in non-interactive mode
- **Setup**: Git repo with merge conflicts, non-interactive
- **Command**: `orchestrator resolve --apply`
- **Expected**: Exit code 1, error suggesting `--strategy ours/theirs`

### TC-012: `orchestrator workflow cleanup --yes` in non-interactive mode
- **Setup**: Multiple old sessions, non-interactive
- **Command**: `orchestrator workflow cleanup --older-than 30 --yes`
- **Expected**: Removes sessions without prompting

## Edge Cases

### TC-013: Interactive mode still works normally
- **Setup**: Real terminal session
- **Expected**: Prompts appear and accept input

### TC-014: CI environment detection
- **Setup**: Various CI env vars (CI, GITHUB_ACTIONS, GITLAB_CI)
- **Expected**: All detected as non-interactive
