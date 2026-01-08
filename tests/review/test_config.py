"""
Tests for the review configuration module.

These tests verify that review types are read from workflow.yaml
(the single source of truth) and validated properly.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# We'll create this module
from src.review.config import (
    ReviewTypeConfig,
    get_review_config,
    get_tool_for_review,
    get_available_review_types,
    ReviewConfigError,
)


class TestReviewTypeConfig:
    """Tests for ReviewTypeConfig class."""

    def test_load_from_workflow_settings(self):
        """ReviewConfig loads review types from workflow settings."""
        settings = {
            "reviews": {
                "enabled": True,
                "types": {
                    "security_review": "codex",
                    "quality_review": "codex",
                    "consistency_review": "gemini",
                }
            }
        }
        config = ReviewTypeConfig(settings)

        assert config.is_enabled()
        assert config.get_tool("security_review") == "codex"
        assert config.get_tool("quality_review") == "codex"
        assert config.get_tool("consistency_review") == "gemini"

    def test_default_config_when_not_specified(self):
        """ReviewConfig provides defaults when settings are missing."""
        config = ReviewTypeConfig({})

        # Should have sensible defaults
        assert config.is_enabled() is True  # Reviews on by default
        assert config.get_tool("security_review") == "codex"
        assert config.get_tool("quality_review") == "codex"
        assert config.get_tool("consistency_review") == "gemini"
        assert config.get_tool("holistic_review") == "gemini"
        assert config.get_tool("vibe_coding_review") == "grok"

    def test_short_name_aliases(self):
        """ReviewConfig supports short names (security, quality, etc.)."""
        settings = {
            "reviews": {
                "types": {
                    "security_review": "codex",
                    "quality_review": "codex",
                }
            }
        }
        config = ReviewTypeConfig(settings)

        # Both full and short names should work
        assert config.get_tool("security_review") == "codex"
        assert config.get_tool("security") == "codex"
        assert config.get_tool("quality_review") == "codex"
        assert config.get_tool("quality") == "codex"

    def test_invalid_tool_raises_error(self):
        """ReviewConfig raises error for invalid tool names."""
        settings = {
            "reviews": {
                "types": {
                    "security_review": "invalid_tool",
                }
            }
        }

        with pytest.raises(ReviewConfigError) as exc:
            ReviewTypeConfig(settings)

        assert "invalid_tool" in str(exc.value)
        assert "security_review" in str(exc.value)

    def test_valid_tools(self):
        """ReviewConfig accepts all valid tool names."""
        valid_tools = ["codex", "gemini", "grok"]

        for tool in valid_tools:
            settings = {
                "reviews": {
                    "types": {
                        "security_review": tool,
                    }
                }
            }
            config = ReviewTypeConfig(settings)
            assert config.get_tool("security_review") == tool

    def test_get_available_review_types(self):
        """ReviewConfig returns list of available review types."""
        settings = {
            "reviews": {
                "types": {
                    "security_review": "codex",
                    "quality_review": "codex",
                    "custom_review": "gemini",
                }
            }
        }
        config = ReviewTypeConfig(settings)

        types = config.get_available_types()
        assert "security_review" in types
        assert "quality_review" in types
        assert "custom_review" in types

    def test_unknown_review_type_uses_default(self):
        """Unknown review types fall back to gemini."""
        config = ReviewTypeConfig({})

        # Unknown type should return default (gemini)
        assert config.get_tool("unknown_review") == "gemini"

    def test_disabled_reviews(self):
        """ReviewConfig respects enabled flag."""
        settings = {
            "reviews": {
                "enabled": False,
            }
        }
        config = ReviewTypeConfig(settings)

        assert config.is_enabled() is False


class TestGetToolForReview:
    """Tests for get_tool_for_review() function."""

    def test_returns_tool_from_config(self):
        """get_tool_for_review returns tool from workflow config."""
        # Mock the config loading
        mock_config = MagicMock()
        mock_config.get_tool.return_value = "codex"

        with patch("src.review.config.get_review_config", return_value=mock_config):
            tool = get_tool_for_review("security_review")

        assert tool == "codex"
        mock_config.get_tool.assert_called_once_with("security_review")

    def test_works_with_short_names(self):
        """get_tool_for_review works with short names."""
        mock_config = MagicMock()
        mock_config.get_tool.return_value = "gemini"

        with patch("src.review.config.get_review_config", return_value=mock_config):
            tool = get_tool_for_review("holistic")

        assert tool == "gemini"


class TestGetAvailableReviewTypes:
    """Tests for get_available_review_types() function."""

    def test_returns_configured_types(self):
        """get_available_review_types returns all configured types."""
        mock_config = MagicMock()
        mock_config.get_available_types.return_value = [
            "security_review",
            "quality_review",
        ]

        with patch("src.review.config.get_review_config", return_value=mock_config):
            types = get_available_review_types()

        assert "security_review" in types
        assert "quality_review" in types


class TestReviewConfigValidation:
    """Tests for review configuration validation."""

    def test_validates_prompt_exists_for_review_type(self):
        """ReviewConfig validates that prompts exist for configured types."""
        # When we add a review type that has no prompt template,
        # validation should warn (not fail - for extensibility)
        settings = {
            "reviews": {
                "types": {
                    "security_review": "codex",
                    "nonexistent_review": "gemini",  # No prompt for this
                }
            }
        }

        # Should work but log a warning
        config = ReviewTypeConfig(settings)
        warnings = config.get_validation_warnings()

        assert any("nonexistent_review" in w for w in warnings)

    def test_all_default_types_have_prompts(self):
        """All default review types have corresponding prompts."""
        from src.review.prompts import REVIEW_PROMPTS

        default_types = [
            "security_review",
            "quality_review",
            "consistency_review",
            "holistic_review",
            "vibe_coding_review",
        ]

        for review_type in default_types:
            assert review_type in REVIEW_PROMPTS or review_type.replace("_review", "") in REVIEW_PROMPTS


class TestConfigCaching:
    """Tests for configuration caching."""

    def test_config_is_cached(self):
        """get_review_config caches the config for performance."""
        from src.review import config as config_module

        # Clear any existing cache
        config_module._cached_config = None

        config1 = get_review_config()
        config2 = get_review_config()

        # Should be the same instance
        assert config1 is config2

    def test_cache_can_be_cleared(self):
        """Config cache can be cleared for testing."""
        from src.review import config as config_module

        config1 = get_review_config()
        config_module.clear_config_cache()
        config2 = get_review_config()

        # Should be different instances after cache clear
        assert config1 is not config2
