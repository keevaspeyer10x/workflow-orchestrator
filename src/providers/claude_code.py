"""
Claude Code provider for agent execution.

This provider uses the Claude Code CLI to execute prompts.
Refactored from the original claude_integration.py module.
"""

import subprocess
import os
import time
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from .base import AgentProvider, ExecutionResult


logger = logging.getLogger(__name__)


class ClaudeCodeProvider(AgentProvider):
    """
    Provider that executes prompts through the Claude Code CLI.
    
    This is a refactored version of the original ClaudeCodeIntegration class,
    now implementing the AgentProvider interface.
    """
    
    DEFAULT_TIMEOUT = 600  # 10 minutes
    
    def __init__(
        self,
        working_dir: Optional[str] = None,
        timeout: Optional[int] = None
    ):
        """
        Initialize the Claude Code provider.
        
        Args:
            working_dir: Working directory for Claude Code execution
            timeout: Request timeout in seconds (defaults to 600)
        """
        self._working_dir = Path(working_dir or ".").resolve()
        self._timeout = timeout or self.DEFAULT_TIMEOUT
        self._claude_available = None  # Lazy check
    
    def name(self) -> str:
        return "claude_code"
    
    def is_available(self) -> bool:
        """Check if Claude Code CLI is available."""
        if self._claude_available is None:
            self._claude_available = self._check_claude_available()
        return self._claude_available
    
    def _check_claude_available(self) -> bool:
        """Check if Claude Code CLI is installed and accessible."""
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
        except Exception as e:
            logger.warning(f"Error checking Claude CLI: {e}")
            return False
    
    def get_default_model(self) -> Optional[str]:
        """Claude Code uses its own model selection."""
        return None
    
    def generate_prompt(self, task: str, context: dict) -> str:
        """
        Generate a handoff prompt formatted for Claude Code.
        
        Args:
            task: The task description
            context: Workflow context dictionary
        
        Returns:
            str: Formatted prompt
        """
        lines = [
            "# Task Handoff from Manus Orchestrator",
            "",
            f"## Task: {task}",
        ]
        
        # Add phase info
        phase = context.get("phase", "Unknown")
        lines.append(f"## Phase: {phase}")
        lines.append("")
        
        # Add constraints if present
        constraints = context.get("constraints", [])
        if constraints:
            lines.extend([
                "## Constraints",
                "",
            ])
            for c in constraints:
                lines.append(f"- {c}")
            lines.append("")
        
        # Add checklist items
        items = context.get("items", [])
        if items:
            lines.extend([
                "## Checklist Items to Complete",
                "",
            ])
            for item in items:
                status = item.get("status", "pending")
                if status not in ["completed", "skipped"]:
                    item_id = item.get("id", "unknown")
                    item_name = item.get("name", item.get("description", "No description"))
                    lines.append(f"- [ ] **{item_id}**: {item_name}")
                    
                    # Add item description if different from name
                    description = item.get("description")
                    if description and description != item_name:
                        lines.append(f"  - {description}")
                    
                    # Add item notes if present
                    item_notes = item.get("notes", [])
                    for note in item_notes:
                        lines.append(f"  - Note: {note}")
            lines.append("")
        
        # Add relevant files if present
        files = context.get("files", [])
        if files:
            lines.extend([
                "## Relevant Files",
                "",
            ])
            for f in files:
                lines.append(f"- `{f}`")
            lines.append("")
        
        # Add phase notes if present
        notes = context.get("notes", [])
        if notes:
            lines.extend([
                "## Operating Notes",
                "",
            ])
            for n in notes:
                lines.append(f"- {n}")
            lines.append("")
        
        # Add acceptance criteria if present
        acceptance_criteria = context.get("acceptance_criteria", [])
        if acceptance_criteria:
            lines.extend([
                "## Acceptance Criteria",
                "",
            ])
            for criterion in acceptance_criteria:
                lines.append(f"- {criterion}")
            lines.append("")
        
        # Add instructions
        lines.extend([
            "## Instructions",
            "",
            "1. Complete each checklist item in order",
            "2. After completing each item, report what was done",
            "3. If you encounter blockers, document them clearly",
            "4. Run tests after implementation to verify",
            "5. Provide a summary of changes made",
            "",
            "## Output Format",
            "",
            "After completing the work, provide:",
            "```",
            "COMPLETED_ITEMS:",
            "- item_id: <notes about what was done>",
            "",
            "FILES_MODIFIED:",
            "- path/to/file.py: <description of changes>",
            "",
            "TESTS_RUN:",
            "- <test results summary>",
            "",
            "BLOCKERS (if any):",
            "- <description of any issues>",
            "```"
        ])
        
        return "\n".join(lines)
    
    def execute(self, prompt: str, model: Optional[str] = None) -> ExecutionResult:
        """
        Execute the prompt through Claude Code CLI.
        
        Args:
            prompt: The prompt to execute
            model: Ignored for Claude Code (uses its own model selection)
        
        Returns:
            ExecutionResult: The result of execution
        """
        if not self.is_available():
            return ExecutionResult(
                success=False,
                output="",
                error="Claude Code CLI not available. Install it from https://claude.ai/code"
            )
        
        start_time = time.time()
        
        try:
            # Use --print for non-interactive execution
            result = subprocess.run(
                ["claude", "--print"],
                input=prompt,
                capture_output=True,
                text=True,
                cwd=self._working_dir,
                timeout=self._timeout,
                env={**os.environ}
            )
            
            duration = time.time() - start_time
            
            if result.returncode == 0:
                return ExecutionResult(
                    success=True,
                    output=result.stdout,
                    duration_seconds=duration,
                    metadata={
                        "provider": "claude_code",
                        "exit_code": result.returncode,
                        "stdout_length": len(result.stdout),
                        "stderr_length": len(result.stderr),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
            else:
                return ExecutionResult(
                    success=False,
                    output=result.stdout or result.stderr,
                    error=f"Claude Code exited with code {result.returncode}",
                    duration_seconds=duration,
                    metadata={
                        "provider": "claude_code",
                        "exit_code": result.returncode,
                        "stderr": result.stderr[:1000] if result.stderr else ""
                    }
                )
                
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return ExecutionResult(
                success=False,
                output="",
                error=f"Claude Code timed out after {self._timeout}s",
                duration_seconds=duration,
                metadata={"error": "timeout"}
            )
        except Exception as e:
            duration = time.time() - start_time
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                duration_seconds=duration,
                metadata={"error": str(type(e).__name__)}
            )
    
    def parse_completion_report(self, output: str) -> dict:
        """
        Parse Claude Code's completion report to extract structured data.
        
        This is a utility method for parsing the expected output format.
        """
        report = {
            "completed_items": [],
            "files_modified": [],
            "tests_run": [],
            "blockers": [],
            "raw_output": output
        }
        
        current_section = None
        
        for line in output.split('\n'):
            line = line.strip()
            
            if line.startswith('COMPLETED_ITEMS:'):
                current_section = 'completed_items'
            elif line.startswith('FILES_MODIFIED:'):
                current_section = 'files_modified'
            elif line.startswith('TESTS_RUN:'):
                current_section = 'tests_run'
            elif line.startswith('BLOCKERS'):
                current_section = 'blockers'
            elif line.startswith('- ') and current_section:
                report[current_section].append(line[2:])
        
        return report
