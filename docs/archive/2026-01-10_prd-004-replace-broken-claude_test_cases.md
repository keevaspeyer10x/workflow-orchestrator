# Test Cases: Multi-Model Review Fixes

## Automated Tests

### API Key Check (check_review_api_keys)
1. **No keys set** → Should warn with full message
2. **One key set** → Should NOT warn (at least one method available)
3. **All keys set** → Should NOT warn
4. **Empty string key** → Should treat as missing

## Manual Verification

### Test File in Git
- `git status` should show test file staged

### default_test Bug
- Run `orchestrator start` with Python project
- Mismatch warning should say "npm test" not "npm run build"

### sops Command Syntax
- Copy suggested command and verify it's valid bash
- Should not have spaces around `=`

### Skip Summary with item_id
- Create workflow, skip an item, run `orchestrator finish`
- Should show `item_id: description` format

### Gate Bypass Highlighting
- Force-skip a gate item, run `orchestrator finish`
- Should show `⚠️ GATE BYPASSED:` prefix

## Existing Test Suite
- Run `pytest tests/` to ensure no regressions
