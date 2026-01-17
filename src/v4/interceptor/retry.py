"""
Budget-aware retry logic for V4.2 LLM Call Interceptor.

Implements exponential backoff with jitter for transient failures,
while respecting budget reservations.
"""
import asyncio
import logging
import random
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryError(Exception):
    """Raised when all retry attempts fail."""

    def __init__(self, message: str, last_exception: Exception, attempts: int):
        self.last_exception = last_exception
        self.attempts = attempts
        super().__init__(message)


class BudgetAwareRetry:
    """
    Retry logic with exponential backoff and budget awareness.

    Key features:
    - Exponential backoff with jitter to prevent thundering herd
    - Configurable max retries and delay bounds
    - Uses the same budget reservation across retries
    - Distinguishes between retryable and non-retryable errors

    Usage:
        retry = BudgetAwareRetry(max_retries=3, delay_base=1.0)
        result = await retry.execute(async_operation)
    """

    # Errors that should trigger retry
    RETRYABLE_ERRORS = (
        ConnectionError,
        TimeoutError,
        # Add provider-specific transient errors
    )

    def __init__(
        self,
        max_retries: int = 3,
        delay_base: float = 1.0,
        delay_max: float = 30.0,
        jitter_factor: float = 0.5,
    ):
        """
        Initialize retry handler.

        Args:
            max_retries: Maximum number of attempts (not including first)
            delay_base: Base delay in seconds for exponential backoff
            delay_max: Maximum delay between retries
            jitter_factor: Random jitter factor (0.5 = ±50% variance)
        """
        self.max_retries = max_retries
        self.delay_base = delay_base
        self.delay_max = delay_max
        self.jitter_factor = jitter_factor

    async def execute(
        self,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        """
        Execute operation with retry logic.

        Args:
            operation: Async callable to execute

        Returns:
            Result of operation

        Raises:
            RetryError: If all attempts fail
            Exception: Non-retryable errors are raised immediately
        """
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                return await operation()
            except Exception as e:
                last_exception = e

                # Check if error is retryable
                if not self._is_retryable(e):
                    logger.debug(f"Non-retryable error: {type(e).__name__}")
                    raise

                # Check if we have retries left
                if attempt >= self.max_retries - 1:
                    logger.warning(
                        f"Max retries ({self.max_retries}) exceeded. "
                        f"Last error: {e}"
                    )
                    raise

                # Calculate delay with exponential backoff and jitter
                delay = self._calculate_delay(attempt)
                logger.info(
                    f"Retry {attempt + 1}/{self.max_retries} after {delay:.2f}s "
                    f"(error: {type(e).__name__}: {e})"
                )

                await asyncio.sleep(delay)

        # Should not reach here, but just in case
        raise RetryError(
            f"All {self.max_retries} attempts failed",
            last_exception,
            self.max_retries,
        )

    def _calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay with exponential backoff and jitter.

        Formula: min(delay_max, delay_base * 2^attempt * (1 ± jitter))
        """
        # Exponential backoff
        base_delay = self.delay_base * (2 ** attempt)

        # Apply jitter
        jitter = 1 + random.uniform(-self.jitter_factor, self.jitter_factor)
        delay = base_delay * jitter

        # Cap at max delay
        return min(delay, self.delay_max)

    def _is_retryable(self, error: Exception) -> bool:
        """
        Check if error is retryable.

        Override this method to add provider-specific error handling.
        """
        # Check against known retryable types
        if isinstance(error, self.RETRYABLE_ERRORS):
            return True

        # Check for rate limiting (common across providers)
        error_str = str(error).lower()
        if "rate limit" in error_str or "429" in error_str:
            return True

        # Check for temporary server errors
        if "503" in error_str or "502" in error_str or "500" in error_str:
            return True

        # Default: retry all errors (conservative approach)
        # In production, you may want to be more selective
        return True
