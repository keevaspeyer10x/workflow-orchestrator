"""Tests for Meta-command handlers."""
import pytest
from datetime import datetime

from src.v4.chat.commands import (
    MetaCommandParser,
    MetaCommand,
    StatusCommand,
    CheckpointCommand,
    RestoreCommand,
    PinCommand,
    HistoryCommand,
)


class TestMetaCommandParser:
    """Tests for MetaCommandParser."""

    def setup_method(self):
        """Set up parser for tests."""
        self.parser = MetaCommandParser()

    def test_parse_status_command(self):
        """Test parsing /status command."""
        result = self.parser.parse("/status")

        assert result is not None
        assert isinstance(result, StatusCommand)

    def test_parse_checkpoint_command(self):
        """Test parsing /checkpoint command."""
        result = self.parser.parse("/checkpoint")

        assert result is not None
        assert isinstance(result, CheckpointCommand)

    def test_parse_checkpoint_with_message(self):
        """Test parsing /checkpoint with optional message."""
        result = self.parser.parse("/checkpoint save before refactor")

        assert result is not None
        assert isinstance(result, CheckpointCommand)
        assert result.message == "save before refactor"

    def test_parse_restore_command(self):
        """Test parsing /restore with checkpoint ID."""
        result = self.parser.parse("/restore cp_abc123")

        assert result is not None
        assert isinstance(result, RestoreCommand)
        assert result.checkpoint_id == "cp_abc123"

    def test_parse_restore_without_id(self):
        """Test parsing /restore without ID returns latest."""
        result = self.parser.parse("/restore")

        assert result is not None
        assert isinstance(result, RestoreCommand)
        assert result.checkpoint_id is None  # Will use latest

    def test_parse_pin_command(self):
        """Test parsing /pin with message ID."""
        result = self.parser.parse("/pin msg_456")

        assert result is not None
        assert isinstance(result, PinCommand)
        assert result.message_id == "msg_456"

    def test_parse_history_command(self):
        """Test parsing /history with count."""
        result = self.parser.parse("/history 10")

        assert result is not None
        assert isinstance(result, HistoryCommand)
        assert result.count == 10

    def test_parse_history_default_count(self):
        """Test parsing /history with default count."""
        result = self.parser.parse("/history")

        assert result is not None
        assert isinstance(result, HistoryCommand)
        assert result.count == 20  # Default

    def test_non_command_returns_none(self):
        """Test that non-commands return None."""
        result = self.parser.parse("Hello, how are you?")

        assert result is None

    def test_command_must_start_line(self):
        """Test that command must be at start of message."""
        result = self.parser.parse("Please run /status")

        assert result is None  # Not a command - / not at start

    def test_unknown_command_returns_none(self):
        """Test that unknown commands return None."""
        result = self.parser.parse("/unknown_cmd")

        assert result is None

    def test_case_insensitive(self):
        """Test commands are case insensitive."""
        result1 = self.parser.parse("/STATUS")
        result2 = self.parser.parse("/Status")

        assert result1 is not None
        assert result2 is not None
        assert isinstance(result1, StatusCommand)
        assert isinstance(result2, StatusCommand)
