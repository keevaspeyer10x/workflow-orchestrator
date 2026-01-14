import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.review.result import ReviewErrorType

# =============================================================================
# Test 8: E1 - API Executor Error Classification
# =============================================================================

class TestAPIExecutorErrorClassification:
    """Tests for E1: API executor populates error_type correctly."""

    def test_api_executor_401_returns_key_invalid(self):
        """HTTP 401 from API should return error_type=KEY_INVALID."""
        from src.review.api_executor import APIExecutor
        from src.review.result import ReviewErrorType
        import requests

        # Create mock response with 401
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "Invalid API key"}
        mock_response.text = "Unauthorized"

        with patch.object(requests, 'post', return_value=mock_response):
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key-12345-valid"}):
                executor = APIExecutor(working_dir=Path("."))
                result = executor.execute("security")

        assert result.success is False
        assert result.error_type == ReviewErrorType.KEY_INVALID

    def test_api_executor_403_returns_key_invalid(self):
        """HTTP 403 from API should return error_type=KEY_INVALID."""
        from src.review.api_executor import APIExecutor
        from src.review.result import ReviewErrorType
        import requests

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"error": "Access denied"}
        mock_response.text = "Forbidden"

        with patch.object(requests, 'post', return_value=mock_response):
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key-12345-valid"}):
                executor = APIExecutor(working_dir=Path("."))
                result = executor.execute("security")

        assert result.success is False
        assert result.error_type == ReviewErrorType.KEY_INVALID

    def test_api_executor_429_returns_rate_limited(self):
        """HTTP 429 from API should return error_type=RATE_LIMITED."""
        from src.review.api_executor import APIExecutor
        from src.review.result import ReviewErrorType
        import requests

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.json.return_value = {"error": "Rate limit exceeded"}
        mock_response.text = "Too Many Requests"

        with patch.object(requests, 'post', return_value=mock_response):
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key-12345-valid"}):
                executor = APIExecutor(working_dir=Path("."))
                result = executor.execute("security")

        assert result.success is False
        assert result.error_type == ReviewErrorType.RATE_LIMITED

    def test_api_executor_500_returns_network_error(self):
        """HTTP 500 from API should return error_type=NETWORK_ERROR."""
        from src.review.api_executor import APIExecutor
        from src.review.result import ReviewErrorType
        import requests

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "Internal server error"}
        mock_response.text = "Internal Server Error"

        with patch.object(requests, 'post', return_value=mock_response):
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key-12345-valid"}):
                executor = APIExecutor(working_dir=Path("."))
                result = executor.execute("security")

        assert result.success is False
        assert result.error_type == ReviewErrorType.NETWORK_ERROR

    def test_api_executor_timeout_returns_timeout(self):
        """Connection timeout should return error_type=TIMEOUT."""
        from src.review.api_executor import APIExecutor
        from src.review.result import ReviewErrorType
        import requests

        with patch.object(requests, 'post', side_effect=requests.exceptions.Timeout("Request timed out")):
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key-12345-valid"}):
                executor = APIExecutor(working_dir=Path("."))
                result = executor.execute("security")

        assert result.success is False
        assert result.error_type == ReviewErrorType.TIMEOUT

    def test_api_executor_connection_error_returns_network_error(self):
        """Connection error should return error_type=NETWORK_ERROR."""
        from src.review.api_executor import APIExecutor
        from src.review.result import ReviewErrorType
        import requests

        with patch.object(requests, 'post', side_effect=requests.exceptions.ConnectionError("Connection refused")):
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key-12345-valid"}):
                executor = APIExecutor(working_dir=Path("."))
                result = executor.execute("security")

        assert result.success is False
        assert result.error_type == ReviewErrorType.NETWORK_ERROR


# =============================================================================
# Test 9: E1 - CLI Executor Error Classification
# =============================================================================

class TestCLIExecutorErrorClassification:
    """Tests for E1: CLI executor populates error_type correctly."""

    def test_cli_executor_timeout_returns_timeout(self):
        """TimeoutExpired should return error_type=TIMEOUT."""
        from src.review.cli_executor import CLIExecutor
        from src.review.result import ReviewErrorType
        import subprocess

        with patch.object(subprocess, 'Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.communicate.side_effect = subprocess.TimeoutExpired(cmd="codex", timeout=300)
            mock_process.kill = MagicMock()
            mock_process.wait = MagicMock()
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            executor = CLIExecutor(working_dir=Path("."), timeout=1)
            result = executor.execute("security")

        assert result.success is False
        assert result.error_type == ReviewErrorType.TIMEOUT

    def test_cli_executor_tool_not_found_returns_key_missing(self):
        """FileNotFoundError (CLI not found) should return error_type=KEY_MISSING."""
        from src.review.cli_executor import CLIExecutor
        from src.review.result import ReviewErrorType
        import subprocess

        with patch.object(subprocess, 'Popen', side_effect=FileNotFoundError("codex not found")):
            executor = CLIExecutor(working_dir=Path("."))
            result = executor.execute("security")

        assert result.success is False
        assert result.error_type == ReviewErrorType.KEY_MISSING

    def test_cli_executor_401_in_output_returns_key_invalid(self):
        """Error containing '401' should return error_type=KEY_INVALID."""
        from src.review.cli_executor import CLIExecutor
        from src.review.result import ReviewErrorType
        import subprocess

        with patch.object(subprocess, 'Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.communicate.side_effect = RuntimeError("API error: 401 Unauthorized")
            mock_process.poll.return_value = None
            mock_process.kill = MagicMock()
            mock_process.wait = MagicMock()
            mock_popen.return_value = mock_process

            executor = CLIExecutor(working_dir=Path("."))
            result = executor.execute("security")

        assert result.success is False
        assert result.error_type == ReviewErrorType.KEY_INVALID

    def test_cli_executor_rate_limit_in_output_returns_rate_limited(self):
        """Error containing 'rate limit' should return error_type=RATE_LIMITED."""
        from src.review.cli_executor import CLIExecutor
        from src.review.result import ReviewErrorType
        import subprocess

        with patch.object(subprocess, 'Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.communicate.side_effect = RuntimeError("Rate limit exceeded, try again later")
            mock_process.poll.return_value = None
            mock_process.kill = MagicMock()
            mock_process.wait = MagicMock()
            mock_popen.return_value = mock_process

            executor = CLIExecutor(working_dir=Path("."))
            result = executor.execute("security")

        assert result.success is False
        assert result.error_type == ReviewErrorType.RATE_LIMITED


# =============================================================================
# Test 10: E2 - Ping Validation
# =============================================================================

class TestPingValidation:
    """Tests for E2: ping=True validates API keys with real requests."""

    def test_ping_false_makes_no_api_calls(self):
        """ping=False (default) should not make any API calls."""
        from src.review.router import validate_api_keys
        import requests

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key-12345-valid"}):
            with patch.object(requests, 'get') as mock_get:
                with patch.object(requests, 'post') as mock_post:
                    valid, errors = validate_api_keys(["openrouter"], ping=False)
                    # No API calls should be made
                    mock_get.assert_not_called()
                    mock_post.assert_not_called()

        assert valid is True
        assert errors == {}

    def test_ping_true_with_valid_key_succeeds(self):
        """ping=True with valid key should return success."""
        from src.review.router import validate_api_keys
        import urllib.request

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": [{"id": "model-1"}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key-12345-valid"}):
            with patch.object(urllib.request, 'urlopen', return_value=mock_response):
                valid, errors = validate_api_keys(["openrouter"], ping=True)

        assert valid is True
        assert errors == {}

    def test_ping_true_with_invalid_key_returns_error(self):
        """ping=True with invalid key should return error."""
        from src.review.router import validate_api_keys
        import urllib.request
        import urllib.error

        error = urllib.error.HTTPError(
            url="https://openrouter.ai/api/v1/models",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None
        )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "invalid-key-12345"}):
            with patch.object(urllib.request, 'urlopen', side_effect=error):
                valid, errors = validate_api_keys(["openrouter"], ping=True)

        assert valid is False
        assert "openrouter" in errors
        assert "401" in errors["openrouter"] or "Unauthorized" in errors["openrouter"]

    def test_ping_true_with_missing_key_returns_error(self):
        """ping=True with missing key should return error without making API call."""
        from src.review.router import validate_api_keys

        # Clear the key
        env = os.environ.copy()
        env.pop("OPENROUTER_API_KEY", None)
        env.pop("openrouter_api_key", None)

        with patch.dict(os.environ, env, clear=True):
            valid, errors = validate_api_keys(["openrouter"], ping=True)

        assert valid is False
        assert "openrouter" in errors

    def test_ping_true_with_network_error_returns_error(self):
        """ping=True with network error should return error."""
        from src.review.router import validate_api_keys
        import urllib.request
        import urllib.error

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key-12345-valid"}):
            with patch.object(urllib.request, 'urlopen', side_effect=urllib.error.URLError("Connection refused")):
                valid, errors = validate_api_keys(["openrouter"], ping=True)

        assert valid is False
        assert "openrouter" in errors
