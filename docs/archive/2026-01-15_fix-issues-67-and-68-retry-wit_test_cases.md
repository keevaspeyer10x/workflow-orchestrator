# Test Cases: Issues #67 and #68

## #67: test_command default
1. Run `orchestrator start` in a directory without package.json/pyproject.toml/etc
2. Verify test_command is set to "true" (not npm)
3. Verify `all_tests_pass` gate succeeds

## #68: subprocess import
1. Run `orchestrator finish` in a workflow
2. Verify no NameError for subprocess
3. Verify command completes successfully
