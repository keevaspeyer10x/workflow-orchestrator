"""Workflow Hooks - Phase 4 CLI & Workflow Integration.

Provides hooks that integrate the healing system with the workflow engine.

Hooks:
- on_phase_complete: Detect errors after each phase
- on_subprocess_complete: Capture subprocess failures
- on_workflow_complete: Display error summary with suggested fixes
- on_learn_phase_complete: Feed learnings back to pattern memory
"""

import asyncio
from typing import Optional, TYPE_CHECKING

try:
    from rich.console import Console
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from .accumulator import ErrorAccumulator
from .fingerprint import Fingerprinter
from .detectors import WorkflowLogDetector, SubprocessDetector
from .client import HealingClient
from .pattern_generator import PatternGenerator
from .config import get_config

if TYPE_CHECKING:
    from .supabase_client import HealingSupabaseClient


def get_console():
    """Get Rich console if available."""
    if RICH_AVAILABLE:
        return Console()

    class SimpleConsole:
        def print(self, *args, **kwargs):
            text = " ".join(str(a) for a in args)
            import re
            text = re.sub(r'\[/?[a-zA-Z_ ]+\]', '', text)
            print(text)

    return SimpleConsole()


class HealingHooks:
    """Hooks into the workflow orchestrator.

    These hooks are called by the workflow engine at key points
    to detect errors and suggest fixes.

    Usage:
        hooks = HealingHooks(healing_client, accumulator)

        # In workflow engine:
        await hooks.on_phase_complete(phase_name, phase_result)
        await hooks.on_subprocess_complete(command, exit_code, stdout, stderr)
        await hooks.on_workflow_complete(workflow_id)
    """

    def __init__(
        self,
        client: Optional[HealingClient] = None,
        accumulator: Optional[ErrorAccumulator] = None,
    ):
        self.client = client
        self.accumulator = accumulator or ErrorAccumulator()
        self.fingerprinter = Fingerprinter()
        self.console = get_console()
        self._enabled = get_config().enabled

    async def on_phase_complete(self, phase: str, result: dict) -> None:
        """Called after each workflow phase.

        Detects errors from phase results and accumulates them.

        Args:
            phase: Phase name (e.g., "PLAN", "EXECUTE")
            result: Phase result dict containing logs, status, etc.
        """
        if not self._enabled:
            return

        try:
            # Detect errors from phase log
            detector = WorkflowLogDetector(self.fingerprinter)
            log_content = result.get("log", "") or result.get("output", "")

            if log_content:
                errors = await detector.detect_from_text(log_content)
                for error in errors:
                    error.phase_id = phase
                    self.accumulator.add(error)
        except Exception:
            # Don't let hook failures stop the workflow
            pass

    async def on_subprocess_complete(
        self,
        command: str,
        exit_code: int,
        stdout: str,
        stderr: str,
    ) -> None:
        """Hook for subprocess monitoring.

        Called after each subprocess completes. Captures failures.

        Args:
            command: Command that was run
            exit_code: Process exit code
            stdout: Standard output
            stderr: Standard error
        """
        if not self._enabled:
            return

        # Only capture failures
        if exit_code == 0:
            return

        try:
            detector = SubprocessDetector(self.fingerprinter)
            errors = await detector.detect(exit_code, stdout, stderr, command)

            for error in errors:
                self.accumulator.add(error)
        except Exception:
            # Don't let hook failures stop the workflow
            pass

    async def on_workflow_complete(self, workflow_id: str) -> None:
        """Called when workflow finishes.

        Displays a summary of detected errors with suggested fixes.

        Args:
            workflow_id: The workflow ID
        """
        if not self._enabled:
            return

        errors = self.accumulator.get_unique_errors()

        if not errors:
            return

        try:
            self.console.print(f"\n[bold]Detected {len(errors)} unique errors:[/bold]")

            for error in errors:
                self.console.print(f"  - {error.description[:60]}...")

                # Check for available fix
                if self.client:
                    try:
                        result = await self.client.lookup(error)
                        if result.pattern:
                            self.console.print(f"    [green]Fix available[/green] (tier {result.tier})")
                        else:
                            self.console.print(f"    [yellow]No fix found[/yellow]")
                    except Exception:
                        pass

            # Offer batch actions
            self.console.print("\nRun 'orchestrator issues review' to review and apply fixes")

        except Exception:
            # Don't let display failures cause issues
            pass

    async def on_learn_phase_complete(
        self,
        workflow_id: str,
        learnings: list[dict],
    ) -> None:
        """Called when LEARN phase completes.

        Extracts patterns from learnings and stores them.

        Args:
            workflow_id: The workflow ID
            learnings: List of learning dicts from the LEARN phase
        """
        if not self._enabled:
            return

        if not self.client:
            return

        try:
            # Process learnings that indicate error resolutions
            for learning in learnings:
                learning_type = learning.get("type")

                if learning_type == "error_resolution":
                    # Generate pattern from this learning
                    await self._process_error_resolution(learning)

                elif learning_type == "successful_fix":
                    # Record successful fix for precedent tracking
                    fingerprint = learning.get("fingerprint")
                    if fingerprint:
                        await self.client.record_fix_result(
                            self._create_stub_error(fingerprint),
                            success=True
                        )

        except Exception:
            # Don't let hook failures stop the workflow
            pass

    async def _process_error_resolution(self, learning: dict) -> None:
        """Process an error resolution learning into a pattern.

        Args:
            learning: Learning dict with error and fix information
        """
        error_desc = learning.get("error")
        fix_diff = learning.get("fix_diff") or learning.get("diff")

        if not error_desc or not fix_diff:
            return

        try:
            # Create error event for the pattern
            from .models import ErrorEvent
            from datetime import datetime

            error = ErrorEvent(
                error_id=f"learning-{datetime.utcnow().isoformat()}",
                timestamp=datetime.utcnow(),
                source="learning",
                description=error_desc,
            )
            error.fingerprint = self.fingerprinter.fingerprint(error)

            # Use pattern generator to create a pattern
            generator = PatternGenerator()
            pattern = await generator.generate_from_diff(
                error=error,
                fix_diff=fix_diff,
                context=learning.get("context"),
            )

            if pattern:
                await self.client.supabase.record_pattern(pattern)

        except Exception:
            pass

    def _create_stub_error(self, fingerprint: str):
        """Create a stub error for recording fix results."""
        from .models import ErrorEvent
        from datetime import datetime

        error = ErrorEvent(
            error_id=f"stub-{fingerprint[:8]}",
            timestamp=datetime.utcnow(),
            source="stub",
            description="",
        )
        error.fingerprint = fingerprint
        return error

    def clear(self) -> None:
        """Clear accumulated errors."""
        self.accumulator.clear()


# Global hooks instance
_hooks: Optional[HealingHooks] = None


def get_hooks() -> HealingHooks:
    """Get the global hooks instance."""
    global _hooks
    if _hooks is None:
        _hooks = HealingHooks()
    return _hooks


def reset_hooks() -> None:
    """Reset the global hooks instance (for testing)."""
    global _hooks
    _hooks = None


async def init_hooks(client: HealingClient = None) -> HealingHooks:
    """Initialize hooks with a healing client.

    Args:
        client: Optional HealingClient for pattern lookup

    Returns:
        Configured HealingHooks instance
    """
    global _hooks
    _hooks = HealingHooks(client=client)
    return _hooks
