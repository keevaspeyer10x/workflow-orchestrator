# V3 Hybrid Orchestration - Phase 1 Implementation Plan

**Task:** Implement v3 hybrid orchestration Phase 1: Phase Types & Tool Scoping
**Date:** 2026-01-16
**Status:** Planning

## Overview

Phase 1 adds phase autonomy levels and tool scoping documentation.

## Files to Modify

### 1. `src/schema.py`

**Add PhaseType enum:**
```python
class PhaseType(str, Enum):
    """Autonomy level for a phase."""
    STRICT = "strict"      # All items required in order, no skipping
    GUIDED = "guided"      # Can reorder items, limited skipping
    AUTONOMOUS = "autonomous"  # Flexible completion, can skip with reason
```

**Add to PhaseDef:**
```python
class PhaseDef(BaseModel):
    # ... existing fields ...
    phase_type: PhaseType = PhaseType.GUIDED  # Default to guided
    intended_tools: list[str] = Field(default_factory=list)  # Documentation only
```

### 2. `src/cli.py`

**Block --force/--skip in LLM mode for strict phases:**
- Import `is_llm_mode` from `src.mode_detection`
- In `skip` command: block if LLM mode and phase is strict
- In commands with `--force`: block if LLM mode

### 3. `tests/test_phase_types.py` (NEW)

Test cases:
- strict phase blocks skip in LLM mode
- guided phase allows reorder
- autonomous phase allows flexibility
- --force blocked in LLM mode
- --force allowed in human mode
- skip blocked in LLM mode for strict phases

## Execution Strategy

**Decision: Sequential execution**

**Rationale:**
- Small scope (schema changes + CLI changes + tests)
- Files are tightly coupled
- ~100 lines of code total

## Implementation Order

1. Add PhaseType enum to src/schema.py
2. Add phase_type and intended_tools to PhaseDef
3. Update src/cli.py to block --force/--skip in LLM mode
4. Create tests/test_phase_types.py
5. Run tests
6. Create rollback point (git tag v3-phase1-complete)

## Success Criteria

- All existing tests still pass
- New phase type tests pass (~6 tests)
- --force and --skip blocked in LLM mode
- Emergency override bypasses blocking
