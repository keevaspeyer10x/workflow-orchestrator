# Test Cases: CLI Scanner Integration

## cmd_finish Integration

### TC-FIN-001: Scanner called on successful finish
**Given**: Workflow completes successfully, healing enabled
**When**: cmd_finish runs
**Then**: Scanner.scan_all() is called

### TC-FIN-002: Scanner error doesn't block finish
**Given**: Scanner raises exception
**When**: cmd_finish runs
**Then**: Workflow completes, warning logged

### TC-FIN-003: Scanner skipped when healing disabled
**Given**: Healing not configured (no Supabase)
**When**: cmd_finish runs
**Then**: Scanner not called, no error

## cmd_start Integration

### TC-START-001: Crash recovery checked on start
**Given**: Orphaned session exists
**When**: cmd_start runs
**Then**: recover_orphaned() called, message shown

### TC-START-002: No action when no orphaned sessions
**Given**: No orphaned sessions
**When**: cmd_start runs
**Then**: No recovery message

### TC-START-003: Recovery error doesn't block start
**Given**: Recovery raises exception
**When**: cmd_start runs
**Then**: Workflow starts normally, debug log

## heal_backfill Enhancement

### TC-BF-001: --scan-only shows recommendations
**Given**: `orchestrator heal backfill --scan-only`
**When**: Command runs
**Then**: Shows recommendations table, no processing

### TC-BF-002: --days parameter passed to scanner
**Given**: `orchestrator heal backfill --days 90`
**When**: Command runs
**Then**: scanner.scan_all(days=90) called

### TC-BF-003: --no-github skips GitHub
**Given**: `orchestrator heal backfill --no-github`
**When**: Command runs
**Then**: GitHub parser not invoked

### TC-BF-004: Default behavior unchanged
**Given**: `orchestrator heal backfill` (no new flags)
**When**: Command runs
**Then**: Existing behavior preserved
