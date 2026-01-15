# V3 Phase 5: Integration Handoff

## Context

V3 Hybrid Orchestration Phases 0-4 are complete. The modules exist but are NOT integrated into the CLI - they're dead code until Phase 5 is done.

**Branch:** `v3-hybrid-orchestration`
**Last commit:** `f9a5509 feat(v3): Phase 4 - Integration & Hardening with security fixes`

## What Exists (Not Wired Up Yet)

| Module | Purpose | Status |
|--------|---------|--------|
| `src/mode_detection.py` | Detect human vs LLM operator | Implemented, not called |
| `src/state_version.py` | V3 state with checksums | Implemented, not used |
| `src/gates.py` | Artifact-based validation | Implemented, not enforced |
| `src/checkpoint.py` | File locking, checkpoint chaining | Implemented, partially used |
| `src/audit.py` | Tamper-evident logging | Implemented, not logging |
| `src/health.py` | System health checks | Implemented, no CLI command |

## Phase 5 Tasks

### 1. Add `orchestrator health` Command (~15 min)
- Expose `HealthChecker` from `src/health.py` via CLI
- Add to `src/cli.py` as new subcommand
- Output: JSON health report or human-readable summary

### 2. Wire Up Mode Detection (~30 min)
- Call `detect_operator_mode()` at workflow start
- Store result in workflow state
- Log mode detection via audit logger
- Adjust behavior based on mode (e.g., skip manual gates in LLM mode)

### 3. Enable Audit Logging (~30 min)
- Initialize `AuditLogger` in orchestrator
- Log key operations: workflow start/finish, phase transitions, checkpoint create/restore
- Store in `.orchestrator/audit.jsonl`

### 4. Migrate State to V3 Directory (~1 hr)
- Use `.orchestrator/v3/state.json` instead of `.workflow_state.json`
- Use `save_state_with_integrity()` / `load_state_with_verification()`
- Handle migration from v2 state files gracefully
- Add `StateIntegrityError` handling

### 5. Gate Enforcement on Workflow Items (~1-2 hr)
- Parse gate definitions from `workflow.yaml` item metadata
- Call `gate.validate()` before marking items complete
- Block completion if gate fails
- Support: ArtifactGate, CommandGate, CompositeGate

## Test Requirements

- All existing 2126 tests must continue to pass
- Add integration tests for each wired-up feature
- Test v2 → v3 state migration path

## Definition of Done

- [ ] `orchestrator health` command works
- [ ] Mode detection runs at workflow start
- [ ] Audit log captures key operations
- [ ] State uses v3 directory with integrity checks
- [ ] Gates are enforced (at least ArtifactGate)
- [ ] All tests pass
- [ ] Multi-model review passes

## Commands to Start

```bash
cd /home/keeva/workflow-orchestrator
git status  # Should be on v3-hybrid-orchestration
orchestrator start "V3 Phase 5: CLI Integration" --constraints "Wire up existing v3 modules" --constraints "Don't break existing tests"
```

## Related Issues

```bash
orchestrator task list  # See tasks 13, 14 for Phase 5 items
```
