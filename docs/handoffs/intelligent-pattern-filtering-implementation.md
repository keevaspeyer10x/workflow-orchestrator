# Handoff: Complete Intelligent Pattern Filtering Implementation

## Context

We're implementing **Phase 6: Cross-Project Pattern Relevance** for the self-healing infrastructure. This enables patterns learned in one repo to help another while respecting context relevance.

**Migration Status**: ✅ SQL migration `002_intelligent_pattern_filtering.sql` has been run against Supabase.

## What's Already Done

### Design Documents
- `docs/designs/intelligent-pattern-filtering-v2.md` - Full design (reviewed by 5 AI models)

### Schema (Migration Applied)
- `migrations/002_intelligent_pattern_filtering.sql`
- New columns on `error_patterns`: `context`, `tags`, `last_failure_at`, `last_success_at`, `universality_score`, `project_count`, `resolution_source`, `verified_by`, `risk_level`, `is_evergreen`
- New junction table `pattern_project_applications` for per-project tracking
- New RPC functions: `record_pattern_application()`, `lookup_patterns_scored()`, `is_eligible_for_cross_project()`

### Python Code
- `src/healing/models.py` - Added `PatternContext` dataclass with `to_dict()`, `from_dict()`, `derive_tags()`
- `src/healing/context_extraction.py` - Added:
  - `extract_context()` - Main entry point
  - `detect_language()` - Language detection from patterns/file extensions
  - `detect_error_category()` - Category detection (dependency, syntax, etc.)
  - `wilson_score()` - Confidence-adjusted success rate
  - `calculate_recency_score()` - Exponential decay (30-day half-life)
  - `calculate_context_overlap()` - Hierarchical weighted matching
  - `calculate_relevance_score()` - Full scoring formula
  - `is_eligible_for_cross_project()` - Cross-project guardrails

## What Needs to Be Done

### 1. Update Supabase Client (`src/healing/supabase_client.py`)

Add methods:
```python
async def lookup_patterns_scored(
    self,
    fingerprint: str,
    language: str | None = None,
    error_category: str | None = None,
) -> list[dict]:
    """Call lookup_patterns_scored RPC function."""

async def record_pattern_application(
    self,
    fingerprint: str,
    project_id: str,
    success: bool,
    context: dict,
) -> None:
    """Call record_pattern_application RPC function."""

async def get_pattern_project_ids(self, fingerprint: str) -> list[str]:
    """Get list of projects where pattern has been used."""
```

### 2. Update HealingClient (`src/healing/client.py`)

Modify the three-tier lookup to use scored results:

```python
# Thresholds
SAME_PROJECT_THRESHOLD = 0.6
CROSS_PROJECT_THRESHOLD = 0.75

async def lookup(self, error: ErrorEvent) -> LookupResult:
    # Extract context from error
    context = extract_context(
        error.description,
        error.error_type,
        error.file_path,
        error.stack_trace,
        error.phase_id,
    )

    # Tier 1a: Exact match, same project
    result = await self._lookup_scored(error, context, same_project_only=True)
    if result and result.score >= SAME_PROJECT_THRESHOLD:
        return result

    # Tier 1b: Exact match, cross-project (with guardrails)
    result = await self._lookup_scored(error, context, same_project_only=False)
    if result and result.score >= CROSS_PROJECT_THRESHOLD:
        if is_eligible_for_cross_project(result.pattern):
            return result

    # Tier 2: RAG (filter by language first)
    # ... existing RAG logic, but filter by language

    # Tier 3: Causality
    # ... existing causality logic
```

### 3. Update Detectors to Capture Context

Update each detector in `src/healing/detectors/` to populate the `context` field:

```python
# In WorkflowLogDetector._parse_event():
error = ErrorEvent(...)
error.context = extract_context(
    error.description,
    error.error_type,
    error.file_path,
    error.stack_trace,
    error.phase_id,
)
```

Apply same pattern to:
- `src/healing/detectors/workflow_log.py`
- `src/healing/detectors/subprocess.py`
- `src/healing/detectors/transcript.py`
- `src/healing/detectors/hook.py`

### 4. Update Backfill (`src/healing/backfill.py`)

Update `_extract_error()` to populate context:

```python
def _extract_error(self, event: dict) -> Optional[ErrorEvent]:
    # ... existing code ...

    # Add context extraction
    error.context = extract_context(
        error.description,
        error.error_type,
        error.file_path,
        error.stack_trace,
        event.get("phase_id"),
    )

    return error
```

### 5. Update `record_fix_result` to Track Per-Project

Update `supabase_client.record_fix_result()` to call `record_pattern_application()`:

```python
async def record_fix_result(
    self,
    fingerprint: str,
    success: bool,
    context: PatternContext | None = None,
) -> None:
    # Call the new RPC function
    await self.client.rpc(
        "record_pattern_application",
        {
            "p_fingerprint": fingerprint,
            "p_project_id": self.project_id,
            "p_success": success,
            "p_context": context.to_dict() if context else {},
        },
    ).execute()
```

### 6. Export New Modules from `__init__.py`

Add to `src/healing/__init__.py`:
```python
from .models import PatternContext
from .context_extraction import (
    extract_context,
    detect_language,
    detect_error_category,
    wilson_score,
    calculate_relevance_score,
    is_eligible_for_cross_project,
)
```

### 7. Write Tests

Create `tests/healing/test_context_extraction.py`:
- `test_detect_language_python` - Python patterns detected
- `test_detect_language_javascript` - JavaScript patterns detected
- `test_detect_language_file_extension` - File extension takes precedence
- `test_detect_error_category` - Category detection works
- `test_wilson_score` - Sample size handling (1/1 < 95/100)
- `test_context_overlap` - Hierarchical matching
- `test_relevance_score` - Full formula calculation
- `test_cross_project_eligibility` - Guardrails enforced

Create `tests/healing/test_scored_lookup.py`:
- `test_same_project_priority` - Same project scores higher
- `test_cross_project_with_guardrails` - Eligibility checked
- `test_language_filtering` - Mismatched language penalized

### 8. Run Tests and Fix Issues

```bash
pytest tests/healing/ -v
pytest tests/ -v  # Full suite
```

## Key Files to Reference

- `docs/designs/intelligent-pattern-filtering-v2.md` - Full design
- `src/healing/context_extraction.py` - Scoring formulas
- `migrations/002_intelligent_pattern_filtering.sql` - RPC functions

## Scoring Formula Summary

```
score = (
    0.30 * wilson_score(success, total) +      # Confidence-adjusted success
    0.25 * context_overlap +                    # Hierarchical matching
    0.15 * universality +                       # log(project_count)
    0.15 * recency +                            # 30-day half-life decay
    0.15 * (1 - failure_penalty)               # Recent failures hurt
) * same_project_multiplier * risk_multiplier

# Same project: 1.2x boost (not additive)
# Risk: low=1.0, medium=0.95, high=0.85, critical=0.70
```

## Cross-Project Guardrails

Pattern must have:
- ≥3 different projects with success
- ≥5 total successes
- Wilson score ≥0.7

## Notes

- The SQL migration has already been run
- Context extraction is complete in `context_extraction.py`
- Focus on integrating into existing code paths
- All changes should be backward compatible (new columns have defaults)
