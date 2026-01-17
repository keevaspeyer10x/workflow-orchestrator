"""
V4.2 Chat Mode Module.

This module provides interactive LLM-driven chat sessions with:
- Safe context management (summarization with validation)
- Session persistence via EventStore
- Crash recovery through event replay
- Meta-commands for session control

Usage:
    from src.v4.chat import (
        ChatSession,
        SafeContextManager,
        SummaryValidator,
        Message,
        MessageRole,
    )

    # Create chat session
    session = ChatSession(
        session_id="my_session",
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        budget_tracker=budget_tracker,
        budget_id="workflow_budget",
        llm_wrapper=llm_wrapper,
    )

    # Send message and get response
    response = await session.send("Hello!")

    # Use meta-commands
    await session.send("/status")
    await session.send("/checkpoint")
"""

from .models import (
    Message,
    MessageRole,
    ChatEvent,
    ChatEventType,
    SessionConfig,
    ValidationResult,
)

from .validator import SummaryValidator

from .context import SafeContextManager

from .commands import (
    MetaCommandParser,
    MetaCommand,
    StatusCommand,
    CheckpointCommand,
    RestoreCommand,
    PinCommand,
    HistoryCommand,
)

from .session import ChatSession

__all__ = [
    # Models
    "Message",
    "MessageRole",
    "ChatEvent",
    "ChatEventType",
    "SessionConfig",
    "ValidationResult",
    # Validator
    "SummaryValidator",
    # Context
    "SafeContextManager",
    # Commands
    "MetaCommandParser",
    "MetaCommand",
    "StatusCommand",
    "CheckpointCommand",
    "RestoreCommand",
    "PinCommand",
    "HistoryCommand",
    # Session
    "ChatSession",
]
