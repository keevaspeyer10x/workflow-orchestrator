"""
Backend selector for hybrid local/remote execution.

Updated for PRD-004: Replaced Claude Squad with direct tmux management.
Tmux is preferred, with subprocess as fallback.
"""

from enum import Enum
from pathlib import Path
from typing import Optional, Union
import shutil
import logging

logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    """Execution mode for PRD tasks."""
    INTERACTIVE = "interactive"  # tmux-based (user can attach)
    BATCH = "batch"              # GitHub Actions - fire and forget
    SUBPROCESS = "subprocess"    # Fallback when tmux not available
    MANUAL = "manual"            # Generate prompts only


class BackendSelector:
    """
    Select appropriate backend based on task requirements.

    Strategy (PRD-004 updated):
    - Interactive tasks with tmux -> INTERACTIVE (TmuxAdapter)
    - Interactive tasks without tmux -> SUBPROCESS (SubprocessAdapter)
    - Batch tasks (can run unattended) -> BATCH (GitHub Actions)
    - No backend available -> MANUAL (prompts only)
    """

    def __init__(
        self,
        working_dir: Path,
        squad_available: bool = False,
        gha_available: bool = False,
        tmux_available: Optional[bool] = None,
    ):
        self.working_dir = working_dir
        self.squad_available = squad_available
        self.gha_available = gha_available

        # Auto-detect tmux if not specified
        if tmux_available is None:
            self.tmux_available = shutil.which("tmux") is not None
        else:
            self.tmux_available = tmux_available

    @classmethod
    def detect(cls, working_dir: Path) -> "BackendSelector":
        """
        Create a BackendSelector with auto-detected availability.
        """
        # Check tmux (new primary for interactive)
        tmux_available = shutil.which("tmux") is not None

        # Check Claude Squad (deprecated, kept for backwards compat)
        squad_available = False
        try:
            from ._deprecated.squad_capabilities import CapabilityDetector
            detector = CapabilityDetector()
            caps = detector.detect()
            squad_available = caps.is_compatible
        except Exception as e:
            logger.debug(f"Claude Squad not available: {e}")

        # Check GitHub Actions
        gha_available = False
        try:
            from ._deprecated.github_actions import GitHubActionsBackend
            gha = GitHubActionsBackend()
            gha_available = gha.is_available()
        except Exception as e:
            logger.debug(f"GitHub Actions not available: {e}")

        return cls(
            working_dir=working_dir,
            squad_available=squad_available,
            gha_available=gha_available,
            tmux_available=tmux_available,
        )

    def select(
        self,
        task_count: int,
        interactive: bool = True,
        prefer_remote: bool = False
    ) -> ExecutionMode:
        """
        Select backend for given parameters.

        Args:
            task_count: Number of tasks to execute
            interactive: Whether user interaction is needed
            prefer_remote: Prefer remote execution if available

        Priority (PRD-004):
        1. prefer_remote + GHA available -> BATCH
        2. interactive + tmux available -> INTERACTIVE (TmuxAdapter)
        3. interactive + no tmux -> SUBPROCESS (fallback)
        4. non-interactive + GHA -> BATCH
        5. fallback -> SUBPROCESS (always available)
        """
        # prefer_remote overrides interactive preference
        if prefer_remote and self.gha_available:
            return ExecutionMode.BATCH

        # Interactive: prefer tmux, fall back to subprocess
        if interactive:
            if self.tmux_available:
                return ExecutionMode.INTERACTIVE
            else:
                logger.info("tmux not available, using subprocess fallback")
                return ExecutionMode.SUBPROCESS

        # Non-interactive: prefer batch if available
        if self.gha_available:
            return ExecutionMode.BATCH

        # Fallback: subprocess is always available
        if self.tmux_available:
            return ExecutionMode.INTERACTIVE

        return ExecutionMode.SUBPROCESS

    def get_available_modes(self) -> list[ExecutionMode]:
        """Get list of available execution modes."""
        modes = [ExecutionMode.MANUAL, ExecutionMode.SUBPROCESS]  # Always available

        if self.tmux_available:
            modes.append(ExecutionMode.INTERACTIVE)

        if self.gha_available:
            modes.append(ExecutionMode.BATCH)

        return modes

    def get_status(self) -> dict:
        """Get status of all backends."""
        return {
            "tmux": {
                "available": self.tmux_available,
                "mode": ExecutionMode.INTERACTIVE.value,
                "description": "Direct tmux session management (preferred)",
            },
            "subprocess": {
                "available": True,  # Always available
                "mode": ExecutionMode.SUBPROCESS.value,
                "description": "Fire-and-forget subprocess (fallback)",
            },
            "github_actions": {
                "available": self.gha_available,
                "mode": ExecutionMode.BATCH.value,
                "description": "GitHub Actions for batch execution",
            },
            "manual": {
                "available": True,
                "mode": ExecutionMode.MANUAL.value,
                "description": "Generate prompts only",
            },
            # Deprecated
            "claude_squad": {
                "available": self.squad_available,
                "mode": ExecutionMode.INTERACTIVE.value,
                "deprecated": True,
                "description": "Deprecated - use tmux instead",
            },
        }

    def get_adapter(self, inject_approval_gate: bool = True):
        """
        Get the appropriate adapter based on current selection.

        Args:
            inject_approval_gate: Whether to inject approval gate instructions
                into agent prompts (PRD-006). Default: True.

        Returns TmuxAdapter, SubprocessAdapter, or None (for manual/batch).
        """
        mode = self.select(task_count=1, interactive=True)

        if mode == ExecutionMode.INTERACTIVE:
            from .tmux_adapter import TmuxAdapter, TmuxConfig
            config = TmuxConfig(inject_approval_gate=inject_approval_gate)
            return TmuxAdapter(working_dir=self.working_dir, config=config)

        if mode == ExecutionMode.SUBPROCESS:
            from .subprocess_adapter import SubprocessAdapter, SubprocessConfig
            config = SubprocessConfig(inject_approval_gate=inject_approval_gate)
            return SubprocessAdapter(working_dir=self.working_dir, config=config)

        return None
