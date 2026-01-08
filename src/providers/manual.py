"""
Manual provider for agent execution.

This provider generates prompts for manual copy/paste execution.
It is always available and serves as the fallback when no other provider is configured.
"""

from typing import Optional

from .base import AgentProvider, ExecutionResult


class ManualProvider(AgentProvider):
    """
    Provider for manual prompt execution via copy/paste.
    
    This provider is always available and generates formatted prompts
    that users can copy and paste into their preferred LLM interface.
    """
    
    def __init__(self):
        """Initialize the Manual provider."""
        pass
    
    def name(self) -> str:
        return "manual"
    
    def is_available(self) -> bool:
        """Manual provider is always available."""
        return True
    
    def supports_execution(self) -> bool:
        """Manual provider does not support direct execution."""
        return False
    
    def get_default_model(self) -> Optional[str]:
        """No default model for manual provider."""
        return None
    
    def generate_prompt(self, task: str, context: dict) -> str:
        """
        Generate a handoff prompt formatted for manual copy/paste.
        
        Args:
            task: The task description
            context: Workflow context dictionary
        
        Returns:
            str: Formatted prompt with instructions for manual use
        """
        lines = [
            "=" * 60,
            "MANUAL HANDOFF PROMPT",
            "=" * 60,
            "",
            "Copy the content below and paste it into your preferred LLM",
            "(Claude, ChatGPT, etc.)",
            "",
            "-" * 60,
            "",
            "# Task Handoff",
            "",
            f"## Task",
            task,
            "",
        ]
        
        # Add constraints if present
        constraints = context.get("constraints", [])
        if constraints:
            lines.extend([
                "## Constraints",
                *[f"- {c}" for c in constraints],
                "",
            ])
        
        # Add phase info
        phase = context.get("phase", "Unknown")
        lines.extend([
            f"## Current Phase: {phase}",
            "",
        ])
        
        # Add checklist items
        items = context.get("items", [])
        if items:
            lines.extend([
                "## Checklist Items to Complete",
            ])
            for item in items:
                status = item.get("status", "pending")
                if status not in ["completed", "skipped"]:
                    item_id = item.get("id", "unknown")
                    description = item.get("description", item.get("name", "No description"))
                    lines.append(f"- [ ] **{item_id}**: {description}")
                    
                    # Add item notes if present
                    item_notes = item.get("notes", [])
                    for note in item_notes:
                        lines.append(f"  - Note: {note}")
            lines.append("")
        
        # Add phase notes if present
        notes = context.get("notes", [])
        if notes:
            lines.extend([
                "## Operating Notes",
                *[f"- {n}" for n in notes],
                "",
            ])
        
        # Add relevant files if present
        files = context.get("files", [])
        if files:
            lines.extend([
                "## Relevant Files",
                *[f"- {f}" for f in files],
                "",
            ])
        
        # Add instructions
        lines.extend([
            "## Instructions",
            "1. Complete each checklist item in order",
            "2. After completing each item, report what was done",
            "3. If you encounter blockers, document them clearly",
            "4. Run tests after implementation to verify",
            "5. Provide a summary of changes made",
            "",
            "## Output Format",
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
            "```",
            "",
            "-" * 60,
            "",
            "After receiving the response, run:",
            "  orchestrator complete <item_id> --notes \"<summary>\"",
            "",
            "=" * 60,
        ])
        
        return "\n".join(lines)
    
    def execute(self, prompt: str, model: Optional[str] = None) -> ExecutionResult:
        """
        Manual provider does not support execution.
        
        Raises:
            NotImplementedError: Always, with helpful instructions
        """
        raise NotImplementedError(
            "Manual provider does not support direct execution.\n"
            "Please copy the generated prompt and paste it into your preferred LLM.\n"
            "Then manually complete the workflow items using:\n"
            "  orchestrator complete <item_id> --notes \"<summary>\""
        )
