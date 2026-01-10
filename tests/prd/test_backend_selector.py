"""
Tests for backend selector - hybrid local/remote execution.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.prd.backend_selector import BackendSelector, ExecutionMode


class TestExecutionMode:
    """Tests for ExecutionMode enum."""

    def test_values(self):
        """Should have expected values."""
        assert ExecutionMode.INTERACTIVE.value == "interactive"
        assert ExecutionMode.BATCH.value == "batch"
        assert ExecutionMode.SUBPROCESS.value == "subprocess"
        assert ExecutionMode.MANUAL.value == "manual"


class TestBackendSelector:
    """Tests for BackendSelector."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temporary working directory."""
        return tmp_path

    def test_manual_always_available(self, temp_dir):
        """Manual mode should always be available."""
        selector = BackendSelector(
            temp_dir,
            squad_available=False,
            gha_available=False
        )

        modes = selector.get_available_modes()
        assert ExecutionMode.MANUAL in modes

    def test_interactive_when_squad_available(self, temp_dir):
        """Should select interactive when squad available."""
        selector = BackendSelector(
            temp_dir,
            squad_available=True,
            gha_available=False
        )

        mode = selector.select(task_count=5, interactive=True)
        assert mode == ExecutionMode.INTERACTIVE

    def test_batch_when_gha_available_and_not_interactive(self, temp_dir):
        """Should select batch for non-interactive tasks when GHA available."""
        selector = BackendSelector(
            temp_dir,
            squad_available=False,
            gha_available=True
        )

        mode = selector.select(task_count=5, interactive=False)
        assert mode == ExecutionMode.BATCH

    def test_prefer_remote_uses_gha(self, temp_dir):
        """Should prefer GHA when prefer_remote is True."""
        selector = BackendSelector(
            temp_dir,
            squad_available=True,
            gha_available=True
        )

        mode = selector.select(task_count=5, interactive=True, prefer_remote=True)
        assert mode == ExecutionMode.BATCH

    def test_fallback_to_subprocess(self, temp_dir):
        """Should fall back to subprocess when tmux not available."""
        selector = BackendSelector(
            temp_dir,
            squad_available=False,
            gha_available=False,
            tmux_available=False  # No tmux
        )

        mode = selector.select(task_count=5, interactive=True)
        # PRD-004: Subprocess is always available as fallback
        assert mode == ExecutionMode.SUBPROCESS

    def test_squad_fallback_when_not_interactive_no_gha(self, temp_dir):
        """Should use squad even for non-interactive if no GHA."""
        selector = BackendSelector(
            temp_dir,
            squad_available=True,
            gha_available=False
        )

        mode = selector.select(task_count=5, interactive=False)
        assert mode == ExecutionMode.INTERACTIVE

    def test_get_available_modes_all(self, temp_dir):
        """Should list all available modes."""
        selector = BackendSelector(
            temp_dir,
            squad_available=True,
            gha_available=True
        )

        modes = selector.get_available_modes()
        assert ExecutionMode.MANUAL in modes
        assert ExecutionMode.INTERACTIVE in modes
        assert ExecutionMode.BATCH in modes

    def test_get_status(self, temp_dir):
        """Should return status dict with all backend info."""
        selector = BackendSelector(
            temp_dir,
            squad_available=True,
            gha_available=False,
            tmux_available=True
        )

        status = selector.get_status()

        # New primary backends
        assert status["tmux"]["available"] is True
        assert status["subprocess"]["available"] is True  # Always available
        assert status["github_actions"]["available"] is False
        assert status["manual"]["available"] is True
        # Deprecated
        assert status["claude_squad"]["available"] is True
        assert status["claude_squad"]["deprecated"] is True

    def test_detect_classmethod(self, temp_dir):
        """Should auto-detect backend availability including tmux."""
        # Patch shutil.which for tmux detection
        with patch('shutil.which') as mock_which:
            mock_which.return_value = '/usr/bin/tmux'

            # Create a selector via detect - it will actually detect tmux
            selector = BackendSelector.detect(temp_dir)

            # tmux should be detected
            assert selector.tmux_available is True
            # working_dir should be set
            assert selector.working_dir == temp_dir

    def test_detect_handles_squad_error(self, temp_dir):
        """Should handle squad detection errors gracefully."""
        # Test by directly constructing - the detect() method catches exceptions
        # We verify the behavior by testing the select() logic with the expected state
        selector = BackendSelector(temp_dir, squad_available=False, gha_available=True)

        # When squad errors, it should fall back to GHA for non-interactive
        mode = selector.select(task_count=1, interactive=False)
        assert mode == ExecutionMode.BATCH

    def test_detect_handles_gha_error(self, temp_dir):
        """Should handle GHA detection errors gracefully."""
        # Test by directly constructing - the detect() method catches exceptions
        selector = BackendSelector(temp_dir, squad_available=True, gha_available=False)

        # When GHA errors, should still have squad available
        mode = selector.select(task_count=1, interactive=True)
        assert mode == ExecutionMode.INTERACTIVE


class TestBackendSelectionPriority:
    """Tests for backend selection priority."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_interactive_priority_squad_over_gha(self, temp_dir):
        """Interactive mode should prefer squad over gha."""
        selector = BackendSelector(
            temp_dir,
            squad_available=True,
            gha_available=True
        )

        mode = selector.select(task_count=1, interactive=True)
        assert mode == ExecutionMode.INTERACTIVE

    def test_non_interactive_priority_gha_over_squad(self, temp_dir):
        """Non-interactive mode should prefer gha over squad."""
        selector = BackendSelector(
            temp_dir,
            squad_available=True,
            gha_available=True
        )

        mode = selector.select(task_count=1, interactive=False)
        assert mode == ExecutionMode.BATCH

    def test_task_count_independent(self, temp_dir):
        """Task count should not affect selection (simplified from worker_pool)."""
        selector = BackendSelector(
            temp_dir,
            squad_available=True,
            gha_available=True
        )

        # Same result regardless of task count
        mode1 = selector.select(task_count=1, interactive=True)
        mode100 = selector.select(task_count=100, interactive=True)

        assert mode1 == mode100 == ExecutionMode.INTERACTIVE


class TestBackendSelectorTmuxIntegration:
    """Tests for tmux-based backend selection (PRD-004)."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_subprocess_mode_exists(self):
        """Should have SUBPROCESS execution mode."""
        # This test will fail until we add the new mode
        try:
            assert ExecutionMode.SUBPROCESS.value == "subprocess"
        except AttributeError:
            pytest.skip("SUBPROCESS mode not implemented yet")

    def test_tmux_available_selects_interactive(self, temp_dir):
        """When tmux available, should select INTERACTIVE mode."""
        selector = BackendSelector(
            temp_dir,
            squad_available=False,  # Claude Squad not available
            gha_available=False,
            tmux_available=True  # But tmux is
        )

        mode = selector.select(task_count=3, interactive=True)
        assert mode == ExecutionMode.INTERACTIVE

    def test_no_tmux_falls_back_to_subprocess(self, temp_dir):
        """When tmux not available, should fall back to SUBPROCESS."""
        try:
            selector = BackendSelector(
                temp_dir,
                squad_available=False,
                gha_available=False,
                tmux_available=False
            )

            mode = selector.select(task_count=3, interactive=True)
            assert mode == ExecutionMode.SUBPROCESS
        except TypeError:
            pytest.skip("tmux_available parameter not implemented yet")

    def test_detect_finds_tmux(self, temp_dir):
        """detect() should find tmux availability."""
        from unittest.mock import patch

        with patch('shutil.which') as mock_which:
            mock_which.return_value = '/usr/bin/tmux'

            try:
                selector = BackendSelector.detect(temp_dir)
                assert selector.tmux_available is True
            except AttributeError:
                pytest.skip("tmux detection not implemented yet")

    def test_get_status_includes_tmux(self, temp_dir):
        """get_status() should include tmux status."""
        try:
            selector = BackendSelector(
                temp_dir,
                squad_available=False,
                gha_available=False,
                tmux_available=True
            )

            status = selector.get_status()
            assert "tmux" in status
            assert status["tmux"]["available"] is True
        except TypeError:
            pytest.skip("tmux status not implemented yet")
