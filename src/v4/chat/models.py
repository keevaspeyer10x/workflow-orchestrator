"""
Data models for V4.2 Chat Mode.

Defines message types, events, and configuration.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class MessageRole(Enum):
    """Role of a message in the conversation."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    """
    A single message in a chat conversation.

    Attributes:
        id: Unique message identifier
        role: Who sent the message (user, assistant, system)
        content: The message text
        metadata: Additional metadata (timestamps, source, etc.)
        timestamp: When the message was created
    """
    id: str
    role: MessageRole
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for LLM API calls."""
        return {
            "role": self.role.value,
            "content": self.content,
        }

    @classmethod
    def create(
        cls,
        role: MessageRole,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "Message":
        """Create a new message with auto-generated ID."""
        return cls(
            id=f"msg_{uuid.uuid4().hex[:12]}",
            role=role,
            content=content,
            metadata=metadata or {},
            timestamp=datetime.now(),
        )


class ChatEventType(Enum):
    """Types of events in a chat session."""
    MESSAGE_ADDED = "message_added"
    CHECKPOINT_CREATED = "checkpoint_created"
    SESSION_RESTORED = "session_restored"
    MESSAGE_PINNED = "message_pinned"
    CONTEXT_SUMMARIZED = "context_summarized"


@dataclass
class ChatEvent:
    """
    An event in the chat session event stream.

    Used for event sourcing and session recovery.
    """
    type: ChatEventType
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")

    @classmethod
    def message_added(
        cls,
        session_id: str,
        message_id: str,
        role: MessageRole,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ChatEvent":
        """Create MESSAGE_ADDED event."""
        return cls(
            type=ChatEventType.MESSAGE_ADDED,
            data={
                "session_id": session_id,
                "message_id": message_id,
                "role": role.value,
                "content": content,
                "metadata": metadata or {},
            },
        )

    @classmethod
    def checkpoint_created(
        cls,
        session_id: str,
        checkpoint_id: str,
        message_count: int,
    ) -> "ChatEvent":
        """Create CHECKPOINT_CREATED event."""
        return cls(
            type=ChatEventType.CHECKPOINT_CREATED,
            data={
                "session_id": session_id,
                "checkpoint_id": checkpoint_id,
                "message_count": message_count,
            },
        )

    @classmethod
    def session_restored(
        cls,
        session_id: str,
        checkpoint_id: str,
    ) -> "ChatEvent":
        """Create SESSION_RESTORED event."""
        return cls(
            type=ChatEventType.SESSION_RESTORED,
            data={
                "session_id": session_id,
                "checkpoint_id": checkpoint_id,
            },
        )

    @classmethod
    def message_pinned(
        cls,
        session_id: str,
        message_id: str,
    ) -> "ChatEvent":
        """Create MESSAGE_PINNED event."""
        return cls(
            type=ChatEventType.MESSAGE_PINNED,
            data={
                "session_id": session_id,
                "message_id": message_id,
            },
        )

    def to_storage_event(self):
        """Convert to storage Event format."""
        from ..security.storage import Event

        return Event(
            id=self.id,
            stream_id="",  # Set by caller
            type=self.type.value,
            version=0,  # Set by caller
            timestamp=self.timestamp,
            correlation_id=self.data.get("session_id", ""),
            data=self.data,
            metadata={},
        )


@dataclass
class SessionConfig:
    """
    Configuration for a chat session.

    Attributes:
        max_tokens: Maximum tokens in context window
        summarization_threshold: Trigger summarization above this % (0.7 = 70%)
        checkpoint_interval_messages: Create checkpoint every N messages
        checkpoint_interval_minutes: Create checkpoint every N minutes
        recent_messages_to_keep: Always keep last N messages
    """
    max_tokens: int = 100000
    summarization_threshold: float = 0.7
    checkpoint_interval_messages: int = 20
    checkpoint_interval_minutes: int = 10
    recent_messages_to_keep: int = 20


@dataclass
class ValidationResult:
    """
    Result of validating a summary against original messages.

    Attributes:
        is_valid: True if summary contains all critical information
        missing_entities: Entities from original not found in summary
        missing_decisions: Decisions from original not found in summary
    """
    is_valid: bool
    missing_entities: List[str] = field(default_factory=list)
    missing_decisions: List[str] = field(default_factory=list)
