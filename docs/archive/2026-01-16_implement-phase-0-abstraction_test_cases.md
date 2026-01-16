# Test Cases: Issues #89, #91, #39

## Issue #89: Fallback Models on Quota Exhaustion

### Unit Tests (`tests/test_review_fallback.py`)

#### TC-89-01: Quota exhaustion triggers fallback
```python
def test_quota_exhaustion_triggers_fallback():
    """Quota error should trigger fallback chain, not fail permanently."""
    # Mock primary model to raise quota error
    # Verify fallback model is called
    # Verify result includes model_used field
```

#### TC-89-02: Rate limit (429) triggers fallback
```python
def test_rate_limit_triggers_fallback():
    """HTTP 429 should trigger fallback chain."""
    # Mock primary model to raise HTTP 429
    # Verify fallback model is called
```

#### TC-89-03: All models exhausted raises clear error
```python
def test_all_models_exhausted_error():
    """When all fallbacks fail, raise AllModelsExhaustedError with model list."""
    # Mock all models to raise quota error
    # Verify error message includes all attempted models
```

#### TC-89-04: Fallback tracking in result
```python
def test_fallback_tracking_in_result():
    """Result should include model_used and fallbacks_tried."""
    # Mock primary to fail, fallback to succeed
    # Verify result.model_used == fallback_model
    # Verify result.fallbacks_tried == [primary_model]
```

#### TC-89-05: Per-model fallback chain from config
```python
def test_per_model_fallback_chain():
    """Model-specific fallback chains should override tool-level defaults."""
    # Configure specific fallback for google/gemini-3-pro
    # Verify that chain is used instead of default gemini chain
```

### Integration Tests

#### TC-89-06: Fallback chain through review execution
```python
def test_fallback_chain_integration():
    """Full review execution with fallback triggered."""
    # Run actual review with mocked API responses
    # Verify audit trail includes fallback info
```

---

## Issue #91: Design Validation

### Unit Tests (`tests/test_design_validation.py`)

#### TC-91-01: Basic plan vs diff comparison
```python
def test_basic_plan_comparison():
    """Validate plan items are detected in implementation."""
    plan = "1. Add login button\n2. Add logout handler"
    diff = "+ <button>Login</button>\n+ def logout():"
    result = validate_design(plan, diff)
    assert result.status == "PASS"
    assert "login button" in result.planned_items_implemented
```

#### TC-91-02: Lenient mode allows minor additions
```python
def test_lenient_mode_minor_additions():
    """Lenient mode should not flag logging, tests, error handling."""
    plan = "1. Add user API endpoint"
    diff = "+ @app.route('/user')\n+ logger.info('Request received')\n+ try:"
    result = validate_design(plan, diff, lenient=True)
    assert result.status in ("PASS", "PASS_WITH_NOTES")
    assert len(result.unplanned_additions) == 0  # Logging not flagged
```

#### TC-91-03: Lenient mode flags major scope creep
```python
def test_lenient_mode_flags_major_additions():
    """Lenient mode should still flag significant unplanned features."""
    plan = "1. Add user API endpoint"
    diff = "+ @app.route('/user')\n+ @app.route('/admin')\n+ class AdminPanel:"
    result = validate_design(plan, diff, lenient=True)
    assert result.status == "NEEDS_REVISION"
    assert "admin" in str(result.unplanned_additions).lower()
```

#### TC-91-04: Missing planned items detected
```python
def test_missing_planned_items():
    """Should flag when planned items are not implemented."""
    plan = "1. Add login\n2. Add logout\n3. Add password reset"
    diff = "+ def login():\n+ def logout():"  # Missing password reset
    result = validate_design(plan, diff)
    assert "password reset" in str(result.notes).lower() or \
           len(result.planned_items_implemented) < 3
```

#### TC-91-05: No plan file graceful handling
```python
def test_no_plan_file():
    """Should handle missing plan file gracefully."""
    result = validate_design(Path("/nonexistent/plan.md"), "some diff")
    assert result is None or result.status == "SKIP"
```

#### TC-91-06: Strict mode flags all deviations
```python
def test_strict_mode():
    """Strict mode should flag all deviations including minor ones."""
    plan = "1. Add login with email"
    diff = "+ def login(username):"  # Different param name
    result = validate_design(plan, diff, lenient=False)
    assert result.status in ("PASS_WITH_NOTES", "NEEDS_REVISION")
    assert len(result.deviations) > 0
```

### CLI Tests

#### TC-91-07: CLI command works
```python
def test_validate_design_cli():
    """orchestrator validate-design should work."""
    result = subprocess.run(
        ["orchestrator", "validate-design", "--help"],
        capture_output=True
    )
    assert result.returncode == 0
```

---

## Issue #39: Minds Proxy

### Unit Tests (`tests/test_minds_proxy.py`)

#### TC-39-01: Weighted voting calculation
```python
def test_weighted_voting():
    """Weighted voting should use model weights correctly."""
    votes = {
        "openai/gpt-5.2": "APPROVE",      # weight 2.0
        "deepseek/deepseek-chat": "REJECT" # weight 0.5
    }
    decision, confidence = weighted_vote(votes)
    assert decision == "APPROVE"
    assert confidence == 2.0 / 2.5  # 0.8
```

#### TC-39-02: Unanimous approval high certainty
```python
def test_unanimous_approval():
    """Unanimous approval should have high certainty."""
    votes = {
        "gpt-5.2": "APPROVE",
        "gemini-3": "APPROVE",
        "grok-4.1": "APPROVE",
    }
    decision = MindsGateProxy().evaluate(votes, gate_context)
    assert decision.certainty >= 0.95
    assert decision.decision == "APPROVE"
```

#### TC-39-03: Split vote triggers re-deliberation
```python
def test_split_vote_re_deliberation():
    """Split vote should trigger re-deliberation."""
    votes = {"gpt": "APPROVE", "gemini": "APPROVE", "grok": "REJECT"}
    proxy = MindsGateProxy(re_deliberation_enabled=True)
    # Mock grok's re-deliberation response
    decision = proxy.evaluate(votes, gate_context)
    assert decision.re_deliberation is not None
```

#### TC-39-04: Re-deliberation can change vote
```python
def test_re_deliberation_vote_change():
    """Model should be able to change vote after seeing other reasoning."""
    # Setup: grok initially rejects, others approve with reasoning
    # Mock grok's re-deliberation to change to APPROVE
    decision = re_deliberate(
        dissenting_model="grok",
        dissenting_vote="REJECT",
        other_votes={"gpt": ("APPROVE", "Tests pass"), "gemini": ("APPROVE", "Clean code")},
        gate_context=context
    )
    assert decision["changed"] == True
    assert decision["final_vote"] == "APPROVE"
```

#### TC-39-05: Certainty-based escalation thresholds
```python
@pytest.mark.parametrize("certainty,risk,expected", [
    (0.95, "CRITICAL", False),  # Very certain, even CRITICAL proceeds
    (0.80, "CRITICAL", True),   # High certain, CRITICAL escalates
    (0.80, "HIGH", False),      # High certain, HIGH proceeds
    (0.60, "HIGH", True),       # Medium certain, HIGH escalates
    (0.50, "LOW", True),        # Low certain, even LOW escalates
])
def test_certainty_escalation(certainty, risk, expected):
    """Escalation should be based on certainty + risk."""
    assert should_escalate("APPROVE", certainty, risk) == expected
```

#### TC-39-06: Audit trail written correctly
```python
def test_audit_trail():
    """Decision should be written to minds_decisions.jsonl."""
    proxy = MindsGateProxy()
    proxy.evaluate(votes, gate_context)

    audit_file = Path(".orchestrator/minds_decisions.jsonl")
    assert audit_file.exists()

    with open(audit_file) as f:
        entry = json.loads(f.readline())

    assert "gate_id" in entry
    assert "model_votes" in entry
    assert "rollback_command" in entry
```

#### TC-39-07: Rollback command generation
```python
def test_rollback_command():
    """Decision should include valid rollback command."""
    decision = MindsDecision(
        gate_id="user_approval",
        decision="APPROVE",
        # ... other fields
    )
    assert decision.rollback_command.startswith("git revert")
```

### CLI Tests

#### TC-39-08: escalations command
```python
def test_escalations_cli():
    """orchestrator escalations should list pending escalations."""
    result = subprocess.run(
        ["orchestrator", "escalations"],
        capture_output=True
    )
    assert result.returncode == 0
```

#### TC-39-09: minds-report command
```python
def test_minds_report_cli():
    """orchestrator minds-report should generate report."""
    result = subprocess.run(
        ["orchestrator", "minds-report"],
        capture_output=True
    )
    assert result.returncode == 0
```

#### TC-39-10: rollback command
```python
def test_rollback_cli():
    """orchestrator rollback should execute rollback."""
    # Setup: Create a decision with rollback command
    result = subprocess.run(
        ["orchestrator", "rollback", "decision_123", "--dry-run"],
        capture_output=True
    )
    assert result.returncode == 0
```

### Integration Tests

#### TC-39-11: Full gate evaluation flow
```python
def test_full_gate_evaluation():
    """Complete flow from gate hit to decision."""
    # Setup workflow with user_approval gate
    # Trigger gate in zero_human mode
    # Verify minds proxy evaluates
    # Verify decision logged
    # Verify workflow continues
```

#### TC-39-12: Hybrid mode override
```python
def test_hybrid_mode_override():
    """In hybrid mode, human can override minds decision."""
    # Setup workflow in hybrid mode
    # Trigger gate, minds approve
    # Human rejects via CLI
    # Verify rejection takes precedence
```

---

## Cross-Issue Integration Tests

### TC-INT-01: Fallback through design validation
```python
def test_fallback_through_validation():
    """Design validation should use fallback when primary model fails."""
    # Mock primary model to fail with quota
    # Run validate-design
    # Verify fallback was used
    # Verify result is valid
```

### TC-INT-02: Minds proxy uses fallback
```python
def test_minds_uses_fallback():
    """Minds proxy should use fallback when model fails."""
    # Configure minds with primary + fallback
    # Mock primary to fail
    # Verify fallback model's vote is used
```

### TC-INT-03: End-to-end zero_human workflow
```python
def test_e2e_zero_human():
    """Full workflow in zero_human mode with all features."""
    # Start workflow
    # Reach REVIEW phase
    # Run design validation (uses fallback if needed)
    # Hit user_approval gate
    # Minds proxy evaluates
    # Complete workflow
    # Verify decision report generated
```

---

## Performance Tests

### TC-PERF-01: Fallback latency acceptable
```python
def test_fallback_latency():
    """Fallback should not add excessive latency."""
    # Time single model call
    # Time call with one fallback
    # Verify overhead < 5 seconds
```

### TC-PERF-02: Minds parallel model calls
```python
def test_minds_parallel_calls():
    """Minds should call models in parallel when possible."""
    # Mock 5 model calls
    # Time evaluation
    # Verify total time < 5x single call time
```

---

## Error Handling Tests

### TC-ERR-01: Network failure graceful handling
```python
def test_network_failure():
    """Network failures should not crash, try fallback."""
    # Mock network timeout
    # Verify fallback tried
    # Verify clear error if all fail
```

### TC-ERR-02: Invalid model response handling
```python
def test_invalid_model_response():
    """Invalid JSON from model should be handled."""
    # Mock model returning invalid JSON
    # Verify retry or fallback
    # Verify no crash
```

### TC-ERR-03: API key missing clear error
```python
def test_missing_api_key_error():
    """Missing API key should give clear error message."""
    # Remove API key from environment
    # Attempt model call
    # Verify error mentions API key setup
```
