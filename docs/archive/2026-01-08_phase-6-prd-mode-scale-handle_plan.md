# Plan: Review Types Single Source of Truth

## Problem Statement

Review types (security_review, quality_review, consistency_review, holistic_review, vibe_coding_review)
are currently defined in **3 separate places**:

1. **workflow.yaml** (lines 70-74): `settings.reviews.types` - Maps review types to tools
2. **prompts.py** (lines 259-271): `REVIEW_TOOLS` dict - Hardcoded mapping
3. **model_registry.py** (lines 353-360): `category_mapping` in `get_latest_model()`

This caused a **bug** when adding `vibe_coding_review` - someone forgot to update all 3 places.

## Solution: Make workflow.yaml the Single Source of Truth

### Design Principles

1. **workflow.yaml defines review types** - The authoritative list of review types and their tool assignments
2. **Code reads configuration at runtime** - No hardcoded review type lists
3. **Fail-fast on misconfiguration** - Validate early, with clear error messages
4. **Backward compatibility** - Support both `_review` suffix and short names (security, quality, etc.)

### Implementation Steps

#### Step 1: Create ReviewConfig module (`src/review/config.py`)

New module that:
- Loads review type configuration from workflow.yaml
- Provides `get_tool_for_review()` function (replaces hardcoded `get_tool()`)
- Provides `get_available_review_types()` function
- Validates review types against known prompts
- Caches configuration for performance

```python
# Key functions:
def get_review_config(workflow_def: WorkflowDef = None) -> ReviewConfig
def get_tool_for_review(review_type: str) -> str  # Replaces get_tool()
def get_available_review_types() -> list[str]
```

#### Step 2: Update prompts.py

- Remove hardcoded `REVIEW_TOOLS` dict
- Update `get_tool()` to call `config.get_tool_for_review()`
- Keep `REVIEW_PROMPTS` - these are the actual prompt templates (valid to keep in code)

#### Step 3: Update model_registry.py

- Remove hardcoded `category_mapping` from `get_latest_model()`
- Add `get_tool_for_review()` call to resolve review types to tool categories
- Keep the `latest_models` dict - model versions are runtime data

#### Step 4: Update cli_executor.py and api_executor.py

- Import from new config module
- No other changes needed (they already call `get_tool()`)

#### Step 5: Add validation

In `src/review/config.py`:
- Validate that each review type in workflow.yaml has a corresponding prompt template
- Validate that tool mappings point to valid tools (codex, gemini, grok)
- Log warning if using deprecated review type names

In `src/schema.py`:
- Add optional `ReviewsSettings` Pydantic model for type safety
- Validate settings.reviews structure at workflow load time

#### Step 6: Update default_workflow.yaml

Ensure `src/default_workflow.yaml` has the same review types section as `workflow.yaml`.

### Files to Modify

| File | Change |
|------|--------|
| `src/review/config.py` | **CREATE** - New configuration module |
| `src/review/prompts.py` | Remove `REVIEW_TOOLS`, update `get_tool()` |
| `src/model_registry.py` | Remove `category_mapping`, use config |
| `src/review/__init__.py` | Export new config functions |
| `src/default_workflow.yaml` | Ensure matches workflow.yaml |
| `tests/review/test_config.py` | **CREATE** - Tests for new module |

### Validation Rules

1. Every review type in `settings.reviews.types` must have a prompt in `REVIEW_PROMPTS`
2. Every tool in `settings.reviews.types` must be one of: `codex`, `gemini`, `grok`
3. Every phase item ID ending in `_review` should match a configured review type

### Example Configuration (already in workflow.yaml)

```yaml
settings:
  reviews:
    enabled: true
    types:
      security_review: codex
      quality_review: codex
      consistency_review: gemini
      holistic_review: gemini
      vibe_coding_review: grok
```

### Test Plan

1. Unit tests for `ReviewConfig` class
2. Test that `get_tool_for_review()` returns correct tools
3. Test validation errors for missing prompts
4. Test validation errors for invalid tools
5. Test backward compatibility with short names (security vs security_review)
6. Integration test: run reviews end-to-end with new config

### Rollback Plan

If issues arise:
1. `REVIEW_TOOLS` dict is preserved as `_LEGACY_REVIEW_TOOLS` (commented)
2. Can quickly revert by uncommenting and removing config dependency

### Success Criteria

- [ ] Review types defined ONLY in workflow.yaml
- [ ] Adding a new review type requires changes in ONLY 2 places:
  1. workflow.yaml (type → tool mapping)
  2. prompts.py (add the prompt template)
- [ ] All existing tests pass
- [ ] New validation catches configuration errors at startup
