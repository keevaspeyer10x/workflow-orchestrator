# Issues #65 and #66: CLI Review Choices + Model DRY Refactor - Test Cases

## Issue #65: CLI Review Type Choices

### TC-65-1: CLI Accepts vibe_coding Review Type
**Input**: `orchestrator review vibe_coding --help`
**Expected**: Command parses successfully (no argparse error)

### TC-65-2: CLI Choices Match Registry
**Input**: Parse CLI choices from argparse
**Expected**: Choices include all items from `get_all_review_types()` plus 'all'
**Verification**:
```python
from src.review.registry import get_all_review_types
expected = set(get_all_review_types()) | {'all'}
# Verify CLI choices == expected
```

### TC-65-3: All Review Types Executable
**Input**: Run each review type individually
**Expected**: Each type starts execution (may fail due to missing API keys, but no argparse error)
```bash
for type in security quality consistency holistic vibe_coding; do
  orchestrator review $type --help
done
```

## Issue #66: Model Version DRY Refactor

### TC-66-1: get_latest_model Returns Valid IDs
**Input**: Call `get_latest_model()` for each category
**Expected**: Returns non-empty string with valid model ID format
```python
from src.model_registry import get_latest_model
for category in ['codex', 'gemini', 'grok', 'claude']:
    model = get_latest_model(category)
    assert model is not None
    assert '/' in model  # Has provider prefix
```

### TC-66-2: Review Type to Model Resolution
**Input**: Call `get_latest_model()` with review type names
**Expected**: Resolves correctly via `_resolve_category()`
```python
from src.model_registry import get_latest_model
# Review types should resolve to their tool categories
assert 'gpt' in get_latest_model('security').lower() or 'codex' in get_latest_model('security').lower()
assert 'gemini' in get_latest_model('consistency').lower()
assert 'grok' in get_latest_model('vibe_coding').lower()
```

### TC-66-3: API Executor Uses Registry
**Input**: Check that `api_executor.py` calls registry instead of hardcoded dict
**Expected**: No hardcoded `OPENROUTER_MODELS` dict with version strings
**Verification**: Grep for hardcoded model versions after refactor

### TC-66-4: Config Module Uses Registry
**Input**: Check `config.py` for hardcoded model versions
**Expected**: Uses `get_latest_model()` instead of static dicts
**Verification**: Grep for hardcoded model versions after refactor

### TC-66-5: Integration Test - Full Review Run
**Input**: `orchestrator review all` (with valid API keys)
**Expected**: All 5 review types execute using correct models from registry
**Note**: Requires API keys to be configured

## Regression Tests

### RT-1: Existing Review Types Still Work
**Input**: Run `orchestrator review security`
**Expected**: Executes security review as before

### RT-2: CLI Help Shows All Options
**Input**: `orchestrator review --help`
**Expected**: Help text shows all review types including vibe_coding

## Acceptance Criteria

- [ ] `orchestrator review vibe_coding` no longer fails with argparse error
- [ ] All 5 review types available in CLI choices
- [ ] `get_latest_model()` used instead of hardcoded strings in api_executor.py
- [ ] `get_latest_model()` used instead of hardcoded strings in config.py
- [ ] Existing test suite passes
- [ ] New tests added to prevent regression
