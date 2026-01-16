# Plan: Fix State File Integrity Warnings (#94)

## Problem

State file integrity check warnings appear constantly during normal workflow operation.

## Root Cause

Bug in checksum computation logic - `_version` is included when computing checksum on save, but removed before verification on load.

## Fix

Add `_version` to excluded fields in `compute_state_checksum` (state_version.py line 38):

```python
excluded = {'_checksum', '_updated_at', '_version'}
```

## Files Changed

1. `src/state_version.py` - Add `_version` to excluded set (1 line)

## Execution Mode

Sequential - single file, single line change. No parallel agents needed.
