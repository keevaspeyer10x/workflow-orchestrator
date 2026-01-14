"""
Natural language command registration for workflow-orchestrator.

This module registers orchestrator commands with ai-tool-bridge,
enabling natural language discovery and invocation.

Usage:
    from src.nl_commands import register_nl_commands
    register_nl_commands()  # Call after imports, before parsing
"""

from ai_tool_bridge import nl_command
from ai_tool_bridge.registry import CommandSpec, Framework, get_registry


def register_nl_commands():
    """Register all orchestrator commands with the NL registry."""
    registry = get_registry()

    # Only register if not already registered
    if registry.get_command("orchestrator.start"):
        return

    commands = [
        # start - Start a new workflow
        CommandSpec(
            command_id="orchestrator.start",
            triggers=[
                "start workflow",
                "begin workflow",
                "new workflow",
                "start a workflow",
                "create workflow",
            ],
            description="Start a new development workflow",
            tool_name="orchestrator",
            framework=Framework.ARGPARSE,
            cli_command="orchestrator start",
            examples=[
                "start workflow for fixing the login bug",
                "begin workflow to add user authentication",
            ],
        ),
        # status - Show workflow status
        CommandSpec(
            command_id="orchestrator.status",
            triggers=[
                "workflow status",
                "check status",
                "show status",
                "where am i",
                "current phase",
                "progress",
            ],
            description="Show current workflow status and phase",
            tool_name="orchestrator",
            framework=Framework.ARGPARSE,
            cli_command="orchestrator status",
        ),
        # complete - Mark an item as complete
        CommandSpec(
            command_id="orchestrator.complete",
            triggers=[
                "complete item",
                "mark complete",
                "mark done",
                "finish item",
                "done with",
            ],
            description="Mark a workflow item as complete",
            tool_name="orchestrator",
            framework=Framework.ARGPARSE,
            cli_command="orchestrator complete",
            examples=[
                "complete item initial_plan",
                "mark done with risk_analysis",
            ],
        ),
        # skip - Skip an item
        CommandSpec(
            command_id="orchestrator.skip",
            triggers=[
                "skip item",
                "skip task",
                "skip step",
            ],
            description="Skip an optional workflow item",
            tool_name="orchestrator",
            framework=Framework.ARGPARSE,
            cli_command="orchestrator skip",
        ),
        # advance - Move to next phase
        CommandSpec(
            command_id="orchestrator.advance",
            triggers=[
                "advance phase",
                "next phase",
                "move forward",
                "advance workflow",
            ],
            description="Advance to the next workflow phase",
            tool_name="orchestrator",
            framework=Framework.ARGPARSE,
            cli_command="orchestrator advance",
        ),
        # finish - Complete the workflow
        CommandSpec(
            command_id="orchestrator.finish",
            triggers=[
                "finish workflow",
                "complete workflow",
                "end workflow",
                "workflow done",
            ],
            description="Finish and close the current workflow",
            tool_name="orchestrator",
            framework=Framework.ARGPARSE,
            cli_command="orchestrator finish",
        ),
        # task add - Add a new task
        CommandSpec(
            command_id="orchestrator.task.add",
            triggers=[
                "add task",
                "create task",
                "new task",
                "add issue",
                "create issue",
                "log bug",
                "new todo",
            ],
            description="Add a new task or issue",
            tool_name="orchestrator",
            framework=Framework.ARGPARSE,
            cli_command="orchestrator task add",
            examples=[
                "add task fix the memory leak",
                "create issue for login timeout",
            ],
        ),
        # task list - List tasks
        CommandSpec(
            command_id="orchestrator.task.list",
            triggers=[
                "list tasks",
                "show tasks",
                "list issues",
                "what's open",
                "open tasks",
            ],
            description="List tasks and issues",
            tool_name="orchestrator",
            framework=Framework.ARGPARSE,
            cli_command="orchestrator task list",
        ),
        # task next - Get next task
        CommandSpec(
            command_id="orchestrator.task.next",
            triggers=[
                "next task",
                "what's next",
                "highest priority task",
                "what should i work on",
            ],
            description="Show the highest priority open task",
            tool_name="orchestrator",
            framework=Framework.ARGPARSE,
            cli_command="orchestrator task next",
        ),
        # handoff - Generate handoff prompt
        CommandSpec(
            command_id="orchestrator.handoff",
            triggers=[
                "generate handoff",
                "handoff prompt",
                "create handoff",
            ],
            description="Generate a handoff prompt for agent transition",
            tool_name="orchestrator",
            framework=Framework.ARGPARSE,
            cli_command="orchestrator handoff",
        ),
        # checkpoint - Create checkpoint
        CommandSpec(
            command_id="orchestrator.checkpoint",
            triggers=[
                "create checkpoint",
                "save checkpoint",
                "checkpoint",
            ],
            description="Create a workflow checkpoint for later resumption",
            tool_name="orchestrator",
            framework=Framework.ARGPARSE,
            cli_command="orchestrator checkpoint",
        ),
        # review - Run code review
        CommandSpec(
            command_id="orchestrator.review",
            triggers=[
                "run review",
                "code review",
                "run reviews",
                "external review",
            ],
            description="Run third-party model code reviews",
            tool_name="orchestrator",
            framework=Framework.ARGPARSE,
            cli_command="orchestrator review",
        ),
        # resolve - Resolve git conflicts
        CommandSpec(
            command_id="orchestrator.resolve",
            triggers=[
                "resolve conflicts",
                "fix conflicts",
                "merge conflicts",
                "rebase conflicts",
            ],
            description="Resolve git merge or rebase conflicts",
            tool_name="orchestrator",
            framework=Framework.ARGPARSE,
            cli_command="orchestrator resolve",
        ),
    ]

    for cmd in commands:
        try:
            registry.register(cmd)
        except ValueError:
            # Already registered
            pass


# Auto-register when module is imported
register_nl_commands()
