"""Tests for ChatSession."""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.v4.chat.models import Message, MessageRole, SessionConfig
from src.v4.chat.session import ChatSession
from src.v4.chat.context import SafeContextManager
from src.v4.chat.commands import MetaCommandParser
from src.v4.security.async_storage import SQLiteAsyncEventStore, CheckpointStore, SQLiteAdapter
from src.v4.budget import AtomicBudgetTracker, EstimationTokenCounter


class TestChatSession:
    """Tests for ChatSession."""

    async def _setup_stores(self):
        """Set up event store and checkpoint store."""
        event_store = SQLiteAsyncEventStore(":memory:")
        checkpoint_store = CheckpointStore(event_store._adapter)
        return event_store, checkpoint_store

    async def _setup_budget(self, limit: int = 100000):
        """Set up budget tracker."""
        tracker = AtomicBudgetTracker(":memory:")
        await tracker.create_budget("test_budget", limit=limit)
        return tracker

    def _mock_llm_wrapper(self):
        """Create mock LLM wrapper."""
        wrapper = AsyncMock()
        wrapper.call = AsyncMock(return_value=MagicMock(
            content="I can help with that.",
            usage=MagicMock(input_tokens=100, output_tokens=50),
            model="test-model",
            finish_reason="stop",
        ))
        return wrapper

    @pytest.mark.asyncio
    async def test_send_message(self):
        """Test sending a message and receiving response."""
        event_store, checkpoint_store = await self._setup_stores()
        budget_tracker = await self._setup_budget()
        mock_llm_wrapper = self._mock_llm_wrapper()

        config = SessionConfig(
            max_tokens=100000,
            summarization_threshold=0.7,
            checkpoint_interval_messages=5,
        )

        try:
            session = ChatSession(
                session_id="test_session",
                event_store=event_store,
                checkpoint_store=checkpoint_store,
                budget_tracker=budget_tracker,
                budget_id="test_budget",
                llm_wrapper=mock_llm_wrapper,
                config=config,
            )

            response = await session.send("Hello!")

            assert response is not None
            assert "help" in response.lower() or len(response) > 0
            mock_llm_wrapper.call.assert_called_once()

        finally:
            await event_store.close()
            await budget_tracker.close()

    @pytest.mark.asyncio
    async def test_message_persistence(self):
        """Test that messages are persisted to EventStore."""
        event_store, checkpoint_store = await self._setup_stores()
        budget_tracker = await self._setup_budget()
        mock_llm_wrapper = self._mock_llm_wrapper()

        config = SessionConfig(
            max_tokens=100000,
            summarization_threshold=0.7,
            checkpoint_interval_messages=5,
        )

        try:
            session = ChatSession(
                session_id="test_session",
                event_store=event_store,
                checkpoint_store=checkpoint_store,
                budget_tracker=budget_tracker,
                budget_id="test_budget",
                llm_wrapper=mock_llm_wrapper,
                config=config,
            )

            await session.send("Test message")

            # Check events were stored
            events = []
            async for event in event_store.read("chat:test_session"):
                events.append(event)

            assert len(events) >= 2  # User message + assistant response

        finally:
            await event_store.close()
            await budget_tracker.close()

    @pytest.mark.asyncio
    async def test_auto_checkpoint(self):
        """Test that checkpoint is created after N messages."""
        event_store, checkpoint_store = await self._setup_stores()
        budget_tracker = await self._setup_budget()
        mock_llm_wrapper = self._mock_llm_wrapper()

        config = SessionConfig(
            max_tokens=100000,
            summarization_threshold=0.7,
            checkpoint_interval_messages=5,
        )

        try:
            session = ChatSession(
                session_id="test_session",
                event_store=event_store,
                checkpoint_store=checkpoint_store,
                budget_tracker=budget_tracker,
                budget_id="test_budget",
                llm_wrapper=mock_llm_wrapper,
                config=config,
            )

            # Send enough messages to trigger checkpoint (5 rounds = 10 messages)
            for i in range(6):
                await session.send(f"Message {i}")

            # Check checkpoint was created
            checkpoint = await checkpoint_store.load_latest("chat:test_session")
            assert checkpoint is not None

        finally:
            await event_store.close()
            await budget_tracker.close()

    @pytest.mark.asyncio
    async def test_restore_checkpoint(self):
        """Test restoring from a checkpoint."""
        event_store, checkpoint_store = await self._setup_stores()
        budget_tracker = await self._setup_budget()
        mock_llm_wrapper = self._mock_llm_wrapper()

        config = SessionConfig(
            max_tokens=100000,
            summarization_threshold=0.7,
            checkpoint_interval_messages=20,  # High to prevent auto-checkpoint
        )

        try:
            session = ChatSession(
                session_id="test_session",
                event_store=event_store,
                checkpoint_store=checkpoint_store,
                budget_tracker=budget_tracker,
                budget_id="test_budget",
                llm_wrapper=mock_llm_wrapper,
                config=config,
            )

            # Send some messages
            await session.send("Message 1")
            await session.send("Message 2")

            # Create checkpoint
            cp_id = await session.checkpoint()
            assert cp_id is not None

            # Send more messages
            await session.send("Message 3")

            # Restore
            await session.restore(cp_id)

            # Message count should be back to checkpoint state
            assert len(session.messages) == 4  # 2 user + 2 assistant

        finally:
            await event_store.close()
            await budget_tracker.close()

    @pytest.mark.asyncio
    async def test_crash_recovery(self):
        """Test recovery after simulated crash."""
        event_store, checkpoint_store = await self._setup_stores()
        budget_tracker = await self._setup_budget()
        mock_llm_wrapper = self._mock_llm_wrapper()

        config = SessionConfig(
            max_tokens=100000,
            summarization_threshold=0.7,
            checkpoint_interval_messages=20,
        )

        try:
            # Create first session and send messages
            session1 = ChatSession(
                session_id="crash_test",
                event_store=event_store,
                checkpoint_store=checkpoint_store,
                budget_tracker=budget_tracker,
                budget_id="test_budget",
                llm_wrapper=mock_llm_wrapper,
                config=config,
            )

            await session1.send("Before crash 1")
            await session1.send("Before crash 2")

            # Create checkpoint
            await session1.checkpoint()

            # "Crash" - create new session with same ID
            session2 = ChatSession(
                session_id="crash_test",
                event_store=event_store,
                checkpoint_store=checkpoint_store,
                budget_tracker=budget_tracker,
                budget_id="test_budget",
                llm_wrapper=mock_llm_wrapper,
                config=config,
            )

            # Recover
            await session2.recover()

            # Should have messages from before crash
            assert len(session2.messages) == 4  # 2 user + 2 assistant

        finally:
            await event_store.close()
            await budget_tracker.close()

    @pytest.mark.asyncio
    async def test_budget_enforcement(self):
        """Test graceful handling when budget exhausted."""
        event_store, checkpoint_store = await self._setup_stores()

        # Create budget that's already exhausted
        budget_tracker = AtomicBudgetTracker(":memory:")
        await budget_tracker.create_budget("exhausted_budget", limit=100)
        # Reserve and commit to exhaust it
        result = await budget_tracker.reserve("exhausted_budget", 100)
        if result.success:
            await budget_tracker.commit(result.reservation_id, 100)

        mock_llm_wrapper = self._mock_llm_wrapper()

        config = SessionConfig(
            max_tokens=100000,
            summarization_threshold=0.7,
            checkpoint_interval_messages=20,
        )

        try:
            session = ChatSession(
                session_id="budget_test",
                event_store=event_store,
                checkpoint_store=checkpoint_store,
                budget_tracker=budget_tracker,
                budget_id="exhausted_budget",
                llm_wrapper=mock_llm_wrapper,
                config=config,
            )

            # Should get error about budget
            response = await session.send("This should fail due to budget")

            assert "budget" in response.lower() or "token" in response.lower()

        finally:
            await event_store.close()
            await budget_tracker.close()

    @pytest.mark.asyncio
    async def test_meta_command_execution(self):
        """Test that /status returns session info."""
        event_store, checkpoint_store = await self._setup_stores()
        budget_tracker = await self._setup_budget()
        mock_llm_wrapper = self._mock_llm_wrapper()

        config = SessionConfig(
            max_tokens=100000,
            summarization_threshold=0.7,
            checkpoint_interval_messages=20,
        )

        try:
            session = ChatSession(
                session_id="test_session",
                event_store=event_store,
                checkpoint_store=checkpoint_store,
                budget_tracker=budget_tracker,
                budget_id="test_budget",
                llm_wrapper=mock_llm_wrapper,
                config=config,
            )

            # Send a regular message first
            await session.send("Hello")

            # Execute status command
            response = await session.send("/status")

            # Should contain session info, not LLM response
            assert "session" in response.lower() or "message" in response.lower()
            # LLM should not be called for /status
            # (call count should be 1 from "Hello", not 2)
            assert mock_llm_wrapper.call.call_count == 1

        finally:
            await event_store.close()
            await budget_tracker.close()

    @pytest.mark.asyncio
    async def test_pinned_message_survives(self):
        """Test that pinned messages are tracked."""
        event_store, checkpoint_store = await self._setup_stores()
        budget_tracker = await self._setup_budget()
        mock_llm_wrapper = self._mock_llm_wrapper()

        config = SessionConfig(
            max_tokens=100000,
            summarization_threshold=0.7,
            checkpoint_interval_messages=20,
        )

        try:
            session = ChatSession(
                session_id="test_session",
                event_store=event_store,
                checkpoint_store=checkpoint_store,
                budget_tracker=budget_tracker,
                budget_id="test_budget",
                llm_wrapper=mock_llm_wrapper,
                config=config,
            )

            # Send message and pin it
            await session.send("Important: Remember API key is xyz123")
            msg_id = session.messages[0].id
            session.pin(msg_id)

            # Check that message is pinned
            assert msg_id in session.pinned_ids

        finally:
            await event_store.close()
            await budget_tracker.close()


class TestIntegration:
    """Integration tests for full session lifecycle."""

    @pytest.mark.asyncio
    async def test_full_session_lifecycle(self):
        """Test create → chat → checkpoint → restore → verify."""
        # Setup
        event_store = SQLiteAsyncEventStore(":memory:")
        checkpoint_store = CheckpointStore(event_store._adapter)
        budget_tracker = AtomicBudgetTracker(":memory:")
        await budget_tracker.create_budget("test_budget", limit=100000)

        # Create properly serializable mock response
        mock_response = MagicMock()
        mock_response.content = "Response"
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.model = "test-model"
        mock_response.finish_reason = "stop"

        mock_wrapper = AsyncMock()
        mock_wrapper.call = AsyncMock(return_value=mock_response)

        config = SessionConfig(checkpoint_interval_messages=50)

        try:
            # Create session
            session = ChatSession(
                session_id="lifecycle_test",
                event_store=event_store,
                checkpoint_store=checkpoint_store,
                budget_tracker=budget_tracker,
                budget_id="test_budget",
                llm_wrapper=mock_wrapper,
                config=config,
            )

            # Chat
            await session.send("Hello")
            await session.send("How are you?")

            # Checkpoint
            cp_id = await session.checkpoint()
            assert cp_id is not None

            initial_msg_count = len(session.messages)

            # More chat
            await session.send("After checkpoint")

            # Verify we have more messages now
            assert len(session.messages) > initial_msg_count

            # Restore
            await session.restore(cp_id)

            # Verify - should be back to checkpoint state
            assert len(session.messages) == initial_msg_count

        finally:
            await event_store.close()
            await budget_tracker.close()
