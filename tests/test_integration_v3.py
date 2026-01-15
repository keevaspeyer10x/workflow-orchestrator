"""
Tests for v3 Integration - End-to-End Tests.

Tests cover:
- Full workflow cycle integration
- Checkpoint round-trip
- Gate validation integration
"""

import json
from pathlib import Path
import pytest


class TestWorkflowIntegration:
    """Test full workflow integration."""

    def test_checkpoint_round_trip(self, tmp_path):
        """Checkpoint create and restore maintains state."""
        from src.checkpoint import CheckpointManager

        manager = CheckpointManager(working_dir=str(tmp_path))

        # Create checkpoint with state
        original_state = {
            "workflow_id": "wf_test",
            "phase": "EXECUTE",
            "items_completed": ["item_1", "item_2"]
        }

        checkpoint = manager.create_checkpoint(
            workflow_id="wf_test",
            phase_id="EXECUTE",
            message="Test checkpoint",
            workflow_state=original_state,
            auto_detect_files=False
        )

        # Restore checkpoint
        restored = manager.get_checkpoint(checkpoint.checkpoint_id)

        assert restored is not None
        assert restored.workflow_state_snapshot == original_state
        assert restored.phase_id == "EXECUTE"

    def test_gate_validation_integration(self, tmp_path):
        """Gates integrate with workflow validation."""
        from src.gates import ArtifactGate, CommandGate, CompositeGate

        # Create test file
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Implementation Plan\n\nThis is the plan.")

        # Composite gate: file exists AND command succeeds
        gate = CompositeGate(
            operator="and",
            gates=[
                ArtifactGate(path="plan.md", validator="not_empty"),
                CommandGate(command="true")
            ]
        )

        assert gate.validate(tmp_path) is True

    def test_mode_detection_integration(self, tmp_path, monkeypatch):
        """Mode detection integrates with state operations."""
        from src.mode_detection import detect_operator_mode, OperatorMode

        # Clear environment
        monkeypatch.delenv("CLAUDECODE", raising=False)
        monkeypatch.delenv("ORCHESTRATOR_OPERATOR_MODE", raising=False)
        monkeypatch.delenv("ORCHESTRATOR_EMERGENCY_OVERRIDE", raising=False)

        result = detect_operator_mode()
        # Should detect some mode (human or llm depending on TTY)
        assert result.mode in (OperatorMode.HUMAN, OperatorMode.LLM)
        assert result.confidence in ("high", "medium", "low")


class TestStateIntegration:
    """Test state file integration."""

    def test_state_version_integration(self, tmp_path):
        """State versioning integrates with save/load cycle."""
        from src.state_version import (
            save_state_with_integrity,
            load_state_with_verification,
            STATE_VERSION
        )

        state_file = tmp_path / "state.json"
        original_state = {
            "workflow_id": "wf_test",
            "phase": "PLAN",
            "data": {"key": "value"}
        }

        # Save with integrity
        save_state_with_integrity(state_file, original_state)

        # Load with verification
        loaded_state = load_state_with_verification(state_file)

        assert loaded_state['workflow_id'] == original_state['workflow_id']
        assert loaded_state['_version'] == STATE_VERSION

    def test_checkpoint_chain_integration(self, tmp_path):
        """Checkpoint chaining works across save/load cycles."""
        import time
        from src.checkpoint import CheckpointManager

        manager = CheckpointManager(working_dir=str(tmp_path))

        # Create chain of checkpoints
        cp1 = manager.create_checkpoint(
            workflow_id="wf_test",
            phase_id="PLAN",
            message="First",
            auto_detect_files=False
        )
        time.sleep(1.1)  # Ensure unique timestamp

        cp2 = manager.create_checkpoint(
            workflow_id="wf_test",
            phase_id="EXECUTE",
            message="Second",
            parent_checkpoint_id=cp1.checkpoint_id,
            auto_detect_files=False
        )

        # Verify chain retrieval
        chain = manager.get_checkpoint_chain(cp2.checkpoint_id)
        assert len(chain) == 2
        assert chain[0].checkpoint_id == cp2.checkpoint_id
        assert chain[1].checkpoint_id == cp1.checkpoint_id
