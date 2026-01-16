"""Tests for validation pipeline."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _utcnow() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)

from src.healing.validation import (
    ValidationPipeline,
    ValidationPhase,
    ValidationResult,
    VerificationOutput,
    validate_fix,
)
from src.healing.judges import SuggestedFix, JudgeVote, JudgeResult, MultiModelJudge
from src.healing.safety import SafetyCategory
from src.healing.cascade import CascadeDetector, reset_cascade_detector
from src.healing.costs import CostTracker, reset_cost_tracker
from src.healing.adapters.base import TestResult, BuildResult, LintResult
from src.healing.models import ErrorEvent, FixAction
from src.healing.config import HealingConfig, reset_config


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_passed_preflight(self):
        """Should detect preflight pass."""
        result = ValidationResult(
            approved=True,
            phase=ValidationPhase.PRE_FLIGHT,
            reason="All checks passed",
        )
        assert result.passed_preflight

    def test_failed_preflight(self):
        """Should detect preflight failure."""
        result = ValidationResult(
            approved=False,
            phase=ValidationPhase.PRE_FLIGHT,
            reason="Kill switch active",
        )
        assert not result.passed_preflight

    def test_passed_verification(self):
        """Should detect verification pass."""
        result = ValidationResult(
            approved=True,
            phase=ValidationPhase.APPROVAL,  # Got past verification
            reason="Approved",
        )
        assert result.passed_verification

    def test_passed_approval(self):
        """Should detect approval pass."""
        result = ValidationResult(
            approved=True,
            phase=ValidationPhase.APPROVAL,
            reason="2/2 judges approved",
        )
        assert result.passed_approval


class TestValidationPipeline:
    """Tests for ValidationPipeline."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset global state before each test."""
        reset_config()
        reset_cost_tracker()
        reset_cascade_detector()
        yield

    @pytest.fixture
    def config(self):
        """Create test config."""
        return HealingConfig(
            enabled=True,
            kill_switch_active=False,
            max_daily_cost_usd=100.0,
            max_validations_per_day=1000,
        )

    @pytest.fixture
    def pipeline(self, config):
        """Create a ValidationPipeline with test config."""
        mock_judge = MagicMock(spec=MultiModelJudge)
        return ValidationPipeline(
            config=config,
            judge=mock_judge,
            execution=None,
            cascade_detector=CascadeDetector(),
            cost_tracker=CostTracker(),
        )

    @pytest.fixture
    def sample_fix(self):
        """Create a sample fix."""
        action = FixAction(action_type="diff", diff="+import os\n")
        return SuggestedFix(
            fix_id="fix-test",
            title="Add import",
            action=action,
            safety_category=SafetyCategory.SAFE,
            affected_files=["src/utils.py"],
            lines_changed=1,
            pattern={"is_preseeded": True},  # Has precedent
        )

    @pytest.fixture
    def sample_error(self):
        """Create a sample error."""
        return ErrorEvent(
            error_id="err-1",
            timestamp=_utcnow(),
            source="subprocess",
            description="ModuleNotFoundError",
            fingerprint="abc123",
        )

    @pytest.mark.asyncio
    async def test_kill_switch_blocks(self, sample_fix, sample_error):
        """Kill switch should block validation."""
        config = HealingConfig(kill_switch_active=True)
        pipeline = ValidationPipeline(config=config)

        result = await pipeline.validate(sample_fix, sample_error, skip_verification=True)

        assert not result.approved
        assert result.phase == ValidationPhase.PRE_FLIGHT
        assert "Kill switch" in result.reason

    @pytest.mark.asyncio
    async def test_hard_constraints_too_many_files(self, pipeline, sample_error):
        """Should reject fixes affecting too many files."""
        action = FixAction(action_type="diff", diff="+x\n")
        fix = SuggestedFix(
            fix_id="fix-test",
            title="Fix",
            action=action,
            safety_category=SafetyCategory.SAFE,
            affected_files=["a.py", "b.py", "c.py"],  # 3 > 2
            lines_changed=1,
            pattern={"is_preseeded": True},
        )

        result = await pipeline.validate(fix, sample_error, skip_verification=True)

        assert not result.approved
        assert "Too many files" in result.reason

    @pytest.mark.asyncio
    async def test_hard_constraints_too_many_lines(self, pipeline, sample_error):
        """Should reject fixes with too many lines changed."""
        action = FixAction(action_type="diff", diff="+x\n")
        fix = SuggestedFix(
            fix_id="fix-test",
            title="Fix",
            action=action,
            safety_category=SafetyCategory.SAFE,
            affected_files=["a.py"],
            lines_changed=50,  # > 30
            pattern={"is_preseeded": True},
        )

        result = await pipeline.validate(fix, sample_error, skip_verification=True)

        assert not result.approved
        assert "Too many lines" in result.reason

    @pytest.mark.asyncio
    async def test_no_precedent_blocks(self, pipeline, sample_error):
        """Should reject fixes without precedent."""
        action = FixAction(action_type="diff", diff="+x\n")
        fix = SuggestedFix(
            fix_id="fix-test",
            title="Fix",
            action=action,
            safety_category=SafetyCategory.SAFE,
            affected_files=["a.py"],
            lines_changed=1,
            pattern=None,  # No pattern
        )

        result = await pipeline.validate(fix, sample_error, skip_verification=True)

        assert not result.approved
        assert "No pattern" in result.reason

    @pytest.mark.asyncio
    async def test_preseeded_has_precedent(self, pipeline, sample_fix, sample_error):
        """Pre-seeded patterns should have precedent."""
        # Mock judge to return approval
        mock_result = JudgeResult(
            approved=True,
            votes=[JudgeVote(model="test", approved=True, confidence=0.9, reasoning="OK")],
            consensus_score=1.0,
            required_votes=1,
            received_votes=1,
        )
        pipeline.judge.judge = AsyncMock(return_value=mock_result)

        result = await pipeline.validate(sample_fix, sample_error, skip_verification=True)

        # Should pass preflight (preseeded has precedent)
        assert result.phase != ValidationPhase.PRE_FLIGHT or result.approved

    @pytest.mark.asyncio
    async def test_cascade_detection_blocks(self, config, sample_fix, sample_error):
        """Should block when file is hot."""
        cascade = CascadeDetector(max_mods_per_hour=2)
        # Make file hot
        cascade.record_modification("src/utils.py")
        cascade.record_modification("src/utils.py")

        # Update error to point to hot file
        sample_error.file_path = "src/utils.py"

        pipeline = ValidationPipeline(
            config=config,
            cascade_detector=cascade,
        )

        result = await pipeline.validate(sample_fix, sample_error, skip_verification=True)

        assert not result.approved
        assert "hot" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_risky_never_auto_approved(self, pipeline, sample_error):
        """RISKY fixes should never be auto-approved."""
        action = FixAction(action_type="diff", diff="+x\n")
        fix = SuggestedFix(
            fix_id="fix-test",
            title="Fix",
            action=action,
            safety_category=SafetyCategory.RISKY,
            affected_files=["a.py"],
            lines_changed=1,
            pattern={"is_preseeded": True},
        )

        result = await pipeline.validate(fix, sample_error, skip_verification=True)

        assert not result.approved
        assert "RISKY" in result.reason or "human" in result.reason.lower()


class TestValidateFixFunction:
    """Tests for the validate_fix convenience function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset global state."""
        reset_config()
        reset_cost_tracker()
        reset_cascade_detector()
        yield

    @pytest.mark.asyncio
    async def test_validate_fix_basic(self):
        """Should run validation through convenience function."""
        action = FixAction(action_type="diff", diff="+x\n")
        fix = SuggestedFix(
            fix_id="fix-test",
            title="Fix",
            action=action,
            safety_category=SafetyCategory.SAFE,
            affected_files=["a.py"],
            lines_changed=1,
            pattern=None,  # No pattern - will fail precedent check
        )
        error = ErrorEvent(
            error_id="err-1",
            timestamp=_utcnow(),
            source="subprocess",
            description="Error",
            fingerprint="abc123",
        )

        result = await validate_fix(fix, error, skip_verification=True)

        # Should fail (no pattern)
        assert isinstance(result, ValidationResult)
        assert not result.approved
