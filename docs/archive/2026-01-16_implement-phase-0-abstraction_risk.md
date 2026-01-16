# Risk Analysis: Issues #89, #91, #39

## Executive Summary

| Issue | Risk Level | Impact | Reversibility |
|-------|------------|--------|---------------|
| #89 Fallback Models | LOW | Improves resilience | Fully reversible |
| #91 Design Validation | LOW | New opt-in feature | Fully reversible |
| #39 Minds Proxy | MEDIUM | Changes gate behavior | Reversible via config |

---

## Issue #89: Fallback Models on Quota Exhaustion

### Risk Level: LOW

### Positive Impacts
- **Resilience**: Workflows continue even when primary model quota exhausted
- **Transparency**: Logging which model actually responded
- **Flexibility**: Per-workflow and per-model fallback chains

### Potential Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Fallback model quality differs | Medium | Low | Log which model used, user can verify |
| Cost increase from fallback | Low | Low | Fallback only on quota, not every request |
| Breaking existing behavior | Very Low | Medium | Additive change, existing code paths unchanged |

### Failure Modes
1. **All models exhausted**: Clear error with list of tried models
2. **Fallback slow**: User sees status, can abort
3. **Inconsistent results**: Model logged, reproducible

### Rollback Plan
- Revert changes to `retry.py`, `config.py`, `api_executor.py`
- No data migration, no schema changes

---

## Issue #91: Automate Design Validation

### Risk Level: LOW

### Positive Impacts
- **Quality**: Catches plan deviations before merge
- **Objectivity**: LLM comparison vs self-assessment
- **Efficiency**: Automated check in REVIEW phase

### Potential Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| False positives (flagging OK changes) | Medium | Low | Lenient mode, user override |
| False negatives (missing issues) | Low | Medium | Still has human review |
| LLM quota during validation | Low | Low | Uses #89 fallback chain |
| Large diffs confuse LLM | Medium | Low | Truncate diff, focus on key changes |

### Failure Modes
1. **No plan.md exists**: Skip validation gracefully
2. **Git diff fails**: Clear error, manual validation
3. **LLM returns invalid JSON**: Retry with structured prompt

### Rollback Plan
- Remove `design_validator.py` and CLI command
- Remove REVIEW phase integration
- No data migration

---

## Issue #39: Zero-Human Mode with Minds as Proxy

### Risk Level: MEDIUM

### Positive Impacts
- **Autonomy**: Workflows complete without human intervention
- **Speed**: No waiting for human approval
- **Consistency**: Multi-model consensus reduces bias
- **Transparency**: Full audit trail with rollback commands

### Potential Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Wrong decision on important gate | Low | High | Certainty-based escalation, audit trail |
| All models agree incorrectly | Very Low | High | Re-deliberation, diverse model set |
| Model weights unfair | Low | Medium | Configurable weights, user can adjust |
| API costs from 5 model calls | Medium | Low | Only at gates, not every operation |
| Security-sensitive gates auto-approved | Low | High | CRITICAL risk always escalates |

### Detailed Risk Analysis

#### Wrong Decision Risk
**Scenario**: Minds approve a gate that should have been rejected (e.g., buggy code).

**Mitigations**:
1. **Certainty-based escalation**: Low certainty → escalate to human
2. **Re-deliberation**: Dissenting models get to explain, majority must address concerns
3. **Rollback commands**: Every decision includes how to undo
4. **Audit trail**: Human can review all decisions post-hoc
5. **Model diversity**: 5 different models from 5 vendors reduces groupthink

#### Runaway Automation Risk
**Scenario**: Agent runs autonomously but makes bad decisions.

**Mitigations**:
1. **Supervision modes**: Can start with `hybrid` (minds + human override)
2. **Auto-checkpoint**: Snapshot before each gate for rollback
3. **Decision report**: Summary at workflow end for review
4. **Escalation for CRITICAL**: Human always sees critical decisions

#### API Cost Risk
**Scenario**: 5 model calls per gate × many gates = expensive.

**Mitigations**:
1. **Gate consolidation**: Not every workflow item is a gate
2. **Caching**: Similar gates can reuse reasoning
3. **Configurable models**: Use cheaper models in model list
4. **Fallback chains**: If one model fails, try cheaper alternative

### Failure Modes

1. **All models fail (quota/network)**: Uses #89 fallback, escalates if all fail
2. **Re-deliberation loops**: Max 1 round, then decide
3. **Audit file corrupted**: Append-only JSONL, easy recovery
4. **Wrong rollback command**: Commands are generated, user verifies before running

### Rollback Plan

**Immediate**:
```yaml
settings:
  supervision:
    mode: supervised  # Disable zero_human
```

**Full removal**:
- Delete `src/gates/minds_proxy.py`
- Revert `cli.py` changes
- Human approval gates work as before

---

## Cross-Cutting Concerns

### API Key Management
All three issues rely on API keys for external models.

**Risk**: Missing API keys cause failures.

**Mitigation**:
- Clear error messages
- Fallback chain tries multiple providers
- SOPS encryption for secure key storage

### Testing Coverage
| Issue | Unit Tests | Integration Tests | E2E Tests |
|-------|------------|-------------------|-----------|
| #89 | ✓ Required | ✓ Required | ○ Optional |
| #91 | ✓ Required | ✓ Required | ○ Optional |
| #39 | ✓ Required | ✓ Required | ✓ Required |

### Backwards Compatibility
- #89: Fully compatible, additive changes
- #91: Fully compatible, new command
- #39: Compatible via config (`supervision.mode: supervised`)

---

## Decision Matrix

| Question | Decision | Rationale |
|----------|----------|-----------|
| Proceed with #89? | YES | Low risk, high value |
| Proceed with #91? | YES | Low risk, addresses pain point |
| Proceed with #39? | YES with caution | Medium risk, start with hybrid mode |
| Default supervision mode? | `hybrid` | Conservative start, user opts into `zero_human` |
| Default threshold? | 0.6 (60%) | Supermajority weighted, per user preference |

---

## Monitoring Plan

### Metrics to Track
1. **Fallback frequency**: How often fallbacks triggered
2. **Validation accuracy**: False positive/negative rate
3. **Minds decision quality**: Post-hoc human agreement rate
4. **Escalation rate**: % of gates escalated to human
5. **Rollback frequency**: How often users rollback minds decisions

### Alerts
- High fallback rate (>50%) → investigate primary model
- High escalation rate (>30%) → threshold may be too conservative
- Any rollback → review decision for pattern
