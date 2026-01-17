"""Tests for Chat Mode models."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock

# These imports will fail until implementation exists (TDD RED phase)
from src.v4.chat.models import (
    Message,
    MessageRole,
    ChatEvent,
    ChatEventType,
    SessionConfig,
    ValidationResult,
)


class TestMessage:
    """Tests for Message dataclass."""

    def test_message_creation(self):
        """Test creating a Message with all fields."""
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content="Hello, world!",
            metadata={"source": "test"},
            timestamp=datetime(2026, 1, 17, 12, 0, 0),
        )

        assert msg.id == "msg_001"
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello, world!"
        assert msg.metadata == {"source": "test"}
        assert msg.timestamp == datetime(2026, 1, 17, 12, 0, 0)

    def test_message_role_enum(self):
        """Test MessageRole enum values."""
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.SYSTEM.value == "system"

    def test_message_to_dict(self):
        """Test serializing message to dict for LLM."""
        msg = Message(
            id="msg_002",
            role=MessageRole.ASSISTANT,
            content="I can help with that.",
            metadata={},
            timestamp=datetime.now(),
        )

        d = msg.to_dict()

        assert d["role"] == "assistant"
        assert d["content"] == "I can help with that."

    def test_message_default_timestamp(self):
        """Test Message with default timestamp."""
        msg = Message(
            id="msg_003",
            role=MessageRole.USER,
            content="Test",
        )

        assert msg.timestamp is not None
        assert isinstance(msg.timestamp, datetime)

    def test_message_default_metadata(self):
        """Test Message with default metadata."""
        msg = Message(
            id="msg_004",
            role=MessageRole.SYSTEM,
            content="System message",
        )

        assert msg.metadata == {}


class TestChatEvent:
    """Tests for ChatEvent types."""

    def test_message_added_event(self):
        """Test creating MESSAGE_ADDED event."""
        event = ChatEvent.message_added(
            session_id="sess_001",
            message_id="msg_001",
            role=MessageRole.USER,
            content="Hello",
        )

        assert event.type == ChatEventType.MESSAGE_ADDED
        assert event.data["session_id"] == "sess_001"
        assert event.data["message_id"] == "msg_001"
        assert event.data["role"] == "user"
        assert event.data["content"] == "Hello"

    def test_checkpoint_created_event(self):
        """Test creating CHECKPOINT_CREATED event."""
        event = ChatEvent.checkpoint_created(
            session_id="sess_001",
            checkpoint_id="cp_001",
            message_count=10,
        )

        assert event.type == ChatEventType.CHECKPOINT_CREATED
        assert event.data["session_id"] == "sess_001"
        assert event.data["checkpoint_id"] == "cp_001"
        assert event.data["message_count"] == 10

    def test_session_restored_event(self):
        """Test creating SESSION_RESTORED event."""
        event = ChatEvent.session_restored(
            session_id="sess_001",
            checkpoint_id="cp_001",
        )

        assert event.type == ChatEventType.SESSION_RESTORED
        assert event.data["session_id"] == "sess_001"
        assert event.data["checkpoint_id"] == "cp_001"


class TestSessionConfig:
    """Tests for SessionConfig."""

    def test_default_config(self):
        """Test SessionConfig with defaults."""
        config = SessionConfig()

        assert config.max_tokens == 100000
        assert config.summarization_threshold == 0.7
        assert config.checkpoint_interval_messages == 20
        assert config.checkpoint_interval_minutes == 10
        assert config.recent_messages_to_keep == 20

    def test_custom_config(self):
        """Test SessionConfig with custom values."""
        config = SessionConfig(
            max_tokens=50000,
            summarization_threshold=0.8,
            checkpoint_interval_messages=10,
        )

        assert config.max_tokens == 50000
        assert config.summarization_threshold == 0.8
        assert config.checkpoint_interval_messages == 10


class TestValidationResult:
    """Tests for ValidationResult."""

    def test_valid_result(self):
        """Test a valid result."""
        result = ValidationResult(is_valid=True)

        assert result.is_valid is True
        assert result.missing_entities == []
        assert result.missing_decisions == []

    def test_invalid_result_with_missing(self):
        """Test invalid result with missing items."""
        result = ValidationResult(
            is_valid=False,
            missing_entities=["file.py", "function()"],
            missing_decisions=["approved", "rejected"],
        )

        assert result.is_valid is False
        assert "file.py" in result.missing_entities
        assert "approved" in result.missing_decisions
