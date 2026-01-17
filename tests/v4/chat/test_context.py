"""Tests for SafeContextManager."""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.v4.chat.models import Message, MessageRole, SessionConfig, ValidationResult
from src.v4.chat.context import SafeContextManager
from src.v4.chat.validator import SummaryValidator
from src.v4.budget import EstimationTokenCounter


class TestSafeContextManager:
    """Tests for SafeContextManager."""

    def _create_message(self, id: str, content: str, role: MessageRole = MessageRole.USER) -> Message:
        """Helper to create test messages."""
        return Message(
            id=id,
            role=role,
            content=content,
            timestamp=datetime.now(),
        )

    @pytest.mark.asyncio
    async def test_no_summarization_below_threshold(self):
        """Test that no summarization happens below 70% threshold."""
        token_counter = EstimationTokenCounter()
        validator = SummaryValidator()
        config = SessionConfig(
            max_tokens=10000,  # Large enough that short messages don't trigger
            summarization_threshold=0.7,
            recent_messages_to_keep=5,
        )

        # Create messages that use less than 70% of context
        messages = [
            self._create_message("1", "Short message"),
            self._create_message("2", "Another short one"),
        ]

        mock_wrapper = MagicMock()
        manager = SafeContextManager(
            token_counter=token_counter,
            validator=validator,
            llm_wrapper=mock_wrapper,
            config=config,
        )

        result = await manager.prepare_context(messages, pinned=[])

        # Should return messages unchanged
        assert len(result) == 2
        assert result[0].id == "1"
        assert result[1].id == "2"
        # LLM should not be called
        mock_wrapper.call.assert_not_called()

    @pytest.mark.asyncio
    async def test_summarization_triggered_above_threshold(self):
        """Test that summarization triggers above 70% threshold."""
        token_counter = EstimationTokenCounter()
        validator = SummaryValidator()
        config = SessionConfig(
            max_tokens=100,  # Very small to trigger summarization
            summarization_threshold=0.5,
            recent_messages_to_keep=2,
        )

        # Create many messages to exceed threshold
        messages = [
            self._create_message(str(i), "A" * 50)  # Long content
            for i in range(10)
        ]

        mock_wrapper = AsyncMock()
        mock_wrapper.call.return_value = MagicMock(
            content="Summary of conversation about various topics.",
            usage=MagicMock(input_tokens=100, output_tokens=50),
        )

        manager = SafeContextManager(
            token_counter=token_counter,
            validator=validator,
            llm_wrapper=mock_wrapper,
            config=config,
        )

        # Mock validator to return valid
        with patch.object(validator, 'validate', return_value=ValidationResult(is_valid=True)):
            result = await manager.prepare_context(messages, pinned=[])

        # Should have fewer messages (summary + recent)
        assert len(result) < len(messages)
        # LLM should be called for summarization
        mock_wrapper.call.assert_called()

    @pytest.mark.asyncio
    async def test_pinned_messages_preserved(self):
        """Test that pinned messages are never summarized."""
        token_counter = EstimationTokenCounter()
        validator = SummaryValidator()
        config = SessionConfig(
            max_tokens=100,
            summarization_threshold=0.5,
            recent_messages_to_keep=2,
        )

        messages = [
            self._create_message(str(i), "A" * 50)
            for i in range(10)
        ]

        mock_wrapper = AsyncMock()
        mock_wrapper.call.return_value = MagicMock(
            content="Summary of conversation.",
            usage=MagicMock(input_tokens=100, output_tokens=50),
        )

        manager = SafeContextManager(
            token_counter=token_counter,
            validator=validator,
            llm_wrapper=mock_wrapper,
            config=config,
        )

        # Pin message "5"
        with patch.object(validator, 'validate', return_value=ValidationResult(is_valid=True)):
            result = await manager.prepare_context(messages, pinned=["5"])

        # Pinned message should be in result
        result_ids = [m.id for m in result]
        assert "5" in result_ids

    @pytest.mark.asyncio
    async def test_recent_messages_preserved(self):
        """Test that last N messages are always kept."""
        token_counter = EstimationTokenCounter()
        validator = SummaryValidator()
        config = SessionConfig(
            max_tokens=100,
            summarization_threshold=0.5,
            recent_messages_to_keep=3,
        )

        messages = [
            self._create_message(str(i), "A" * 50)
            for i in range(10)
        ]

        mock_wrapper = AsyncMock()
        mock_wrapper.call.return_value = MagicMock(
            content="Summary of conversation.",
            usage=MagicMock(input_tokens=100, output_tokens=50),
        )

        manager = SafeContextManager(
            token_counter=token_counter,
            validator=validator,
            llm_wrapper=mock_wrapper,
            config=config,
        )

        with patch.object(validator, 'validate', return_value=ValidationResult(is_valid=True)):
            result = await manager.prepare_context(messages, pinned=[])

        # Last 3 messages should be present (config.recent_messages_to_keep=3)
        result_ids = [m.id for m in result]
        for i in range(7, 10):
            assert str(i) in result_ids

    @pytest.mark.asyncio
    async def test_validation_failure_fallback(self):
        """Test fallback to truncation when validation fails."""
        token_counter = EstimationTokenCounter()
        validator = SummaryValidator()
        config = SessionConfig(
            max_tokens=100,
            summarization_threshold=0.5,
            recent_messages_to_keep=3,
        )

        messages = [
            self._create_message(str(i), "A" * 50)
            for i in range(10)
        ]

        mock_wrapper = AsyncMock()
        mock_wrapper.call.return_value = MagicMock(
            content="Bad summary missing entities.",
            usage=MagicMock(input_tokens=100, output_tokens=50),
        )

        manager = SafeContextManager(
            token_counter=token_counter,
            validator=validator,
            llm_wrapper=mock_wrapper,
            config=config,
        )

        # Mock validator to return invalid
        with patch.object(validator, 'validate', return_value=ValidationResult(
            is_valid=False,
            missing_entities=["file.py"],
        )):
            result = await manager.prepare_context(messages, pinned=[])

        # Should fall back to truncation - only recent messages kept
        # No summary message should be present (summary messages have "summary" in id)
        summary_msgs = [m for m in result if "summary" in m.id.lower()]
        assert len(summary_msgs) == 0

    @pytest.mark.asyncio
    async def test_summary_message_created(self):
        """Test that summary becomes a SYSTEM message."""
        token_counter = EstimationTokenCounter()
        validator = SummaryValidator()
        config = SessionConfig(
            max_tokens=100,
            summarization_threshold=0.5,
            recent_messages_to_keep=2,
        )

        messages = [
            self._create_message(str(i), "A" * 50)
            for i in range(10)
        ]

        mock_wrapper = AsyncMock()
        mock_wrapper.call.return_value = MagicMock(
            content="Summary: Discussion about API design.",
            usage=MagicMock(input_tokens=100, output_tokens=50),
        )

        manager = SafeContextManager(
            token_counter=token_counter,
            validator=validator,
            llm_wrapper=mock_wrapper,
            config=config,
        )

        with patch.object(validator, 'validate', return_value=ValidationResult(is_valid=True)):
            result = await manager.prepare_context(messages, pinned=[])

        # First message should be SYSTEM with summary
        summary_msgs = [m for m in result if m.role == MessageRole.SYSTEM and "summary" in m.id.lower()]
        assert len(summary_msgs) >= 1

    @pytest.mark.asyncio
    async def test_empty_message_list(self):
        """Test handling empty message list."""
        token_counter = EstimationTokenCounter()
        validator = SummaryValidator()
        config = SessionConfig()

        mock_wrapper = MagicMock()
        manager = SafeContextManager(
            token_counter=token_counter,
            validator=validator,
            llm_wrapper=mock_wrapper,
            config=config,
        )

        result = await manager.prepare_context([], pinned=[])

        assert result == []
        mock_wrapper.call.assert_not_called()
