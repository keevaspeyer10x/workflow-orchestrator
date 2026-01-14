# CORE-026: Test Cases

## Unit Tests

### 1. ReviewErrorType Classification

**File:** `tests/test_review_error_types.py`

```python
def test_http_401_classified_as_key_invalid():
    """HTTP 401 Unauthorized should be KEY_INVALID"""
    result = classify_http_error(401, "Invalid API key")
    assert result == ReviewErrorType.KEY_INVALID

def test_http_403_classified_as_key_invalid():
    """HTTP 403 Forbidden should be KEY_INVALID"""
    result = classify_http_error(403, "Access denied")
    assert result == ReviewErrorType.KEY_INVALID

def test_http_429_classified_as_rate_limited():
    """HTTP 429 Too Many Requests should be RATE_LIMITED"""
    result = classify_http_error(429, "Rate limit exceeded")
    assert result == ReviewErrorType.RATE_LIMITED

def test_connection_error_classified_as_network():
    """Connection refused should be NETWORK_ERROR"""
    result = classify_exception(ConnectionError("refused"))
    assert result == ReviewErrorType.NETWORK_ERROR

def test_timeout_classified_correctly():
    """Timeout should be TIMEOUT"""
    result = classify_exception(TimeoutError("timed out"))
    assert result == ReviewErrorType.TIMEOUT
```

### 2. API Key Validation

**File:** `tests/test_key_validation.py`

```python
def test_validate_missing_key():
    """Missing API key returns error"""
    with patch.dict(os.environ, {}, clear=True):
        valid, errors = validate_api_keys(["gemini"])
        assert not valid
        assert "gemini" in errors
        assert "GEMINI_API_KEY not set" in errors["gemini"]

def test_validate_present_key():
    """Present API key passes validation"""
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
        with patch("src.review.router.ping_api", return_value=True):
            valid, errors = validate_api_keys(["gemini"])
            assert valid
            assert not errors

def test_validate_invalid_key():
    """Invalid API key (ping fails) returns error"""
    with patch.dict(os.environ, {"GEMINI_API_KEY": "bad-key"}):
        with patch("src.review.router.ping_api", return_value=False):
            valid, errors = validate_api_keys(["gemini"])
            assert not valid
            assert "invalid or expired" in errors["gemini"]

def test_validate_multiple_keys_partial_failure():
    """One missing key fails whole validation"""
    with patch.dict(os.environ, {"GEMINI_API_KEY": "ok"}, clear=True):
        with patch("src.review.router.ping_api", return_value=True):
            valid, errors = validate_api_keys(["gemini", "openai"])
            assert not valid
            assert "openai" in errors
            assert "gemini" not in errors
```

### 3. Required Reviews from Workflow

**File:** `tests/test_required_reviews.py`

```python
def test_get_required_reviews_from_workflow():
    """Engine reads required_reviews from workflow definition"""
    workflow = {
        "phases": [{
            "id": "REVIEW",
            "required_reviews": ["security", "quality", "consistency"]
        }]
    }
    engine = WorkflowEngine(workflow_definition=workflow)
    required = engine.get_required_reviews()
    assert required == {"security", "quality", "consistency"}

def test_get_required_reviews_defaults_empty():
    """Missing required_reviews defaults to empty set"""
    workflow = {"phases": [{"id": "REVIEW"}]}
    engine = WorkflowEngine(workflow_definition=workflow)
    required = engine.get_required_reviews()
    assert required == set()

def test_validate_reviews_uses_workflow_definition():
    """validate_reviews_completed checks workflow required_reviews"""
    workflow = {
        "phases": [{
            "id": "REVIEW",
            "required_reviews": ["security", "quality"]
        }]
    }
    engine = WorkflowEngine(workflow_definition=workflow)
    engine.log_event(REVIEW_COMPLETED, "security")
    valid, missing = engine.validate_reviews_completed()
    assert not valid
    assert "quality" in missing
```

### 4. Recovery Instructions

**File:** `tests/test_recovery.py`

```python
def test_recovery_instructions_for_gemini():
    """Gemini recovery instructions include sops command"""
    instructions = get_recovery_instructions("gemini")
    assert "GEMINI_API_KEY" in instructions
    assert "sops -d secrets.enc.yaml" in instructions
    assert "orchestrator review retry" in instructions

def test_recovery_instructions_for_openai():
    """OpenAI recovery instructions exist"""
    instructions = get_recovery_instructions("openai")
    assert "OPENAI_API_KEY" in instructions

def test_error_output_includes_recovery():
    """Review failure output includes recovery guidance"""
    result = ReviewResult(
        success=False,
        error="API key invalid",
        error_type=ReviewErrorType.KEY_INVALID
    )
    output = format_review_error(result, review_type="gemini")
    assert "GEMINI_API_KEY" in output
    assert "retry" in output.lower()
```

## Integration Tests

### 5. cmd_complete Blocks on Key Failure

**File:** `tests/test_cli_review_blocking.py`

```python
def test_cmd_complete_blocks_on_missing_key(tmp_path, monkeypatch):
    """cmd_complete exits 1 if API key missing for review"""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = runner.invoke(cli, ["complete", "consistency_review"])
    assert result.exit_code == 1
    assert "API key" in result.output
    assert "GEMINI_API_KEY" in result.output

def test_cmd_complete_shows_recovery_instructions(tmp_path, monkeypatch):
    """cmd_complete shows how to fix missing key"""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = runner.invoke(cli, ["complete", "security_review"])
    assert "sops" in result.output or "export" in result.output
    assert "retry" in result.output.lower()
```

### 6. cmd_finish Validates Required Reviews

**File:** `tests/test_cli_finish_validation.py`

```python
def test_cmd_finish_blocks_missing_required_reviews(workflow_with_state):
    """cmd_finish exits 1 if required reviews not completed"""
    # Workflow requires security + quality, only security completed
    result = runner.invoke(cli, ["finish"])
    assert result.exit_code == 1
    assert "quality" in result.output.lower()
    assert "Required reviews not completed" in result.output

def test_cmd_finish_allows_skip_with_reason(workflow_with_state):
    """cmd_finish --skip-review-check --reason bypasses validation"""
    result = runner.invoke(cli, [
        "finish",
        "--skip-review-check",
        "--reason", "Testing bypass"
    ])
    assert result.exit_code == 0

def test_cmd_finish_passes_with_all_reviews(workflow_with_state):
    """cmd_finish passes when all required reviews completed"""
    # All required reviews completed
    result = runner.invoke(cli, ["finish"])
    assert result.exit_code == 0
```

### 7. Retry Command

**File:** `tests/test_review_retry.py`

```python
def test_retry_command_exists():
    """orchestrator review retry command is registered"""
    result = runner.invoke(cli, ["review", "retry", "--help"])
    assert result.exit_code == 0

def test_retry_reruns_failed_reviews(workflow_with_failed_reviews):
    """retry command re-runs reviews that previously failed"""
    with patch("src.cli.run_auto_review", return_value=(True, "", "", {})):
        result = runner.invoke(cli, ["review", "retry"])
        assert "Retrying" in result.output

def test_retry_validates_keys_first(workflow_with_failed_reviews, monkeypatch):
    """retry validates API keys before attempting review"""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = runner.invoke(cli, ["review", "retry"])
    assert "Still failing" in result.output or "key" in result.output.lower()

def test_retry_no_failed_reviews():
    """retry with no failed reviews shows message"""
    result = runner.invoke(cli, ["review", "retry"])
    assert "No failed reviews" in result.output
```

## Edge Cases

### 8. Backward Compatibility

**File:** `tests/test_backward_compat.py`

```python
def test_old_workflow_without_required_reviews():
    """Workflows without required_reviews field still work"""
    old_workflow = {"phases": [{"id": "REVIEW", "items": [...]}]}
    engine = WorkflowEngine(workflow_definition=old_workflow)
    # Should not raise, defaults to empty
    required = engine.get_required_reviews()
    assert required == set()

def test_finish_with_no_required_reviews():
    """Finish works when workflow has no required_reviews"""
    result = runner.invoke(cli, ["finish"])
    # Should pass since no reviews required
    assert result.exit_code == 0
```

## Test Count Summary

| Category | Count |
|----------|-------|
| Error Classification | 5 |
| Key Validation | 4 |
| Required Reviews | 3 |
| Recovery Instructions | 3 |
| cmd_complete Blocking | 2 |
| cmd_finish Validation | 3 |
| Retry Command | 4 |
| Backward Compatibility | 2 |
| **Total** | **26** |
