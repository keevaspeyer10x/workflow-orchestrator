# Implementation Plan: Issues #89, #91, #39

## Overview

Implementing three related improvements for resilience and autonomous operations:

1. **#89 - Fallback models on quota exhaustion** (foundation)
2. **#91 - Automate design validation** (review automation)
3. **#39 - Zero-Human Mode with Minds as Proxy** (autonomous gates)

## User Requirements (from clarifying questions)

- **#89**: Per-workflow fallback config (not just hardcoded defaults)
- **#91**: Lenient validation - only flag major deviations, allow minor scope additions
- **#39**:
  - Configurable thresholds with supermajority (4/5) default
  - Model weighting (smarter models like GPT have more say)
  - Re-deliberation: models that disagree can be shown other reasoning to potentially change their vote
  - Certainty-based escalation (not just risk-based)
  - Full decision audit trail with rollback commands

## Implementation Order

```
#89 (Fallback) → #91 (Design Validation) → #39 (Minds Proxy)
```

---

## Issue #89: Fallback Models on Quota Exhaustion

### Current State
- `src/review/config.py`: Has `DEFAULT_FALLBACK_CHAINS` and `get_fallback_chain()`
- `src/review/retry.py`: Has `is_retryable_error()` and `retry_with_backoff()`
- Already reads from `workflow.yaml settings.reviews.fallback_chains`

### Gap Analysis
1. ❌ Quota exhaustion not explicitly in `is_retryable_error()` (it's in `is_permanent_error()`)
2. ❌ No logging of which fallback model was actually used
3. ❌ No model-specific fallback chains (just tool-level: gemini, codex, grok)
4. ❌ No tracking of fallback usage in audit trail

### Implementation

#### 1.1 Fix quota detection in retry.py
Move "quota exceeded" from permanent to retryable (it's a signal to try fallback).

```python
# In is_retryable_error(), add:
quota_patterns = ["quota exceeded", "rate limit", "429", "too many requests"]
```

#### 1.2 Add fallback tracking to result.py
```python
@dataclass
class ReviewResult:
    # ... existing fields
    model_used: str = ""           # Actual model that responded
    fallbacks_tried: list[str] = field(default_factory=list)  # Models attempted before success
```

#### 1.3 Log fallback decisions in api_executor.py
```python
def execute_with_fallback(self, ...) -> ReviewResult:
    fallbacks_tried = []
    for model in [primary] + fallback_chain:
        try:
            result = self._call_model(model, ...)
            result.model_used = model
            result.fallbacks_tried = fallbacks_tried
            logger.info(f"Review completed: {model}" + (f" (after {len(fallbacks_tried)} fallbacks)" if fallbacks_tried else ""))
            return result
        except QuotaError as e:
            fallbacks_tried.append(model)
            logger.warning(f"Quota exhausted for {model}, trying fallback...")
    raise AllModelsExhaustedError(...)
```

#### 1.4 Support per-model fallbacks in workflow.yaml
```yaml
settings:
  reviews:
    fallback_chains:
      gemini:
        - google/gemini-2.5-flash
        - anthropic/claude-3.5-sonnet
      # NEW: Model-specific overrides
      google/gemini-3-pro:
        - google/gemini-2.5-flash
        - openai/gpt-4-turbo
```

### Files to Modify
- `src/review/retry.py` - Fix quota detection
- `src/review/result.py` - Add fallback tracking fields
- `src/review/api_executor.py` - Log fallback usage
- `src/review/config.py` - Support model-specific chains

### Tests
- `tests/test_review_fallback.py` - Add quota detection tests
- `tests/test_fallback_tracking.py` - New file for tracking tests

---

## Issue #91: Automate Design Validation

### Overview
Automated comparison of plan.md against implementation diff using LLM.

### Implementation

#### 2.1 Create DesignValidationResult schema
```python
# src/review/design_validator.py
from dataclasses import dataclass
from typing import Literal

@dataclass
class DesignValidationResult:
    status: Literal["PASS", "PASS_WITH_NOTES", "NEEDS_REVISION"]
    planned_items_implemented: list[str]
    unplanned_additions: list[str]  # Scope creep
    deviations: list[str]           # Major deviations only (lenient)
    notes: str
    confidence: float               # 0.0-1.0
```

#### 2.2 Implement validation logic
```python
def validate_design(
    plan_path: Path = Path("docs/plan.md"),
    base_branch: str = "main",
    lenient: bool = True,  # User preference
) -> DesignValidationResult:
    """
    Compare plan against implementation.

    Args:
        plan_path: Path to plan file
        base_branch: Branch to diff against
        lenient: If True, only flag major deviations

    Returns:
        DesignValidationResult with findings
    """
    plan_content = plan_path.read_text()
    diff = get_git_diff(base_branch)

    prompt = f"""
    Compare this implementation plan against the actual code changes.

    MODE: {"LENIENT - only flag MAJOR deviations" if lenient else "STRICT - flag all deviations"}

    ## Plan
    {plan_content}

    ## Implementation (git diff)
    {diff}

    Analyze:
    1. Are all planned items implemented?
    2. Are there significant unplanned additions? (scope creep)
    3. Do implementations match the planned approach?
    4. Are there major deviations that need discussion?

    LENIENT MODE GUIDELINES:
    - Minor additions (logging, error handling, tests beyond spec) = OK
    - Refactoring to support the change = OK
    - Different variable names = OK
    - FLAG: Missing planned items, different architecture, new features

    Return JSON:
    {{
        "status": "PASS" | "PASS_WITH_NOTES" | "NEEDS_REVISION",
        "planned_items_implemented": ["item1", "item2"],
        "unplanned_additions": ["only significant ones"],
        "deviations": ["major only"],
        "notes": "summary",
        "confidence": 0.9
    }}
    """

    response = call_with_fallback("gemini", prompt)  # Uses #89 fallback
    return parse_result(response)
```

#### 2.3 CLI integration
```bash
# New command
orchestrator validate-design [--plan docs/plan.md] [--base main] [--strict]
```

#### 2.4 REVIEW phase integration
When `design_validation` item is reached, auto-run if plan.md exists.

### Files to Create/Modify
- `src/review/design_validator.py` - New module
- `src/cli.py` - Add `validate-design` command
- `src/default_workflow.yaml` - Update design_validation item hints

### Tests
- `tests/test_design_validation.py` - New test file

---

## Issue #39: Zero-Human Mode with Minds as Proxy

### Overview
Multi-model consensus system to replace human approval gates.

### Architecture

#### 3.1 Model Weighting System
```python
# src/gates/minds_proxy.py
MODEL_WEIGHTS = {
    "openai/gpt-5.2-codex-max": 2.0,    # High capability, double weight
    "anthropic/claude-3-opus": 2.0,
    "google/gemini-3-pro": 1.5,
    "xai/grok-4.1": 1.0,
    "deepseek/deepseek-chat": 0.5,       # Lower weight per user feedback
}

def weighted_vote(votes: dict[str, str]) -> tuple[str, float]:
    """Calculate weighted consensus."""
    approve_weight = sum(MODEL_WEIGHTS.get(m, 1.0) for m, v in votes.items() if v == "APPROVE")
    reject_weight = sum(MODEL_WEIGHTS.get(m, 1.0) for m, v in votes.items() if v == "REJECT")
    total_weight = approve_weight + reject_weight

    if approve_weight > reject_weight:
        return "APPROVE", approve_weight / total_weight
    return "REJECT", reject_weight / total_weight
```

#### 3.2 Re-Deliberation Feature
```python
def re_deliberate(
    dissenting_model: str,
    dissenting_vote: str,
    other_votes: dict[str, tuple[str, str]],  # model -> (vote, reasoning)
    gate_context: GateContext,
) -> tuple[str, str]:
    """
    Allow dissenting model to reconsider after seeing other reasoning.

    Returns:
        (new_vote, updated_reasoning)
    """
    prompt = f"""
    You previously voted {dissenting_vote} on this gate.

    Other models voted differently:
    {format_other_votes(other_votes)}

    Gate context:
    {gate_context}

    After considering the other perspectives:
    1. Do you want to change your vote?
    2. If not, explain what specific concern remains unaddressed.

    Return JSON:
    {{
        "final_vote": "APPROVE" | "REJECT",
        "changed": true/false,
        "reasoning": "why"
    }}
    """
    return call_model(dissenting_model, prompt)
```

#### 3.3 Certainty-Based Escalation
```python
@dataclass
class MindsDecision:
    gate_id: str
    decision: Literal["APPROVE", "REJECT", "ESCALATE"]
    certainty: float           # 0.0-1.0 (based on vote consensus + reasoning quality)
    risk_level: str
    model_votes: dict[str, str]
    weighted_consensus: float  # e.g., 0.85 = 85% weighted approval
    reasoning_summary: str
    rollback_command: str
    timestamp: datetime

def should_escalate(decision: str, certainty: float, risk_level: str) -> bool:
    """
    Certainty-based escalation (user preference).

    Even HIGH risk can proceed if certainty is high.
    Even LOW risk escalates if certainty is low.
    """
    # User said: "If it's critical but certain perhaps its OK to proceed"
    if certainty >= 0.95:
        # Very high certainty - proceed unless CRITICAL + unanimous reject
        return risk_level == "CRITICAL" and decision == "REJECT"

    if certainty >= 0.80:
        # High certainty - only escalate CRITICAL
        return risk_level == "CRITICAL"

    if certainty >= 0.60:
        # Medium certainty - escalate HIGH and CRITICAL
        return risk_level in ("HIGH", "CRITICAL")

    # Low certainty - always escalate
    return True
```

#### 3.4 Decision Audit Trail
```python
# .orchestrator/minds_decisions.jsonl
{
    "gate_id": "user_approval",
    "decision": "APPROVE",
    "certainty": 0.87,
    "weighted_consensus": 0.82,
    "model_votes": {
        "gpt-5.2": {"vote": "APPROVE", "reasoning": "Tests pass, no breaking changes"},
        "gemini-3": {"vote": "APPROVE", "reasoning": "Architecture looks solid"},
        "grok-4.1": {"vote": "REJECT", "reasoning": "Concerned about edge case X"},
        "claude-opus": {"vote": "APPROVE", "reasoning": "Edge case X is handled on line 45"},
        "deepseek": {"vote": "APPROVE", "reasoning": "LGTM"}
    },
    "re_deliberation": {
        "grok-4.1": {"changed": true, "final_vote": "APPROVE", "reasoning": "Convinced by Claude's analysis"}
    },
    "rollback_command": "git revert abc1234",
    "timestamp": "2026-01-16T12:34:56Z"
}
```

#### 3.5 CLI Commands
```bash
# View pending escalations
orchestrator escalations

# Generate minds decision report
orchestrator minds-report

# Rollback a minds decision
orchestrator rollback <decision_id>

# Configure supervision mode
orchestrator config set supervision_mode zero_human  # or: supervised, hybrid
```

#### 3.6 Configuration
```yaml
# workflow.yaml
settings:
  supervision:
    mode: zero_human  # supervised | hybrid | zero_human

    minds_proxy:
      enabled: true
      models:
        - openai/gpt-5.2-codex-max
        - google/gemini-3-pro
        - anthropic/claude-3-opus
        - xai/grok-4.1
        - deepseek/deepseek-chat

      # Weighted voting
      model_weights:
        openai/gpt-5.2-codex-max: 2.0
        anthropic/claude-3-opus: 2.0
        google/gemini-3-pro: 1.5
        deepseek/deepseek-chat: 0.5

      # Threshold: weighted approval required
      approval_threshold: 0.6  # 60% weighted approval (supermajority-ish)

      # Re-deliberation settings
      re_deliberation:
        enabled: true
        max_rounds: 1  # One chance to reconsider

      # Certainty thresholds for escalation
      escalation:
        auto_proceed_certainty: 0.95   # Proceed even on CRITICAL
        escalate_below_certainty: 0.60  # Always escalate if uncertain

    rollback:
      auto_checkpoint: true  # Create checkpoint before each gate
```

### Files to Create
- `src/gates/minds_proxy.py` - MindsGateProxy class
- `src/gates/minds_config.py` - Configuration loading
- `tests/test_minds_proxy.py` - Comprehensive tests

### Files to Modify
- `src/cli.py` - Add escalations, minds-report, rollback commands
- `src/enforcement/gates.py` - Integrate minds proxy
- `src/default_workflow.yaml` - Add supervision configuration

---

## Parallel Execution Assessment

### Decision: **SEQUENTIAL** execution

**Reasoning:**
1. #89 is foundation - #91 and #39 depend on it
2. #91 uses #89's fallback chains
3. #39 calls models that may need fallbacks from #89
4. Integration testing requires #89 working first

### Implementation Phases
1. **Phase 1**: Complete #89 fallback improvements (~30 min)
2. **Phase 2**: Implement #91 design validation (~45 min)
3. **Phase 3**: Implement #39 minds proxy (~1.5 hours)

---

## Risk Assessment

| Issue | Risk | Mitigation |
|-------|------|------------|
| #89 | LOW | Additive change, doesn't break success path |
| #91 | LOW | New command, opt-in usage |
| #39 | MEDIUM | Changes gate behavior |

### #39 Mitigations
1. Start with `hybrid` mode (minds decide but human can override)
2. Auto-checkpoint before each gate for easy rollback
3. Certainty-based escalation catches uncertain decisions
4. Re-deliberation gives dissenting models a voice
5. Full audit trail for post-hoc review

---

## Test Strategy

1. **Unit tests** for each new module
2. **Integration tests** for fallback chain through design validation
3. **Mock multi-model responses** for minds proxy tests
4. **End-to-end test**: Run workflow in zero_human mode with recorded responses

---

## Success Criteria

### #89
- [x] Quota errors trigger fallback chain
- [ ] Fallback model logged in results
- [ ] Per-model chains supported
- [ ] Audit trail includes fallback info

### #91
- [ ] `orchestrator validate-design` command works
- [ ] Lenient mode ignores minor additions
- [ ] Integrates with REVIEW phase
- [ ] Uses fallback chain from #89

### #39
- [ ] MindsGateProxy evaluates gates via weighted consensus
- [ ] Re-deliberation allows vote changes
- [ ] Certainty-based escalation works correctly
- [ ] Decision report generated at workflow end
- [ ] Rollback commands provided for each decision
- [ ] Full audit trail in minds_decisions.jsonl
- [ ] CLI commands work: escalations, minds-report, rollback
