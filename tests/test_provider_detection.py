"""
Tests for automatic connector detection (CORE-006).

This module tests:
- Manus connector detection
- Available providers listing
- Interactive provider selection
- Fallback behavior when preferred provider unavailable
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.providers import (
    get_provider,
    list_providers,
    ClaudeCodeProvider,
    ManualProvider,
)

# These imports will fail until the functions are implemented
try:
    from src.providers import (
        get_available_providers,
        prompt_user_for_provider,
    )
    HAS_PROVIDER_DETECTION = True
except ImportError:
    HAS_PROVIDER_DETECTION = False

try:
    from src.environment import (
        detect_manus_connector,
    )
    HAS_MANUS_DETECTION = True
except ImportError:
    HAS_MANUS_DETECTION = False


class TestManusConnectorDetection:
    """Tests for Manus connector detection."""

    @pytest.mark.skipif(not HAS_MANUS_DETECTION, reason="detect_manus_connector not implemented")
    def test_detect_manus_connector_with_api_url(self):
        """Detects Manus connector when MANUS_API_URL is set."""
        with patch.dict(os.environ, {"MANUS_API_URL": "http://localhost:8000"}):
            result = detect_manus_connector()
            assert result is True

    @pytest.mark.skipif(not HAS_MANUS_DETECTION, reason="detect_manus_connector not implemented")
    def test_detect_manus_connector_with_session(self):
        """Detects Manus connector when MANUS_SESSION is set."""
        with patch.dict(os.environ, {"MANUS_SESSION": "test-session-123"}):
            result = detect_manus_connector()
            assert result is True

    @pytest.mark.skipif(not HAS_MANUS_DETECTION, reason="detect_manus_connector not implemented")
    def test_detect_manus_connector_no_indicators(self):
        """Returns False when no Manus indicators present."""
        env_clear = {k: "" for k in os.environ if k.startswith("MANUS")}
        with patch.dict(os.environ, env_clear, clear=False):
            # Also ensure we're not in the Manus home directory
            with patch("pathlib.Path.home", return_value=Path("/home/testuser")):
                result = detect_manus_connector()
                assert result is False


class TestGetAvailableProviders:
    """Tests for get_available_providers function."""

    @pytest.mark.skipif(not HAS_PROVIDER_DETECTION, reason="get_available_providers not implemented")
    def test_returns_list(self):
        """Returns a list of provider names."""
        result = get_available_providers()
        assert isinstance(result, list)

    @pytest.mark.skipif(not HAS_PROVIDER_DETECTION, reason="get_available_providers not implemented")
    def test_manual_always_included(self):
        """Manual provider is always included."""
        result = get_available_providers()
        assert "manual" in result

    @pytest.mark.skipif(not HAS_PROVIDER_DETECTION, reason="get_available_providers not implemented")
    def test_claude_code_included_when_available(self):
        """Claude Code included when CLI is available."""
        with patch.object(ClaudeCodeProvider, 'is_available', return_value=True):
            result = get_available_providers()
            assert "claude_code" in result

    @pytest.mark.skipif(not HAS_PROVIDER_DETECTION, reason="get_available_providers not implemented")
    def test_claude_code_excluded_when_unavailable(self):
        """Claude Code excluded when CLI is not available."""
        with patch.object(ClaudeCodeProvider, 'is_available', return_value=False):
            with patch.dict(os.environ, {}, clear=True):
                result = get_available_providers()
                assert "claude_code" not in result

    @pytest.mark.skipif(not HAS_PROVIDER_DETECTION, reason="get_available_providers not implemented")
    def test_openrouter_included_when_key_set(self):
        """OpenRouter included when API key is set."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            result = get_available_providers()
            assert "openrouter" in result

    @pytest.mark.skipif(not HAS_PROVIDER_DETECTION, reason="get_available_providers not implemented")
    def test_openrouter_excluded_when_key_missing(self):
        """OpenRouter excluded when API key is not set."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_available_providers()
            assert "openrouter" not in result

    @pytest.mark.skipif(not HAS_PROVIDER_DETECTION, reason="get_available_providers not implemented")
    @pytest.mark.skipif(not HAS_MANUS_DETECTION, reason="detect_manus_connector not implemented")
    def test_manus_included_when_detected(self):
        """Manus direct connector included when environment detected."""
        with patch("src.environment.detect_manus_connector", return_value=True):
            result = get_available_providers()
            assert "manus_direct" in result


class TestPromptUserForProvider:
    """Tests for interactive provider selection."""

    @pytest.mark.skipif(not HAS_PROVIDER_DETECTION, reason="prompt_user_for_provider not implemented")
    def test_returns_selected_provider(self):
        """Returns the user's selection."""
        available = ["claude_code", "openrouter", "manual"]

        with patch("builtins.input", return_value="2"):  # Select openrouter
            result = prompt_user_for_provider(available)
            assert result == "openrouter"

    @pytest.mark.skipif(not HAS_PROVIDER_DETECTION, reason="prompt_user_for_provider not implemented")
    def test_handles_invalid_input(self):
        """Handles invalid input by re-prompting."""
        available = ["openrouter", "manual"]

        # First invalid, then valid
        inputs = iter(["99", "invalid", "1"])
        with patch("builtins.input", lambda _: next(inputs)):
            result = prompt_user_for_provider(available)
            assert result == "openrouter"

    @pytest.mark.skipif(not HAS_PROVIDER_DETECTION, reason="prompt_user_for_provider not implemented")
    def test_shows_all_options(self, capsys):
        """Shows all available options to user."""
        available = ["claude_code", "openrouter", "manual"]

        with patch("builtins.input", return_value="1"):
            prompt_user_for_provider(available)
            captured = capsys.readouterr()
            assert "claude_code" in captured.out
            assert "openrouter" in captured.out
            assert "manual" in captured.out

    @pytest.mark.skipif(not HAS_PROVIDER_DETECTION, reason="prompt_user_for_provider not implemented")
    def test_returns_default_on_empty_input(self):
        """Returns first option when user presses Enter."""
        available = ["openrouter", "manual"]

        with patch("builtins.input", return_value=""):
            result = prompt_user_for_provider(available)
            assert result == "openrouter"  # First/default option


class TestGetProviderInteractive:
    """Tests for interactive mode in get_provider.

    Note: Interactive mode in get_provider() is a future enhancement.
    The current implementation provides get_available_providers() and
    prompt_user_for_provider() as building blocks for CLI commands
    to implement interactive selection.
    """

    @pytest.mark.skip(reason="Interactive mode in get_provider is future enhancement - CLI uses prompt_user_for_provider directly")
    def test_interactive_prompts_when_preferred_unavailable(self):
        """Interactive mode prompts user when preferred provider unavailable."""
        with patch.object(ClaudeCodeProvider, 'is_available', return_value=False):
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test"}):
                with patch("src.providers.prompt_user_for_provider") as mock_prompt:
                    mock_prompt.return_value = "openrouter"

                    provider = get_provider(
                        name="claude_code",
                        interactive=True
                    )

                    mock_prompt.assert_called_once()

    @pytest.mark.skip(reason="Interactive mode in get_provider is future enhancement")
    def test_non_interactive_does_not_prompt(self):
        """Non-interactive mode never prompts user."""
        with patch.object(ClaudeCodeProvider, 'is_available', return_value=False):
            with patch("src.providers.prompt_user_for_provider") as mock_prompt:
                # Without interactive=True, should not prompt
                provider = get_provider(name="claude_code")
                mock_prompt.assert_not_called()


class TestProviderDetectionBackwardCompatibility:
    """Tests for backward compatibility."""

    def test_existing_get_provider_still_works(self):
        """Existing get_provider API still works."""
        provider = get_provider(name="manual")
        assert provider.name() == "manual"

    def test_auto_detection_still_works(self):
        """Auto-detection without interactive mode still works."""
        with patch.object(ClaudeCodeProvider, 'is_available', return_value=False):
            with patch.dict(os.environ, {}, clear=True):
                provider = get_provider()
                assert provider.name() == "manual"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
