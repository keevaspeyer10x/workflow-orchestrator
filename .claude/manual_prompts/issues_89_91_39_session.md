# Session: Issues #89, #91, #39 - Resilience & Autonomous Operations

## Overview

Implement three related improvements to make the orchestrator more resilient and capable of autonomous operation:

1. **#89 - Fallback models on quota exhaustion** (foundation)
2. **#91 - Automate design validation** (review automation)
3. **#39 - Zero-Human Mode with Minds as Proxy** (autonomous gates)

Use the orchestrator workflow: `orchestrator start "Issues #89, #91, #39: Resilience and autonomous operations"`

---

## Issue #89: Fallback Models on Quota Exhaustion

### Problem
During V3 development, Gemini API quota was exhausted mid-workflow, blocking reviews and requiring manual workarounds.

### Requirements
1. Detect quota/rate limit errors automatically (HTTP 429, quota exceeded messages)
2. Switch to configured fallback model chain
3. Log which fallback was used (transparency)
4. Support per-model fallback configuration

### Proposed Implementation

```python
# src/review/fallback.py
@dataclass
class FallbackChain:
    primary: str
    fallbacks: list[str]

DEFAULT_FALLBACKS = {
    "gemini/gemini-3-pro": ["anthropic/claude-3-opus", "openai/gpt-4-turbo"],
    "openai/gpt-5.1-codex-max": ["anthropic/claude-3-opus", "gemini/gemini-3-pro"],
    # etc.
}

def call_with_fallback(model: str, prompt: str, chain: FallbackChain = None) -> tuple[str, str]:
    """Returns (response, model_used)"""
    models_to_try = [model] + (chain.fallbacks if chain else DEFAULT_FALLBACKS.get(model, []))

    for m in models_to_try:
        try:
            response = call_model(m, prompt)
            return response, m
        except QuotaExhaustedError:
            logger.warning(f"Quota exhausted for {m}, trying fallback...")
            continue

    raise AllModelsExhaustedError(f"All models in chain exhausted: {models_to_try}")
```

### Configuration (workflow.yaml or user config)
```yaml
model_fallbacks:
  gemini/gemini-3-pro:
    - anthropic/claude-3-opus
    - openai/gpt-4-turbo
  openai/gpt-5.1-codex-max:
    - gemini/gemini-3-pro
    - anthropic/claude-3-opus
```

### Acceptance Criteria
- [ ] Detects 429/quota errors from Gemini, OpenAI, Anthropic, OpenRouter
- [ ] Automatically tries fallback chain
- [ ] Logs which model ultimately responded
- [ ] Configurable fallback chains
- [ ] Works with existing review system

---

## Issue #91: Automate Design Validation

### Problem
The `design_validation` review item is manual self-assessment. Implementers miss the same things they missed during implementation.

### Requirements
1. Read plan.md (or configured plan file)
2. Get git diff of implementation
3. Send both to LLM for objective comparison
4. Return structured result: PASS / PASS_WITH_NOTES / NEEDS_REVISION
5. List specific deviations found

### Proposed Implementation

```python
# src/review/design_validator.py
@dataclass
class DesignValidationResult:
    status: Literal["PASS", "PASS_WITH_NOTES", "NEEDS_REVISION"]
    planned_items_implemented: list[str]
    unplanned_additions: list[str]
    deviations: list[str]
    notes: str

def validate_design(plan_path: Path, diff: str) -> DesignValidationResult:
    prompt = f"""
    Compare this implementation plan against the actual code changes.

    ## Plan
    {plan_path.read_text()}

    ## Implementation (git diff)
    {diff}

    Analyze:
    1. Are all planned items implemented?
    2. Are there unplanned additions? (scope creep)
    3. Do implementations match the specified approach?
    4. Are there deviations needing justification?

    Return JSON:
    {{
        "status": "PASS" | "PASS_WITH_NOTES" | "NEEDS_REVISION",
        "planned_items_implemented": ["item1", "item2"],
        "unplanned_additions": ["addition1"],
        "deviations": ["deviation description"],
        "notes": "summary"
    }}
    """
    return call_model_json(prompt, DesignValidationResult)
```

### Integration
- Add `orchestrator validate-design` command
- Auto-run during REVIEW phase when plan.md exists
- Use fallback chain from #89

### Acceptance Criteria
- [ ] Reads docs/plan.md by default (configurable)
- [ ] Gets diff via `git diff main...HEAD` or staged changes
- [ ] Returns structured validation result
- [ ] Integrates with review phase
- [ ] Uses fallback models (#89)

---

## Issue #39: Zero-Human Mode with Minds as Proxy

### Problem
Manual gates (`user_approval`, `manual_smoke_test`) block autonomous workflows. Simply removing them loses oversight.

### Solution: Minds as Human Proxy

Instead of removing gates, have the multi-model "minds" system act as the human reviewer:

1. **Minds evaluate** - Send gate decision to multiple models
2. **Consensus decides** - Require threshold agreement (e.g., 3/5 approve)
3. **Transparency** - Log all decisions with reasoning
4. **Risk assessment** - Flag high-risk decisions for human review
5. **Rollback support** - Easy rollback if minds made wrong call

### Architecture

```python
# src/gates/minds_proxy.py
@dataclass
class MindsDecision:
    gate_id: str
    decision: Literal["APPROVE", "REJECT", "ESCALATE"]
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    model_votes: dict[str, str]  # model -> vote
    consensus: str  # "4/5 APPROVE"
    reasoning: str
    rollback_command: str  # How to undo if wrong
    timestamp: datetime

class MindsGateProxy:
    """Use multi-model consensus for gate decisions."""

    def __init__(self, models: list[str], threshold: int = 3):
        self.models = models
        self.threshold = threshold

    def evaluate_gate(self, gate: GateContext) -> MindsDecision:
        prompt = self._build_gate_prompt(gate)

        votes = {}
        reasonings = []
        for model in self.models:
            response = call_with_fallback(model, prompt)
            votes[model] = response.decision
            reasonings.append(f"[{model}]: {response.reasoning}")

        approve_count = sum(1 for v in votes.values() if v == "APPROVE")
        decision = "APPROVE" if approve_count >= self.threshold else "REJECT"

        # Assess risk based on gate type and context
        risk = self._assess_risk(gate, votes)

        # If HIGH/CRITICAL risk, escalate to human even if approved
        if risk in ("HIGH", "CRITICAL") and decision == "APPROVE":
            decision = "ESCALATE"

        return MindsDecision(
            gate_id=gate.id,
            decision=decision,
            risk_level=risk,
            model_votes=votes,
            consensus=f"{approve_count}/{len(self.models)} APPROVE",
            reasoning="\n".join(reasonings),
            rollback_command=self._get_rollback_command(gate),
            timestamp=datetime.now()
        )

    def _assess_risk(self, gate: GateContext, votes: dict) -> str:
        """Assess risk level of this decision."""
        # High risk indicators:
        # - Split vote (close to threshold)
        # - Security-related gate
        # - Irreversible action
        # - Production deployment

        split_vote = abs(sum(1 for v in votes.values() if v == "APPROVE") - len(votes)/2) < 1
        security_gate = "security" in gate.id.lower()
        irreversible = gate.metadata.get("irreversible", False)

        if irreversible or security_gate:
            return "HIGH" if split_vote else "MEDIUM"
        if split_vote:
            return "MEDIUM"
        return "LOW"
```

### Decision Report Format

At workflow end, generate a decision report:

```markdown
# Minds Gate Decisions Report

## Summary
- Total gates evaluated: 5
- Auto-approved (LOW risk): 3
- Auto-approved (MEDIUM risk): 1
- Escalated to human: 1
- Rejected: 0

## Decisions Requiring Review

### Gate: security_review_approval (MEDIUM risk)
- **Decision**: APPROVE
- **Consensus**: 4/5 APPROVE
- **Votes**:
  - gemini-3-pro: APPROVE - "No critical vulnerabilities found"
  - gpt-5.1: APPROVE - "Security patterns look standard"
  - claude-opus: APPROVE - "Input validation present"
  - grok-4.1: REJECT - "Concerned about rate limiting"
  - deepseek: APPROVE - "LGTM"
- **Rollback**: `git revert abc123`

### Gate: deploy_approval (ESCALATED - HIGH risk)
- **Decision**: ESCALATE (requires human)
- **Reason**: Irreversible production deployment with split vote
- **Consensus**: 3/5 APPROVE
- **Action needed**: Run `orchestrator approve deploy_approval` or `orchestrator reject deploy_approval`

## All Decisions Log
[Full audit trail in .orchestrator/minds_decisions.jsonl]
```

### CLI Integration

```bash
# Configure supervision mode
orchestrator config set supervision_mode zero_human  # or: supervised, hybrid

# View pending escalations
orchestrator escalations

# Review minds decisions
orchestrator minds-report

# Approve/reject escalated gate
orchestrator approve <gate_id> --reason "Reviewed, acceptable"
orchestrator reject <gate_id> --reason "Need more testing"

# Rollback a minds decision
orchestrator rollback <decision_id>
```

### Configuration

```yaml
# workflow.yaml or user config
supervision:
  mode: zero_human  # supervised | hybrid | zero_human

  minds_proxy:
    enabled: true
    models:
      - gemini/gemini-3-pro
      - openai/gpt-5.1-codex-max
      - anthropic/claude-3-opus
      - xai/grok-4.1
      - deepseek/deepseek-chat
    threshold: 3  # Minimum approvals needed

  escalation:
    risk_levels: [HIGH, CRITICAL]  # Auto-escalate these
    always_escalate:
      - deploy_production
      - delete_data

  rollback:
    auto_checkpoint: true  # Create checkpoint before each gate
```

### Acceptance Criteria
- [ ] MindsGateProxy evaluates gates via multi-model consensus
- [ ] Risk assessment flags HIGH/CRITICAL decisions
- [ ] Decision report generated at workflow end
- [ ] Escalation system for high-risk decisions
- [ ] Rollback commands provided for each decision
- [ ] Full audit trail in .orchestrator/minds_decisions.jsonl
- [ ] CLI commands: `orchestrator escalations`, `orchestrator minds-report`, `orchestrator rollback`
- [ ] Configuration for supervision mode and thresholds

---

## Implementation Order

1. **#89 first** - Fallback models (foundation for #91 and #39)
2. **#91 second** - Design validation (uses fallbacks)
3. **#39 third** - Minds proxy (builds on both)

## Testing Strategy

- Unit tests for fallback chain logic
- Integration tests for design validation
- Mock multi-model responses for minds proxy tests
- End-to-end test: run workflow in zero_human mode

## Risk Considerations

- **#89**: Low risk - additive feature, doesn't change success path
- **#91**: Low risk - new command, opt-in usage
- **#39**: Medium risk - changes gate behavior
  - Mitigation: Start with `hybrid` mode (minds decide but human can override)
  - Mitigation: Auto-checkpoint before each gate for easy rollback
  - Mitigation: Escalate HIGH/CRITICAL by default

---

## Notes

- Skip #90 (consolidate reviews) for now - needs separate pros/cons analysis
- Focus on transparency and auditability for #39
- All minds decisions should be easily reviewable and reversible
