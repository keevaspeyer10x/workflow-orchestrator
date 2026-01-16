"""
Retry and fallback utilities for review execution.

CORE-028b: Model Fallback Execution Chain

Ported from multiminds/resilience/retry.py with sync adaptations.
"""

import time
import logging
from typing import Callable, TypeVar, Tuple, Type, Optional

import requests

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Exceptions that indicate transient failures (should retry)
TRANSIENT_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    ConnectionError,
    OSError,
)

# Programming errors that should never be retried
PROGRAMMING_ERRORS: Tuple[Type[Exception], ...] = (
    TypeError,
    ValueError,
    AttributeError,
    KeyError,
    IndexError,
    NameError,
    SyntaxError,
    ImportError,
    NotImplementedError,
    AssertionError,
)


def is_permanent_error(error: Exception) -> bool:
    """
    Check if an error is permanent (should not retry).

    Args:
        error: The exception to check

    Returns:
        True if the error is permanent and should fail immediately
    """
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    permanent_patterns = [
        # Authentication/authorization errors
        "unauthorized",
        "401",
        "403",
        "forbidden",
        "invalid api key",
        "invalid_api_key",
        "authentication failed",
        "permission denied",
        "access denied",
        # Client errors (bad request)
        "invalid request",
        "invalid_request",
        "bad request",
        "400",
        "malformed",
        "validation error",
        "validation_error",
        # Not found
        "not found",
        "404",
        "model not found",
        "does not exist",
        # Content policy / safety
        "content policy",
        "safety",
        "blocked",
        "harmful",
        # Billing (not quota - quota should trigger fallback per Issue #89)
        "billing",
        "payment required",
        "402",
        # Invalid model/parameters
        "invalid model",
        "unknown model",
        "unsupported",
    ]

    # Check error message
    if any(pattern in error_str for pattern in permanent_patterns):
        return True

    # Check for known permanent exception types by name
    permanent_exception_types = [
        "permissiondenied",
        "invalidargument",
        "notfound",
        "unauthenticated",
    ]
    if any(exc_type in error_type for exc_type in permanent_exception_types):
        return True

    return False


def is_retryable_error(error: Exception) -> bool:
    """
    Check if an error is retryable (transient).

    Uses a balanced approach:
    - Never retry programming errors (TypeError, ValueError, etc.)
    - Never retry known permanent errors (401, 403, invalid API key, etc.)
    - Always retry known transient exceptions (timeouts, connection errors)
    - Retry unknown API/SDK errors with transient patterns (rate limits, 5xx)

    Args:
        error: The exception to check

    Returns:
        True if the error should be retried
    """
    # Never retry programming errors - these are bugs, not transient issues
    if isinstance(error, PROGRAMMING_ERRORS):
        return False

    # Never retry known permanent errors
    if is_permanent_error(error):
        return False

    # Always retry known transient exceptions
    if isinstance(error, TRANSIENT_EXCEPTIONS):
        return True

    # For unknown errors (likely API/SDK-specific), check for transient patterns
    error_str = str(error).lower()
    transient_patterns = [
        "rate limit",
        "too many requests",
        "429",
        "503",
        "502",
        "504",
        "500",
        "timeout",
        "timed out",
        "connection refused",
        "connection reset",
        "temporary failure",
        "server error",
        "internal server error",
        "service unavailable",
        "overloaded",
        "capacity",
        "try again",
        # Issue #89: Quota exhaustion should trigger fallback, not fail permanently
        "quota exceeded",
        "quota exhausted",
        "exhausted your daily quota",
        "quota limit",
    ]

    # If error message contains transient patterns, retry
    if any(pattern in error_str for pattern in transient_patterns):
        return True

    # For truly unknown errors, don't retry by default (conservative)
    return False


def retry_with_backoff(
    func: Callable[..., T],
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    **kwargs,
) -> T:
    """
    Retry a function call with exponential backoff.

    Args:
        func: Function to call
        *args: Arguments to pass to func
        max_retries: Maximum number of attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 60.0)
        on_retry: Optional callback called before each retry with (attempt, error)
        **kwargs: Keyword arguments to pass to func

    Returns:
        Result from func

    Raises:
        Last exception if all retries fail or permanent error encountered
    """
    last_error: Exception = Exception("No attempts made")

    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e

            # Check if this is a permanent error
            if is_permanent_error(e):
                logger.debug(
                    f"Permanent error on attempt {attempt + 1}, not retrying: {e}"
                )
                raise

            # Check if this is a retryable error
            if not is_retryable_error(e):
                logger.debug(
                    f"Non-retryable error on attempt {attempt + 1}: {e}"
                )
                raise

            # Don't sleep on the last attempt
            if attempt < max_retries - 1:
                delay = min(base_delay * (2 ** attempt), max_delay)
                func_name = getattr(func, '__name__', repr(func))
                logger.debug(
                    f"Retry {attempt + 1}/{max_retries} for {func_name} "
                    f"after {delay:.1f}s due to: {e}"
                )
                if on_retry:
                    on_retry(attempt + 1, e)
                time.sleep(delay)

    raise last_error
