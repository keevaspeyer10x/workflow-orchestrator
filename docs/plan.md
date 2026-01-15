# Issue #58: CORE-028b - Model Fallback Execution Chain

## Overview

Implement automatic model fallback when primary review model fails with transient errors (rate limits, timeouts, network errors).

## Existing Infrastructure (from #34)

Already implemented:
- `ReviewErrorType` enum with `is_transient()` method
- `classify_http_error()` for error categorization
- `ReviewResult` has `was_fallback` and `fallback_reason` fields
- `recovery.py` with error recovery guidance

## Reference Implementation: multiminds

The `multiminds` project has a complete implementation we can adapt:
- `/home/keeva/multiminds/src/multiminds/resilience/retry.py` - Async retry with exponential backoff
- `/home/keeva/multiminds/tests/test_fallback_execution.py` - Tests for fallback logic

Key patterns to port:
1. `is_retryable_error()` / `is_permanent_error()` - Error classification
2. `async_retry_with_backoff()` - Retry decorator
3. Fallback chain execution - Try primary, then fallbacks on transient failure

## Implementation Plan

### Phase 1: Add Retry Module (Port from multiminds)

Create `src/review/retry.py`:
- `is_retryable_error(error)` - Check if error is transient
- `is_permanent_error(error)` - Check if error is permanent (401, 403, invalid key)
- `retry_with_backoff(func, max_retries, base_delay)` - Sync retry wrapper

### Phase 2: Add Fallback Execution to APIExecutor

Modify `src/review/api_executor.py`:
- Add `fallbacks` parameter to `execute()`
- Try primary model first
- On transient failure → try fallback models in order
- Populate `was_fallback` and `fallback_reason` on ReviewResult
- Respect `max_fallback_attempts` setting

```python
def execute_with_fallback(
    self,
    review_type: str,
    fallbacks: list[str] = None,
    no_fallback: bool = False
) -> ReviewResult:
    """Execute review with automatic fallback on transient failures."""
```

### Phase 3: Update Review CLI

Modify `src/cli.py`:
- Add `--no-fallback` flag to `orchestrator review` command
- Update output to show fallback usage:
  ```
  ✓ GPT-5.2 Max: Passed (45s)
  ⟳ Gemini 3 Pro: Rate limited, falling back to Gemini 2.5 Flash...
  ✓ Gemini 2.5 Flash: Passed (12s) [fallback]
  ```

### Phase 4: Configuration

Add fallback chains to config/schema:
```yaml
review:
  fallback_chains:
    gemini: [gemini-2.5-flash, claude-3.5-sonnet]
    codex: [gpt-5.1, claude-3.5-sonnet]
    grok: [grok-3, claude-3.5-sonnet]
  max_fallback_attempts: 2
```

### Phase 5: Tests

Add `tests/test_review_fallback.py`:
- Test primary succeeds (no fallback)
- Test transient error triggers fallback
- Test permanent error (401/403) does NOT trigger fallback
- Test all fallbacks fail
- Test `--no-fallback` flag disables fallback

## Files to Modify/Create

| File | Action |
|------|--------|
| `src/review/retry.py` | CREATE - Retry utilities |
| `src/review/api_executor.py` | MODIFY - Add fallback logic |
| `src/cli.py` | MODIFY - Add --no-fallback flag |
| `src/review/config.py` | MODIFY - Add fallback chain config |
| `tests/test_review_fallback.py` | CREATE - Fallback tests |

## Parallel Execution Decision

**Sequential execution** - Changes are interdependent (retry module must exist before executor uses it).

## Success Criteria

1. When Gemini rate limits, automatically falls back to Gemini Flash
2. When permanent error (401), fails immediately without fallback
3. `--no-fallback` flag disables automatic fallback
4. Output shows which reviews used fallback
5. All existing tests pass
