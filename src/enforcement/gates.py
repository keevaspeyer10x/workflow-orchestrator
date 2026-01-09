"""
Hard gate execution.

Executes commands directly via subprocess - these cannot be skipped
and are not delegated to the LLM.
"""

import subprocess
import shlex
import logging
from pathlib import Path
from typing import Optional
from pydantic import BaseModel


logger = logging.getLogger(__name__)


class GateResult(BaseModel):
    """Result of a hard gate execution."""
    success: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    command: str = ""
    error: Optional[str] = None
    duration_seconds: Optional[float] = None


class HardGateExecutor:
    """
    Executes hard gate commands directly via subprocess.

    Hard gates are commands that:
    - Run externally (not via LLM)
    - Cannot be skipped
    - Block workflow on failure
    """

    DEFAULT_TIMEOUT = 300  # 5 minutes

    def __init__(self, timeout: Optional[int] = None):
        """
        Initialize the executor.

        Args:
            timeout: Command timeout in seconds (default 300)
        """
        self.timeout = timeout or self.DEFAULT_TIMEOUT

    def execute(
        self,
        command: str,
        working_dir: Path,
        env: Optional[dict] = None
    ) -> GateResult:
        """
        Execute a hard gate command.

        Args:
            command: The command to execute
            working_dir: Working directory for execution
            env: Optional environment variables

        Returns:
            GateResult with success status and output
        """
        import time
        import os

        start_time = time.time()

        try:
            # Parse command safely
            if command.startswith("bash -c"):
                # For bash -c commands, run through shell
                args = command
                use_shell = True
            else:
                # For regular commands, use shlex for safety
                args = shlex.split(command)
                use_shell = False

            # Merge environment
            run_env = os.environ.copy()
            if env:
                run_env.update(env)

            logger.info(f"Executing hard gate: {command}")

            result = subprocess.run(
                args,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=run_env,
                shell=use_shell
            )

            duration = time.time() - start_time

            return GateResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout[:10000] if result.stdout else "",  # Truncate large output
                stderr=result.stderr[:10000] if result.stderr else "",
                command=command,
                duration_seconds=duration
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            logger.error(f"Gate command timed out after {self.timeout}s: {command}")
            return GateResult(
                success=False,
                exit_code=-1,
                command=command,
                error=f"Command timed out after {self.timeout} seconds",
                duration_seconds=duration
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.exception(f"Gate command failed: {command}")
            return GateResult(
                success=False,
                exit_code=-1,
                command=command,
                error=str(e),
                duration_seconds=duration
            )
