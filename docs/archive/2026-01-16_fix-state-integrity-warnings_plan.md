# Plan: Fix State File Integrity Warnings (#94)

## Problem

State file integrity check warnings appear constantly during normal workflow operation:
```
State file integrity check failed. Expected X, got Y. State may have been modified externally.
```

## Root Cause

Bug in checksum computation logic:

**Save (engine.py:294):**
```python
state_data['_version'] = STATE_VERSION
state_data['_checksum'] = compute_state_checksum(state_data)  # _version IS in data
```

**compute_state_checksum (state_version.py:38):**
```python
excluded = {'_checksum', '_updated_at'}  # _version NOT excluded!
```

**Load (engine.py:235-240):**
```python
stored_checksum = data.pop('_checksum', None)
stored_version = data.pop('_version', None)  # <-- BUG: removed before verify
data.pop('_updated_at', None)
computed = compute_state_checksum(data)  # _version NOT in data = mismatch!
```

## Fix

Add `_version` to excluded fields in `compute_state_checksum`:

```python
# state_version.py line 38
excluded = {'_checksum', '_updated_at', '_version'}
```

This is the cleanest fix because:
1. All metadata fields (`_checksum`, `_updated_at`, `_version`) are excluded consistently
2. Checksum represents actual workflow data, not metadata
3. No changes needed in engine.py

## Files Changed

1. `src/state_version.py` - Add `_version` to excluded set (1 line)

## Test Plan

1. Existing tests should pass
2. Run orchestrator commands and verify no integrity warnings
3. Verify checksum still catches actual tampering

## Execution

Sequential - single file, single line change.
