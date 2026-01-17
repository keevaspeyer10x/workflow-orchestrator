# CLI Integration for Scanner

## Overview

Integrate the Phase 7 PatternScanner into CLI commands to provide seamless pattern learning.

## Integration Points

### 1. cmd_finish (cli.py:1492)

Add auto-scan after successful workflow completion:

```python
# After workflow completion, before final message
if healing_enabled():
    try:
        from .healing.scanner import PatternScanner
        scanner = PatternScanner(
            state_path=working_dir / ".orchestrator" / "scan_state.json",
            project_root=working_dir,
            healing_client=await _get_healing_client(),
        )
        summary = await scanner.scan_all()
        if summary.errors_extracted > 0:
            print(f"Learning: Found {summary.errors_extracted} errors, "
                  f"created {summary.patterns_created} patterns")
    except Exception as e:
        logger.warning(f"Scanner failed (non-blocking): {e}")
```

Key points:
- Non-blocking: Errors logged but don't fail workflow
- Only runs if healing is enabled
- Shows summary if patterns found

### 2. cmd_start (cli.py:379)

Add crash recovery check at session start:

```python
# At start of cmd_start, after working_dir setup
if healing_enabled():
    try:
        from .healing.scanner import PatternScanner
        scanner = PatternScanner(
            state_path=working_dir / ".orchestrator" / "scan_state.json",
            project_root=working_dir,
        )
        if scanner.has_orphaned_session():
            print("Recovering learnings from previous incomplete session...")
            summary = await scanner.recover_orphaned()
            if summary.errors_extracted > 0:
                print(f"Recovered {summary.errors_extracted} errors")
    except Exception as e:
        logger.debug(f"Crash recovery check failed: {e}")
```

### 3. heal_backfill (cli_heal.py:317)

Enhance with new flags:

```python
def heal_backfill(
    log_dir: Optional[str] = None,
    dry_run: bool = False,
    limit: Optional[int] = None,
    scan_only: bool = False,      # NEW: Just show recommendations
    days: int = 30,                # NEW: Limit to last N days
    no_github: bool = False,       # NEW: Skip GitHub issue scanning
) -> int:
```

Implementation:
- `--scan-only`: Call `scanner.get_recommendations()` and display table
- `--days N`: Pass to `scanner.scan_all(days=N)`
- `--no-github`: Skip GitHubIssueParser (add flag to scanner)

## Files to Modify

| File | Change |
|------|--------|
| `src/cli.py` | Add scanner calls to cmd_finish, cmd_start |
| `src/healing/cli_heal.py` | Enhance heal_backfill with new flags |
| `src/healing/scanner.py` | Add `include_github` parameter |

## Execution Plan

**Sequential execution** - Small, focused changes with shared context.

1. Add `include_github` parameter to scanner.scan_all()
2. Modify heal_backfill with new flags
3. Add scanner to cmd_finish
4. Add crash recovery to cmd_start
5. Write tests
6. Verify

## Test Cases

1. cmd_finish calls scanner (mock scanner, verify call)
2. cmd_start checks for orphaned sessions (mock scanner)
3. heal_backfill --scan-only shows recommendations
4. heal_backfill --days 90 passes days parameter
5. heal_backfill --no-github skips GitHub
6. Scanner errors don't block workflow completion
