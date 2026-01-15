# Issues #65 and #66: CLI Review Choices + Model DRY Refactor - Risk Analysis

## Issue #65: CLI Review Type Choices

### Risk Level: LOW

**Risks:**
1. **Import Error**: If `get_all_review_types()` fails to import at CLI startup
   - Mitigation: The function already exists and is tested
   - Fallback: Keep hardcoded list as fallback (not recommended, defeats purpose)

2. **Empty List**: If registry returns empty list
   - Mitigation: Registry always has 5 defined types (static, not API-dependent)
   - Impact: Low - this would be a bug in the registry itself

**Impact Assessment:**
- Breaking change: No (additive - adds `vibe_coding` option)
- Backwards compatible: Yes (existing review types still work)
- Recovery: Trivial (revert 1 line)

## Issue #66: Model Version DRY Refactor

### Risk Level: MEDIUM

**Risks:**
1. **Circular Import**: `model_registry.py` imports from `review.config`, and vice versa
   - Mitigation: Use lazy imports or move model resolution to a single module
   - Already addressed: `model_registry._resolve_category()` handles this

2. **Model ID Format Mismatch**: CLI vs API use different formats
   - CLI: `gpt-5.2-codex-max` (bare)
   - API: `openai/gpt-5.2-codex-max` (prefixed)
   - Mitigation: Registry already handles both via `get_latest_model()`

3. **Runtime vs Import-time Resolution**: Moving from static dict to function calls
   - Risk: Performance impact if called frequently
   - Mitigation: Low frequency (once per review run)

4. **Test Breakage**: Tests may mock hardcoded values
   - Mitigation: Update tests to use registry or mock registry

**Impact Assessment:**
- Breaking change: No (external API unchanged)
- Backwards compatible: Yes (same model IDs returned)
- Recovery: Medium (multiple files, but straightforward revert)

## Overall Risk: LOW-MEDIUM

The changes are:
- Well-isolated (specific files, specific functions)
- Additive (#65) or internal refactor (#66)
- Easy to verify (run `orchestrator review vibe_coding`)
- Easy to revert if needed
