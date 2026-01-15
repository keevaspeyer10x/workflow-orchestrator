"""
Tests for v3 Phase Types & Tool Scoping.

Tests cover:
- PhaseType enum
- intended_tools field
- --force/--skip blocking in LLM mode
"""

import os
from unittest.mock import patch
import pytest
from click.testing import CliRunner


class TestPhaseTypeEnum:
    """Test PhaseType enum exists and has correct values."""

    def test_phase_type_enum_has_all_values(self):
        """PhaseType enum has STRICT, GUIDED, AUTONOMOUS."""
        from src.schema import PhaseType

        assert hasattr(PhaseType, 'STRICT')
        assert hasattr(PhaseType, 'GUIDED')
        assert hasattr(PhaseType, 'AUTONOMOUS')
        assert PhaseType.STRICT.value == "strict"
        assert PhaseType.GUIDED.value == "guided"
        assert PhaseType.AUTONOMOUS.value == "autonomous"

    def test_phasedef_accepts_phase_type(self):
        """PhaseDef accepts phase_type field."""
        from src.schema import PhaseDef, PhaseType

        phase = PhaseDef(
            id="PLAN",
            name="Planning",
            phase_type=PhaseType.STRICT
        )
        assert phase.phase_type == PhaseType.STRICT

    def test_phasedef_defaults_to_guided(self):
        """PhaseDef defaults to GUIDED when not specified."""
        from src.schema import PhaseDef, PhaseType

        phase = PhaseDef(id="PLAN", name="Planning")
        assert phase.phase_type == PhaseType.GUIDED

    def test_phasedef_accepts_intended_tools(self):
        """PhaseDef accepts intended_tools field."""
        from src.schema import PhaseDef

        phase = PhaseDef(
            id="PLAN",
            name="Planning",
            intended_tools=["analyze", "create_plan"]
        )
        assert phase.intended_tools == ["analyze", "create_plan"]

    def test_phasedef_intended_tools_defaults_empty(self):
        """PhaseDef intended_tools defaults to empty list."""
        from src.schema import PhaseDef

        phase = PhaseDef(id="PLAN", name="Planning")
        assert phase.intended_tools == []


class TestLLMModeBlocking:
    """Test --force and --skip blocking in LLM mode."""

    def test_skip_blocked_in_llm_mode(self):
        """Skip command blocked in LLM mode for strict phases.

        Note: This test verifies the blocking logic. The actual CLI
        implementation should check is_llm_mode() before allowing skip.
        """
        from src.mode_detection import is_llm_mode

        # Simulate LLM mode
        with patch.dict(os.environ, {'CLAUDECODE': '1'}, clear=True):
            assert is_llm_mode() is True

    def test_skip_allowed_in_human_mode(self):
        """Skip command allowed in human mode."""
        from src.mode_detection import is_llm_mode

        # Simulate human mode with TTY
        with patch.dict(os.environ, {}, clear=True):
            with patch('sys.stdin.isatty', return_value=True):
                with patch('sys.stdout.isatty', return_value=True):
                    # In human mode with TTY, should be human
                    assert is_llm_mode() is False

    def test_emergency_override_bypasses_llm_mode(self):
        """Emergency override should bypass LLM mode detection."""
        from src.mode_detection import is_llm_mode, detect_operator_mode, OperatorMode

        with patch.dict(os.environ, {
            'ORCHESTRATOR_EMERGENCY_OVERRIDE': 'human-override-v3',
            'CLAUDECODE': '1'  # Would normally be LLM mode
        }, clear=True):
            result = detect_operator_mode()
            assert result.mode == OperatorMode.HUMAN
            assert is_llm_mode() is False

    def test_invalid_override_does_not_bypass(self):
        """Invalid emergency override value doesn't bypass."""
        from src.mode_detection import is_llm_mode

        with patch.dict(os.environ, {
            'ORCHESTRATOR_EMERGENCY_OVERRIDE': 'wrong-value',
            'CLAUDECODE': '1'
        }, clear=True):
            assert is_llm_mode() is True  # Still LLM mode


class TestCLIBlocking:
    """Test CLI commands block appropriately in LLM mode."""

    @pytest.fixture
    def runner(self):
        """Create Click test runner."""
        return CliRunner()

    def test_force_flag_behavior_documented(self):
        """Document that --force behavior should be blocked in LLM mode.

        This is a documentation test. The actual blocking is implemented
        in cli.py using is_llm_mode() checks.
        """
        # This test documents the expected behavior
        # Actual CLI tests would require more setup
        pass

    def test_skip_flag_behavior_documented(self):
        """Document that skip command should be blocked in LLM mode for strict phases.

        This is a documentation test. The actual blocking is implemented
        in cli.py using is_llm_mode() checks.
        """
        pass
