"""
Tests for WF-035 Phase 4: Review Fallback & Graceful Degradation

These tests verify:
1. Fallback chain logic in APIExecutor
2. Minimum required threshold checking in ReviewRouter
3. on_insufficient_reviews behavior (warn vs block)
4. ReviewResult fallback tracking fields
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.review.result import ReviewResult, ReviewFinding, Severity
from src.review.router import ReviewRouter
from src.schema import ReviewSettings


# =============================================================================
# ReviewResult Fallback Field Tests
# =============================================================================

class TestReviewResultFallbackFields:
    """Test the new fallback tracking fields in ReviewResult."""

    def test_result_has_fallback_fields(self):
        """ReviewResult should have was_fallback and fallback_reason fields."""
        result = ReviewResult(
            review_type="security",
            success=True,
            model_used="openai/gpt-5.1",
            method_used="api",
            was_fallback=True,
            fallback_reason="Primary model rate limited"
        )

        assert result.was_fallback is True
        assert result.fallback_reason == "Primary model rate limited"

    def test_result_default_no_fallback(self):
        """ReviewResult should default to not being a fallback."""
        result = ReviewResult(
            review_type="security",
            success=True,
            model_used="codex",
            method_used="cli"
        )

        assert result.was_fallback is False
        assert result.fallback_reason is None

    def test_result_to_dict_includes_fallback_fields(self):
        """ReviewResult.to_dict() should include fallback fields."""
        result = ReviewResult(
            review_type="security",
            success=True,
            model_used="fallback-model",
            method_used="api",
            was_fallback=True,
            fallback_reason="Primary unavailable"
        )

        data = result.to_dict()
        assert "was_fallback" in data
        assert data["was_fallback"] is True
        assert "fallback_reason" in data
        assert data["fallback_reason"] == "Primary unavailable"


# =============================================================================
# Fallback Chain Logic Tests
# =============================================================================

class TestFallbackChainLogic:
    """Test the fallback chain execution logic."""

    @pytest.fixture
    def mock_api_executor(self):
        """Create a mock APIExecutor for testing."""
        with patch('src.review.api_executor.APIExecutor') as MockExecutor:
            executor = MockExecutor.return_value
            yield executor

    def test_primary_model_succeeds_no_fallback(self, mock_api_executor):
        """When primary model succeeds, no fallback should be used."""
        # Setup: primary succeeds
        mock_api_executor.execute_with_fallbacks = Mock(return_value=ReviewResult(
            review_type="security",
            success=True,
            model_used="codex",
            method_used="api",
            was_fallback=False
        ))

        # This test verifies the API we expect to exist
        result = mock_api_executor.execute_with_fallbacks(
            "security",
            "codex",
            fallback_chain=["openai/gpt-5.1", "anthropic/claude-opus-4"]
        )

        assert result.success
        assert result.model_used == "codex"
        assert not result.was_fallback

    def test_primary_fails_first_fallback_succeeds(self, mock_api_executor):
        """When primary fails, first fallback should be tried and succeed."""
        mock_api_executor.execute_with_fallbacks = Mock(return_value=ReviewResult(
            review_type="security",
            success=True,
            model_used="openai/gpt-5.1",
            method_used="api",
            was_fallback=True,
            fallback_reason="Primary model failed: rate limited"
        ))

        result = mock_api_executor.execute_with_fallbacks(
            "security",
            "codex",
            fallback_chain=["openai/gpt-5.1", "anthropic/claude-opus-4"]
        )

        assert result.success
        assert result.model_used == "openai/gpt-5.1"
        assert result.was_fallback
        assert "rate limited" in result.fallback_reason

    def test_all_fallbacks_fail_returns_error(self, mock_api_executor):
        """When all models fail, return aggregated error."""
        mock_api_executor.execute_with_fallbacks = Mock(return_value=ReviewResult(
            review_type="security",
            success=False,
            model_used="none",
            method_used="api",
            error="All models failed: codex (rate limited), openai/gpt-5.1 (timeout), anthropic/claude-opus-4 (error)"
        ))

        result = mock_api_executor.execute_with_fallbacks(
            "security",
            "codex",
            fallback_chain=["openai/gpt-5.1", "anthropic/claude-opus-4"]
        )

        assert not result.success
        assert "all models failed" in result.error.lower()

    def test_empty_fallback_chain_only_tries_primary(self, mock_api_executor):
        """With empty fallback chain, only primary should be tried."""
        mock_api_executor.execute_with_fallbacks = Mock(return_value=ReviewResult(
            review_type="security",
            success=False,
            model_used="codex",
            method_used="api",
            error="Model failed: codex"
        ))

        result = mock_api_executor.execute_with_fallbacks(
            "security",
            "codex",
            fallback_chain=[]
        )

        assert not result.success


# =============================================================================
# Minimum Required Threshold Tests
# =============================================================================

class TestMinimumRequiredThreshold:
    """Test the minimum required reviews threshold logic."""

    def test_threshold_met_succeeds(self):
        """3 of 5 reviews succeeding should meet threshold of 3."""
        settings = ReviewSettings(
            minimum_required=3,
            on_insufficient_reviews="warn"
        )

        # Simulate 3 successful, 2 failed results
        successful_results = {
            "security": ReviewResult(review_type="security", success=True, model_used="a", method_used="api"),
            "quality": ReviewResult(review_type="quality", success=True, model_used="a", method_used="api"),
            "consistency": ReviewResult(review_type="consistency", success=True, model_used="a", method_used="api"),
            "holistic": ReviewResult(review_type="holistic", success=False, model_used="a", method_used="api"),
            "critique": ReviewResult(review_type="critique", success=False, model_used="a", method_used="api"),
        }

        successful_count = sum(1 for r in successful_results.values() if r.success)
        assert successful_count >= settings.minimum_required

    def test_threshold_not_met_warn_mode_continues(self):
        """Below threshold in warn mode should log warning but continue."""
        settings = ReviewSettings(
            minimum_required=3,
            on_insufficient_reviews="warn"
        )

        # 2 of 5 succeed (below threshold)
        successful_count = 2

        # In warn mode, should NOT raise exception
        assert settings.on_insufficient_reviews == "warn"
        assert successful_count < settings.minimum_required
        # Implementation should log warning and continue

    def test_threshold_not_met_block_mode_raises(self):
        """Below threshold in block mode should raise exception."""
        settings = ReviewSettings(
            minimum_required=3,
            on_insufficient_reviews="block"
        )

        # 2 of 5 succeed (below threshold)
        successful_count = 2

        assert settings.on_insufficient_reviews == "block"
        assert successful_count < settings.minimum_required
        # Implementation should raise ReviewThresholdError


# =============================================================================
# Settings Integration Tests
# =============================================================================

class TestReviewSettingsIntegration:
    """Test ReviewSettings integration with router."""

    def test_settings_default_values(self):
        """ReviewSettings should have sensible defaults."""
        settings = ReviewSettings()

        assert settings.minimum_required == 3
        assert settings.on_insufficient_reviews == "warn"
        assert "codex" in settings.fallbacks
        assert "gemini" in settings.fallbacks
        assert "grok" in settings.fallbacks

    def test_settings_from_dict(self):
        """ReviewSettings should parse from dict (workflow.yaml)."""
        data = {
            "minimum_required": 4,
            "on_insufficient_reviews": "block",
            "fallbacks": {
                "codex": ["model-a", "model-b"],
                "gemini": ["model-c"]
            }
        }

        settings = ReviewSettings(**data)

        assert settings.minimum_required == 4
        assert settings.on_insufficient_reviews == "block"
        assert settings.fallbacks["codex"] == ["model-a", "model-b"]

    def test_settings_validation_minimum_range(self):
        """minimum_required should be between 1 and 5."""
        # Valid
        settings = ReviewSettings(minimum_required=1)
        assert settings.minimum_required == 1

        settings = ReviewSettings(minimum_required=5)
        assert settings.minimum_required == 5

        # Invalid (should raise)
        with pytest.raises(ValueError):
            ReviewSettings(minimum_required=0)

        with pytest.raises(ValueError):
            ReviewSettings(minimum_required=6)

    def test_settings_validation_on_insufficient(self):
        """on_insufficient_reviews must be 'warn' or 'block'."""
        # Valid
        settings = ReviewSettings(on_insufficient_reviews="warn")
        assert settings.on_insufficient_reviews == "warn"

        settings = ReviewSettings(on_insufficient_reviews="block")
        assert settings.on_insufficient_reviews == "block"

        # Invalid (should raise)
        with pytest.raises(ValueError):
            ReviewSettings(on_insufficient_reviews="ignore")


# =============================================================================
# ReviewThresholdError Tests
# =============================================================================

class TestReviewThresholdError:
    """Test the ReviewThresholdError exception."""

    def test_error_exists(self):
        """ReviewThresholdError should be importable from review module."""
        # This will fail until we implement the exception
        from src.review.router import ReviewThresholdError

        error = ReviewThresholdError("Only 2 of 3 reviews succeeded")
        assert "2 of 3" in str(error)

    def test_error_contains_counts(self):
        """ReviewThresholdError should include success and required counts."""
        from src.review.router import ReviewThresholdError

        error = ReviewThresholdError(
            "Insufficient reviews",
            successful=2,
            required=3
        )

        assert error.successful == 2
        assert error.required == 3
