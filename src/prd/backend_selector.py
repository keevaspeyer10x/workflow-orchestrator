"""
Backend selector for hybrid local/remote execution.

Addresses AI concern: "Consider retaining one remote backend for
non-interactive tasks"
"""

from enum import Enum
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    """Execution mode for PRD tasks."""
    INTERACTIVE = "interactive"  # Claude Squad - user interacts
    BATCH = "batch"              # GitHub Actions - fire and forget
    MANUAL = "manual"            # Generate prompts only


class BackendSelector:
    """
    Select appropriate backend based on task requirements.

    Strategy:
    - Interactive tasks (need user input) -> Claude Squad
    - Batch tasks (can run unattended) -> GitHub Actions
    - No backend available -> Manual (prompts only)
    """

    def __init__(
        self,
        working_dir: Path,
        squad_available: bool = False,
        gha_available: bool = False
    ):
        self.working_dir = working_dir
        self.squad_available = squad_available
        self.gha_available = gha_available

    @classmethod
    def detect(cls, working_dir: Path) -> "BackendSelector":
        """
        Create a BackendSelector with auto-detected availability.
        """
        from .squad_capabilities import CapabilityDetector
        from .backends.github_actions import GitHubActionsBackend

        # Check Claude Squad
        squad_available = False
        try:
            detector = CapabilityDetector()
            caps = detector.detect()
            squad_available = caps.is_compatible
        except Exception as e:
            logger.debug(f"Claude Squad not available: {e}")

        # Check GitHub Actions
        gha_available = False
        try:
            gha = GitHubActionsBackend()
            gha_available = gha.is_available()
        except Exception as e:
            logger.debug(f"GitHub Actions not available: {e}")

        return cls(
            working_dir=working_dir,
            squad_available=squad_available,
            gha_available=gha_available
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
        """
        # prefer_remote overrides interactive preference
        if prefer_remote and self.gha_available:
            return ExecutionMode.BATCH

        if interactive and self.squad_available:
            return ExecutionMode.INTERACTIVE

        if not interactive and self.gha_available:
            return ExecutionMode.BATCH

        if self.squad_available:
            return ExecutionMode.INTERACTIVE

        logger.warning("No execution backend available, falling back to manual")
        return ExecutionMode.MANUAL

    def get_available_modes(self) -> list[ExecutionMode]:
        """Get list of available execution modes."""
        modes = [ExecutionMode.MANUAL]  # Always available

        if self.squad_available:
            modes.append(ExecutionMode.INTERACTIVE)

        if self.gha_available:
            modes.append(ExecutionMode.BATCH)

        return modes

    def get_status(self) -> dict:
        """Get status of all backends."""
        return {
            "claude_squad": {
                "available": self.squad_available,
                "mode": ExecutionMode.INTERACTIVE.value,
            },
            "github_actions": {
                "available": self.gha_available,
                "mode": ExecutionMode.BATCH.value,
            },
            "manual": {
                "available": True,
                "mode": ExecutionMode.MANUAL.value,
            },
        }
