"""
Claude Code Integration Module

This module provides integration with Claude Code CLI for delegating
coding tasks to Claude Code while Manus orchestrates the workflow.
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime, timezone


class ClaudeCodeIntegration:
    """
    Integration with Claude Code CLI for executing coding tasks.
    """
    
    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir).resolve()
        self.claude_available = self._check_claude_available()
    
    def _check_claude_available(self) -> bool:
        """Check if Claude Code CLI is available."""
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
    
    def is_available(self) -> bool:
        """Check if Claude Code is available for use."""
        return self.claude_available
    
    def generate_handoff_prompt(
        self,
        task_description: str,
        phase_name: str,
        checklist_items: list[dict],
        context_files: list[str] = None,
        constraints: list[str] = None,
        acceptance_criteria: list[str] = None
    ) -> str:
        """
        Generate a comprehensive prompt for Claude Code handoff.
        
        This creates a structured prompt that Claude Code can execute,
        including all necessary context and constraints.
        """
        prompt_parts = [
            "# Task Handoff from Manus Orchestrator",
            "",
            f"## Task: {task_description}",
            f"## Phase: {phase_name}",
            "",
            "## Checklist Items to Complete",
            ""
        ]
        
        for item in checklist_items:
            status = item.get('status', 'pending')
            if status not in ['completed', 'skipped']:
                prompt_parts.append(f"- [ ] **{item['id']}**: {item['name']}")
                if item.get('description'):
                    prompt_parts.append(f"  - {item['description']}")
        
        if context_files:
            prompt_parts.extend([
                "",
                "## Relevant Files",
                ""
            ])
            for file in context_files:
                prompt_parts.append(f"- `{file}`")
        
        if constraints:
            prompt_parts.extend([
                "",
                "## Constraints",
                ""
            ])
            for constraint in constraints:
                prompt_parts.append(f"- {constraint}")
        
        if acceptance_criteria:
            prompt_parts.extend([
                "",
                "## Acceptance Criteria",
                ""
            ])
            for criterion in acceptance_criteria:
                prompt_parts.append(f"- {criterion}")
        
        prompt_parts.extend([
            "",
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
        
        return "\n".join(prompt_parts)
    
    def execute_prompt(
        self,
        prompt: str,
        timeout: int = 600
    ) -> Tuple[bool, str, dict]:
        """
        Execute a prompt using Claude Code CLI.
        
        Returns (success, output, details).
        """
        if not self.claude_available:
            return False, "Claude Code CLI not available", {"error": "not_installed"}
        
        try:
            # Use --print for non-interactive execution
            result = subprocess.run(
                ["claude", "--print"],
                input=prompt,
                capture_output=True,
                text=True,
                cwd=self.working_dir,
                timeout=timeout,
                env={**os.environ}
            )
            
            details = {
                "exit_code": result.returncode,
                "stdout_length": len(result.stdout),
                "stderr_length": len(result.stderr),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            if result.returncode == 0:
                return True, result.stdout, details
            else:
                details["stderr"] = result.stderr[:1000] if result.stderr else ""
                return False, result.stdout or result.stderr, details
                
        except subprocess.TimeoutExpired:
            return False, f"Claude Code timed out after {timeout}s", {"error": "timeout"}
        except Exception as e:
            return False, str(e), {"error": str(type(e).__name__)}
    
    def parse_completion_report(self, output: str) -> dict:
        """
        Parse Claude Code's completion report to extract structured data.
        """
        report = {
            "completed_items": [],
            "files_modified": [],
            "tests_run": [],
            "blockers": [],
            "raw_output": output
        }
        
        # Simple parsing - look for our expected sections
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


def get_claude_integration(working_dir: str = ".") -> ClaudeCodeIntegration:
    """Factory function to get a Claude Code integration instance."""
    return ClaudeCodeIntegration(working_dir)
