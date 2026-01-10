# Risk Analysis: Multi-Model Review Fixes

## Overall Risk: LOW

All changes are localized to `src/cli.py` with no database, API, or architectural changes.

## Per-Fix Risk Assessment

| Fix | Risk | Rationale |
|-----|------|-----------|
| Add test file to git | None | Just staging existing file |
| Fix default_test bug | Low | Simple string change, improves correctness |
| Fix sops syntax | Low | String change, need to verify bash syntax |
| Smarter API key check | Medium | Changes behavior - fewer warnings shown |
| Show item_id in skip summary | Low | Additive change, no breaking impact |
| Highlight gate bypasses | Low | Visual formatting only |

## Key Risk: Smarter API Key Check

**Concern**: Might be too quiet, users won't realize reviews will fail

**Mitigation**: 
- Still warn when ALL keys missing
- Show which keys ARE available
- Reviews still fail loudly at REVIEW phase if truly misconfigured

**Acceptable** given constraint: "Maintain seamless UX for vibe coders"

## Backwards Compatibility
- All changes are backwards compatible
- No CLI flag changes
- No workflow.yaml schema changes
