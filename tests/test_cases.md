# CORE-026-E1 & E2 Test Cases

## E1: Error Classification in Executors

### API Executor Tests

| ID | Test | Expected | Priority |
|----|------|----------|----------|
| E1-API-01 | HTTP 401 error during review | error_type = KEY_INVALID | HIGH |
| E1-API-02 | HTTP 403 error during review | error_type = KEY_INVALID | HIGH |
| E1-API-03 | HTTP 429 error during review | error_type = RATE_LIMITED | HIGH |
| E1-API-04 | HTTP 500 error during review | error_type = NETWORK_ERROR | MEDIUM |
| E1-API-05 | Connection timeout | error_type = TIMEOUT | HIGH |
| E1-API-06 | Network error (no connection) | error_type = NETWORK_ERROR | MEDIUM |
| E1-API-07 | Parse error (invalid JSON response) | error_type = PARSE_ERROR | LOW |
| E1-API-08 | Generic exception | error_type = REVIEW_FAILED | MEDIUM |

### CLI Executor Tests

| ID | Test | Expected | Priority |
|----|------|----------|----------|
| E1-CLI-01 | TimeoutExpired exception | error_type = TIMEOUT | HIGH |
| E1-CLI-02 | FileNotFoundError (CLI not found) | error_type = KEY_MISSING | HIGH |
| E1-CLI-03 | Error output contains "401" | error_type = KEY_INVALID | MEDIUM |
| E1-CLI-04 | Error output contains "rate limit" | error_type = RATE_LIMITED | MEDIUM |
| E1-CLI-05 | Generic subprocess error | error_type = REVIEW_FAILED | MEDIUM |

## E2: Ping Validation Tests

### validate_api_keys() with ping=True

| ID | Test | Expected | Priority |
|----|------|----------|----------|
| E2-PING-01 | ping=True with valid OpenRouter key | returns (True, {}) | HIGH |
| E2-PING-02 | ping=True with invalid key | returns (False, {model: error}) | HIGH |
| E2-PING-03 | ping=True with missing key | returns (False, {model: "not set"}) | HIGH |
| E2-PING-04 | ping=False (default) | no API calls made | HIGH |
| E2-PING-05 | ping=True with network error | returns (False, {model: error}) | MEDIUM |
| E2-PING-06 | ping=True with rate limited | returns (False, {model: error}) | MEDIUM |

### Ping Helper Tests

| ID | Test | Expected | Priority |
|----|------|----------|----------|
| E2-HELPER-01 | _ping_openai with valid key | PingResult(success=True) | MEDIUM |
| E2-HELPER-02 | _ping_openrouter with valid key | PingResult(success=True) | MEDIUM |
| E2-HELPER-03 | _ping_google with valid key | PingResult(success=True) | MEDIUM |
| E2-HELPER-04 | _ping_xai_or_openrouter with valid key | PingResult(success=True) | MEDIUM |

## Test Implementation Notes

### Mocking Strategy

- **E1 Tests**: Mock HTTP responses using `responses` or `unittest.mock.patch`
- **E2 Tests**: Mock API endpoints, verify no real API calls for ping=False

### Existing Test File

Add to existing `tests/test_review_resilience.py` which already has:
- TestReviewErrorType
- TestAPIKeyValidation
- TestRequiredReviewsFromWorkflow
- TestRecoveryInstructions
- TestRetryCommand
- TestBackwardCompatibility
- TestErrorTypeInEvents

### New Test Classes

```python
class TestAPIExecutorErrorClassification:
    """E1: API executor populates error_type correctly."""

class TestCLIExecutorErrorClassification:
    """E1: CLI executor populates error_type correctly."""

class TestPingValidation:
    """E2: ping=True tests API keys with real requests."""
```
