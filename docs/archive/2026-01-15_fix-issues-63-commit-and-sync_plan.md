# Implementation Plan: Issues #65 and #66

## Summary
Fix CLI review type choices bug (#65) and refactor model versions to use single source of truth (#66 Phase 1).

## Issue #65: vibe_coding CLI Choices Bug

**Problem**: `orchestrator review vibe_coding` fails because CLI hardcodes choices.

**Solution**: Replace hardcoded list with dynamic `get_all_review_types()`.

**File**: `src/cli.py` line 6236-6238

**Before**:
```python
review_parser.add_argument('review_type', nargs='?',
                           choices=['security', 'consistency', 'quality', 'holistic', 'all'],
                           default='all', help='Review type to run (default: all)')
```

**After**:
```python
from src.review.registry import get_all_review_types

review_choices = list(get_all_review_types()) + ['all']
review_parser.add_argument('review_type', nargs='?',
                           choices=review_choices,
                           default='all', help='Review type to run (default: all)')
```

## Issue #66: Model Version DRY Refactor (Phase 1 Only)

**Problem**: Model versions hardcoded in 7+ files, requiring multi-file updates.

**Solution**: Make Python code use `model_registry.get_latest_model()`.

### Files to Update

1. **`src/review/api_executor.py`** (lines 24-27)
   - Replace `OPENROUTER_MODELS` dict with calls to `get_latest_model()`

2. **`src/review/config.py`** (lines 289-297)
   - Replace `DEFAULT_CLI_MODELS` and `DEFAULT_API_MODELS` with registry calls

3. **`src/schema.py`** (lines 183-185)
   - Replace hardcoded fallback chains with registry-based defaults

### Deferred (YAGNI)

- **Phase 2**: Workflow YAML tokens (`"latest"` or `"{{models.codex}}"`)
- **Phase 3**: Pattern-based capability detection for `NO_TEMPERATURE_MODELS`

These provide marginal benefit vs. complexity. Hardcoded YAML is acceptable since workflow.yaml is version-locked at workflow start.

## Test Cases

1. **CLI Review Choices Test**: Verify CLI accepts all registry review types
2. **Registry Sync Test**: Verify `get_all_review_types()` matches expected set
3. **Model Resolution Test**: Verify `get_latest_model()` returns valid models

## Execution Decision

**SEQUENTIAL execution** because:
- Issue #65 is a 1-line fix (trivial)
- Issue #66 changes touch related files
- Total changes are small (~20 lines)
- No benefit from parallelization for this scope
