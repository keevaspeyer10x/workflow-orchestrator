"""Tests for CLI non-interactive mode handling - Issue #61

Tests that CLI commands fail-fast instead of hanging when run from
non-interactive shells (Claude Code, CI/CD, scripts).
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.cli import is_interactive, confirm


class TestIsInteractive:
    """Unit tests for is_interactive() helper function."""

    def test_returns_true_with_both_tty(self):
        """TC-001: Returns True when both stdin and stdout are TTY."""
        with patch.object(sys.stdin, 'isatty', return_value=True), \
             patch.object(sys.stdout, 'isatty', return_value=True), \
             patch.dict(os.environ, {}, clear=True):
            assert is_interactive() is True

    def test_returns_false_without_stdin_tty(self):
        """TC-002: Returns False when stdin is not a TTY."""
        with patch.object(sys.stdin, 'isatty', return_value=False), \
             patch.object(sys.stdout, 'isatty', return_value=True):
            assert is_interactive() is False

    def test_returns_false_without_stdout_tty(self):
        """Returns False when stdout is not a TTY."""
        with patch.object(sys.stdin, 'isatty', return_value=True), \
             patch.object(sys.stdout, 'isatty', return_value=False):
            assert is_interactive() is False

    def test_returns_false_with_ci_env(self):
        """TC-003: Returns False when CI environment variable is set."""
        with patch.object(sys.stdin, 'isatty', return_value=True), \
             patch.object(sys.stdout, 'isatty', return_value=True), \
             patch.dict(os.environ, {'CI': 'true'}):
            assert is_interactive() is False

    def test_returns_false_with_github_actions_env(self):
        """Returns False when GITHUB_ACTIONS is set."""
        with patch.object(sys.stdin, 'isatty', return_value=True), \
             patch.object(sys.stdout, 'isatty', return_value=True), \
             patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}):
            assert is_interactive() is False


class TestConfirm:
    """Unit tests for confirm() helper function."""

    def test_yes_flag_skips_prompt(self):
        """TC-004: confirm() with yes_flag=True skips prompt."""
        # Should not call input() at all
        with patch('builtins.input') as mock_input:
            result = confirm("Question?", yes_flag=True)
            assert result is True
            mock_input.assert_not_called()

    def test_exits_in_noninteractive_mode(self, capsys):
        """TC-005: confirm() exits with error in non-interactive mode."""
        with patch('src.cli.is_interactive', return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                confirm("Continue anyway? [y/N]: ")
            assert exc_info.value.code == 1

            captured = capsys.readouterr()
            assert "non-interactive" in captured.out.lower() or "Cannot prompt" in captured.out

    def test_prompts_in_interactive_mode(self):
        """TC-006: confirm() prompts and returns True for 'y'."""
        with patch('src.cli.is_interactive', return_value=True), \
             patch('builtins.input', return_value='y'):
            assert confirm("Question?") is True

    def test_prompts_returns_false_for_n(self):
        """confirm() returns False for 'n' response."""
        with patch('src.cli.is_interactive', return_value=True), \
             patch('builtins.input', return_value='n'):
            assert confirm("Question?") is False

    def test_prompts_returns_false_for_empty(self):
        """confirm() returns False for empty response (default)."""
        with patch('src.cli.is_interactive', return_value=True), \
             patch('builtins.input', return_value=''):
            assert confirm("Question?") is False

    def test_accepts_yes_variations(self):
        """confirm() accepts 'yes', 'Y', 'YES' as True."""
        for response in ['yes', 'Y', 'YES', 'Yes']:
            with patch('src.cli.is_interactive', return_value=True), \
                 patch('builtins.input', return_value=response):
                assert confirm("Question?") is True


class TestCmdAdvanceNonInteractive:
    """Integration tests for cmd_advance in non-interactive mode."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock workflow engine."""
        engine = MagicMock()
        engine.state = MagicMock()
        engine.state.current_phase_id = "PLAN"
        engine.workflow_def = MagicMock()
        engine.workflow_def.phases = [
            MagicMock(id="PLAN"),
            MagicMock(id="EXECUTE"),
        ]
        engine.working_dir = Path("/tmp/test")
        engine.can_advance_phase = MagicMock(return_value=(True, [], []))
        engine.advance_phase = MagicMock(return_value=(True, "Advanced"))
        engine.get_skipped_items = MagicMock(return_value=[])
        engine.get_recitation_text = MagicMock(return_value="")
        return engine

    def test_advance_with_yes_flag_succeeds(self, mock_engine):
        """TC-007: orchestrator advance --yes works in non-interactive mode."""
        from src.cli import cmd_advance

        args = MagicMock()
        args.dir = None
        args.force = False
        args.quiet = True
        args.yes = True  # Key: --yes flag set

        # PhaseCritique is imported inside cmd_advance, so patch at source
        with patch('src.cli.get_engine', return_value=mock_engine), \
             patch('src.cli.is_interactive', return_value=False), \
             patch('src.critique.PhaseCritique') as mock_critique, \
             patch('src.critique.format_critique_result', return_value="Critique"):
            # Mock critique to return blocking result
            mock_result = MagicMock()
            mock_result.should_block = True
            mock_critique.return_value.run_if_enabled.return_value = mock_result

            # Should NOT hang or exit - yes flag bypasses prompt
            cmd_advance(args)

            # Should have advanced
            mock_engine.advance_phase.assert_called_once()


class TestCmdInitNonInteractive:
    """Integration tests for cmd_init in non-interactive mode."""

    def test_init_force_flag_overwrites(self, tmp_path, capsys):
        """TC-009: orchestrator init --force works in non-interactive mode."""
        from src.cli import cmd_init

        # Create existing workflow.yaml
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("existing: content")

        args = MagicMock()
        args.dir = str(tmp_path)
        args.force = True  # Key: --force flag set

        with patch('src.cli.is_interactive', return_value=False):
            cmd_init(args)

            # Should have overwritten
            captured = capsys.readouterr()
            assert "Created" in captured.out or "workflow.yaml" in captured.out

    def test_init_without_force_exits_noninteractive(self, tmp_path, capsys):
        """TC-010: orchestrator init exits with error in non-interactive mode."""
        from src.cli import cmd_init

        # Create existing workflow.yaml
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("existing: content")

        args = MagicMock()
        args.dir = str(tmp_path)
        args.force = False  # No --force

        with patch('src.cli.is_interactive', return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                cmd_init(args)
            assert exc_info.value.code == 1

            captured = capsys.readouterr()
            assert "--force" in captured.out or "non-interactive" in captured.out.lower()
