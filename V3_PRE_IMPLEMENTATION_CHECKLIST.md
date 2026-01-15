# V3 Pre-Implementation Checklist

**Status:** COMPLETED
**Last Updated:** 2026-01-16

Complete ALL items in order before starting v3 implementation.

---

## 🔴 BLOCKING: Must Complete First

### 1. [x] Create Rollback Point

```bash
cd /home/keeva/workflow-orchestrator
git stash  # if uncommitted changes
git tag v2.0-stable -m "Last stable v2 before v3 refactor"
git push origin v2.0-stable
```

**Verify:**
```bash
git tag -l | grep v2.0-stable  # Should show v2.0-stable
```

### 2. [x] Verify Tests Pass

```bash
cd /home/keeva/workflow-orchestrator
pip install -e ".[dev]"
pytest --tb=short -q
```

**If tests fail:** Fix them FIRST or create issue and defer.

### 3. [x] Add Emergency Override (Immediate Safety Net)

Add to `src/cli.py` BEFORE any other changes:

```python
import os

def _emergency_override_active():
    """Check if emergency override is set."""
    return os.environ.get('ORCHESTRATOR_EMERGENCY_OVERRIDE') == 'human-override-v3'

# Add check at start of advance/skip/force commands:
# if not _emergency_override_active() and is_llm_mode():
#     print("Error: This command is blocked in LLM mode.")
#     return
```

**Verify:**
```bash
ORCHESTRATOR_EMERGENCY_OVERRIDE=human-override-v3 orchestrator status
# Should work even if other detection fails
```

### 4. [x] Create v3 Branch

```bash
git checkout -b v3-hybrid-orchestration
```

---

## 🟡 High Value: Before Phase 3

### 5. [x] Verify Actual Environment Detection Works

Run this IN Claude Code to verify signals:

```python
import os
# These should return values in Claude Code:
print("CLAUDECODE:", os.environ.get('CLAUDECODE'))  # Should be "1"
print("CLAUDE_CODE_ENTRYPOINT:", os.environ.get('CLAUDE_CODE_ENTRYPOINT'))  # Should exist
```

**Results from 2025-01-15:**
- `CLAUDECODE=1` ✓
- `CLAUDE_CODE_ENTRYPOINT=sdk-ts` ✓
- `stdin.isatty()=False` ✓

### 6. [x] Document Rollback Procedure

Create `ROLLBACK.md`:

```bash
cat > ROLLBACK.md << 'EOF'
# Emergency Rollback to v2

## Quick Rollback
git checkout v2.0-stable
pip install -e .
rm -rf .orchestrator/v3/

## Verify
orchestrator --version
orchestrator status
EOF
```

### 7. [x] Review Existing Issues

Check if any existing issues should be fixed first:

```bash
gh issue list --state open --label "bug"
```

**Known issues to consider:**
- #70: filelock dependency (may already be fixed)
- #69: Settings changes mid-session (defer)

---

## 🟢 Recommended: Before Phase 5

### 8. [x] Set Up Isolated Test Repo

```bash
mkdir /tmp/orchestrator-dogfood-test
cd /tmp/orchestrator-dogfood-test
git init
echo "# Test Repo" > README.md
git add -A && git commit -m "init"
```

### 9. [x] Prepare Dogfood Workflow

Copy workflow config to test repo for dogfooding.

---

## Completion Sign-Off

| Item | Completed | Date | Notes |
|------|-----------|------|-------|
| Rollback point | [x] | 2026-01-16 | v2.0-stable tag created |
| Tests pass | [x] | 2026-01-16 | 2019 pass, 24 known failures |
| Emergency override | [x] | 2026-01-16 | is_llm_mode() + _emergency_override_active() added |
| v3 branch created | [x] | 2026-01-16 | v3-hybrid-orchestration branch |
| Env detection verified | [x] | 2025-01-15 | CLAUDECODE=1 works |
| Rollback documented | [x] | 2026-01-16 | ROLLBACK.md created |
| Issues reviewed | [x] | 2026-01-16 | No blocking bugs |
| Test repo ready | [x] | 2026-01-16 | /tmp/orchestrator-dogfood-test |
| Dogfood workflow | [x] | 2026-01-16 | .orchestrator.yaml copied |

---

## Start Implementation

Once ALL blocking items (1-4) are complete:

```bash
cd /home/keeva/workflow-orchestrator
git checkout v3-hybrid-orchestration

# Begin Phase 0 from implementation plan
# See: /home/keeva/ai-tool-bridge/docs/orchestrator_implementation_plan_v2.md
```
