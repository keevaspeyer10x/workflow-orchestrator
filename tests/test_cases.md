# Test Cases: V3 Pre-Implementation Checklist

## Verification Tests

### Item 1: Rollback Point
```bash
git tag -l | grep v2.0-stable  # Should show v2.0-stable
git show v2.0-stable --quiet   # Should show tag info
```

### Item 2: Tests Pass
```bash
pytest --tb=short -q
# Expected: All tests pass (or known failures documented)
```

### Item 3: Emergency Override
```bash
ORCHESTRATOR_EMERGENCY_OVERRIDE=human-override-v3 orchestrator status
# Expected: Works even if mode detection would block
```

### Item 4: V3 Branch
```bash
git branch | grep v3-hybrid-orchestration  # Should show branch
git rev-parse --abbrev-ref HEAD           # Should show current branch
```

### Item 5: Environment Detection
Already verified:
- CLAUDECODE=1 ✓
- CLAUDE_CODE_ENTRYPOINT=sdk-ts ✓
- stdin.isatty()=False ✓

### Item 6: Rollback Docs
```bash
test -f ROLLBACK.md && echo "EXISTS" || echo "MISSING"
cat ROLLBACK.md | head -5  # Should show rollback instructions
```

### Item 7: Review Issues
```bash
gh issue list --state open --label "bug" | head -10
# Expected: No critical blocking bugs
```

### Item 8: Test Repo
```bash
test -d /tmp/orchestrator-dogfood-test/.git && echo "EXISTS" || echo "MISSING"
```

### Item 9: Dogfood Workflow
```bash
test -f /tmp/orchestrator-dogfood-test/.orchestrator.yaml && echo "EXISTS" || echo "MISSING"
```

## Success Criteria
All 9 verification commands should pass.
