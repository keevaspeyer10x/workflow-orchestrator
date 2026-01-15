"""
Tests for v3 mode detection and state versioning.

These tests cover Phase 0 of the v3 hybrid orchestration system:
- Operator mode detection (human vs LLM)
- State file integrity verification
- State versioning

Written TDD-style: tests written BEFORE implementation.
"""

import os
import sys
import json
from unittest.mock import patch
import pytest


class TestModeDetection:
    """Test operator mode detection."""

    def test_emergency_override_always_works(self):
        """Emergency override returns human mode regardless of other signals.

        Test case MD-01: Emergency override should ALWAYS work, even when
        all other signals indicate LLM mode. This is the escape hatch.
        """
        from src.mode_detection import detect_operator_mode, OperatorMode

        with patch.dict(os.environ, {
            'ORCHESTRATOR_EMERGENCY_OVERRIDE': 'human-override-v3',
            'CLAUDECODE': '1'  # Would normally trigger LLM mode
        }, clear=True):
            result = detect_operator_mode()
            assert result.mode == OperatorMode.HUMAN
            assert "EMERGENCY" in result.reason.upper()
            assert result.confidence == "high"

    def test_explicit_llm_mode(self):
        """ORCHESTRATOR_MODE=llm forces LLM mode.

        Test case MD-02: Explicit mode override should work with high confidence.
        """
        from src.mode_detection import detect_operator_mode, OperatorMode

        with patch.dict(os.environ, {'ORCHESTRATOR_MODE': 'llm'}, clear=True):
            result = detect_operator_mode()
            assert result.mode == OperatorMode.LLM
            assert result.confidence == "high"

    def test_explicit_human_mode(self):
        """ORCHESTRATOR_MODE=human forces human mode.

        Test case MD-03: Explicit human mode for cases where detection fails.
        """
        from src.mode_detection import detect_operator_mode, OperatorMode

        with patch.dict(os.environ, {'ORCHESTRATOR_MODE': 'human'}, clear=True):
            result = detect_operator_mode()
            assert result.mode == OperatorMode.HUMAN
            assert result.confidence == "high"

    def test_claudecode_env_detected(self):
        """CLAUDECODE=1 triggers LLM mode (actual Claude Code signal).

        Test case MD-04: This is the primary detection signal for Claude Code.
        Verified working in Claude Code environment on 2025-01-15.
        """
        from src.mode_detection import detect_operator_mode, OperatorMode

        with patch.dict(os.environ, {'CLAUDECODE': '1'}, clear=True):
            result = detect_operator_mode()
            assert result.mode == OperatorMode.LLM
            assert "Claude Code" in result.reason or "CLAUDECODE" in result.reason
            assert result.confidence == "high"

    def test_claude_code_entrypoint_detected(self):
        """CLAUDE_CODE_ENTRYPOINT triggers LLM mode.

        Test case MD-05: Secondary Claude Code detection signal.
        """
        from src.mode_detection import detect_operator_mode, OperatorMode

        with patch.dict(os.environ, {'CLAUDE_CODE_ENTRYPOINT': 'sdk-ts'}, clear=True):
            result = detect_operator_mode()
            assert result.mode == OperatorMode.LLM
            assert result.confidence == "high"

    def test_no_tty_triggers_llm_mode(self):
        """Non-interactive session (no TTY) defaults to LLM mode.

        Test case MD-06: Claude Code has no TTY, so this is a fallback signal.
        """
        from src.mode_detection import detect_operator_mode, OperatorMode

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys.stdin, 'isatty', return_value=False):
                result = detect_operator_mode()
                assert result.mode == OperatorMode.LLM
                assert "TTY" in result.reason.upper() or "tty" in result.reason.lower()
                assert result.confidence == "medium"

    def test_tty_suggests_human_mode(self):
        """Interactive TTY session suggests human mode.

        Test case MD-07: Interactive terminal = likely human operator.
        """
        from src.mode_detection import detect_operator_mode, OperatorMode

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys.stdin, 'isatty', return_value=True):
                with patch.object(sys.stdout, 'isatty', return_value=True):
                    result = detect_operator_mode()
                    assert result.mode == OperatorMode.HUMAN
                    assert result.confidence == "medium"

    def test_unknown_defaults_to_llm(self):
        """Unknown environment defaults to LLM mode (conservative).

        Test case MD-08: Safety first - when unsure, assume restricted mode.
        """
        from src.mode_detection import detect_operator_mode, OperatorMode

        with patch.dict(os.environ, {}, clear=True):
            # Mock both stdin and stdout as non-TTY but not clearly LLM
            with patch.object(sys.stdin, 'isatty', return_value=False):
                with patch.object(sys.stdout, 'isatty', return_value=True):
                    result = detect_operator_mode()
                    # Should default to LLM (conservative)
                    assert result.mode == OperatorMode.LLM

    def test_is_llm_mode_returns_boolean(self):
        """is_llm_mode() convenience function returns boolean.

        Test case MD-09: Simple API for checking mode.
        """
        from src.mode_detection import is_llm_mode

        with patch.dict(os.environ, {'CLAUDECODE': '1'}, clear=True):
            result = is_llm_mode()
            assert isinstance(result, bool)
            assert result is True

    def test_mode_detection_result_has_all_fields(self):
        """ModeDetectionResult has mode, reason, and confidence fields.

        Test case MD-10: Result dataclass has required fields.
        """
        from src.mode_detection import detect_operator_mode, ModeDetectionResult

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys.stdin, 'isatty', return_value=True):
                with patch.object(sys.stdout, 'isatty', return_value=True):
                    result = detect_operator_mode()
                    assert isinstance(result, ModeDetectionResult)
                    assert hasattr(result, 'mode')
                    assert hasattr(result, 'reason')
                    assert hasattr(result, 'confidence')
                    assert result.reason  # Non-empty
                    assert result.confidence in ('high', 'medium', 'low')


class TestStateIntegrity:
    """Test state file integrity verification."""

    def test_save_and_load_state(self, tmp_path):
        """State can be saved and loaded with integrity check.

        Test case SI-01: Round-trip save/load should preserve data.
        """
        from src.state_version import save_state_with_integrity, load_state_with_verification

        state_path = tmp_path / "state.json"
        state_data = {"phase": "PLAN", "items": ["a", "b"]}

        save_state_with_integrity(state_path, state_data)
        loaded = load_state_with_verification(state_path)

        assert loaded["phase"] == "PLAN"
        assert loaded["items"] == ["a", "b"]
        assert loaded["_version"] == "3.0"
        assert "_checksum" in loaded
        assert "_updated_at" in loaded

    def test_tampered_state_detected(self, tmp_path):
        """Tampered state file is detected.

        Test case SI-02: Modifying state without updating checksum should fail.
        """
        from src.state_version import save_state_with_integrity, load_state_with_verification

        state_path = tmp_path / "state.json"
        save_state_with_integrity(state_path, {"phase": "PLAN"})

        # Tamper with state
        with open(state_path) as f:
            data = json.load(f)
        data["phase"] = "EXECUTE"  # Change without updating checksum
        with open(state_path, 'w') as f:
            json.dump(data, f)

        with pytest.raises(ValueError, match="integrity"):
            load_state_with_verification(state_path)

    def test_wrong_version_rejected(self, tmp_path):
        """State file with wrong version is rejected.

        Test case SI-03: v2 state should not be loaded by v3 code.
        """
        from src.state_version import load_state_with_verification

        state_path = tmp_path / "state.json"
        with open(state_path, 'w') as f:
            json.dump({"_version": "2.0", "_checksum": "fake", "phase": "PLAN"}, f)

        with pytest.raises(ValueError, match="incompatible"):
            load_state_with_verification(state_path)

    def test_missing_checksum_handled(self, tmp_path):
        """State without checksum is handled appropriately.

        Test case SI-04: Missing checksum should raise error.
        """
        from src.state_version import load_state_with_verification

        state_path = tmp_path / "state.json"
        with open(state_path, 'w') as f:
            json.dump({"_version": "3.0", "phase": "PLAN"}, f)  # No _checksum

        # Should raise ValueError for missing checksum
        with pytest.raises(ValueError):
            load_state_with_verification(state_path)

    def test_empty_state_handled(self, tmp_path):
        """Empty state dict is handled appropriately.

        Test case SI-05: Empty dict should save/load without issues.
        """
        from src.state_version import save_state_with_integrity, load_state_with_verification

        state_path = tmp_path / "state.json"
        state_data = {}

        save_state_with_integrity(state_path, state_data)
        loaded = load_state_with_verification(state_path)

        # Should have version and checksum added
        assert loaded["_version"] == "3.0"
        assert "_checksum" in loaded


class TestStateVersioning:
    """Test state file versioning."""

    def test_v3_state_directory_used(self, tmp_path):
        """V3 state directory path is correct.

        Test case SV-01: get_state_dir() returns correct path.
        """
        from src.state_version import get_state_dir

        state_dir = get_state_dir()
        assert str(state_dir) == ".orchestrator/v3"

    def test_checksum_excludes_metadata(self, tmp_path):
        """Checksum is computed without _checksum field.

        Test case SV-02: Changing _checksum shouldn't affect computed checksum.
        """
        from src.state_version import compute_state_checksum

        data1 = {"phase": "PLAN", "_checksum": "old"}
        data2 = {"phase": "PLAN", "_checksum": "new"}

        # Checksums should be identical (both exclude _checksum)
        assert compute_state_checksum(data1) == compute_state_checksum(data2)

    def test_checksum_content_sensitive(self, tmp_path):
        """Checksum changes when content changes.

        Test case SV-03: Different content = different checksum.
        """
        from src.state_version import compute_state_checksum

        data1 = {"phase": "PLAN"}
        data2 = {"phase": "EXECUTE"}

        # Checksums should differ
        assert compute_state_checksum(data1) != compute_state_checksum(data2)
