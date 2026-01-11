# WF-035 Phase 4: Test Cases

## Unit Tests

### 1. Fallback Chain Logic

```python
# tests/test_review_fallbacks.py

def test_primary_model_succeeds_no_fallback():
    """Primary model success should not trigger fallback."""
    executor = APIExecutor(...)
    executor.models = {"primary": Mock(success=True)}

    result = executor.execute_with_fallbacks("security", "primary", ["fallback1"])

    assert result.success
    assert result.model_used == "primary"
    assert not result.was_fallback

def test_primary_fails_fallback_succeeds():
    """When primary fails, first fallback should be tried."""
    executor = APIExecutor(...)
    executor.models = {
        "primary": Mock(side_effect=Exception("Rate limited")),
        "fallback1": Mock(success=True)
    }

    result = executor.execute_with_fallbacks("security", "primary", ["fallback1"])

    assert result.success
    assert result.model_used == "fallback1"
    assert result.was_fallback

def test_all_fallbacks_fail():
    """When all models fail, return aggregated error."""
    executor = APIExecutor(...)
    executor.models = {
        "primary": Mock(side_effect=Exception("Error 1")),
        "fallback1": Mock(side_effect=Exception("Error 2")),
        "fallback2": Mock(side_effect=Exception("Error 3"))
    }

    result = executor.execute_with_fallbacks("security", "primary", ["fallback1", "fallback2"])

    assert not result.success
    assert "all models failed" in result.error.lower()

def test_empty_fallback_chain():
    """Empty fallback chain should only try primary."""
    executor = APIExecutor(...)
    executor.models = {"primary": Mock(side_effect=Exception("Failed"))}

    result = executor.execute_with_fallbacks("security", "primary", [])

    assert not result.success
```

### 2. Minimum Required Threshold

```python
def test_threshold_met_proceeds():
    """3 of 5 reviews succeeding should proceed."""
    router = ReviewRouter(..., settings=ReviewSettings(minimum_required=3))
    router.execute_single = Mock(side_effect=[
        ReviewResult(success=True),
        ReviewResult(success=True),
        ReviewResult(success=True),
        ReviewResult(success=False),
        ReviewResult(success=False)
    ])

    results = router.execute_all_reviews()

    assert len([r for r in results.values() if r.success]) == 3
    # Should proceed without exception

def test_threshold_not_met_warn_mode():
    """Below threshold in warn mode logs warning but proceeds."""
    router = ReviewRouter(..., settings=ReviewSettings(
        minimum_required=3,
        on_insufficient_reviews="warn"
    ))
    router.execute_single = Mock(side_effect=[
        ReviewResult(success=True),
        ReviewResult(success=True),
        ReviewResult(success=False),
        ReviewResult(success=False),
        ReviewResult(success=False)
    ])

    with patch('logging.warning') as mock_warn:
        results = router.execute_all_reviews()

    assert len([r for r in results.values() if r.success]) == 2
    mock_warn.assert_called()  # Warning logged
    # Should NOT raise exception

def test_threshold_not_met_block_mode():
    """Below threshold in block mode raises exception."""
    router = ReviewRouter(..., settings=ReviewSettings(
        minimum_required=3,
        on_insufficient_reviews="block"
    ))
    router.execute_single = Mock(side_effect=[
        ReviewResult(success=True),
        ReviewResult(success=True),
        ReviewResult(success=False),
        ReviewResult(success=False),
        ReviewResult(success=False)
    ])

    with pytest.raises(ReviewThresholdError):
        router.execute_all_reviews()
```

### 3. Settings Integration

```python
def test_no_settings_uses_defaults():
    """Router without settings uses default behavior."""
    router = ReviewRouter(working_dir=Path("."))

    assert router.settings is None or isinstance(router.settings, ReviewSettings)
    # Should not crash

def test_settings_from_workflow():
    """Router reads settings from workflow definition."""
    workflow = WorkflowDef(
        name="Test",
        phases=[],
        settings={"reviews": {"minimum_required": 4}}
    )
    engine = WorkflowEngine.from_workflow(workflow)

    assert engine.settings.reviews.minimum_required == 4
```

### 4. Result Schema

```python
def test_result_tracks_fallback():
    """ReviewResult tracks if fallback was used."""
    result = ReviewResult(
        success=True,
        model_used="fallback1",
        was_fallback=True,
        fallback_reason="Primary rate limited"
    )

    assert result.was_fallback
    assert result.fallback_reason

def test_result_serialization():
    """ReviewResult serializes with new fields."""
    result = ReviewResult(
        success=True,
        model_used="codex",
        was_fallback=False
    )

    data = result.dict()
    assert "was_fallback" in data
    assert data["was_fallback"] == False
```

## Integration Tests

### 5. End-to-End Workflow Test

```python
def test_zero_human_workflow_with_fallbacks():
    """Full workflow with fallback handling."""
    # Setup workflow with zero_human mode and review fallbacks
    engine = WorkflowEngine(working_dir=".")
    engine.start_workflow("Test task")

    # Advance to REVIEW phase
    while engine.state.current_phase_id != "REVIEW":
        engine.advance_phase()

    # Run reviews (with mocked fallbacks)
    # Verify fallback chain is used on primary failure
    # Verify minimum_required threshold is checked
```

## Manual Test Checklist

1. [ ] Start workflow with `supervision_mode: zero_human`
2. [ ] Reach REVIEW phase
3. [ ] Temporarily remove one API key (e.g., unset GEMINI_API_KEY)
4. [ ] Verify fallback model is used for gemini reviews
5. [ ] Verify warning logged about fallback usage
6. [ ] Verify workflow completes if minimum_required threshold met
7. [ ] Test with all API keys removed - verify graceful error message
