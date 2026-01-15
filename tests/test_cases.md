# Issue #58: Test Cases

## Retry Logic Tests

### TC-58-1: is_retryable_error Returns True for Rate Limit
**Input**: Exception with message "429: Rate limit exceeded"
**Expected**: Returns True
**Verification**: Unit test assertion

### TC-58-2: is_retryable_error Returns True for Timeout
**Input**: `requests.exceptions.Timeout` exception
**Expected**: Returns True
**Verification**: Unit test assertion

### TC-58-3: is_retryable_error Returns False for Auth Error
**Input**: Exception with message "401: Unauthorized"
**Expected**: Returns False
**Verification**: Unit test assertion

### TC-58-4: is_permanent_error Detects 401
**Input**: Exception with message "401: Invalid API key"
**Expected**: Returns True
**Verification**: Unit test assertion

### TC-58-5: retry_with_backoff Retries on Transient Error
**Setup**: Mock function that fails twice with 503, then succeeds
**Input**: Call with max_retries=3
**Expected**: Function called 3 times, returns success
**Verification**: Mock call count, return value

### TC-58-6: retry_with_backoff Fails Immediately on Permanent Error
**Setup**: Mock function that fails with 401
**Input**: Call with max_retries=3
**Expected**: Function called once, raises immediately
**Verification**: Mock call count = 1

---

## Fallback Execution Tests

### TC-58-7: Primary Succeeds - No Fallback Used
**Setup**: Primary model returns successful review
**Input**: `execute_with_fallback("security", fallbacks=["backup"])`
**Expected**:
- `was_fallback = False`
- `fallback_reason = None`
- Primary model used
**Verification**: ReviewResult fields

### TC-58-8: Primary Rate Limited - Fallback Used
**Setup**:
- Primary model raises 429 rate limit
- Fallback model succeeds
**Input**: `execute_with_fallback("security", fallbacks=["backup"])`
**Expected**:
- `was_fallback = True`
- `fallback_reason` contains "rate limit"
- Fallback model used
**Verification**: ReviewResult fields

### TC-58-9: Primary Auth Error - No Fallback (Permanent)
**Setup**: Primary model raises 401 unauthorized
**Input**: `execute_with_fallback("security", fallbacks=["backup"])`
**Expected**:
- `success = False`
- `was_fallback = False`
- `error_type = KEY_INVALID`
- Fallback NOT attempted
**Verification**: ReviewResult, mock call count

### TC-58-10: All Models Fail - Error Returned
**Setup**: All models raise 503 errors
**Input**: `execute_with_fallback("security", fallbacks=["backup1", "backup2"])`
**Expected**:
- `success = False`
- Error message indicates all attempts failed
**Verification**: ReviewResult

### TC-58-11: no_fallback Flag Disables Fallback
**Setup**: Primary model raises 429 rate limit
**Input**: `execute_with_fallback("security", fallbacks=["backup"], no_fallback=True)`
**Expected**:
- `success = False`
- `was_fallback = False`
- Fallback NOT attempted
**Verification**: ReviewResult, mock call count

---

## CLI Tests

### TC-58-12: --no-fallback Flag Recognized
**Input**: `orchestrator review security --no-fallback`
**Expected**: Command executes with fallback disabled
**Verification**: argparse accepts flag

### TC-58-13: Output Shows Fallback Usage
**Setup**: Review uses fallback
**Input**: `orchestrator review all`
**Expected**: Output shows "[fallback]" indicator
**Verification**: stdout contains fallback marker

---

## Configuration Tests

### TC-58-14: Default Fallback Chains Exist
**Input**: Load review config
**Expected**: `fallback_chains` has entries for gemini, codex, grok
**Verification**: Config access

### TC-58-15: max_fallback_attempts Defaults to 2
**Input**: Load review config without override
**Expected**: `max_fallback_attempts = 2`
**Verification**: Config access

---

## Integration Tests

### TC-58-16: End-to-End Fallback (Manual)
**Setup**: Set GEMINI_API_KEY to invalid value
**Input**: `orchestrator review security`
**Expected**:
- Gemini fails with auth error
- Falls back to next model
- Review completes
**Verification**: Manual observation

### TC-58-17: Regression - Normal Reviews Still Work
**Input**: `orchestrator review all`
**Expected**: All reviews complete (may use fallback)
**Verification**: Exit code 0, reviews completed

---

## Test File Structure

```python
# tests/test_review_fallback.py

class TestRetryLogic:
    def test_is_retryable_rate_limit(self): ...
    def test_is_retryable_timeout(self): ...
    def test_is_retryable_auth_error(self): ...
    def test_is_permanent_401(self): ...
    def test_retry_with_backoff_success(self): ...
    def test_retry_with_backoff_permanent_fail(self): ...

class TestFallbackExecution:
    def test_primary_succeeds_no_fallback(self): ...
    def test_rate_limit_triggers_fallback(self): ...
    def test_auth_error_no_fallback(self): ...
    def test_all_fail_returns_error(self): ...
    def test_no_fallback_flag(self): ...

class TestFallbackConfig:
    def test_default_chains_exist(self): ...
    def test_max_attempts_default(self): ...
```
