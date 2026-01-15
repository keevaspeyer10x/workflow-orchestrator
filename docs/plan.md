# V3 Hybrid Orchestration - Phase 0 Implementation Plan

**Task:** Implement v3 hybrid orchestration Phase 0
**Date:** 2026-01-16
**Status:** Planning

## Overview

Phase 0 establishes the foundation for v3 hybrid orchestration with:
1. Robust operator mode detection (human vs LLM)
2. State file versioning with integrity checks
3. Comprehensive tests

## Files to Create

### 1. `src/mode_detection.py` (NEW)

**Purpose:** Centralized operator mode detection with audit logging.

**Key Components:**
- `OperatorMode` enum (HUMAN, LLM)
- `ModeDetectionResult` dataclass (mode, reason, confidence)
- `detect_operator_mode()` - Main detection function
- `is_llm_mode()` - Convenience boolean helper
- `log_mode_detection()` - Audit logging

**Detection Priority:**
1. Emergency override (`ORCHESTRATOR_EMERGENCY_OVERRIDE=human-override-v3`)
2. Explicit mode (`ORCHESTRATOR_MODE=llm|human`)
3. Claude Code env (`CLAUDECODE=1`, `CLAUDE_CODE_ENTRYPOINT`)
4. Codex detection (to be verified)
5. TTY heuristic (`stdin.isatty()`)
6. Conservative default: LLM mode (safer)

**Integration:** Replace existing `is_llm_mode()` in cli.py with import from this module.

### 2. `src/state_version.py` (NEW)

**Purpose:** Versioned state files with integrity verification.

**Key Components:**
- `STATE_VERSION = "3.0"` - Version constant
- `STATE_DIR_V3 = ".orchestrator/v3"` - Isolated v3 state directory
- `compute_state_checksum()` - SHA256 checksum for integrity
- `save_state_with_integrity()` - Atomic write with checksum
- `load_state_with_verification()` - Load with version/checksum validation

**Atomic Write Strategy:**
1. Write to temp file
2. fsync to ensure disk write
3. Atomic rename

**Security Features:**
- Checksum verification detects tampering
- Version check prevents v2/v3 state confusion
- Atomic writes prevent corruption

### 3. `tests/test_mode_detection.py` (NEW)

**Test Categories:**
- Emergency override tests (always works)
- Explicit mode tests (ORCHESTRATOR_MODE)
- Claude Code detection tests (CLAUDECODE, CLAUDE_CODE_ENTRYPOINT)
- TTY heuristic tests
- Conservative default tests

### 4. State integrity tests (in `tests/test_mode_detection.py`)

**Test Categories:**
- Save/load round-trip
- Tamper detection
- Version incompatibility rejection

## Execution Strategy

**Decision: Sequential execution**

**Rationale:**
- Phase 0 is small scope (2 files + tests, ~300 lines total)
- Files are tightly coupled (both need to work together for v3)
- Sequential allows clean integration and immediate testing
- Parallel agents would add coordination overhead without benefit

## Implementation Order

1. Create `src/mode_detection.py` with full implementation
2. Create `tests/test_mode_detection.py` with mode detection tests
3. Create `src/state_version.py` with full implementation
4. Add state integrity tests to test file
5. Update `src/cli.py` to use new mode_detection module
6. Run full test suite
7. Create rollback point (`git tag v3-phase0-complete`)

## Success Criteria

- [ ] All existing tests still pass (2019 tests)
- [ ] New mode detection tests pass (~10 tests)
- [ ] New state integrity tests pass (~5 tests)
- [ ] `is_llm_mode()` correctly detects Claude Code environment
- [ ] Emergency override works
- [ ] State checksum detects tampering

## Dependencies

- None - Phase 0 is foundation layer

## Risks

See `docs/risk_analysis.md`

## Test Cases

See `tests/test_cases.md`
