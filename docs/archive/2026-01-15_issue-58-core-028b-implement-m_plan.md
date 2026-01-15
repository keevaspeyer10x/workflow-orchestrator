# Plan: Fix Issues #67 and #68

## Issue #67: Default test_command fails on non-npm projects
**Fix:** Added else clause to set test_command/build_command to "true" when no project detected.
**Location:** src/cli.py lines 485-492

## Issue #68: subprocess not imported in cmd_finish
**Fix:** Added `import subprocess` at line 1789.

## Status
Both fixes implemented and verified.
