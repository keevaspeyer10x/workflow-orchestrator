"""
Chat Session for V4.2 Chat Mode.

Manages persistent chat sessions with crash recovery.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
import json

from .models import (
    Message,
    MessageRole,
    ChatEvent,
    ChatEventType,
    SessionConfig,
)
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
from .validator import SummaryValidator
from ..security.async_storage import (
    AsyncEventStore,
    CheckpointStore,
    Checkpoint,
)
from ..security.storage import Event
from ..budget import AtomicBudgetTracker, TokenCounter, EstimationTokenCounter
from ..interceptor import LLMCallWrapper, LLMRequest, BudgetExhaustedError

logger = logging.getLogger(__name__)


class ChatSession:
    """
    Persistent chat session with crash recovery.

    Features:
    - Session persistence via EventStore
    - Meta-commands: /status, /checkpoint, /restore, /pin, /history
    - Automatic checkpointing at configurable intervals
    - Crash recovery by replaying events
    - Budget enforcement
    """

    def __init__(
        self,
        session_id: str,
        event_store: AsyncEventStore,
        checkpoint_store: CheckpointStore,
        budget_tracker: AtomicBudgetTracker,
        budget_id: str,
        llm_wrapper: LLMCallWrapper,
        config: Optional[SessionConfig] = None,
        token_counter: Optional[TokenCounter] = None,
    ):
        """
        Initialize chat session.

        Args:
            session_id: Unique session identifier
            event_store: Event store for persistence
            checkpoint_store: Checkpoint store for snapshots
            budget_tracker: Budget tracker for token limits
            budget_id: Budget to use for this session
            llm_wrapper: LLM wrapper for API calls
            config: Session configuration
            token_counter: Token counter (defaults to estimation)
        """
        self.session_id = session_id
        self.event_store = event_store
        self.checkpoint_store = checkpoint_store
        self.budget_tracker = budget_tracker
        self.budget_id = budget_id
        self.llm_wrapper = llm_wrapper
        self.config = config or SessionConfig()
        self.token_counter = token_counter or EstimationTokenCounter()

        # Session state
        self.messages: List[Message] = []
        self.pinned_ids: Set[str] = set()
        self._message_count_since_checkpoint = 0
        self._last_checkpoint_time = datetime.now()
        self._event_version = 0

        # Components
        self.validator = SummaryValidator()
        self.context_manager = SafeContextManager(
            token_counter=self.token_counter,
            validator=self.validator,
            llm_wrapper=llm_wrapper,
            config=self.config,
        )
        self.command_parser = MetaCommandParser()

    @property
    def stream_id(self) -> str:
        """Event stream ID for this session."""
        return f"chat:{self.session_id}"

    async def send(self, user_input: str) -> str:
        """
        Send a message and get response.

        Args:
            user_input: User's message or command

        Returns:
            Assistant response or command result
        """
        # Check for meta-command
        command = self.command_parser.parse(user_input)
        if command:
            return await self._execute_command(command)

        # Regular message
        return await self._send_message(user_input)

    async def _send_message(self, content: str) -> str:
        """Send a regular message to LLM."""
        # Create user message
        user_msg = Message.create(
            role=MessageRole.USER,
            content=content,
        )
        self.messages.append(user_msg)

        # Persist user message
        await self._persist_message(user_msg)

        # Check budget
        status = await self.budget_tracker.get_status(self.budget_id)
        if status and status.exceeded:
            error_msg = f"Token budget exhausted. Used: {status.used}/{status.limit}"
            logger.warning(error_msg)
            return error_msg

        try:
            # Prepare context (may summarize)
            context_msgs = await self.context_manager.prepare_context(
                self.messages,
                list(self.pinned_ids),
            )

            # Build LLM request
            request = LLMRequest(
                messages=[m.to_dict() for m in context_msgs],
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                temperature=1.0,
            )

            # Make LLM call
            response = await self.llm_wrapper.call(request)

            # Create assistant message
            assistant_msg = Message.create(
                role=MessageRole.ASSISTANT,
                content=response.content,
                metadata={
                    "model": response.model,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                    },
                },
            )
            self.messages.append(assistant_msg)

            # Persist assistant message
            await self._persist_message(assistant_msg)

            # Check for auto-checkpoint
            await self._maybe_checkpoint()

            return response.content

        except BudgetExhaustedError as e:
            logger.warning(f"Budget exhausted: {e}")
            return f"Token budget exhausted: {e.message}"

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return f"Error: {str(e)}"

    async def _execute_command(self, command: MetaCommand) -> str:
        """Execute a meta-command."""
        if isinstance(command, StatusCommand):
            return await self._cmd_status()

        elif isinstance(command, CheckpointCommand):
            cp_id = await self.checkpoint(message=command.message)
            return f"Checkpoint created: {cp_id}"

        elif isinstance(command, RestoreCommand):
            await self.restore(command.checkpoint_id)
            return f"Session restored from checkpoint"

        elif isinstance(command, PinCommand):
            self.pin(command.message_id)
            return f"Message {command.message_id} pinned"

        elif isinstance(command, HistoryCommand):
            return await self._cmd_history(command.count)

        return "Unknown command"

    async def _cmd_status(self) -> str:
        """Execute /status command."""
        status = await self.budget_tracker.get_status(self.budget_id)
        budget_info = ""
        if status:
            budget_info = f"\nBudget: {status.used}/{status.limit} tokens ({status.percent_used:.1f}%)"

        checkpoints = await self.checkpoint_store.list_checkpoints(self.stream_id)
        checkpoint_info = f"\nCheckpoints: {len(checkpoints)}"

        return (
            f"Session: {self.session_id}\n"
            f"Messages: {len(self.messages)}\n"
            f"Pinned: {len(self.pinned_ids)}"
            f"{budget_info}"
            f"{checkpoint_info}"
        )

    async def _cmd_history(self, count: int) -> str:
        """Execute /history command."""
        recent = self.messages[-count:] if len(self.messages) > count else self.messages

        lines = []
        for msg in recent:
            role = msg.role.value.upper()
            content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            lines.append(f"[{msg.id}] {role}: {content}")

        return "\n".join(lines) if lines else "No messages"

    async def checkpoint(self, message: Optional[str] = None) -> str:
        """
        Create a checkpoint.

        Args:
            message: Optional checkpoint message

        Returns:
            Checkpoint ID
        """
        # Build state
        state = {
            "messages": [
                {
                    "id": m.id,
                    "role": m.role.value,
                    "content": m.content,
                    "metadata": m.metadata,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in self.messages
            ],
            "pinned_ids": list(self.pinned_ids),
            "message_count": len(self.messages),
        }

        # Create checkpoint
        checkpoint = Checkpoint.create(
            stream_id=self.stream_id,
            version=self._event_version,
            state=state,
            metadata={"message": message} if message else None,
        )

        await self.checkpoint_store.save(checkpoint)

        # Persist event
        event = ChatEvent.checkpoint_created(
            session_id=self.session_id,
            checkpoint_id=checkpoint.id,
            message_count=len(self.messages),
        )
        await self._persist_event(event)

        # Reset checkpoint counters
        self._message_count_since_checkpoint = 0
        self._last_checkpoint_time = datetime.now()

        logger.info(f"Checkpoint created: {checkpoint.id}")
        return checkpoint.id

    async def restore(self, checkpoint_id: Optional[str] = None) -> None:
        """
        Restore session from a checkpoint.

        Args:
            checkpoint_id: Checkpoint to restore (None = latest)
        """
        if checkpoint_id:
            # Load specific checkpoint
            checkpoint = await self.checkpoint_store.load_at_version(
                self.stream_id,
                version=0,  # We need to find by ID
            )
            # Fall back to listing and finding
            checkpoints = await self.checkpoint_store.list_checkpoints(self.stream_id)
            checkpoint = next((c for c in checkpoints if c.id == checkpoint_id), None)
        else:
            # Load latest
            checkpoint = await self.checkpoint_store.load_latest(self.stream_id)

        if not checkpoint:
            raise ValueError(f"Checkpoint not found: {checkpoint_id or 'latest'}")

        # Restore state
        self.messages = []
        for msg_data in checkpoint.state.get("messages", []):
            msg = Message(
                id=msg_data["id"],
                role=MessageRole(msg_data["role"]),
                content=msg_data["content"],
                metadata=msg_data.get("metadata", {}),
                timestamp=datetime.fromisoformat(msg_data["timestamp"]),
            )
            self.messages.append(msg)

        self.pinned_ids = set(checkpoint.state.get("pinned_ids", []))
        self._message_count_since_checkpoint = 0
        self._last_checkpoint_time = datetime.now()

        # Get current stream version for appending
        self._event_version = await self.event_store.get_stream_version(self.stream_id)

        # Persist event
        event = ChatEvent.session_restored(
            session_id=self.session_id,
            checkpoint_id=checkpoint.id,
        )
        await self._persist_event(event)

        logger.info(f"Session restored from checkpoint: {checkpoint.id}")

    async def recover(self) -> None:
        """
        Recover session from latest checkpoint and replay events.

        Use after crash to restore session state.
        """
        # Load latest checkpoint
        checkpoint = await self.checkpoint_store.load_latest(self.stream_id)

        if checkpoint:
            # Restore from checkpoint
            self.messages = []
            for msg_data in checkpoint.state.get("messages", []):
                msg = Message(
                    id=msg_data["id"],
                    role=MessageRole(msg_data["role"]),
                    content=msg_data["content"],
                    metadata=msg_data.get("metadata", {}),
                    timestamp=datetime.fromisoformat(msg_data["timestamp"]),
                )
                self.messages.append(msg)

            self.pinned_ids = set(checkpoint.state.get("pinned_ids", []))
            from_version = checkpoint.version
            self._event_version = checkpoint.version
        else:
            from_version = 0
            self._event_version = 0

        # Replay events after checkpoint
        async for event in self.event_store.read(self.stream_id, from_version):
            await self._apply_event(event)
            self._event_version = event.version

        logger.info(f"Session recovered: {len(self.messages)} messages")

    def pin(self, message_id: str) -> None:
        """
        Pin a message (prevent summarization).

        Args:
            message_id: Message to pin
        """
        self.pinned_ids.add(message_id)
        logger.info(f"Message pinned: {message_id}")

    async def _persist_message(self, message: Message) -> None:
        """Persist a message to the event store."""
        event = ChatEvent.message_added(
            session_id=self.session_id,
            message_id=message.id,
            role=message.role,
            content=message.content,
            metadata=message.metadata,
        )
        await self._persist_event(event)

        # Update checkpoint counter
        self._message_count_since_checkpoint += 1

    async def _persist_event(self, chat_event: ChatEvent) -> None:
        """Persist a chat event."""
        self._event_version += 1

        storage_event = Event(
            id=chat_event.id,
            stream_id=self.stream_id,
            type=chat_event.type.value,
            version=self._event_version,
            timestamp=chat_event.timestamp,
            correlation_id=self.session_id,
            causation_id=None,
            data=chat_event.data,
            metadata={},
        )

        await self.event_store.append(
            self.stream_id,
            [storage_event],
        )

    async def _apply_event(self, event: Event) -> None:
        """Apply an event during recovery."""
        if event.type == ChatEventType.MESSAGE_ADDED.value:
            msg = Message(
                id=event.data["message_id"],
                role=MessageRole(event.data["role"]),
                content=event.data["content"],
                metadata=event.data.get("metadata", {}),
                timestamp=event.timestamp,
            )
            self.messages.append(msg)
            self._event_version = event.version

        elif event.type == ChatEventType.MESSAGE_PINNED.value:
            self.pinned_ids.add(event.data["message_id"])

    async def _maybe_checkpoint(self) -> None:
        """Create checkpoint if interval reached."""
        should_checkpoint = False

        # Check message interval
        if self._message_count_since_checkpoint >= self.config.checkpoint_interval_messages:
            should_checkpoint = True
            logger.debug("Checkpoint triggered by message count")

        # Check time interval
        elapsed = datetime.now() - self._last_checkpoint_time
        if elapsed > timedelta(minutes=self.config.checkpoint_interval_minutes):
            should_checkpoint = True
            logger.debug("Checkpoint triggered by time interval")

        if should_checkpoint:
            await self.checkpoint(message="auto-checkpoint")
