# Plan: Complete V3 Pre-Implementation Checklist

## Task
Complete all 9 items in V3_PRE_IMPLEMENTATION_CHECKLIST.md to prepare for orchestrator v3 refactor.

## Execution Strategy
**SEQUENTIAL EXECUTION** - Items must be done in order (e.g., can't create v3 branch before rollback tag).

## Items

### 🔴 BLOCKING (1-4)

1. **Create rollback point**
   - `git tag v2.0-stable -m "Last stable v2 before v3 refactor"`
   - `git push origin v2.0-stable`

2. **Verify tests pass**
   - `pytest --tb=short -q`
   - If failures: fix or document

3. **Add emergency override**
   - Add to src/cli.py: check for ORCHESTRATOR_EMERGENCY_OVERRIDE env var
   - This is a safety net if mode detection fails

4. **Create v3 branch**
   - `git checkout -b v3-hybrid-orchestration`

### 🟡 HIGH VALUE (5-7)

5. **Verify environment detection** ✅ ALREADY DONE
   - Confirmed: CLAUDECODE=1 exists in Claude Code
   - Confirmed: stdin.isatty()=False in Claude Code

6. **Document rollback procedure**
   - Create/update ROLLBACK.md with clear steps

7. **Review existing issues**
   - Check for blocking bugs before v3 work

### 🟢 RECOMMENDED (8-9)

8. **Set up isolated test repo**
   - Create /tmp/orchestrator-dogfood-test
   - Initialize git repo for safe testing

9. **Prepare dogfood workflow**
   - Copy .orchestrator.yaml to test repo

## Risk Assessment
- LOW RISK: All items are reversible
- Rollback tag ensures we can always go back to v2

## Test Cases
- Verify v2.0-stable tag exists after item 1
- Verify pytest passes after item 2
- Verify emergency override works after item 3
- Verify v3 branch exists after item 4
