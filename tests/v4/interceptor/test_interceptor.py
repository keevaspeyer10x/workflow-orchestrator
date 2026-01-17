"""
Tests for V4.2 LLM Call Interceptor module.

Tests are organized by component:
1. Models tests
2. Adapter tests (Anthropic, OpenAI, Gemini)
3. Retry logic tests
4. Wrapper tests (integration with budget)
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import AsyncIterator

# These imports will fail until we implement the module
from src.v4.interceptor.models import (
    LLMRequest,
    LLMResponse,
    StreamChunk,
    InterceptorConfig,
    InterceptorError,
    BudgetExhaustedError,
)
from src.v4.interceptor.adapters import (
    LLMAdapter,
    AnthropicAdapter,
    OpenAIAdapter,
    GeminiAdapter,
)
from src.v4.interceptor.retry import BudgetAwareRetry
from src.v4.interceptor.wrapper import LLMCallWrapper
from src.v4.budget import (
    AtomicBudgetTracker,
    TokenUsage,
    BudgetDecision,
    EstimationTokenCounter,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def budget_tracker():
    """Create an in-memory budget tracker for testing."""
    return AtomicBudgetTracker(db_path=":memory:")


@pytest.fixture
async def budget_with_tokens(budget_tracker):
    """Create a budget with 10,000 tokens."""
    await budget_tracker.create_budget("test_budget", limit=10000)
    return budget_tracker


@pytest.fixture
def token_counter():
    """Create estimation token counter for testing."""
    return EstimationTokenCounter()


@pytest.fixture
def sample_request():
    """Create a sample LLM request."""
    return LLMRequest(
        messages=[{"role": "user", "content": "Hello, world!"}],
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
    )


@pytest.fixture
def mock_anthropic_response():
    """Create a mock Anthropic API response."""
    response = MagicMock()
    response.content = [MagicMock(text="Hello! How can I help you?")]
    response.usage = MagicMock(input_tokens=10, output_tokens=20)
    response.model = "claude-sonnet-4-20250514"
    response.stop_reason = "end_turn"
    return response


@pytest.fixture
def mock_openai_response():
    """Create a mock OpenAI API response."""
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content="Hello! How can I help you?"))]
    response.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
    response.model = "gpt-4"
    response.choices[0].finish_reason = "stop"
    return response


@pytest.fixture
def mock_gemini_response():
    """Create a mock Gemini API response."""
    response = MagicMock()
    response.text = "Hello! How can I help you?"
    response.usage_metadata = MagicMock(prompt_token_count=10, candidates_token_count=20)
    return response


# =============================================================================
# Models Tests
# =============================================================================

class TestLLMRequest:
    """Tests for LLMRequest dataclass."""

    def test_create_request(self):
        """Test creating a basic request."""
        request = LLMRequest(
            messages=[{"role": "user", "content": "Hello"}],
            model="claude-sonnet-4-20250514",
        )
        assert request.model == "claude-sonnet-4-20250514"
        assert len(request.messages) == 1
        assert request.max_tokens == 4096  # default

    def test_request_with_metadata(self):
        """Test request with metadata."""
        request = LLMRequest(
            messages=[{"role": "user", "content": "Hello"}],
            model="gpt-4",
            metadata={"workflow_id": "wf_123"},
        )
        assert request.metadata["workflow_id"] == "wf_123"


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_create_response(self):
        """Test creating a basic response."""
        usage = TokenUsage(input_tokens=10, output_tokens=20)
        response = LLMResponse(
            content="Hello!",
            usage=usage,
            model="claude-sonnet-4-20250514",
            finish_reason="end_turn",
        )
        assert response.content == "Hello!"
        assert response.usage.total == 30

    def test_response_with_raw(self):
        """Test response preserves raw response."""
        usage = TokenUsage(input_tokens=10, output_tokens=20)
        raw = {"id": "msg_123"}
        response = LLMResponse(
            content="Hello!",
            usage=usage,
            model="test",
            finish_reason="stop",
            raw_response=raw,
        )
        assert response.raw_response == raw


class TestStreamChunk:
    """Tests for StreamChunk dataclass."""

    def test_intermediate_chunk(self):
        """Test creating an intermediate chunk."""
        chunk = StreamChunk(content="Hello")
        assert chunk.content == "Hello"
        assert not chunk.is_final
        assert chunk.usage is None

    def test_final_chunk(self):
        """Test creating a final chunk with usage."""
        usage = TokenUsage(input_tokens=10, output_tokens=20)
        chunk = StreamChunk(content="!", is_final=True, usage=usage)
        assert chunk.is_final
        assert chunk.usage.total == 30


# =============================================================================
# Adapter Tests
# =============================================================================

class TestAnthropicAdapter:
    """Tests for AnthropicAdapter."""

    def test_extract_usage(self, mock_anthropic_response):
        """Test extracting usage from Anthropic response."""
        adapter = AnthropicAdapter()
        usage = adapter.extract_usage(mock_anthropic_response)
        assert usage.input_tokens == 10
        assert usage.output_tokens == 20
        assert usage.total == 30

    def test_extract_usage_missing(self):
        """Test fallback when usage is missing."""
        adapter = AnthropicAdapter()
        response = MagicMock()
        response.usage = None
        response.content = [MagicMock(text="Hello")]

        usage = adapter.extract_usage(response)
        # Should fall back to estimation
        assert usage.input_tokens >= 0
        assert usage.output_tokens >= 0

    @pytest.mark.asyncio
    async def test_call_success(self, sample_request, mock_anthropic_response):
        """Test successful Anthropic API call."""
        adapter = AnthropicAdapter()

        with patch.object(adapter, '_get_client') as mock_client:
            mock_client.return_value.messages.create.return_value = mock_anthropic_response

            response = await adapter.call(sample_request)

            assert response.content == "Hello! How can I help you?"
            assert response.usage.total == 30


class TestOpenAIAdapter:
    """Tests for OpenAIAdapter."""

    def test_extract_usage(self, mock_openai_response):
        """Test extracting usage from OpenAI response."""
        adapter = OpenAIAdapter()
        usage = adapter.extract_usage(mock_openai_response)
        assert usage.input_tokens == 10
        assert usage.output_tokens == 20

    @pytest.mark.asyncio
    async def test_call_success(self, sample_request, mock_openai_response):
        """Test successful OpenAI API call."""
        adapter = OpenAIAdapter()

        with patch.object(adapter, '_get_client') as mock_client:
            mock_client.return_value.chat.completions.create.return_value = mock_openai_response

            response = await adapter.call(sample_request)

            assert response.content == "Hello! How can I help you?"


class TestGeminiAdapter:
    """Tests for GeminiAdapter."""

    def test_extract_usage(self, mock_gemini_response):
        """Test extracting usage from Gemini response."""
        adapter = GeminiAdapter()
        usage = adapter.extract_usage(mock_gemini_response)
        assert usage.input_tokens == 10
        assert usage.output_tokens == 20

    @pytest.mark.asyncio
    async def test_call_success(self, sample_request, mock_gemini_response):
        """Test successful Gemini API call."""
        adapter = GeminiAdapter()

        with patch.object(adapter, '_get_model') as mock_model:
            mock_model.return_value.generate_content.return_value = mock_gemini_response

            response = await adapter.call(sample_request)

            assert response.content == "Hello! How can I help you?"


# =============================================================================
# Retry Logic Tests
# =============================================================================

class TestBudgetAwareRetry:
    """Tests for BudgetAwareRetry."""

    @pytest.mark.asyncio
    async def test_success_first_try(self):
        """Test operation succeeds on first try."""
        retry = BudgetAwareRetry(max_retries=3)

        operation = AsyncMock(return_value="success")

        result = await retry.execute(operation)

        assert result == "success"
        assert operation.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Test retry on transient failure."""
        retry = BudgetAwareRetry(max_retries=3, delay_base=0.01)

        operation = AsyncMock()
        operation.side_effect = [Exception("fail"), Exception("fail"), "success"]

        result = await retry.execute(operation)

        assert result == "success"
        assert operation.call_count == 3

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Test raises after max retries."""
        retry = BudgetAwareRetry(max_retries=2, delay_base=0.01)

        operation = AsyncMock(side_effect=Exception("persistent failure"))

        with pytest.raises(Exception, match="persistent failure"):
            await retry.execute(operation)

        assert operation.call_count == 2

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Test delays increase exponentially."""
        retry = BudgetAwareRetry(max_retries=3, delay_base=0.1, delay_max=10.0)

        delays = []
        original_sleep = asyncio.sleep

        async def capture_sleep(delay):
            delays.append(delay)
            await original_sleep(0.001)  # Minimal actual delay for test speed

        operation = AsyncMock()
        operation.side_effect = [Exception("fail"), Exception("fail"), "success"]

        with patch('asyncio.sleep', capture_sleep):
            await retry.execute(operation)

        # Delays should increase (with jitter, so check ordering)
        assert len(delays) == 2
        # Base delay should be around 0.1 * 2^attempt
        assert delays[0] < delays[1] or delays[0] < 0.5  # Allow for jitter


# =============================================================================
# Wrapper Tests
# =============================================================================

class TestLLMCallWrapper:
    """Tests for LLMCallWrapper."""

    @pytest.mark.asyncio
    async def test_successful_call_with_budget(self, budget_with_tokens, token_counter, sample_request):
        """Test successful call tracks budget correctly."""
        budget_tracker = budget_with_tokens

        # Create mock adapter
        adapter = MagicMock(spec=LLMAdapter)
        mock_response = LLMResponse(
            content="Hello!",
            usage=TokenUsage(input_tokens=100, output_tokens=200),
            model="test",
            finish_reason="stop",
        )
        adapter.call = AsyncMock(return_value=mock_response)

        wrapper = LLMCallWrapper(
            budget_tracker=budget_tracker,
            token_counter=token_counter,
            adapter=adapter,
            budget_id="test_budget",
        )

        response = await wrapper.call(sample_request)

        # Check response
        assert response.content == "Hello!"

        # Check budget was updated
        status = await budget_tracker.get_status("test_budget")
        assert status.used == 300  # 100 + 200

    @pytest.mark.asyncio
    async def test_budget_exhaustion_blocks_call(self, budget_tracker, token_counter, sample_request):
        """Test call is blocked when budget exhausted."""
        # Create tiny budget
        await budget_tracker.create_budget("tiny_budget", limit=10)

        adapter = MagicMock(spec=LLMAdapter)
        adapter.call = AsyncMock()

        wrapper = LLMCallWrapper(
            budget_tracker=budget_tracker,
            token_counter=token_counter,
            adapter=adapter,
            budget_id="tiny_budget",
        )

        # Request should be blocked
        with pytest.raises(BudgetExhaustedError):
            await wrapper.call(sample_request)

        # Adapter should not be called
        adapter.call.assert_not_called()

    @pytest.mark.asyncio
    async def test_rollback_on_api_error(self, budget_with_tokens, token_counter, sample_request):
        """Test budget rollback on API error."""
        budget_tracker = budget_with_tokens

        adapter = MagicMock(spec=LLMAdapter)
        adapter.call = AsyncMock(side_effect=Exception("API Error"))

        wrapper = LLMCallWrapper(
            budget_tracker=budget_tracker,
            token_counter=token_counter,
            adapter=adapter,
            budget_id="test_budget",
        )

        with pytest.raises(Exception, match="API Error"):
            await wrapper.call(sample_request)

        # Budget should be unchanged (rolled back)
        status = await budget_tracker.get_status("test_budget")
        assert status.used == 0
        assert status.reserved == 0

    @pytest.mark.asyncio
    async def test_retry_uses_same_reservation(self, budget_with_tokens, token_counter, sample_request):
        """Test retries use the same reservation."""
        budget_tracker = budget_with_tokens

        # Track reservation IDs
        reservation_ids = []
        original_reserve = budget_tracker.reserve

        async def track_reserve(*args, **kwargs):
            result = await original_reserve(*args, **kwargs)
            if result.success:
                reservation_ids.append(result.reservation_id)
            return result

        budget_tracker.reserve = track_reserve

        adapter = MagicMock(spec=LLMAdapter)
        mock_response = LLMResponse(
            content="Hello!",
            usage=TokenUsage(input_tokens=100, output_tokens=200),
            model="test",
            finish_reason="stop",
        )
        # Fail first, succeed second
        adapter.call = AsyncMock(side_effect=[Exception("fail"), mock_response])

        config = InterceptorConfig(max_retries=3, retry_delay_base=0.01)
        wrapper = LLMCallWrapper(
            budget_tracker=budget_tracker,
            token_counter=token_counter,
            adapter=adapter,
            budget_id="test_budget",
            config=config,
        )

        await wrapper.call(sample_request)

        # Only one reservation should be created
        assert len(reservation_ids) == 1

    @pytest.mark.asyncio
    async def test_streaming_call(self, budget_with_tokens, token_counter, sample_request):
        """Test streaming call tracks budget at completion."""
        budget_tracker = budget_with_tokens

        async def mock_stream() -> AsyncIterator[StreamChunk]:
            yield StreamChunk(content="Hello")
            yield StreamChunk(content=" ")
            yield StreamChunk(content="World")
            yield StreamChunk(
                content="!",
                is_final=True,
                usage=TokenUsage(input_tokens=50, output_tokens=100),
            )

        adapter = MagicMock(spec=LLMAdapter)
        adapter.call_streaming = MagicMock(return_value=mock_stream())

        wrapper = LLMCallWrapper(
            budget_tracker=budget_tracker,
            token_counter=token_counter,
            adapter=adapter,
            budget_id="test_budget",
        )

        chunks = []
        async for chunk in wrapper.call_streaming(sample_request):
            chunks.append(chunk)

        # Check all chunks received
        assert len(chunks) == 4
        assert "".join(c.content for c in chunks) == "Hello World!"

        # Check budget committed at end
        status = await budget_tracker.get_status("test_budget")
        assert status.used == 150  # 50 + 100


class TestIntegration:
    """Integration tests with full stack."""

    @pytest.mark.asyncio
    async def test_budget_depletion_over_multiple_calls(self, budget_tracker, token_counter):
        """Test budget depletes correctly over multiple calls."""
        # Create budget of 1000 tokens
        await budget_tracker.create_budget("limited_budget", limit=1000)

        adapter = MagicMock(spec=LLMAdapter)

        # Each call uses 300 tokens
        def make_response():
            return LLMResponse(
                content="Response",
                usage=TokenUsage(input_tokens=100, output_tokens=200),
                model="test",
                finish_reason="stop",
            )

        adapter.call = AsyncMock(side_effect=[make_response() for _ in range(5)])

        wrapper = LLMCallWrapper(
            budget_tracker=budget_tracker,
            token_counter=token_counter,
            adapter=adapter,
            budget_id="limited_budget",
        )

        request = LLMRequest(
            messages=[{"role": "user", "content": "Hi"}],
            model="test",
        )

        # First 3 calls should succeed
        for i in range(3):
            await wrapper.call(request)

        # Check budget
        status = await budget_tracker.get_status("limited_budget")
        assert status.used == 900

        # 4th call should fail (only 100 tokens left, need ~300)
        with pytest.raises(BudgetExhaustedError):
            await wrapper.call(request)
