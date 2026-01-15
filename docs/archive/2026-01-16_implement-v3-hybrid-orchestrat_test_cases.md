# V3 Hybrid Orchestration - Phase 0 Test Cases

**Task:** Implement v3 hybrid orchestration Phase 0
**Date:** 2026-01-16

## Test Categories

### Category 1: Mode Detection (10 tests)

| ID | Test Case | Input | Expected Output | Priority |
|----|-----------|-------|-----------------|----------|
| MD-01 | Emergency override always works | `ORCHESTRATOR_EMERGENCY_OVERRIDE=human-override-v3`, `CLAUDECODE=1` | mode=HUMAN, confidence=high | Critical |
| MD-02 | Explicit LLM mode | `ORCHESTRATOR_MODE=llm` | mode=LLM, confidence=high | High |
| MD-03 | Explicit human mode | `ORCHESTRATOR_MODE=human` | mode=HUMAN, confidence=high | High |
| MD-04 | Claude Code detection (CLAUDECODE) | `CLAUDECODE=1` | mode=LLM, confidence=high | Critical |
| MD-05 | Claude Code detection (entrypoint) | `CLAUDE_CODE_ENTRYPOINT=sdk-ts` | mode=LLM, confidence=high | High |
| MD-06 | No TTY triggers LLM mode | `stdin.isatty()=False` | mode=LLM, confidence=medium | High |
| MD-07 | TTY suggests human mode | `stdin.isatty()=True`, `stdout.isatty()=True` | mode=HUMAN, confidence=medium | High |
| MD-08 | Unknown defaults to LLM | All signals absent | mode=LLM, confidence=low | High |
| MD-09 | is_llm_mode() returns boolean | `CLAUDECODE=1` | True | Medium |
| MD-10 | ModeDetectionResult has all fields | Any | mode, reason, confidence present | Medium |

### Category 2: State Integrity (5 tests)

| ID | Test Case | Input | Expected Output | Priority |
|----|-----------|-------|-----------------|----------|
| SI-01 | Save and load round-trip | Valid state dict | Same data + _version, _checksum, _updated_at | Critical |
| SI-02 | Tampered state detected | State with modified phase | ValueError with "integrity check failed" | Critical |
| SI-03 | Wrong version rejected | State with _version="2.0" | ValueError with "incompatible" | High |
| SI-04 | Missing checksum handled | State without _checksum | ValueError or graceful handling | Medium |
| SI-05 | Empty state rejected | Empty dict | Appropriate error | Medium |

### Category 3: State Versioning (3 tests)

| ID | Test Case | Input | Expected Output | Priority |
|----|-----------|-------|-----------------|----------|
| SV-01 | V3 state directory used | save_state_with_integrity() | File in .orchestrator/v3/ | High |
| SV-02 | Checksum excludes metadata | State with _checksum | Hash computed without _checksum field | High |
| SV-03 | Atomic write (no partial) | Interrupt during write | Either complete file or no file | Medium |

## Test Implementation Notes

### Mocking Requirements

- `os.environ` - Use `unittest.mock.patch.dict`
- `sys.stdin.isatty()` - Use `unittest.mock.patch.object`
- `sys.stdout.isatty()` - Use `unittest.mock.patch.object`

### Test Fixtures

```python
@pytest.fixture
def clean_env():
    """Clear all orchestrator-related env vars."""
    env_vars = [
        'ORCHESTRATOR_EMERGENCY_OVERRIDE',
        'ORCHESTRATOR_MODE',
        'CLAUDECODE',
        'CLAUDE_CODE_ENTRYPOINT',
        'CODEX',
    ]
    with patch.dict(os.environ, {}, clear=True):
        yield

@pytest.fixture
def temp_state_dir(tmp_path):
    """Create temporary state directory."""
    state_dir = tmp_path / ".orchestrator" / "v3"
    state_dir.mkdir(parents=True)
    return state_dir
```

### Coverage Targets

| Module | Target Coverage | Critical Paths |
|--------|-----------------|----------------|
| mode_detection.py | 95% | All detection branches |
| state_version.py | 90% | save/load/checksum |

## Acceptance Criteria

All tests must:
1. Pass with `pytest --tb=short`
2. Complete in < 5 seconds total
3. Have descriptive names and docstrings
4. Cover both happy path and error cases

## Test File Location

Tests will be added to: `tests/test_mode_detection.py`

This consolidates mode detection and state integrity tests in one file since they're closely related (both are Phase 0 foundation).
