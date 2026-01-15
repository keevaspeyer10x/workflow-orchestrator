# CORE-026-E1 & E2 Implementation Plan

## Overview

Complete the CORE-026 feature by wiring error classification in executors and adding ping validation.

## E1: Wire Error Classification in Executors

### Goal
Make the `error_type` field on `ReviewResult` actually populated when errors occur.

### Changes

#### 1. `src/review/api_executor.py`

Update the exception handler to classify HTTP errors:

```python
# In execute() method, update the except block:
from .result import ReviewErrorType, classify_http_error

except Exception as e:
    error_type = ReviewErrorType.REVIEW_FAILED

    # Try to extract HTTP status from exception
    if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
        error_type = classify_http_error(e.response.status_code, str(e))
    elif 'timeout' in str(e).lower():
        error_type = ReviewErrorType.TIMEOUT
    elif 'connection' in str(e).lower() or 'network' in str(e).lower():
        error_type = ReviewErrorType.NETWORK_ERROR

    return ReviewResult(
        ...,
        error_type=error_type,
    )
```

Also update `_call_openrouter()` to raise specific exceptions with status codes.

#### 2. `src/review/cli_executor.py`

Update exception handlers:

```python
# TimeoutExpired -> TIMEOUT
except subprocess.TimeoutExpired:
    return ReviewResult(
        ...,
        error_type=ReviewErrorType.TIMEOUT,
    )

# FileNotFoundError (CLI not found) -> KEY_MISSING (tool not available)
except FileNotFoundError as e:
    return ReviewResult(
        ...,
        error_type=ReviewErrorType.KEY_MISSING,  # CLI tool not installed
    )

# General exception -> REVIEW_FAILED
except Exception as e:
    error_type = ReviewErrorType.REVIEW_FAILED
    error_str = str(e).lower()

    # Parse common error patterns
    if '401' in str(e) or '403' in str(e) or 'unauthorized' in error_str:
        error_type = ReviewErrorType.KEY_INVALID
    elif '429' in str(e) or 'rate limit' in error_str:
        error_type = ReviewErrorType.RATE_LIMITED
    elif 'timeout' in error_str:
        error_type = ReviewErrorType.TIMEOUT

    return ReviewResult(
        ...,
        error_type=error_type,
    )
```

## E2: Ping Validation for API Keys

### Goal
Add `ping=True` option to `validate_api_keys()` that actually tests the API key works.

### Changes

#### 1. `src/review/router.py`

Update `validate_api_keys()`:

```python
def validate_api_keys(
    models: list[str],
    ping: bool = False
) -> tuple[bool, dict[str, str]]:
    # ... existing presence checks ...

    if ping:
        # Actually test the keys with lightweight API calls
        for model in models:
            if model.lower() not in errors:
                ping_result = _ping_api(model.lower())
                if not ping_result.success:
                    errors[model.lower()] = ping_result.error

    return len(errors) == 0, errors
```

Add new helper function:

```python
def _ping_api(model: str) -> "PingResult":
    """
    Test an API key by making a lightweight request.

    Uses model list endpoints which are cheap and fast.
    """
    from dataclasses import dataclass

    @dataclass
    class PingResult:
        success: bool
        error: str = ""
        latency_ms: float = 0

    key_name = MODEL_TO_API_KEY.get(model)
    key_value = os.environ.get(key_name)

    try:
        if model in ("gemini",):
            # Google AI: list models
            _ping_google(key_value)
        elif model in ("openai", "codex"):
            # OpenAI: list models
            _ping_openai(key_value)
        elif model in ("grok",):
            # XAI or OpenRouter: simple request
            _ping_xai_or_openrouter(key_value)
        elif model in ("openrouter",):
            # OpenRouter: list models
            _ping_openrouter(key_value)
        return PingResult(success=True)
    except Exception as e:
        return PingResult(success=False, error=str(e))
```

### Ping Implementations

- **OpenAI**: `GET https://api.openai.com/v1/models` with Bearer token
- **Google AI**: `GET https://generativelanguage.googleapis.com/v1beta/models?key=<key>`
- **OpenRouter**: `GET https://openrouter.ai/api/v1/models` with Bearer token
- **XAI**: `GET https://api.x.ai/v1/models` with Bearer token

## Test Plan

1. **E1 Tests** (in `tests/test_review_resilience.py`):
   - Test API executor returns correct error_type on HTTP 401/403/429/500
   - Test CLI executor returns TIMEOUT on TimeoutExpired
   - Test CLI executor returns KEY_MISSING on FileNotFoundError

2. **E2 Tests**:
   - Test ping with valid key succeeds
   - Test ping with invalid key returns error
   - Test ping with missing key returns error
   - Test ping=False (default) doesn't make API calls

## Files Changed

- `src/review/api_executor.py` - Add error_type classification
- `src/review/cli_executor.py` - Add error_type classification
- `src/review/router.py` - Add ping validation
- `tests/test_review_resilience.py` - Add tests for E1 and E2

## Estimated Effort

- E1: ~30 minutes (straightforward error classification)
- E2: ~30 minutes (4 simple HTTP calls)
- Tests: ~20 minutes
- Total: ~1.5 hours
