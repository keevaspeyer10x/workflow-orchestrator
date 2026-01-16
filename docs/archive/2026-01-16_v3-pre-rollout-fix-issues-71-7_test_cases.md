# V3 Phase 5: Test Cases

## Test 1: Health Command
- [ ] `orchestrator health` returns OK for healthy system
- [ ] `orchestrator health --json` returns valid JSON
- [ ] Health shows warning for missing state file
- [ ] Health shows error for corrupted state file

## Test 2: Mode Detection at Workflow Start
- [ ] `orchestrator start` logs mode detection result
- [ ] Mode stored in workflow state
- [ ] LLM mode detected when CLAUDECODE=1
- [ ] Human mode detected with TTY

## Test 3: Audit Logging
- [ ] Workflow start creates audit entry
- [ ] Workflow finish creates audit entry
- [ ] Phase transition creates audit entry
- [ ] Audit log verifies with `verify_integrity()`

## Test 4: V3 State Migration
- [ ] New workflow creates v3 state in `.orchestrator/v3/`
- [ ] V2 state file is migrated on first load
- [ ] StateIntegrityError raised for corrupted state
- [ ] Checksum validation works

## Test 5: Gate Enforcement
- [ ] ArtifactGate blocks completion when file missing
- [ ] ArtifactGate passes when file exists and not empty
- [ ] CommandGate runs command and checks exit code
- [ ] Clear error message when gate fails

## Existing Test Suite
- All 2126 existing tests must pass
- Run `pytest tests/` after each major change
