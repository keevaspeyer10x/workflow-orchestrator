# Plan: Issue #88 - Plan Validation Review

## Objective

Add a `plan_validation` item to the PLAN phase that reviews `docs/plan.md` BEFORE implementation begins. This catches flawed designs while changes are cheap, complementing the existing Design Validation Review (#82) which validates post-implementation.

## Source Requirements

From issue #88 plus multi-model consensus and user feedback:

### Issue #88 Original Requirements
- [x] Add `plan_validation` item to PLAN phase after `risk_analysis`, before `user_approval`
- [x] 5 core checkpoints with severity levels
- [x] Verdict framework: APPROVED | NEEDS_REVISION | ESCALATE
- [x] Skip conditions: trivial_change, simple_bug_fix, well_understood_pattern
- [x] Update CHANGELOG.md

### Multi-Model Consensus Improvements (from /minds review)
- [x] Expand to 8 checkpoints (add: Security, Dependencies, Testing, Operational Readiness)
- [x] Add APPROVED_WITH_NOTES and BLOCKED verdicts
- [x] Define skip conditions concretely (not just subjective terms)
- [x] Add explicit context loading instruction

### User Requirements (from clarification)
- [x] **Objective-Driven Optimality**: Validate design is optimal for the *underlying objective*, not just "simplest"
- [x] **Request Completeness Check**: Ensure plan comprehensively addresses original request, flag missing items
- [x] **Skip Justification**: If items are deferred, require strong justification (option to create issues)

## Implementation Plan

### 1. Location
Add to `src/default_workflow.yaml` in PLAN phase:
- After: `risk_analysis` (line ~185)
- Before: `define_test_cases` (line ~187)

### 2. Item Structure

```yaml
- id: "plan_validation"
  name: "Plan Validation Review"
  description: |
    <comprehensive description with prompt>
  required: true
  skippable: true
  skip_conditions:
    - "trivial_change"      # <50 lines, 1 file, no logic change
    - "simple_bug_fix"      # Isolated fix, root cause confirmed, <20 lines
    - "well_understood_pattern"  # Standard boilerplate, no architectural decisions
  notes:
    - "[purpose] ..."
    - "[checkpoints] ..."
    - "[verdicts] ..."
    - "[never-skip] ..."
    - "[minds] ..."
```

### 3. Enhanced Prompt (Final Version)

Based on multi-model consensus + user requirements:

```
Read docs/plan.md completely, then validate BEFORE implementation.

## Pre-Check: Request Completeness
First, compare the plan against the original request/issue. List:
- Requirements ADDRESSED in plan (with section reference)
- Requirements MISSING from plan (flag for immediate attention)
- Requirements DEFERRED (must have strong justification + issue created)

## Checkpoints (in priority order)

1. **Request Completeness** (Critical): Does plan address ALL items from original request? Nothing missing or silently dropped? Deferred items have justification?

2. **Requirements Alignment** (Critical): All requirements traced to implementation steps? No scope creep? Testable acceptance criteria defined?

3. **Security & Compliance** (Critical): Auth/authz impacts? Data privacy? Input validation? Threat considerations for this change?

4. **Risk Mitigation** (Critical): Each identified risk has CONCRETE mitigation (not vague)? High-impact risks have rollback/disable plan?

5. **Objective-Driven Optimality** (High): Is this the optimal solution for the UNDERLYING OBJECTIVE (not just simplest)? Were alternatives evaluated against the actual goal? Trade-offs justified?

6. **Dependencies & Integration** (High): External services, APIs, libraries identified? Version constraints? Breaking change risks? Integration points mapped?

7. **Edge Cases & Failure Modes** (High): Error scenarios identified WITH handling strategies? Boundary conditions covered?

8. **Testing & Success Criteria** (High): How will success be measured? Test approach defined? What does "done" look like?

9. **Implementability** (Medium): Steps clear and ordered? No TBD/TODO in critical sections? Dependencies between steps identified?

10. **Operational Readiness** (Medium): Monitoring/logging needed? Rollout plan? How to diagnose failures?

## Output Format
For each issue found:
- **Section**: Quote from plan.md
- **Checkpoint**: Which checkpoint failed
- **Severity**: BLOCKING | SHOULD_FIX | CONSIDER
- **Gap**: What's wrong or missing
- **Fix**: Specific remediation (not vague "improve this")

Then list what's done WELL (minimum 2 items) to prevent over-criticism bias.

## Verdict
APPROVED - Plan is sound, proceed to implementation
APPROVED_WITH_NOTES - Minor suggestions, non-blocking, proceed
NEEDS_REVISION - Issues must be fixed, re-review after changes (max 2 cycles)
BLOCKED - Cannot evaluate, missing critical information
ESCALATE - Fundamental gaps requiring human/architectural decision

Include: one-sentence rationale for verdict
```

### 4. Skip Conditions (Concrete Definitions)

```yaml
skip_conditions:
  - "trivial_change"           # <50 lines, ≤2 files, no logic/behavior change
  - "simple_bug_fix"           # Isolated fix, root cause confirmed, <20 lines
  - "well_understood_pattern"  # Standard boilerplate following existing template
```

**Never skip when** (add to notes):
- Security-sensitive changes (auth, crypto, secrets)
- Data migrations or schema changes
- Breaking API/contract changes
- Multi-system or cross-service impact
- New external dependencies

### 5. Files to Modify

1. **src/default_workflow.yaml** - Add plan_validation item
2. **CHANGELOG.md** - Document the new feature

## Execution Mode

**Sequential execution** - This is a single-file change with no parallelizable subtasks. The implementation involves:
1. Edit one YAML file (default_workflow.yaml)
2. Edit one markdown file (CHANGELOG.md)
3. Validate YAML syntax
4. Run tests

No benefit from parallel agents for this task.

## Acceptance Criteria

From issue #88:
- [ ] `plan_validation` item added to PLAN phase in `src/default_workflow.yaml`
- [ ] Positioned after `risk_analysis`, before `user_approval`
- [ ] Prompt includes all checkpoints with severity levels
- [ ] Skip conditions documented with concrete definitions
- [ ] CHANGELOG.md updated

Additional (from consensus + user):
- [ ] 10 checkpoints (expanded from 5)
- [ ] 5 verdicts (expanded from 3)
- [ ] Request completeness check included
- [ ] Objective-driven optimality emphasized
- [ ] Never-skip scenarios documented
