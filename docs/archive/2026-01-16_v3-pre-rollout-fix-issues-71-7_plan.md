# V3 Phase 5: CLI Integration Plan

## Overview
Wire up existing v3 modules into the CLI. All modules are implemented and tested individually - this phase integrates them.

## Implementation Tasks

### Task 1: Add `orchestrator health` Command
**Files:** `src/cli.py`
**Approach:**
- Add `health` subparser near other diagnostic commands
- Create `cmd_health()` function that:
  - Initializes `HealthChecker` from `src/health.py`
  - Runs `full_check()`
  - Outputs JSON (with `--json` flag) or human-readable summary

### Task 2: Wire Up Mode Detection at Workflow Start
**Files:** `src/cli.py` (cmd_start)
**Approach:**
- Call `detect_operator_mode()` at start of `cmd_start()`
- Store result in workflow state metadata
- Log via audit logger
- Skip manual gates in LLM mode (already partially implemented)

### Task 3: Enable Audit Logging
**Files:** `src/cli.py`, `src/engine.py`
**Approach:**
- Create global `AuditLogger` instance at CLI init
- Log events: workflow_start, workflow_finish, phase_transition, checkpoint_create/restore
- Store in `.orchestrator/audit.jsonl`

### Task 4: Migrate State to V3 Directory
**Files:** `src/engine.py`, `src/path_resolver.py`
**Approach:**
- Use `.orchestrator/v3/state.json` instead of `.workflow_state.json`
- Use `save_state_with_integrity()` / `load_state_with_verification()` from `src/state_version.py`
- Add migration path: detect v2 state file, migrate to v3 format
- Handle `StateIntegrityError` gracefully

### Task 5: Gate Enforcement on Workflow Items
**Files:** `src/cli.py` (cmd_complete), `src/engine.py`
**Approach:**
- Parse gate definitions from workflow.yaml item metadata
- Call `gate.validate()` before marking items complete
- Block completion if gate fails (return error message)
- Support ArtifactGate initially

## Execution Strategy
**Sequential execution** - tasks have dependencies:
1. Health command (standalone) - first
2. Audit logging (needed by mode detection)
3. Mode detection (uses audit logging)
4. State migration (biggest change, do carefully)
5. Gate enforcement (last, needs state working)

## Test Requirements
- All 2126 existing tests must pass
- Add integration tests for each feature
- Test v2 → v3 state migration path

## Risk Mitigation
- Create backup of state files before migration
- Use feature flags if needed
- Run full test suite after each major change
