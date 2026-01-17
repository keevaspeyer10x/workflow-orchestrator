"""
Claude Code subprocess runner.
Spawns a Claude Code session to execute each phase.
"""
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from .base import AgentRunner, RunnerError
from ..v4.models import PhaseInput, PhaseOutput


class ClaudeCodeRunner(AgentRunner):
    """
    Runs phases using Claude Code CLI as a subprocess.

    This is the PRIMARY runner for V4 - it has access to all
    Claude Code capabilities (file editing, terminal, etc.)
    """

    def __init__(
        self,
        working_dir: Path,
        timeout: int = 3600,  # 1 hour default
        claude_binary: str = "claude"
    ):
        self.working_dir = Path(working_dir)
        self.timeout = timeout
        self.claude_binary = claude_binary

    def run_phase(self, phase_input: PhaseInput) -> PhaseOutput:
        """
        Execute a phase using Claude Code.

        Strategy:
        1. Write phase instructions to a temp file
        2. Run Claude Code with --print flag (non-interactive)
        3. Capture output and parse results
        """
        # Build the prompt for this phase
        prompt = self._build_prompt(phase_input)

        # Write prompt to temp file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.md',
            delete=False,
            dir=str(self.working_dir)
        ) as f:
            f.write(prompt)
            prompt_file = f.name

        try:
            # Run Claude Code
            result = self._execute_claude(prompt_file, phase_input)
            return result
        finally:
            # Clean up temp file
            try:
                os.unlink(prompt_file)
            except OSError:
                pass

    def _build_prompt(self, phase_input: PhaseInput) -> str:
        """Build the prompt for Claude Code"""

        retry_section = ""
        if phase_input.is_retry:
            retry_section = f"""
## RETRY NOTICE

Your previous attempt did not pass the gate validation.
Feedback: {phase_input.retry_feedback}

Please address the issues and try again.
"""

        prompt = f"""# Workflow Phase: {phase_input.phase_name}

## Task Description
{phase_input.task_description}

## Phase Objective
{phase_input.phase_description}
{retry_section}
## Constraints
{chr(10).join(f'- {c}' for c in phase_input.constraints) if phase_input.constraints else '- None specified'}

## Context
Previous phases completed: {', '.join(phase_input.context.get('phases_completed', [])) or 'None'}

## Instructions

Complete this phase by performing the necessary work. When you are done:

1. Ensure all required files/artifacts exist
2. The orchestrator will automatically validate completion via gate checks
3. Do NOT call any orchestrator commands - just do the work

Focus on completing the phase objective. The orchestrator handles workflow progression.
"""
        return prompt

    def _execute_claude(self, prompt_file: str, phase_input: PhaseInput) -> PhaseOutput:
        """Execute Claude Code and capture results"""

        # Build command
        # Use --print for non-interactive mode
        # Use --dangerously-skip-permissions to avoid permission prompts
        cmd = [
            self.claude_binary,
            "--print",
            "--dangerously-skip-permissions",
            "-p", f"Execute the task in {prompt_file}. Read the file first, then complete the work described."
        ]

        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.working_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "orchestrator-v4"}
            )

            duration = time.time() - start_time

            # Check if Claude Code executed successfully
            if result.returncode != 0:
                return PhaseOutput(
                    phase_id=phase_input.phase_id,
                    success=False,
                    error_message=f"Claude Code exited with code {result.returncode}: {result.stderr[:500]}"
                )

            # Parse output to extract summary
            output_text = result.stdout
            summary = self._extract_summary(output_text)

            return PhaseOutput(
                phase_id=phase_input.phase_id,
                success=True,
                summary=summary,
                files_modified=[]  # We don't track this currently
            )

        except subprocess.TimeoutExpired:
            return PhaseOutput(
                phase_id=phase_input.phase_id,
                success=False,
                error_message=f"Phase timed out after {self.timeout} seconds"
            )
        except FileNotFoundError:
            raise RunnerError(
                f"Claude Code binary not found: {self.claude_binary}. "
                "Ensure Claude Code is installed and in PATH."
            )
        except Exception as e:
            return PhaseOutput(
                phase_id=phase_input.phase_id,
                success=False,
                error_message=f"Execution error: {str(e)}"
            )

    def _extract_summary(self, output: str) -> str:
        """Extract a summary from Claude's output"""
        # Take the last meaningful chunk of output
        lines = output.strip().split('\n')

        # Filter out empty lines and take last portion
        meaningful_lines = [l for l in lines if l.strip()]

        if not meaningful_lines:
            return "Phase completed (no output captured)"

        # Return last 10 lines as summary
        summary_lines = meaningful_lines[-10:]
        return '\n'.join(summary_lines)
