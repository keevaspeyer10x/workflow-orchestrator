"""
Days 17-18: Error Handling Tests

Tests for retry logic, circuit breakers, and error handling utilities.
"""

import pytest
import time
from unittest.mock import Mock

from src.orchestrator.error_handling import (
    RetryableError,
    NonRetryableError,
    CircuitBreakerOpenError,
    RetryPolicy,
    RetryHandler,
    CircuitBreaker,
    CircuitState,
    FallbackHandler,
    ErrorHandler,
)


class TestRetryPolicy:
    """Tests for RetryPolicy"""

    def test_default_policy(self):
        """Should create policy with defaults"""
        policy = RetryPolicy()

        assert policy.max_attempts == 3
        assert policy.initial_delay_ms == 100
        assert policy.max_delay_ms == 5000
        assert policy.exponential_base == 2.0
        assert policy.jitter is True

    def test_custom_policy(self):
        """Should create policy with custom values"""
        policy = RetryPolicy(
            max_attempts=5,
            initial_delay_ms=200,
            max_delay_ms=10000,
            exponential_base=3.0,
            jitter=False
        )

        assert policy.max_attempts == 5
        assert policy.initial_delay_ms == 200
        assert policy.max_delay_ms == 10000
        assert policy.exponential_base == 3.0
        assert policy.jitter is False


class TestRetryHandler:
    """Tests for RetryHandler"""

    def test_succeeds_first_attempt(self):
        """Should succeed on first attempt"""
        handler = RetryHandler()
        func = Mock(return_value="success")

        result = handler.execute(func)

        assert result == "success"
        assert func.call_count == 1

    def test_retries_on_retryable_error(self):
        """Should retry on retryable errors"""
        handler = RetryHandler(RetryPolicy(max_attempts=3, initial_delay_ms=10))

        func = Mock(side_effect=[
            RetryableError("fail 1"),
            RetryableError("fail 2"),
            "success"
        ])

        result = handler.execute(func)

        assert result == "success"
        assert func.call_count == 3

    def test_fails_after_max_attempts(self):
        """Should fail after max attempts"""
        handler = RetryHandler(RetryPolicy(max_attempts=3, initial_delay_ms=10))

        func = Mock(side_effect=RetryableError("always fails"))

        with pytest.raises(RetryableError):
            handler.execute(func)

        assert func.call_count == 3

    def test_no_retry_on_non_retryable_error(self):
        """Should not retry non-retryable errors"""
        handler = RetryHandler()

        func = Mock(side_effect=NonRetryableError("do not retry"))

        with pytest.raises(NonRetryableError):
            handler.execute(func)

        assert func.call_count == 1

    def test_no_retry_on_unknown_exception(self):
        """Should not retry unknown exceptions"""
        handler = RetryHandler()

        func = Mock(side_effect=ValueError("unknown error"))

        with pytest.raises(ValueError):
            handler.execute(func)

        assert func.call_count == 1

    def test_exponential_backoff(self):
        """Should use exponential backoff for delays"""
        handler = RetryHandler(RetryPolicy(
            max_attempts=4,
            initial_delay_ms=100,
            exponential_base=2.0,
            jitter=False
        ))

        # Calculate expected delays
        delay1 = handler._calculate_delay(1)  # 100 * 2^0 = 100
        delay2 = handler._calculate_delay(2)  # 100 * 2^1 = 200
        delay3 = handler._calculate_delay(3)  # 100 * 2^2 = 400

        assert delay1 == 100
        assert delay2 == 200
        assert delay3 == 400

    def test_max_delay_cap(self):
        """Should cap delay at max_delay_ms"""
        handler = RetryHandler(RetryPolicy(
            initial_delay_ms=100,
            max_delay_ms=500,
            exponential_base=2.0,
            jitter=False
        ))

        # 100 * 2^10 = 102400, should be capped at 500
        delay = handler._calculate_delay(10)

        assert delay == 500

    def test_jitter_adds_randomness(self):
        """Should add jitter to delays"""
        handler = RetryHandler(RetryPolicy(
            initial_delay_ms=100,
            exponential_base=2.0,
            jitter=True
        ))

        # Get multiple delays for same attempt
        delays = [handler._calculate_delay(2) for _ in range(10)]

        # Should have variation due to jitter
        assert len(set(delays)) > 1

        # All should be >= base delay (200) and <= base + 25% (250)
        for delay in delays:
            assert 200 <= delay <= 250


class TestCircuitBreaker:
    """Tests for CircuitBreaker"""

    def test_initial_state_closed(self):
        """Should start in CLOSED state"""
        cb = CircuitBreaker("test")

        assert cb.state == CircuitState.CLOSED

    def test_calls_pass_in_closed_state(self):
        """Should allow calls in CLOSED state"""
        cb = CircuitBreaker("test")
        func = Mock(return_value="success")

        result = cb.call(func)

        assert result == "success"
        assert func.call_count == 1

    def test_opens_after_threshold_failures(self):
        """Should open after failure threshold"""
        cb = CircuitBreaker("test", failure_threshold=3)
        func = Mock(side_effect=Exception("fail"))

        # Fail 3 times
        for _ in range(3):
            with pytest.raises(Exception):
                cb.call(func)

        # Should now be open
        assert cb.state == CircuitState.OPEN

    def test_rejects_calls_when_open(self):
        """Should reject calls when OPEN"""
        cb = CircuitBreaker("test", failure_threshold=2)
        func = Mock(side_effect=Exception("fail"))

        # Fail twice to open
        for _ in range(2):
            with pytest.raises(Exception):
                cb.call(func)

        assert cb.state == CircuitState.OPEN

        # Next call should be rejected
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(func)

    def test_transitions_to_half_open_after_timeout(self):
        """Should transition to HALF_OPEN after timeout"""
        cb = CircuitBreaker("test", failure_threshold=2, timeout_seconds=1)
        func = Mock(side_effect=Exception("fail"))

        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                cb.call(func)

        assert cb.state == CircuitState.OPEN

        # Wait for timeout
        time.sleep(1.1)

        # Next call should transition to HALF_OPEN
        func_success = Mock(return_value="success")
        result = cb.call(func_success)

        assert result == "success"
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_from_half_open_on_success(self):
        """Should close from HALF_OPEN after success threshold"""
        cb = CircuitBreaker("test",
            failure_threshold=2,
            success_threshold=2,
            timeout_seconds=1
        )

        # Open the circuit
        func_fail = Mock(side_effect=Exception("fail"))
        for _ in range(2):
            with pytest.raises(Exception):
                cb.call(func_fail)

        # Wait for timeout
        time.sleep(1.1)

        # Succeed twice in HALF_OPEN
        func_success = Mock(return_value="success")
        cb.call(func_success)
        cb.call(func_success)

        # Should be CLOSED now
        assert cb.state == CircuitState.CLOSED

    def test_reopens_from_half_open_on_failure(self):
        """Should reopen from HALF_OPEN on any failure"""
        cb = CircuitBreaker("test", failure_threshold=2, timeout_seconds=1)

        # Open the circuit
        func_fail = Mock(side_effect=Exception("fail"))
        for _ in range(2):
            with pytest.raises(Exception):
                cb.call(func_fail)

        # Wait for timeout
        time.sleep(1.1)

        # Fail in HALF_OPEN
        with pytest.raises(Exception):
            cb.call(func_fail)

        # Should be OPEN again
        assert cb.state == CircuitState.OPEN

    def test_tracks_statistics(self):
        """Should track call statistics"""
        cb = CircuitBreaker("test")
        func_success = Mock(return_value="success")
        func_fail = Mock(side_effect=Exception("fail"))

        # 3 successes
        for _ in range(3):
            cb.call(func_success)

        # 2 failures
        for _ in range(2):
            with pytest.raises(Exception):
                cb.call(func_fail)

        stats = cb.stats

        assert stats.total_calls == 5
        assert stats.successful_calls == 3
        assert stats.failed_calls == 2

    def test_reset_circuit_breaker(self):
        """Should reset to CLOSED state"""
        cb = CircuitBreaker("test", failure_threshold=2)
        func_fail = Mock(side_effect=Exception("fail"))

        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                cb.call(func_fail)

        assert cb.state == CircuitState.OPEN

        # Reset
        cb.reset()

        assert cb.state == CircuitState.CLOSED

        # Should allow calls again
        func_success = Mock(return_value="success")
        result = cb.call(func_success)
        assert result == "success"


class TestFallbackHandler:
    """Tests for FallbackHandler"""

    def test_returns_primary_on_success(self):
        """Should return primary result on success"""
        primary = Mock(return_value="primary")
        fallback = Mock(return_value="fallback")

        handler = FallbackHandler(fallback)
        result = handler.execute(primary)

        assert result == "primary"
        assert primary.call_count == 1
        assert fallback.call_count == 0

    def test_calls_fallback_on_failure(self):
        """Should call fallback on primary failure"""
        primary = Mock(side_effect=Exception("fail"))
        fallback = Mock(return_value="fallback")

        handler = FallbackHandler(fallback)
        result = handler.execute(primary)

        assert result == "fallback"
        assert primary.call_count == 1
        assert fallback.call_count == 1

    def test_raises_if_no_fallback(self):
        """Should raise exception if no fallback"""
        primary = Mock(side_effect=Exception("fail"))

        handler = FallbackHandler(None)

        with pytest.raises(Exception):
            handler.execute(primary)

    def test_raises_primary_error_if_both_fail(self):
        """Should raise primary error if both fail"""
        primary = Mock(side_effect=ValueError("primary fail"))
        fallback = Mock(side_effect=Exception("fallback fail"))

        handler = FallbackHandler(fallback)

        with pytest.raises(ValueError):
            handler.execute(primary)


class TestErrorHandler:
    """Tests for combined ErrorHandler"""

    def test_succeeds_immediately(self):
        """Should succeed on first attempt"""
        func = Mock(return_value="success")
        handler = ErrorHandler()

        result = handler.execute(func)

        assert result == "success"
        assert func.call_count == 1

    def test_retries_on_failure(self):
        """Should retry on failure"""
        func = Mock(side_effect=[
            RetryableError("fail"),
            "success"
        ])

        handler = ErrorHandler(retry_policy=RetryPolicy(initial_delay_ms=10))
        result = handler.execute(func)

        assert result == "success"
        assert func.call_count == 2

    def test_uses_circuit_breaker(self):
        """Should use circuit breaker"""
        cb = CircuitBreaker("test", failure_threshold=2)
        func = Mock(side_effect=Exception("fail"))

        handler = ErrorHandler(
            retry_policy=RetryPolicy(max_attempts=1),
            circuit_breaker=cb
        )

        # Fail twice to open circuit
        with pytest.raises(Exception):
            handler.execute(func)
        with pytest.raises(Exception):
            handler.execute(func)

        # Should be rejected by circuit breaker
        with pytest.raises(CircuitBreakerOpenError):
            handler.execute(func)

    def test_uses_fallback(self):
        """Should use fallback on failure"""
        primary = Mock(side_effect=Exception("fail"))
        fallback = Mock(return_value="fallback")

        handler = ErrorHandler(
            retry_policy=RetryPolicy(max_attempts=1),
            fallback_func=fallback
        )

        result = handler.execute(primary)

        assert result == "fallback"

    def test_full_error_handling_flow(self):
        """Should use retry, circuit breaker, and fallback together"""
        # Create circuit breaker
        cb = CircuitBreaker("test", failure_threshold=5)

        # Primary function that eventually succeeds
        call_count = {"count": 0}

        def primary_func():
            call_count["count"] += 1
            if call_count["count"] < 3:
                raise RetryableError("fail")
            return "success"

        handler = ErrorHandler(
            retry_policy=RetryPolicy(max_attempts=5, initial_delay_ms=10),
            circuit_breaker=cb
        )

        result = handler.execute(primary_func)

        assert result == "success"
        assert call_count["count"] == 3
        assert cb.stats.successful_calls == 1


class TestErrorHandlerEdgeCases:
    """Tests for edge cases"""

    def test_zero_retries(self):
        """Should handle zero retries"""
        func = Mock(side_effect=RetryableError("fail"))

        handler = ErrorHandler(retry_policy=RetryPolicy(max_attempts=1))

        with pytest.raises(RetryableError):
            handler.execute(func)

        assert func.call_count == 1

    def test_very_long_backoff(self):
        """Should handle very long backoff times"""
        handler = RetryHandler(RetryPolicy(
            initial_delay_ms=1000,
            max_delay_ms=100000,
            exponential_base=10.0,
            jitter=False
        ))

        # Should cap at max_delay
        delay = handler._calculate_delay(5)
        assert delay == 100000

    def test_circuit_breaker_thread_safety(self):
        """Circuit breaker should be thread-safe"""
        import threading

        cb = CircuitBreaker("test", failure_threshold=100)
        func = Mock(return_value="success")

        # Call from multiple threads
        def call_multiple():
            for _ in range(10):
                cb.call(func)

        threads = []
        for _ in range(10):
            t = threading.Thread(target=call_multiple)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should have 100 successful calls
        assert cb.stats.successful_calls == 100
