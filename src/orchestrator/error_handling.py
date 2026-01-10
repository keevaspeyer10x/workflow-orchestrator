"""
Error Handling Utilities

Provides retry logic, circuit breakers, and graceful degradation
for robust error handling in the orchestrator.
"""

import time
import random
from typing import Callable, Any, Optional, Type
from enum import Enum
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
import threading


# ============================================================================
# EXCEPTIONS
# ============================================================================

class OrchestratorError(Exception):
    """Base exception for orchestrator errors"""
    pass


class RetryableError(OrchestratorError):
    """Error that should be retried"""
    pass


class NonRetryableError(OrchestratorError):
    """Error that should not be retried"""
    pass


class CircuitBreakerOpenError(OrchestratorError):
    """Circuit breaker is open, rejecting calls"""
    pass


class ConfigurationError(OrchestratorError):
    """Configuration is invalid"""
    pass


# ============================================================================
# RETRY LOGIC
# ============================================================================

@dataclass
class RetryPolicy:
    """Retry policy configuration"""
    max_attempts: int = 3
    initial_delay_ms: int = 100
    max_delay_ms: int = 5000
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple[Type[Exception], ...] = (RetryableError, ConnectionError, TimeoutError)


class RetryHandler:
    """Handles retry logic with exponential backoff and jitter"""

    def __init__(self, policy: Optional[RetryPolicy] = None):
        """
        Initialize retry handler

        Args:
            policy: Retry policy (uses defaults if not provided)
        """
        self.policy = policy or RetryPolicy()

    def execute(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Execute function with retry logic

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Exception: Last exception if all retries fail
        """
        last_exception = None

        for attempt in range(1, self.policy.max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except self.policy.retryable_exceptions as e:
                last_exception = e

                if attempt == self.policy.max_attempts:
                    # Last attempt failed, raise exception
                    break

                # Calculate delay
                delay_ms = self._calculate_delay(attempt)
                delay_seconds = delay_ms / 1000.0

                # Sleep before retry
                time.sleep(delay_seconds)

            except NonRetryableError:
                # Don't retry non-retryable errors
                raise

            except Exception as e:
                # Unknown exception, don't retry
                raise

        # All retries failed, raise last exception
        raise last_exception

    def _calculate_delay(self, attempt: int) -> int:
        """
        Calculate delay for retry attempt

        Uses exponential backoff with optional jitter

        Args:
            attempt: Attempt number (1-indexed)

        Returns:
            Delay in milliseconds
        """
        # Exponential backoff
        delay = self.policy.initial_delay_ms * (self.policy.exponential_base ** (attempt - 1))

        # Cap at max delay
        delay = min(delay, self.policy.max_delay_ms)

        # Add jitter if enabled
        if self.policy.jitter:
            # Random jitter between 0% and 25% of delay
            jitter_amount = random.uniform(0, delay * 0.25)
            delay = delay + jitter_amount

        return int(delay)


# ============================================================================
# CIRCUIT BREAKER
# ============================================================================

class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, rejecting calls
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None


class CircuitBreaker:
    """
    Circuit breaker for external service calls

    States:
    - CLOSED: Normal operation, calls go through
    - OPEN: Too many failures, rejecting calls
    - HALF_OPEN: Testing if service recovered
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: int = 60,
        half_open_max_calls: int = 1
    ):
        """
        Initialize circuit breaker

        Args:
            name: Circuit breaker name
            failure_threshold: Failures before opening circuit
            success_threshold: Successes in half-open before closing
            timeout_seconds: Seconds to wait before half-open
            half_open_max_calls: Max concurrent calls in half-open state
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._stats = CircuitBreakerStats()
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._opened_at: Optional[datetime] = None
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state"""
        with self._lock:
            return self._state

    @property
    def stats(self) -> CircuitBreakerStats:
        """Get circuit statistics"""
        with self._lock:
            return CircuitBreakerStats(
                total_calls=self._stats.total_calls,
                successful_calls=self._stats.successful_calls,
                failed_calls=self._stats.failed_calls,
                rejected_calls=self._stats.rejected_calls,
                last_failure_time=self._stats.last_failure_time,
                last_success_time=self._stats.last_success_time
            )

    def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Execute function through circuit breaker

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: Circuit is open
            Exception: Exception from function
        """
        with self._lock:
            # Check if should allow call
            if not self._should_allow_call():
                self._stats.rejected_calls += 1
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is open"
                )

            self._stats.total_calls += 1

            # Track half-open calls
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1

        # Execute call
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
        finally:
            with self._lock:
                if self._state == CircuitState.HALF_OPEN:
                    self._half_open_calls -= 1

    def _should_allow_call(self) -> bool:
        """
        Check if call should be allowed

        Returns:
            True if call should proceed
        """
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # Check if timeout elapsed
            if self._opened_at:
                elapsed = datetime.now(timezone.utc) - self._opened_at
                if elapsed.total_seconds() >= self.timeout_seconds:
                    # Transition to half-open
                    self._state = CircuitState.HALF_OPEN
                    self._consecutive_successes = 0
                    return True
            return False

        if self._state == CircuitState.HALF_OPEN:
            # Allow limited calls in half-open
            return self._half_open_calls < self.half_open_max_calls

        return False

    def _on_success(self) -> None:
        """Handle successful call"""
        with self._lock:
            self._stats.successful_calls += 1
            self._stats.last_success_time = datetime.now(timezone.utc)
            self._consecutive_failures = 0
            self._consecutive_successes += 1

            # Check if should close circuit
            if self._state == CircuitState.HALF_OPEN:
                if self._consecutive_successes >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._consecutive_successes = 0

    def _on_failure(self) -> None:
        """Handle failed call"""
        with self._lock:
            self._stats.failed_calls += 1
            self._stats.last_failure_time = datetime.now(timezone.utc)
            self._consecutive_successes = 0
            self._consecutive_failures += 1

            # Check if should open circuit
            if self._state == CircuitState.CLOSED:
                if self._consecutive_failures >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._opened_at = datetime.now(timezone.utc)
                    self._consecutive_failures = 0

            elif self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open reopens circuit
                self._state = CircuitState.OPEN
                self._opened_at = datetime.now(timezone.utc)

    def reset(self) -> None:
        """Reset circuit breaker to closed state"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._consecutive_successes = 0
            self._opened_at = None
            self._half_open_calls = 0


# ============================================================================
# GRACEFUL DEGRADATION
# ============================================================================

class FallbackHandler:
    """Handles fallback logic when primary operation fails"""

    def __init__(self, fallback_func: Optional[Callable[..., Any]] = None):
        """
        Initialize fallback handler

        Args:
            fallback_func: Fallback function to call on failure
        """
        self.fallback_func = fallback_func

    def execute(
        self,
        primary_func: Callable[..., Any],
        *args,
        **kwargs
    ) -> Any:
        """
        Execute with fallback on failure

        Args:
            primary_func: Primary function to try
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Result from primary or fallback function

        Raises:
            Exception: If both primary and fallback fail
        """
        try:
            return primary_func(*args, **kwargs)
        except Exception as e:
            if self.fallback_func:
                try:
                    return self.fallback_func(*args, **kwargs)
                except Exception as fallback_error:
                    # Both failed, raise original error
                    raise e
            else:
                raise


# ============================================================================
# COMBINED ERROR HANDLER
# ============================================================================

class ErrorHandler:
    """
    Combined error handler with retry, circuit breaker, and fallback

    Provides comprehensive error handling for orchestrator operations.
    """

    def __init__(
        self,
        retry_policy: Optional[RetryPolicy] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        fallback_func: Optional[Callable[..., Any]] = None
    ):
        """
        Initialize error handler

        Args:
            retry_policy: Retry policy
            circuit_breaker: Circuit breaker
            fallback_func: Fallback function
        """
        self.retry_handler = RetryHandler(retry_policy)
        self.circuit_breaker = circuit_breaker
        self.fallback_handler = FallbackHandler(fallback_func)

    def execute(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Execute function with full error handling

        Flow:
        1. Circuit breaker check
        2. Retry with exponential backoff
        3. Fallback on failure

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Exception: If all error handling fails
        """
        def wrapped_func(*args, **kwargs):
            if self.circuit_breaker:
                return self.circuit_breaker.call(func, *args, **kwargs)
            else:
                return func(*args, **kwargs)

        # Try with retry logic
        try:
            return self.retry_handler.execute(wrapped_func, *args, **kwargs)
        except Exception as e:
            # Try fallback if available
            if self.fallback_handler.fallback_func:
                return self.fallback_handler.execute(func, *args, **kwargs)
            else:
                raise
