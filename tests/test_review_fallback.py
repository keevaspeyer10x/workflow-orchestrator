"""
Tests for CORE-028b: Model Fallback Execution Chain

Tests cover:
1. is_retryable_error() / is_permanent_error() functions
2. retry_with_backoff() synchronous retry
3. Fallback execution logic in APIExecutor
4. --no-fallback CLI flag
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import requests


# =============================================================================
# Retry Logic Tests
# =============================================================================

class TestIsRetryableError:
    """Test the is_retryable_error() function."""

    def test_rate_limit_429_is_retryable(self):
        """HTTP 429 rate limit errors should be retryable."""
        from src.review.retry import is_retryable_error

        error = Exception("429: Rate limit exceeded")
        assert is_retryable_error(error) is True

    def test_timeout_is_retryable(self):
        """Timeout errors should be retryable."""
        from src.review.retry import is_retryable_error

        error = requests.exceptions.Timeout("Connection timed out")
        assert is_retryable_error(error) is True

    def test_connection_error_is_retryable(self):
        """Connection errors should be retryable."""
        from src.review.retry import is_retryable_error

        error = requests.exceptions.ConnectionError("Connection refused")
        assert is_retryable_error(error) is True

    def test_server_error_503_is_retryable(self):
        """HTTP 503 server errors should be retryable."""
        from src.review.retry import is_retryable_error

        error = Exception("503: Service unavailable")
        assert is_retryable_error(error) is True

    def test_auth_error_401_not_retryable(self):
        """HTTP 401 auth errors should NOT be retryable."""
        from src.review.retry import is_retryable_error

        error = Exception("401: Unauthorized")
        assert is_retryable_error(error) is False

    def test_auth_error_403_not_retryable(self):
        """HTTP 403 forbidden errors should NOT be retryable."""
        from src.review.retry import is_retryable_error

        error = Exception("403: Forbidden")
        assert is_retryable_error(error) is False

    def test_invalid_key_not_retryable(self):
        """Invalid API key errors should NOT be retryable."""
        from src.review.retry import is_retryable_error

        error = Exception("Invalid API key provided")
        assert is_retryable_error(error) is False


class TestIsPermanentError:
    """Test the is_permanent_error() function."""

    def test_401_is_permanent(self):
        """HTTP 401 should be classified as permanent."""
        from src.review.retry import is_permanent_error

        error = Exception("401: Unauthorized - Invalid API key")
        assert is_permanent_error(error) is True

    def test_403_is_permanent(self):
        """HTTP 403 should be classified as permanent."""
        from src.review.retry import is_permanent_error

        error = Exception("403: Forbidden - Access denied")
        assert is_permanent_error(error) is True

    def test_invalid_key_is_permanent(self):
        """Invalid API key message should be permanent."""
        from src.review.retry import is_permanent_error

        error = Exception("Error: Invalid API key")
        assert is_permanent_error(error) is True

    def test_rate_limit_not_permanent(self):
        """Rate limit errors should NOT be permanent."""
        from src.review.retry import is_permanent_error

        error = Exception("429: Rate limit exceeded")
        assert is_permanent_error(error) is False

    def test_timeout_not_permanent(self):
        """Timeout errors should NOT be permanent."""
        from src.review.retry import is_permanent_error

        error = requests.exceptions.Timeout("Request timed out")
        assert is_permanent_error(error) is False


class TestRetryWithBackoff:
    """Test the retry_with_backoff() function."""

    def test_success_on_first_try(self):
        """Function succeeding on first try returns immediately."""
        from src.review.retry import retry_with_backoff

        mock_func = Mock(return_value="success")

        result = retry_with_backoff(mock_func, max_retries=3, base_delay=0.01)

        assert result == "success"
        assert mock_func.call_count == 1

    def test_retry_on_transient_error(self):
        """Transient error triggers retry."""
        from src.review.retry import retry_with_backoff

        # Fail twice with transient error, then succeed
        mock_func = Mock(side_effect=[
            Exception("503: Service unavailable"),
            Exception("503: Service unavailable"),
            "success"
        ])

        result = retry_with_backoff(mock_func, max_retries=3, base_delay=0.01)

        assert result == "success"
        assert mock_func.call_count == 3

    def test_no_retry_on_permanent_error(self):
        """Permanent error fails immediately without retry."""
        from src.review.retry import retry_with_backoff

        mock_func = Mock(side_effect=Exception("401: Unauthorized"))

        with pytest.raises(Exception) as exc_info:
            retry_with_backoff(mock_func, max_retries=3, base_delay=0.01)

        assert "401" in str(exc_info.value)
        assert mock_func.call_count == 1  # No retry

    def test_max_retries_exceeded(self):
        """After max retries, raises last error."""
        from src.review.retry import retry_with_backoff

        mock_func = Mock(side_effect=Exception("503: Service unavailable"))

        with pytest.raises(Exception) as exc_info:
            retry_with_backoff(mock_func, max_retries=3, base_delay=0.01)

        assert "503" in str(exc_info.value)
        assert mock_func.call_count == 3


# =============================================================================
# Fallback Execution Tests
# =============================================================================

class TestFallbackExecution:
    """Test fallback execution in APIExecutor."""

    def test_primary_succeeds_no_fallback(self):
        """When primary model succeeds, no fallback should be used."""
        from src.review.api_executor import APIExecutor
        from src.review.result import ReviewResult

        with patch.object(APIExecutor, '_call_openrouter') as mock_call:
            mock_call.return_value = "## Assessment: PASSED\nNo issues found."

            executor = APIExecutor(
                working_dir="/tmp",
                api_key="test-key"
            )

            with patch.object(executor, 'context_collector'):
                result = executor.execute_with_fallback(
                    "security",
                    fallbacks=["backup-model"]
                )

            assert result.success is True
            assert result.was_fallback is False
            assert result.fallback_reason is None

    def test_transient_error_triggers_fallback(self):
        """When primary fails with transient error (after retry), fallback is tried."""
        from src.review.api_executor import APIExecutor

        call_count = 0
        def mock_call(prompt, model):
            nonlocal call_count
            call_count += 1
            # Primary model (internal retry_with_backoff uses max_retries=2) fails consistently
            # Fallback model (call 3+) succeeds
            if "backup" not in model:
                raise Exception("429: Rate limit exceeded")
            return "## Assessment: PASSED\nNo issues found."

        with patch.object(APIExecutor, '_call_openrouter', side_effect=mock_call):
            executor = APIExecutor(
                working_dir="/tmp",
                api_key="test-key"
            )

            with patch.object(executor, 'context_collector'):
                result = executor.execute_with_fallback(
                    "security",
                    fallbacks=["backup-model"]
                )

            assert result.success is True
            assert result.was_fallback is True
            assert "rate limit" in result.fallback_reason.lower()

    def test_permanent_error_no_fallback(self):
        """When primary fails with permanent error, no fallback is attempted."""
        from src.review.api_executor import APIExecutor
        from src.review.result import ReviewErrorType

        with patch.object(APIExecutor, '_call_openrouter') as mock_call:
            mock_call.side_effect = Exception("401: Unauthorized - Invalid API key")

            executor = APIExecutor(
                working_dir="/tmp",
                api_key="test-key"
            )

            with patch.object(executor, 'context_collector'):
                result = executor.execute_with_fallback(
                    "security",
                    fallbacks=["backup-model"]
                )

            assert result.success is False
            assert result.was_fallback is False
            assert result.error_type == ReviewErrorType.KEY_INVALID

    def test_all_fallbacks_fail(self):
        """When all models fail, error is returned."""
        from src.review.api_executor import APIExecutor

        with patch.object(APIExecutor, '_call_openrouter') as mock_call:
            mock_call.side_effect = Exception("503: Service unavailable")

            executor = APIExecutor(
                working_dir="/tmp",
                api_key="test-key"
            )

            with patch.object(executor, 'context_collector'):
                result = executor.execute_with_fallback(
                    "security",
                    fallbacks=["backup1", "backup2"]
                )

            assert result.success is False
            assert "all" in result.error.lower() or "failed" in result.error.lower()

    def test_no_fallback_flag_disables_fallback(self):
        """no_fallback=True prevents fallback attempts."""
        from src.review.api_executor import APIExecutor

        call_count = 0
        models_tried = []
        def mock_call(prompt, model):
            nonlocal call_count
            call_count += 1
            models_tried.append(model)
            raise Exception("429: Rate limit exceeded")

        with patch.object(APIExecutor, '_call_openrouter', side_effect=mock_call):
            executor = APIExecutor(
                working_dir="/tmp",
                api_key="test-key"
            )

            with patch.object(executor, 'context_collector'):
                result = executor.execute_with_fallback(
                    "security",
                    fallbacks=["backup-model"],
                    no_fallback=True
                )

            assert result.success is False
            assert result.was_fallback is False
            # With no_fallback=True, only primary model is tried (with internal retries)
            # No backup-model should appear in models_tried
            assert "backup-model" not in models_tried


# =============================================================================
# Configuration Tests
# =============================================================================

class TestFallbackConfiguration:
    """Test fallback configuration."""

    def test_default_fallback_chains_exist(self):
        """Default fallback chains should be configured."""
        from src.review.config import get_fallback_chain

        # Each primary model should have a fallback chain
        gemini_fallbacks = get_fallback_chain("gemini")
        assert isinstance(gemini_fallbacks, list)
        assert len(gemini_fallbacks) > 0

    def test_max_fallback_attempts_default(self):
        """max_fallback_attempts should have a default value."""
        from src.review.config import get_max_fallback_attempts

        max_attempts = get_max_fallback_attempts()
        assert isinstance(max_attempts, int)
        assert max_attempts >= 1
