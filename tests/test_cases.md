# V3 Hybrid Orchestration - Phase 1 Test Cases

**Task:** Implement v3 hybrid orchestration Phase 1: Phase Types & Tool Scoping
**Date:** 2026-01-16

## Test Categories

### Category 1: PhaseType Schema (3 tests)

| ID | Test Case | Expected | Priority |
|----|-----------|----------|----------|
| PT-01 | PhaseType enum has all values | STRICT, GUIDED, AUTONOMOUS present | High |
| PT-02 | PhaseDef accepts phase_type | No validation error | High |
| PT-03 | PhaseDef accepts intended_tools | No validation error | High |

### Category 2: LLM Mode Blocking (4 tests)

| ID | Test Case | Expected | Priority |
|----|-----------|----------|----------|
| LM-01 | Skip blocked in LLM mode (strict phase) | Error message, blocked | Critical |
| LM-02 | Skip allowed in human mode | Success | Critical |
| LM-03 | Force blocked in LLM mode | Error message, blocked | Critical |
| LM-04 | Force allowed in human mode | Success | High |

### Category 3: Emergency Override (2 tests)

| ID | Test Case | Expected | Priority |
|----|-----------|----------|----------|
| EO-01 | Emergency override bypasses LLM block | Success | Critical |
| EO-02 | Invalid override doesn't bypass | Blocked | High |

## Test File

Tests in: `tests/test_phase_types.py`
