"""
Tests for v3 Adversarial Input Handling.

Tests cover:
- Concurrent access scenarios
- Malformed input handling
- Resource exhaustion protection
"""

import json
import threading
from pathlib import Path
import pytest


class TestConcurrentAccess:
    """Test concurrent access handling."""

    def test_concurrent_state_access(self, tmp_path):
        """Concurrent state access doesn't cause corruption."""
        from src.state_version import save_state_with_integrity, load_state_with_verification

        state_file = tmp_path / "state.json"
        errors = []
        successes = []

        # Ensure parent directory exists
        state_file.parent.mkdir(parents=True, exist_ok=True)

        def write_state(thread_id):
            try:
                state = {"thread_id": thread_id, "data": f"thread_{thread_id}"}
                save_state_with_integrity(state_file, state)
                successes.append(thread_id)
            except Exception as e:
                errors.append((thread_id, e))

        # Run concurrent writes
        threads = [
            threading.Thread(target=write_state, args=(i,))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed (last write wins)
        assert len(errors) == 0
        assert len(successes) == 5

        # Final state should be valid
        final_state = load_state_with_verification(state_file)
        assert 'thread_id' in final_state

    def test_concurrent_checkpoint_list(self, tmp_path):
        """Concurrent checkpoint listing is safe."""
        from src.checkpoint import CheckpointManager

        manager = CheckpointManager(working_dir=str(tmp_path))
        errors = []

        def list_checkpoints(thread_id):
            try:
                # Create while listing
                manager.create_checkpoint(
                    workflow_id="wf_test",
                    phase_id=f"PHASE_{thread_id}",
                    message=f"Thread {thread_id}",
                    auto_detect_files=False
                )
                manager.list_checkpoints()
            except Exception as e:
                errors.append((thread_id, e))

        threads = [
            threading.Thread(target=list_checkpoints, args=(i,))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestMalformedInput:
    """Test malformed input handling."""

    def test_malformed_json_state(self, tmp_path):
        """Malformed JSON state is handled gracefully."""
        from src.state_version import load_state_with_verification, StateIntegrityError

        state_file = tmp_path / "state.json"
        state_file.write_text("not valid json {{{")

        with pytest.raises((json.JSONDecodeError, StateIntegrityError)):
            load_state_with_verification(state_file)

    def test_malformed_checkpoint(self, tmp_path):
        """Malformed checkpoint file is handled gracefully."""
        from src.checkpoint import CheckpointManager

        manager = CheckpointManager(working_dir=str(tmp_path))

        # Create malformed checkpoint file
        (tmp_path / ".workflow_checkpoints").mkdir(parents=True, exist_ok=True)
        bad_checkpoint = tmp_path / ".workflow_checkpoints" / "cp_bad.json"
        bad_checkpoint.write_text("not valid json")

        # List should not crash
        checkpoints = manager.list_checkpoints()
        # Malformed checkpoint should be skipped
        assert all(cp.checkpoint_id != "cp_bad" for cp in checkpoints)

    def test_empty_gate_path(self, tmp_path):
        """Empty gate path is handled gracefully."""
        from src.gates import ArtifactGate

        gate = ArtifactGate(path="")
        # Should not crash, just fail validation
        result = gate.validate(tmp_path)
        assert result is False


class TestResourceLimits:
    """Test resource limit handling."""

    def test_large_state_file(self, tmp_path):
        """Large state files are handled."""
        from src.state_version import save_state_with_integrity, load_state_with_verification

        state_file = tmp_path / "state.json"

        # Create large state (10MB of data)
        large_state = {
            "workflow_id": "wf_test",
            "data": "x" * (10 * 1024 * 1024)  # 10MB string
        }

        # Should handle without crashing
        save_state_with_integrity(state_file, large_state)
        loaded = load_state_with_verification(state_file)
        assert loaded['workflow_id'] == "wf_test"

    def test_many_checkpoints(self, tmp_path):
        """Many checkpoints don't cause issues."""
        from src.checkpoint import CheckpointManager
        import time

        manager = CheckpointManager(working_dir=str(tmp_path))

        # Create 50 checkpoints quickly
        for i in range(50):
            manager.create_checkpoint(
                workflow_id="wf_test",
                phase_id=f"PHASE_{i}",
                message=f"Checkpoint {i}",
                auto_detect_files=False
            )

        # List should work
        checkpoints = manager.list_checkpoints()
        assert len(checkpoints) == 50
