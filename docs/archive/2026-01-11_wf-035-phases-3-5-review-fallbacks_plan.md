# WF-035 Phases 3-5: Review Fallbacks Implementation Plan

## Summary

Phases 3 (Visual Regression) and 5 (Gate Skipping) are already implemented. This plan focuses on Phase 4: Review Fallback & Graceful Degradation.

## Current State Analysis

### Already Implemented
1. **Phase 3 (Visual Regression):** workflow.yaml:359-377 has full Playwright spec
2. **Phase 5 (Gate Skipping):** engine.py has should_skip_gate() wired into complete_item()
3. **Schema:** ReviewSettings model with minimum_required, fallbacks, on_insufficient_reviews
4. **Config:** default_workflow.yaml has fallback configuration (lines 106-121)

### Gap: Review System Doesn't Use Settings
The review router/executors don't read or use ReviewSettings:
- `router.py` doesn't check minimum_required
- `api_executor.py` doesn't try fallback models
- No tracking of successful reviews vs minimum threshold
- No handling of on_insufficient_reviews (warn/block)

## Implementation Plan

### Step 1: Wire ReviewSettings into ReviewRouter
File: `src/review/router.py`

- Add `review_settings: Optional[ReviewSettings]` parameter to `__init__`
- Pass settings from workflow engine when creating router
- Store settings for fallback logic

### Step 2: Implement Fallback Chain in Executors
File: `src/review/api_executor.py` (primary change)

```python
def execute_with_fallbacks(
    self,
    review_type: str,
    primary_model: str,
    fallback_chain: list[str]
) -> ReviewResult:
    """Try primary model, then fallbacks on failure."""
    models_to_try = [primary_model] + fallback_chain

    for model in models_to_try:
        try:
            result = self._execute_single(review_type, model)
            if result.success:
                result.model_used = model
                result.was_fallback = model != primary_model
                return result
        except Exception as e:
            logger.warning(f"Model {model} failed: {e}, trying next fallback")
            continue

    # All models failed
    return ReviewResult(
        success=False,
        error=f"All models failed: {models_to_try}"
    )
```

### Step 3: Add Review Tracking & Threshold Check
File: `src/review/router.py`

```python
def execute_all_reviews(self) -> dict[str, ReviewResult]:
    """Execute all reviews and check minimum threshold."""
    results = {}
    successful_count = 0

    for review_type in get_all_review_types():
        result = self._execute_with_fallbacks(review_type)
        results[review_type] = result
        if result.success:
            successful_count += 1

    # Check minimum_required threshold
    min_required = self.settings.minimum_required
    if successful_count < min_required:
        self._handle_insufficient_reviews(
            successful_count,
            min_required,
            self.settings.on_insufficient_reviews
        )

    return results
```

### Step 4: Implement on_insufficient_reviews Behavior
File: `src/review/router.py`

```python
def _handle_insufficient_reviews(
    self,
    count: int,
    minimum: int,
    action: str
) -> None:
    """Handle case when not enough reviews succeeded."""
    msg = f"Only {count} of {minimum} reviews completed successfully"

    if action == "block":
        raise ReviewThresholdError(msg)
    else:  # "warn"
        logger.warning(f"[REVIEW WARNING] {msg}. Proceeding with available reviews.")
```

### Step 5: Update CLI to Pass Settings
File: `src/cli.py`

When running reviews, load workflow settings and pass to ReviewRouter:
```python
from .schema import ReviewSettings
# ... in review command
settings = engine.settings.reviews
router = ReviewRouter(working_dir, review_settings=settings)
```

## Files to Modify

1. `src/review/router.py` - Add settings parameter, fallback logic, threshold check
2. `src/review/api_executor.py` - Add execute_with_fallbacks method
3. `src/review/result.py` - Add was_fallback and fallback_model fields
4. `src/cli.py` - Pass ReviewSettings to router

## Files NOT to Modify
- `src/schema.py` - Already has ReviewSettings
- `workflow.yaml` - Already has configuration
- `src/default_workflow.yaml` - Already has configuration
- `src/engine.py` - Already has settings property

## Test Cases

1. **Primary model succeeds** - Use primary, no fallback
2. **Primary fails, fallback1 succeeds** - Use fallback1, log warning
3. **All fallbacks fail** - Return aggregated error
4. **3 of 5 reviews succeed (threshold met)** - Proceed with warning
5. **2 of 5 reviews succeed (below threshold, warn mode)** - Log warning, continue
6. **2 of 5 reviews succeed (below threshold, block mode)** - Raise exception

## Risk Assessment

- **Low risk**: Additive changes, doesn't modify existing successful paths
- **Backward compatible**: Default behavior unchanged if no settings provided
- **Graceful degradation**: Falls back to current behavior on any error

## Estimated Effort

- Implementation: 2-3 hours
- Testing: 1 hour
- Documentation: 30 minutes
