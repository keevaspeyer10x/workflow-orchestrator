"""
Tests for supervision mode configuration and validation.

These tests verify that:
1. supervision_mode defaults to 'supervised' (backward compatible)
2. Invalid supervision modes are rejected
3. Valid modes (supervised, zero_human, hybrid) are accepted
"""

import pytest
from src.schema import WorkflowDef, SupervisionMode, WorkflowSettings


class TestSupervisionModeDefaults:
    """Test default behavior for backward compatibility."""

    def test_supervision_mode_defaults_to_supervised(self):
        """Workflows without supervision_mode should default to supervised."""
        workflow = WorkflowDef(
            name="Test Workflow",
            phases=[],
            settings={}  # No supervision_mode specified
        )

        settings = WorkflowSettings(**workflow.settings)
        assert settings.supervision_mode == SupervisionMode.SUPERVISED

    def test_empty_settings_defaults_to_supervised(self):
        """Empty settings dict should default to supervised."""
        settings = WorkflowSettings()
        assert settings.supervision_mode == SupervisionMode.SUPERVISED


class TestSupervisionModeValidation:
    """Test validation of supervision_mode values."""

    @pytest.mark.parametrize("invalid_mode", [
        "invalid",
        "zero-human",  # Typo (should be zero_human)
        "SUPERVISED",  # Wrong case
        "Zero_Human",  # Wrong case
        "",
        123,  # Wrong type
    ])
    def test_invalid_supervision_modes_rejected(self, invalid_mode):
        """Invalid supervision modes should raise validation error."""
        with pytest.raises((ValueError, TypeError)):
            WorkflowSettings(supervision_mode=invalid_mode)

    @pytest.mark.parametrize("valid_mode", [
        "supervised",
        "zero_human",
        "hybrid",
        SupervisionMode.SUPERVISED,
        SupervisionMode.ZERO_HUMAN,
        SupervisionMode.HYBRID,
    ])
    def test_valid_supervision_modes_accepted(self, valid_mode):
        """All valid supervision modes should be accepted."""
        settings = WorkflowSettings(supervision_mode=valid_mode)

        # Should be stored as enum
        assert isinstance(settings.supervision_mode, SupervisionMode)

        # Verify it matches expected value
        if isinstance(valid_mode, str):
            assert settings.supervision_mode.value == valid_mode
        else:
            assert settings.supervision_mode == valid_mode


class TestWorkflowSettingsModel:
    """Test WorkflowSettings Pydantic model."""

    def test_workflow_settings_basic_structure(self):
        """WorkflowSettings should have all required fields."""
        settings = WorkflowSettings(
            supervision_mode="supervised",
            smoke_test_command="pytest tests/smoke/",
            test_command="pytest tests/",
            build_command="python -m build"
        )

        assert settings.supervision_mode == SupervisionMode.SUPERVISED
        assert settings.smoke_test_command == "pytest tests/smoke/"
        assert settings.test_command == "pytest tests/"
        assert settings.build_command == "python -m build"

    def test_smoke_test_command_optional(self):
        """smoke_test_command should be optional."""
        settings = WorkflowSettings()
        assert settings.smoke_test_command is None

    def test_settings_to_dict(self):
        """Settings should serialize to dict correctly."""
        settings = WorkflowSettings(
            supervision_mode="zero_human",
            smoke_test_command="echo test"
        )

        data = settings.model_dump()
        assert data["supervision_mode"] == "zero_human"
        assert data["smoke_test_command"] == "echo test"


class TestReviewSettings:
    """Test ReviewSettings nested model."""

    def test_review_settings_defaults(self):
        """ReviewSettings should have sensible defaults."""
        from src.schema import ReviewSettings

        settings = ReviewSettings()

        assert settings.enabled is True
        assert settings.minimum_required == 3
        assert isinstance(settings.fallbacks, dict)
        assert "codex" in settings.fallbacks
        assert "gemini" in settings.fallbacks
        assert "grok" in settings.fallbacks
        assert settings.on_insufficient_reviews == "warn"

    def test_review_fallback_configuration(self):
        """Review fallbacks should be configurable."""
        from src.schema import ReviewSettings

        settings = ReviewSettings(
            minimum_required=4,
            fallbacks={
                "codex": ["openai/gpt-5.1", "anthropic/claude-opus-4"],
                "gemini": ["google/gemini-3-pro"]
            },
            on_insufficient_reviews="block"
        )

        assert settings.minimum_required == 4
        assert len(settings.fallbacks["codex"]) == 2
        assert settings.on_insufficient_reviews == "block"

    def test_minimum_required_validation(self):
        """minimum_required should be validated (1-5)."""
        from src.schema import ReviewSettings

        # Valid range
        for value in [1, 2, 3, 4, 5]:
            settings = ReviewSettings(minimum_required=value)
            assert settings.minimum_required == value

        # Invalid values
        with pytest.raises(ValueError):
            ReviewSettings(minimum_required=0)

        with pytest.raises(ValueError):
            ReviewSettings(minimum_required=6)

    def test_on_insufficient_reviews_validation(self):
        """on_insufficient_reviews should only accept warn or block."""
        from src.schema import ReviewSettings

        # Valid values
        settings_warn = ReviewSettings(on_insufficient_reviews="warn")
        assert settings_warn.on_insufficient_reviews == "warn"

        settings_block = ReviewSettings(on_insufficient_reviews="block")
        assert settings_block.on_insufficient_reviews == "block"

        # Invalid value
        with pytest.raises(ValueError):
            ReviewSettings(on_insufficient_reviews="invalid")


class TestWorkflowSettingsIntegration:
    """Test WorkflowSettings integrated into WorkflowDef."""

    def test_workflow_with_typed_settings(self):
        """WorkflowDef should accept typed settings."""
        from src.schema import WorkflowSettings

        settings = WorkflowSettings(
            supervision_mode="zero_human",
            smoke_test_command="pytest tests/smoke/"
        )

        workflow = WorkflowDef(
            name="Test",
            phases=[],
            settings=settings.model_dump()
        )

        # Should be able to reconstruct settings
        reconstructed = WorkflowSettings(**workflow.settings)
        assert reconstructed.supervision_mode == SupervisionMode.ZERO_HUMAN
        assert reconstructed.smoke_test_command == "pytest tests/smoke/"
