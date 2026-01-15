# V3 Hybrid Orchestration - Phase 1 Risk Analysis

**Task:** Implement v3 hybrid orchestration Phase 1: Phase Types & Tool Scoping
**Date:** 2026-01-16

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing workflows | Low | High | Default PhaseType.GUIDED preserves current behavior |
| Over-restricting LLM | Medium | Medium | Emergency override always available |
| Schema validation errors | Low | Medium | Add with defaults, backward compatible |

## Detailed Analysis

### R1: Breaking Existing Workflows

**Risk:** Adding new required fields breaks existing workflow.yaml files

**Mitigation:**
- PhaseType defaults to GUIDED (current behavior)
- intended_tools defaults to empty list
- Both fields optional with sensible defaults

### R2: Over-Restricting LLM

**Risk:** Blocking --force/--skip makes LLM unable to complete workflows

**Mitigation:**
- Emergency override always bypasses restrictions
- GUIDED is default (allows some flexibility)
- Only STRICT phases fully enforce

### R3: Schema Validation Errors

**Risk:** New fields cause validation errors on load

**Mitigation:**
- Use Field(default_factory=...) for optional fields
- Test with existing workflow.yaml files
- Backward compatible schema changes

## Rollback Plan

```bash
git checkout v3-phase0-complete
pip install -e .
```

No state file changes in Phase 1.
