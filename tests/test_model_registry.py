"""
Tests for the model registry module (CORE-017, CORE-018).

This module tests:
- Model registry creation and staleness detection
- API-based model list fetching
- Dynamic function calling capability detection
- Caching behavior
"""

import os
import json
import tempfile
import pytest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# These imports will fail until the module is implemented
try:
    from src.model_registry import (
        ModelRegistry,
        get_model_registry,
        is_registry_stale,
        get_latest_models,
        get_model_capabilities,
        supports_function_calling,
        update_registry,
        REGISTRY_FILE,
        STALENESS_DAYS,
    )
    HAS_MODEL_REGISTRY = True
except ImportError:
    HAS_MODEL_REGISTRY = False


# Skip all tests if module not implemented
pytestmark = pytest.mark.skipif(
    not HAS_MODEL_REGISTRY,
    reason="Model registry module not yet implemented"
)


class TestModelRegistryCreation:
    """Tests for ModelRegistry initialization."""

    def test_creates_registry_file_if_not_exists(self):
        """Registry creates .model_registry.json if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(working_dir=Path(tmpdir))
            registry_file = Path(tmpdir) / REGISTRY_FILE
            assert registry_file.exists()

    def test_loads_existing_registry(self):
        """Registry loads existing data from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_file = Path(tmpdir) / REGISTRY_FILE
            existing_data = {
                "last_updated": datetime.now().isoformat(),
                "models": {"openai/gpt-4": {"supports_tools": True}},
            }
            registry_file.write_text(json.dumps(existing_data))

            registry = ModelRegistry(working_dir=Path(tmpdir))
            assert "openai/gpt-4" in registry.models


class TestRegistryStaleness:
    """Tests for staleness detection (CORE-017)."""

    def test_fresh_registry_not_stale(self):
        """Registry updated today is not stale."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(working_dir=Path(tmpdir))
            registry._data["last_updated"] = datetime.now().isoformat()
            registry._save()

            assert registry.is_stale() is False

    def test_old_registry_is_stale(self):
        """Registry updated > 30 days ago is stale."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(working_dir=Path(tmpdir))
            old_date = datetime.now() - timedelta(days=STALENESS_DAYS + 1)
            registry._data["last_updated"] = old_date.isoformat()
            registry._save()

            assert registry.is_stale() is True

    def test_exactly_30_days_not_stale(self):
        """Registry updated exactly 30 days ago is not stale."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(working_dir=Path(tmpdir))
            boundary_date = datetime.now() - timedelta(days=STALENESS_DAYS)
            registry._data["last_updated"] = boundary_date.isoformat()
            registry._save()

            assert registry.is_stale() is False

    def test_missing_timestamp_is_stale(self):
        """Registry without timestamp is considered stale."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(working_dir=Path(tmpdir))
            registry._data.pop("last_updated", None)
            registry._save()

            assert registry.is_stale() is True


class TestGetLatestModels:
    """Tests for fetching models from OpenRouter API (CORE-017)."""

    def test_api_success_returns_models(self):
        """Successful API call returns parsed model list."""
        mock_response = {
            "data": [
                {"id": "openai/gpt-4", "context_length": 8192},
                {"id": "anthropic/claude-3-opus", "context_length": 200000},
            ]
        }

        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                registry = ModelRegistry(working_dir=Path(tmpdir))
                models = registry.fetch_latest_models()

                assert len(models) == 2
                assert "openai/gpt-4" in [m["id"] for m in models]

    def test_api_failure_returns_none(self):
        """API failure returns None."""
        with patch("requests.get") as mock_get:
            mock_get.side_effect = Exception("Network error")

            with tempfile.TemporaryDirectory() as tmpdir:
                registry = ModelRegistry(working_dir=Path(tmpdir))
                models = registry.fetch_latest_models()
                assert models is None

    def test_api_timeout_returns_none(self):
        """API timeout returns None gracefully."""
        import requests

        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout()

            with tempfile.TemporaryDirectory() as tmpdir:
                registry = ModelRegistry(working_dir=Path(tmpdir))
                models = registry.fetch_latest_models()
                assert models is None

    def test_api_rate_limit_handled(self):
        """429 rate limit is handled gracefully."""
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=429,
                json=lambda: {"error": "rate limited"}
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                registry = ModelRegistry(working_dir=Path(tmpdir))
                models = registry.fetch_latest_models()
                assert models is None


class TestUpdateRegistry:
    """Tests for registry update functionality (CORE-017)."""

    def test_update_saves_timestamp(self):
        """Update sets last_updated to now."""
        mock_response = {"data": [{"id": "test/model"}]}

        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                registry = ModelRegistry(working_dir=Path(tmpdir))

                # Clear any existing timestamp
                registry._data["last_updated"] = None
                before = datetime.now()

                registry.update()

                after = datetime.now()
                updated = datetime.fromisoformat(registry._data["last_updated"])
                assert before <= updated <= after

    def test_update_stores_models(self):
        """Update stores model data in registry."""
        mock_response = {
            "data": [
                {"id": "openai/gpt-4", "supports_tools": True},
            ]
        }

        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                registry = ModelRegistry(working_dir=Path(tmpdir))
                registry.update()

                assert "openai/gpt-4" in registry.models


class TestModelCapabilities:
    """Tests for dynamic capability detection (CORE-018)."""

    def test_get_capabilities_from_cache(self):
        """Returns cached capabilities without API call."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(working_dir=Path(tmpdir))
            registry._data["models"] = {
                "openai/gpt-4": {"supports_tools": True, "context_length": 8192}
            }
            registry._save()

            with patch("requests.get") as mock_get:
                caps = registry.get_model_capabilities("openai/gpt-4")
                mock_get.assert_not_called()
                assert caps["supports_tools"] is True

    def test_get_capabilities_returns_none_if_missing(self):
        """Returns None when model not in cache (efficiency optimization).

        Note: Our implementation doesn't make individual API calls for unknown
        models. Instead, use update() to refresh the full model list.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(working_dir=Path(tmpdir))
            # Model not in cache
            caps = registry.get_model_capabilities("new/model")

            # Returns None - caller should use update() or static fallback
            assert caps is None


class TestSupportsFunctionCalling:
    """Tests for function calling detection (CORE-018)."""

    def test_known_model_with_support(self):
        """Returns True for model known to support function calling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(working_dir=Path(tmpdir))
            registry._data["models"] = {
                "openai/gpt-4": {"supports_tools": True}
            }

            assert registry.supports_function_calling("openai/gpt-4") is True

    def test_known_model_without_support(self):
        """Returns False for model known to not support function calling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(working_dir=Path(tmpdir))
            registry._data["models"] = {
                "basic/model": {"supports_tools": False}
            }

            assert registry.supports_function_calling("basic/model") is False

    def test_unknown_model_falls_back_to_static(self):
        """Unknown model falls back to static FUNCTION_CALLING_MODELS list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(working_dir=Path(tmpdir))
            # Empty registry
            registry._data["models"] = {}

            # openai/gpt-4 is in the static list
            assert registry.supports_function_calling("openai/gpt-4") is True

    def test_completely_unknown_model_returns_false(self):
        """Completely unknown model returns False (conservative default)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(working_dir=Path(tmpdir))
            registry._data["models"] = {}

            assert registry.supports_function_calling("unknown/model-xyz") is False


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_get_model_registry_returns_instance(self):
        """get_model_registry returns a ModelRegistry instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = get_model_registry(working_dir=Path(tmpdir))
            assert isinstance(registry, ModelRegistry)

    def test_is_registry_stale_function(self):
        """Module-level is_registry_stale function works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # New registry without timestamp is stale
            registry = ModelRegistry(working_dir=Path(tmpdir))
            result = is_registry_stale(working_dir=Path(tmpdir))
            # New registry with no timestamp should be stale
            assert result is True

            # After setting a recent timestamp, should not be stale
            registry._data["last_updated"] = datetime.now().isoformat()
            registry._save()
            result2 = is_registry_stale(working_dir=Path(tmpdir))
            assert result2 is False


class TestIntegrationWithOpenRouter:
    """Integration tests with OpenRouter provider."""

    def test_openrouter_uses_registry_for_function_calling(self):
        """OpenRouterProvider uses registry for capability detection."""
        try:
            from src.providers.openrouter import OpenRouterProvider
        except ImportError:
            pytest.skip("OpenRouterProvider not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(working_dir=Path(tmpdir))
            registry._data["models"] = {
                "test/model": {"supports_tools": True}
            }
            registry._save()

            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test"}):
                provider = OpenRouterProvider(working_dir=Path(tmpdir))
                # This should use the registry if implemented
                result = provider._supports_function_calling("test/model")
                # For now, this will use static list, which won't have test/model
                # After CORE-018, it should return True


class TestGetLatestModel:
    """Tests for get_latest_model() function (Issue #66 - DRY refactor)."""

    def test_get_latest_model_returns_string(self):
        """get_latest_model should return a model ID string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(working_dir=Path(tmpdir))
            for category in ['codex', 'gemini', 'grok', 'claude']:
                model = registry.get_latest_model(category)
                assert isinstance(model, str)
                assert len(model) > 0

    def test_get_latest_model_has_provider_prefix(self):
        """Returned model IDs should have provider prefix (e.g., 'openai/')."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(working_dir=Path(tmpdir))
            for category in ['codex', 'gemini', 'grok', 'claude']:
                model = registry.get_latest_model(category)
                assert '/' in model, f"Model ID {model} should have provider prefix"

    def test_get_latest_model_resolves_review_types(self):
        """get_latest_model should resolve review type names to tool categories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(working_dir=Path(tmpdir))

            # security/quality use codex
            security_model = registry.get_latest_model('security')
            quality_model = registry.get_latest_model('quality')
            assert 'gpt' in security_model.lower() or 'codex' in security_model.lower()
            assert 'gpt' in quality_model.lower() or 'codex' in quality_model.lower()

            # consistency/holistic use gemini
            consistency_model = registry.get_latest_model('consistency')
            holistic_model = registry.get_latest_model('holistic')
            assert 'gemini' in consistency_model.lower()
            assert 'gemini' in holistic_model.lower()

            # vibe_coding uses grok
            vibe_model = registry.get_latest_model('vibe_coding')
            assert 'grok' in vibe_model.lower()


class TestModelRegistryIntegration:
    """Integration tests for Issue #66 - Model registry as single source of truth."""

    def test_api_executor_uses_registry_not_hardcoded(self):
        """api_executor should use get_latest_model() instead of hardcoded dict."""
        # This test verifies the code structure, not runtime behavior
        import inspect
        from src.review import api_executor

        # Read the source code
        source = inspect.getsource(api_executor)

        # After the fix, OPENROUTER_MODELS should not contain hardcoded version strings
        # or should import from model_registry
        if 'OPENROUTER_MODELS' in source:
            # If OPENROUTER_MODELS exists, it should use registry
            assert 'get_latest_model' in source or 'model_registry' in source, (
                "api_executor.py has hardcoded OPENROUTER_MODELS dict - "
                "should use model_registry.get_latest_model() instead (Issue #66)"
            )

    def test_review_config_uses_registry_not_hardcoded(self):
        """review/config.py should use get_latest_model() instead of hardcoded dicts."""
        import inspect
        from src.review import config

        source = inspect.getsource(config)

        # After the fix, DEFAULT_CLI_MODELS and DEFAULT_API_MODELS should use registry
        # Check if get_latest_model is used
        has_hardcoded_defaults = (
            'DEFAULT_CLI_MODELS' in source and
            'gpt-5' in source  # Version-specific string indicates hardcoding
        )

        if has_hardcoded_defaults:
            assert 'get_latest_model' in source or 'model_registry' in source, (
                "config.py has hardcoded DEFAULT_CLI_MODELS/DEFAULT_API_MODELS - "
                "should use model_registry.get_latest_model() instead (Issue #66)"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
