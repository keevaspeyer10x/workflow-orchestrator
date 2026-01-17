"""
Safe Context Manager for V4.2 Chat Mode.

Manages conversation context with safe summarization and validation.
"""
import logging
from typing import List, Optional, Set
import uuid

from .models import Message, MessageRole, SessionConfig, ValidationResult
from .validator import SummaryValidator
from ..budget import TokenCounter
from ..interceptor import LLMCallWrapper, LLMRequest

logger = logging.getLogger(__name__)


class SafeContextManager:
    """
    Context management with safety guarantees.

    Features:
    - Deterministic compression with validation
    - Pinned messages preserved (never summarized)
    - Recent messages always kept
    - Fallback to truncation if summarization fails validation
    """

    SUMMARIZATION_PROMPT = """Summarize the following conversation concisely.
Preserve ALL of the following:
- File paths and code references
- Function/method names
- URLs
- Decisions made (what was decided and why)
- Key entities and their relationships

Conversation to summarize:
{conversation}

Provide a comprehensive summary that captures all critical information:"""

    def __init__(
        self,
        token_counter: TokenCounter,
        validator: SummaryValidator,
        llm_wrapper: LLMCallWrapper,
        config: Optional[SessionConfig] = None,
    ):
        """
        Initialize context manager.

        Args:
            token_counter: Counter for token estimation
            validator: Validator for summary quality
            llm_wrapper: LLM wrapper for summarization calls
            config: Session configuration
        """
        self.token_counter = token_counter
        self.validator = validator
        self.llm_wrapper = llm_wrapper
        self.config = config or SessionConfig()

    async def _count_tokens(self, messages: List[Message]) -> int:
        """Count total tokens in messages."""
        total = 0
        for msg in messages:
            total += await self.token_counter.count(msg.content)
        return total

    async def _should_summarize(self, messages: List[Message]) -> bool:
        """Check if context needs summarization."""
        if not messages:
            return False

        token_count = await self._count_tokens(messages)
        threshold = int(self.config.max_tokens * self.config.summarization_threshold)

        return token_count > threshold

    async def prepare_context(
        self,
        messages: List[Message],
        pinned: List[str],
    ) -> List[Message]:
        """
        Prepare context, summarizing if needed.

        Args:
            messages: All conversation messages
            pinned: Message IDs that must be preserved

        Returns:
            Prepared messages (possibly with summary)
        """
        if not messages:
            return []

        # Check if summarization needed
        if not await self._should_summarize(messages):
            return messages

        logger.info(f"Context exceeds threshold, summarizing {len(messages)} messages")

        # Separate messages into categories
        pinned_set = set(pinned)
        recent_count = self.config.recent_messages_to_keep

        # Always keep: pinned + recent
        pinned_msgs = [m for m in messages if m.id in pinned_set]
        recent_msgs = messages[-recent_count:] if len(messages) > recent_count else []

        # Messages to summarize: everything else
        recent_ids = {m.id for m in recent_msgs}
        to_summarize = [
            m for m in messages
            if m.id not in pinned_set and m.id not in recent_ids
        ]

        if not to_summarize:
            # Nothing to summarize
            return messages

        # Generate summary
        summary_text = await self._generate_summary(to_summarize)

        if summary_text:
            # Validate summary
            result = self.validator.validate(to_summarize, summary_text)

            if result.is_valid:
                # Create summary message
                summary_msg = Message(
                    id=f"summary_{uuid.uuid4().hex[:8]}",
                    role=MessageRole.SYSTEM,
                    content=f"[Previous conversation summary]\n{summary_text}",
                    metadata={"is_summary": True, "summarized_count": len(to_summarize)},
                )

                # Combine: summary + pinned + recent
                result_msgs = [summary_msg] + pinned_msgs + recent_msgs
                logger.info(f"Summarization successful: {len(messages)} -> {len(result_msgs)}")
                return result_msgs
            else:
                logger.warning(
                    f"Summary validation failed: {len(result.missing_entities)} missing entities, "
                    f"{len(result.missing_decisions)} missing decisions. Falling back to truncation."
                )

        # Fallback: truncation (keep pinned + recent only)
        logger.info(f"Falling back to truncation: keeping {len(pinned_msgs)} pinned + {len(recent_msgs)} recent")
        return pinned_msgs + recent_msgs

    async def _generate_summary(self, messages: List[Message]) -> Optional[str]:
        """Generate summary of messages using LLM."""
        try:
            # Format conversation
            conversation = "\n\n".join(
                f"{m.role.value.upper()}: {m.content}"
                for m in messages
            )

            prompt = self.SUMMARIZATION_PROMPT.format(conversation=conversation)

            # Call LLM
            request = LLMRequest(
                messages=[{"role": "user", "content": prompt}],
                model="claude-sonnet-4-20250514",  # Use configured model
                max_tokens=2000,
                temperature=0.3,  # Low temperature for consistency
            )

            response = await self.llm_wrapper.call(request)
            return response.content

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return None
