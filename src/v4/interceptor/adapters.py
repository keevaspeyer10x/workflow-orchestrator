"""
Provider adapters for V4.2 LLM Call Interceptor.

Implements adapters for different LLM providers:
- AnthropicAdapter: Claude models
- OpenAIAdapter: GPT models
- GeminiAdapter: Google Gemini models

Each adapter translates between standardized LLMRequest/LLMResponse
and provider-specific API formats.
"""
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional
import logging

from .models import LLMRequest, LLMResponse, StreamChunk
from ..budget.models import TokenUsage

logger = logging.getLogger(__name__)


class LLMAdapter(ABC):
    """
    Abstract base class for LLM provider adapters.

    Subclasses implement provider-specific API calls and token extraction.
    """

    @abstractmethod
    async def call(self, request: LLMRequest) -> LLMResponse:
        """
        Make a non-streaming LLM API call.

        Args:
            request: Standardized LLM request

        Returns:
            Standardized LLM response with usage information
        """
        pass

    @abstractmethod
    async def call_streaming(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        """
        Make a streaming LLM API call.

        Args:
            request: Standardized LLM request

        Yields:
            StreamChunk objects, with final chunk containing usage
        """
        pass

    @abstractmethod
    def extract_usage(self, response: Any) -> TokenUsage:
        """
        Extract token usage from provider-specific response.

        Args:
            response: Raw provider response

        Returns:
            TokenUsage with input and output tokens
        """
        pass

    def _estimate_usage(self, content: str, input_estimate: int = 0) -> TokenUsage:
        """
        Estimate usage when not available from response.

        Used as fallback when provider doesn't return usage.
        """
        # Rough estimation: ~4 chars per token
        output_tokens = max(1, len(content) // 4)
        return TokenUsage(
            input_tokens=input_estimate or 100,
            output_tokens=output_tokens,
        )


class AnthropicAdapter(LLMAdapter):
    """
    Adapter for Anthropic Claude API.

    Uses the anthropic Python package for API calls.
    Token usage extracted from response.usage.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 300,
    ):
        """
        Initialize Anthropic adapter.

        Args:
            api_key: Anthropic API key (uses env var if not provided)
            timeout: Request timeout in seconds
        """
        self._api_key = api_key
        self._timeout = timeout
        self._client = None

    def _get_client(self):
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(
                    api_key=self._api_key,
                    timeout=self._timeout,
                )
            except ImportError:
                raise ImportError(
                    "anthropic package not installed. "
                    "Install with: pip install anthropic"
                )
        return self._client

    async def call(self, request: LLMRequest) -> LLMResponse:
        """Make a non-streaming Claude API call."""
        client = self._get_client()

        # Build API request
        kwargs = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": request.messages,
        }

        if request.system:
            kwargs["system"] = request.system

        if request.temperature != 1.0:
            kwargs["temperature"] = request.temperature

        # Make API call
        response = client.messages.create(**kwargs)

        # Extract content
        content = ""
        if response.content:
            content = "".join(
                block.text for block in response.content
                if hasattr(block, "text")
            )

        # Extract usage
        usage = self.extract_usage(response)

        return LLMResponse(
            content=content,
            usage=usage,
            model=response.model,
            finish_reason=response.stop_reason or "unknown",
            raw_response=response,
        )

    async def call_streaming(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        """Make a streaming Claude API call."""
        client = self._get_client()

        kwargs = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": request.messages,
        }

        if request.system:
            kwargs["system"] = request.system

        if request.temperature != 1.0:
            kwargs["temperature"] = request.temperature

        # Make streaming API call
        with client.messages.stream(**kwargs) as stream:
            accumulated_content = ""

            for event in stream:
                if hasattr(event, "delta") and hasattr(event.delta, "text"):
                    text = event.delta.text
                    accumulated_content += text
                    yield StreamChunk(content=text)

            # Get final message for usage
            final_message = stream.get_final_message()
            usage = self.extract_usage(final_message)

            yield StreamChunk(
                content="",
                is_final=True,
                usage=usage,
            )

    def extract_usage(self, response: Any) -> TokenUsage:
        """Extract usage from Anthropic response."""
        if hasattr(response, "usage") and response.usage is not None:
            return TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

        # Fallback to estimation
        logger.warning("No usage in Anthropic response, using estimation")
        content = ""
        if hasattr(response, "content") and response.content:
            content = "".join(
                block.text for block in response.content
                if hasattr(block, "text")
            )
        return self._estimate_usage(content)


class OpenAIAdapter(LLMAdapter):
    """
    Adapter for OpenAI GPT API.

    Uses the openai Python package for API calls.
    Token usage extracted from response.usage.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 300,
        base_url: Optional[str] = None,
    ):
        """
        Initialize OpenAI adapter.

        Args:
            api_key: OpenAI API key (uses env var if not provided)
            timeout: Request timeout in seconds
            base_url: Optional base URL (for OpenRouter, Azure, etc.)
        """
        self._api_key = api_key
        self._timeout = timeout
        self._base_url = base_url
        self._client = None

    def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            try:
                import openai
                kwargs = {"api_key": self._api_key, "timeout": self._timeout}
                if self._base_url:
                    kwargs["base_url"] = self._base_url
                self._client = openai.OpenAI(**kwargs)
            except ImportError:
                raise ImportError(
                    "openai package not installed. "
                    "Install with: pip install openai"
                )
        return self._client

    async def call(self, request: LLMRequest) -> LLMResponse:
        """Make a non-streaming OpenAI API call."""
        client = self._get_client()

        # Build messages (include system if present)
        messages = list(request.messages)
        if request.system:
            messages.insert(0, {"role": "system", "content": request.system})

        # Make API call
        response = client.chat.completions.create(
            model=request.model,
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )

        # Extract content
        content = ""
        if response.choices:
            content = response.choices[0].message.content or ""

        # Extract usage
        usage = self.extract_usage(response)

        # Extract finish reason
        finish_reason = "unknown"
        if response.choices:
            finish_reason = response.choices[0].finish_reason or "unknown"

        return LLMResponse(
            content=content,
            usage=usage,
            model=response.model,
            finish_reason=finish_reason,
            raw_response=response,
        )

    async def call_streaming(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        """Make a streaming OpenAI API call."""
        client = self._get_client()

        messages = list(request.messages)
        if request.system:
            messages.insert(0, {"role": "system", "content": request.system})

        # Make streaming API call
        stream = client.chat.completions.create(
            model=request.model,
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stream=True,
            stream_options={"include_usage": True},
        )

        accumulated_content = ""
        final_usage = None

        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                accumulated_content += text
                yield StreamChunk(content=text)

            # Check for usage in final chunk
            if hasattr(chunk, "usage") and chunk.usage:
                final_usage = TokenUsage(
                    input_tokens=chunk.usage.prompt_tokens,
                    output_tokens=chunk.usage.completion_tokens,
                )

        # If no usage from stream, estimate
        if final_usage is None:
            final_usage = self._estimate_usage(accumulated_content)

        yield StreamChunk(
            content="",
            is_final=True,
            usage=final_usage,
        )

    def extract_usage(self, response: Any) -> TokenUsage:
        """Extract usage from OpenAI response."""
        if hasattr(response, "usage") and response.usage is not None:
            return TokenUsage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
            )

        # Fallback to estimation
        logger.warning("No usage in OpenAI response, using estimation")
        content = ""
        if hasattr(response, "choices") and response.choices:
            content = response.choices[0].message.content or ""
        return self._estimate_usage(content)


class GeminiAdapter(LLMAdapter):
    """
    Adapter for Google Gemini API.

    Uses the google-generativeai Python package for API calls.
    Token usage extracted from response.usage_metadata.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 300,
    ):
        """
        Initialize Gemini adapter.

        Args:
            api_key: Google API key (uses env var if not provided)
            timeout: Request timeout in seconds
        """
        self._api_key = api_key
        self._timeout = timeout
        self._model = None
        self._model_name = None

    def _get_model(self, model_name: str):
        """Lazy initialization of Gemini model."""
        if self._model is None or self._model_name != model_name:
            try:
                import google.generativeai as genai

                if self._api_key:
                    genai.configure(api_key=self._api_key)

                self._model = genai.GenerativeModel(model_name)
                self._model_name = model_name
            except ImportError:
                raise ImportError(
                    "google-generativeai package not installed. "
                    "Install with: pip install google-generativeai"
                )
        return self._model

    async def call(self, request: LLMRequest) -> LLMResponse:
        """Make a non-streaming Gemini API call."""
        model = self._get_model(request.model)

        # Convert messages to Gemini format
        # Gemini uses a different conversation format
        contents = []
        for msg in request.messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}],
            })

        # Add system instruction if present
        generation_config = {
            "max_output_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        # Make API call
        if request.system:
            # Gemini handles system prompts differently
            response = model.generate_content(
                contents,
                generation_config=generation_config,
                system_instruction=request.system,
            )
        else:
            response = model.generate_content(
                contents,
                generation_config=generation_config,
            )

        # Extract content
        content = response.text if hasattr(response, "text") else ""

        # Extract usage
        usage = self.extract_usage(response)

        # Determine finish reason
        finish_reason = "unknown"
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, "finish_reason"):
                finish_reason = str(candidate.finish_reason)

        return LLMResponse(
            content=content,
            usage=usage,
            model=request.model,
            finish_reason=finish_reason,
            raw_response=response,
        )

    async def call_streaming(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        """Make a streaming Gemini API call."""
        model = self._get_model(request.model)

        contents = []
        for msg in request.messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}],
            })

        generation_config = {
            "max_output_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        # Make streaming API call
        if request.system:
            response_stream = model.generate_content(
                contents,
                generation_config=generation_config,
                system_instruction=request.system,
                stream=True,
            )
        else:
            response_stream = model.generate_content(
                contents,
                generation_config=generation_config,
                stream=True,
            )

        accumulated_content = ""
        final_response = None

        for chunk in response_stream:
            if hasattr(chunk, "text") and chunk.text:
                accumulated_content += chunk.text
                yield StreamChunk(content=chunk.text)
            final_response = chunk

        # Extract usage from final response
        usage = self.extract_usage(final_response) if final_response else \
            self._estimate_usage(accumulated_content)

        yield StreamChunk(
            content="",
            is_final=True,
            usage=usage,
        )

    def extract_usage(self, response: Any) -> TokenUsage:
        """Extract usage from Gemini response."""
        if hasattr(response, "usage_metadata") and response.usage_metadata is not None:
            metadata = response.usage_metadata
            return TokenUsage(
                input_tokens=getattr(metadata, "prompt_token_count", 0),
                output_tokens=getattr(metadata, "candidates_token_count", 0),
            )

        # Fallback to estimation
        logger.warning("No usage metadata in Gemini response, using estimation")
        content = response.text if hasattr(response, "text") else ""
        return self._estimate_usage(content)
