"""
Meta-command handlers for V4.2 Chat Mode.

Parses and executes session control commands like /status, /checkpoint, etc.
"""
import re
from abc import ABC
from dataclasses import dataclass
from typing import Optional


class MetaCommand(ABC):
    """Base class for meta-commands."""
    pass


@dataclass
class StatusCommand(MetaCommand):
    """Show session status."""
    pass


@dataclass
class CheckpointCommand(MetaCommand):
    """Create a checkpoint."""
    message: Optional[str] = None


@dataclass
class RestoreCommand(MetaCommand):
    """Restore from a checkpoint."""
    checkpoint_id: Optional[str] = None  # None = use latest


@dataclass
class PinCommand(MetaCommand):
    """Pin a message (prevent summarization)."""
    message_id: str


@dataclass
class HistoryCommand(MetaCommand):
    """Show message history."""
    count: int = 20


class MetaCommandParser:
    """
    Parser for meta-commands.

    Commands:
    - /status - Show session status
    - /checkpoint [message] - Create checkpoint
    - /restore [checkpoint_id] - Restore from checkpoint
    - /pin <message_id> - Pin message
    - /history [count] - Show history
    """

    # Command patterns
    COMMAND_PATTERN = re.compile(r'^/(\w+)(?:\s+(.*))?$', re.IGNORECASE)

    COMMANDS = {
        "status": StatusCommand,
        "checkpoint": CheckpointCommand,
        "restore": RestoreCommand,
        "pin": PinCommand,
        "history": HistoryCommand,
    }

    def parse(self, text: str) -> Optional[MetaCommand]:
        """
        Parse text for a meta-command.

        Args:
            text: User input text

        Returns:
            MetaCommand if valid command, None otherwise
        """
        text = text.strip()

        # Must start with /
        if not text.startswith("/"):
            return None

        # Parse command and args
        match = self.COMMAND_PATTERN.match(text)
        if not match:
            return None

        command_name = match.group(1).lower()
        args = match.group(2) or ""
        args = args.strip()

        # Check if known command
        if command_name not in self.COMMANDS:
            return None

        # Create command object based on type
        if command_name == "status":
            return StatusCommand()

        elif command_name == "checkpoint":
            return CheckpointCommand(message=args if args else None)

        elif command_name == "restore":
            return RestoreCommand(checkpoint_id=args if args else None)

        elif command_name == "pin":
            if not args:
                return None  # pin requires message_id
            return PinCommand(message_id=args)

        elif command_name == "history":
            try:
                count = int(args) if args else 20
            except ValueError:
                count = 20
            return HistoryCommand(count=count)

        return None

    def is_command(self, text: str) -> bool:
        """Check if text is a meta-command."""
        return self.parse(text) is not None
