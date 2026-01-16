"""Tests for cost tracking."""

import pytest
from datetime import date

from src.healing.costs import (
    CostTracker,
    CostStatus,
    get_cost_tracker,
    reset_cost_tracker,
)
from src.healing.safety import SafetyCategory
from src.healing.config import reset_config


class TestCostTracker:
    """Tests for CostTracker."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset config and cost tracker before each test."""
        reset_config()
        reset_cost_tracker()
        yield

    @pytest.fixture
    def tracker(self):
        """Create a fresh CostTracker."""
        return CostTracker()

    def test_initial_status(self, tracker):
        """Initial status should be zero usage."""
        status = tracker.get_status()
        assert status.daily_cost_usd == 0.0
        assert status.daily_validations == 0
        assert status.daily_embeddings == 0

    def test_record_embedding_cost(self, tracker):
        """Recording embeddings should increase cost."""
        tracker.record("embedding", count=10)
        status = tracker.get_status()
        assert status.daily_cost_usd > 0
        assert status.daily_embeddings == 10

    def test_record_judge_cost(self, tracker):
        """Recording judge calls should increase cost and count."""
        tracker.record("judge_claude")
        status = tracker.get_status()
        assert status.daily_cost_usd > 0
        assert status.daily_validations == 1

    def test_can_validate_safe(self, tracker):
        """Should allow SAFE validations when under limit."""
        allowed, reason = tracker.can_validate(SafetyCategory.SAFE)
        assert allowed
        assert reason == "OK"

    def test_can_validate_moderate(self, tracker):
        """Should allow MODERATE validations when under limit."""
        allowed, reason = tracker.can_validate(SafetyCategory.MODERATE)
        assert allowed
        assert reason == "OK"

    def test_can_validate_risky(self, tracker):
        """Should allow RISKY validations when under limit."""
        allowed, reason = tracker.can_validate(SafetyCategory.RISKY)
        assert allowed
        assert reason == "OK"

    def test_estimate_cost_safe(self, tracker):
        """SAFE should require 1 judge."""
        cost = tracker.estimate_cost(SafetyCategory.SAFE)
        # 1 judge at ~$0.035 average
        assert cost > 0
        assert cost < 0.1

    def test_estimate_cost_moderate(self, tracker):
        """MODERATE should require 2 judges."""
        cost = tracker.estimate_cost(SafetyCategory.MODERATE)
        safe_cost = tracker.estimate_cost(SafetyCategory.SAFE)
        # Should be roughly 2x the safe cost
        assert cost > safe_cost

    def test_estimate_cost_risky(self, tracker):
        """RISKY should require 3 judges."""
        cost = tracker.estimate_cost(SafetyCategory.RISKY)
        moderate_cost = tracker.estimate_cost(SafetyCategory.MODERATE)
        # Should be roughly 1.5x the moderate cost
        assert cost > moderate_cost

    def test_reset(self, tracker):
        """Reset should clear all counters."""
        tracker.record("judge_claude")
        tracker.record("embedding", count=5)
        tracker.reset()
        status = tracker.get_status()
        assert status.daily_cost_usd == 0.0
        assert status.daily_validations == 0
        assert status.daily_embeddings == 0


class TestCostStatus:
    """Tests for CostStatus dataclass."""

    def test_is_over_budget(self):
        """Should detect when over budget."""
        status = CostStatus(
            daily_cost_usd=15.0,
            daily_limit_usd=10.0,
            daily_validations=50,
            validation_limit=100,
            daily_embeddings=100,
            budget_remaining_usd=-5.0,
        )
        assert status.is_over_budget

    def test_not_over_budget(self):
        """Should detect when not over budget."""
        status = CostStatus(
            daily_cost_usd=5.0,
            daily_limit_usd=10.0,
            daily_validations=50,
            validation_limit=100,
            daily_embeddings=100,
            budget_remaining_usd=5.0,
        )
        assert not status.is_over_budget

    def test_is_over_validation_limit(self):
        """Should detect when over validation limit."""
        status = CostStatus(
            daily_cost_usd=5.0,
            daily_limit_usd=10.0,
            daily_validations=100,
            validation_limit=100,
            daily_embeddings=100,
            budget_remaining_usd=5.0,
        )
        assert status.is_over_validation_limit


class TestGlobalCostTracker:
    """Tests for global cost tracker functions."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset tracker before each test."""
        reset_cost_tracker()
        yield
        reset_cost_tracker()

    def test_get_cost_tracker(self):
        """Should return a singleton."""
        tracker1 = get_cost_tracker()
        tracker2 = get_cost_tracker()
        assert tracker1 is tracker2

    def test_reset_creates_new_instance(self):
        """Reset should create a new instance."""
        tracker1 = get_cost_tracker()
        reset_cost_tracker()
        tracker2 = get_cost_tracker()
        assert tracker1 is not tracker2
