"""
LLM Call Wrapper for V4.2 LLM Call Interceptor.

Main component that intercepts all LLM API calls with:
- Pre-call: budget check, token estimation, reservation
- Post-call: actual token counting, budget commit/rollback
- Retry logic with same reservation
"""
import logging
from typing import AsyncIterator, Optional

from .models import (
    LLMRequest,
    LLMResponse,
    StreamChunk,
    InterceptorConfig,
    BudgetExhaustedError,
)
from .adapters import LLMAdapter
from .retry import BudgetAwareRetry
from ..budget import (
    AtomicBudgetTracker,
    BudgetDecision,
    TokenUsage,
)
from ..budget.counters import TokenCounter

logger = logging.getLogger(__name__)


class LLMCallWrapper:
    """
    Wrapper that intercepts LLM API calls with budget tracking.

    Flow:
    1. Estimate tokens needed for the request
    2. Reserve tokens from budget (with buffer)
    3. Make LLM API call (with retries using same reservation)
    4. On success: commit actual token usage
    5. On failure: rollback reservation

    Usage:
        wrapper = LLMCallWrapper(
            budget_tracker=tracker,
            token_counter=counter,
            adapter=AnthropicAdapter(),
            budget_id="workflow_budget",
        )

        response = await wrapper.call(request)
    """

    def __init__(
        self,
        budget_tracker: AtomicBudgetTracker,
        token_counter: TokenCounter,
        adapter: LLMAdapter,
        budget_id: str,
        config: Optional[InterceptorConfig] = None,
    ):
        """
        Initialize LLM call wrapper.

        Args:
            budget_tracker: Budget tracker for reserve/commit/rollback
            token_counter: Token counter for estimation
            adapter: Provider adapter for making API calls
            budget_id: Budget ID to track usage against
            config: Optional configuration
        """
        self.budget_tracker = budget_tracker
        self.token_counter = token_counter
        self.adapter = adapter
        self.budget_id = budget_id
        self.config = config or InterceptorConfig()

        # Initialize retry handler
        self.retry = BudgetAwareRetry(
            max_retries=self.config.max_retries,
            delay_base=self.config.retry_delay_base,
            delay_max=self.config.retry_delay_max,
        )

    async def call(self, request: LLMRequest) -> LLMResponse:
        """
        Make a non-streaming LLM API call with budget tracking.

        Args:
            request: LLM request

        Returns:
            LLM response

        Raises:
            BudgetExhaustedError: If budget is insufficient
            Exception: If API call fails after retries
        """
        # Step 1: Estimate tokens needed
        estimated_input = await self._estimate_input_tokens(request)
        estimated_output = request.max_tokens  # Worst case
        estimated_total = self.config.estimate_with_buffer(
            estimated_input + estimated_output
        )

        logger.debug(
            f"Estimated tokens: input={estimated_input}, "
            f"output={estimated_output}, total_with_buffer={estimated_total}"
        )

        # Step 2: Reserve tokens
        reservation = await self.budget_tracker.reserve(
            self.budget_id,
            estimated_total,
            correlation_id=request.metadata.get("correlation_id"),
        )

        if not reservation.success:
            # Get current budget status for error
            status = await self.budget_tracker.get_status(self.budget_id)
            available = status.available if status else 0
            raise BudgetExhaustedError(
                budget_id=self.budget_id,
                requested=estimated_total,
                available=available,
                message=reservation.reason,
            )

        reservation_id = reservation.reservation_id
        logger.debug(f"Reserved {estimated_total} tokens: {reservation_id}")

        try:
            # Step 3: Make API call with retry (same reservation)
            async def make_call():
                return await self.adapter.call(request)

            response = await self.retry.execute(make_call)

            # Step 4: Commit actual usage
            actual_tokens = response.usage.total
            await self.budget_tracker.commit(
                reservation_id,
                actual_tokens,
                correlation_id=request.metadata.get("correlation_id"),
            )

            logger.debug(
                f"Committed {actual_tokens} tokens (estimated {estimated_total})"
            )

            return response

        except Exception as e:
            # Step 5: Rollback on failure
            logger.warning(f"API call failed, rolling back reservation: {e}")
            await self.budget_tracker.rollback(
                reservation_id,
                reason=f"API error: {type(e).__name__}",
                correlation_id=request.metadata.get("correlation_id"),
            )
            raise

    async def call_streaming(
        self, request: LLMRequest
    ) -> AsyncIterator[StreamChunk]:
        """
        Make a streaming LLM API call with budget tracking.

        Budget is committed when stream completes (final chunk).

        Args:
            request: LLM request

        Yields:
            StreamChunk objects

        Raises:
            BudgetExhaustedError: If budget is insufficient
            Exception: If API call fails
        """
        # Step 1: Estimate tokens needed
        estimated_input = await self._estimate_input_tokens(request)
        estimated_output = request.max_tokens
        estimated_total = self.config.estimate_with_buffer(
            estimated_input + estimated_output
        )

        # Step 2: Reserve tokens
        reservation = await self.budget_tracker.reserve(
            self.budget_id,
            estimated_total,
            correlation_id=request.metadata.get("correlation_id"),
        )

        if not reservation.success:
            status = await self.budget_tracker.get_status(self.budget_id)
            available = status.available if status else 0
            raise BudgetExhaustedError(
                budget_id=self.budget_id,
                requested=estimated_total,
                available=available,
                message=reservation.reason,
            )

        reservation_id = reservation.reservation_id
        logger.debug(f"Reserved {estimated_total} tokens for streaming: {reservation_id}")

        try:
            # Step 3: Start streaming
            stream = self.adapter.call_streaming(request)

            # Track final usage
            final_usage = None

            async for chunk in stream:
                if chunk.is_final and chunk.usage:
                    final_usage = chunk.usage
                yield chunk

            # Step 4: Commit actual usage
            if final_usage:
                actual_tokens = final_usage.total
            else:
                # Fallback to estimation if no usage in stream
                logger.warning("No usage in stream, using estimation")
                actual_tokens = estimated_total

            await self.budget_tracker.commit(
                reservation_id,
                actual_tokens,
                correlation_id=request.metadata.get("correlation_id"),
            )

            logger.debug(
                f"Committed {actual_tokens} streaming tokens"
            )

        except Exception as e:
            # Rollback on failure
            logger.warning(f"Streaming failed, rolling back reservation: {e}")
            await self.budget_tracker.rollback(
                reservation_id,
                reason=f"Streaming error: {type(e).__name__}",
                correlation_id=request.metadata.get("correlation_id"),
            )
            raise

    async def _estimate_input_tokens(self, request: LLMRequest) -> int:
        """
        Estimate input tokens for a request.

        Uses the token counter for accurate estimation when possible.
        """
        # Build content to count
        content_parts = []

        if request.system:
            content_parts.append(request.system)

        for msg in request.messages:
            msg_content = msg.get("content", "")
            if isinstance(msg_content, str):
                content_parts.append(msg_content)
            elif isinstance(msg_content, list):
                # Multimodal content
                for part in msg_content:
                    if isinstance(part, dict) and "text" in part:
                        content_parts.append(part["text"])

        full_content = "\n".join(content_parts)

        # Use token counter
        try:
            return await self.token_counter.count(full_content)
        except Exception as e:
            logger.warning(f"Token counting failed, using estimation: {e}")
            return request.estimate_input_tokens()

    async def pre_check(self, request: LLMRequest) -> BudgetDecision:
        """
        Pre-flight check if request can be made within budget.

        Does NOT reserve tokens - just checks availability.
        Useful for UI to show warnings before committing.

        Args:
            request: LLM request to check

        Returns:
            BudgetDecision (OK, WARNING, BLOCKED, EMERGENCY_STOP)
        """
        estimated_input = await self._estimate_input_tokens(request)
        estimated_total = self.config.estimate_with_buffer(
            estimated_input + request.max_tokens
        )

        return await self.budget_tracker.pre_check(
            self.budget_id,
            estimated_total,
        )
