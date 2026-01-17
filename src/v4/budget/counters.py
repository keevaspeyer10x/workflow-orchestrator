"""
Provider-specific token counters for V4.2 Token Budget System.

Implements accurate token counting for different LLM providers:
- ClaudeTokenCounter: Uses Anthropic's count_tokens API
- OpenAITokenCounter: Uses tiktoken library
- EstimationTokenCounter: Fallback (~4 chars/token)
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class TokenCounter(ABC):
    """
    Abstract base class for provider-specific token counters.

    Token counting is provider-specific:
    - Claude uses a custom tokenizer (requires API call for accuracy)
    - OpenAI uses tiktoken (cl100k_base encoding)
    - Other providers may have different tokenizers

    All methods are async to support providers requiring network calls.
    """

    @abstractmethod
    async def count(self, text: str) -> int:
        """
        Count tokens in a text string.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        pass

    @abstractmethod
    async def count_messages(self, messages: List[Dict[str, Any]]) -> int:
        """
        Count tokens in a message array (includes overhead).

        Different providers have different message overhead:
        - OpenAI: ~3 tokens per message + 3 for reply priming
        - Claude: Varies by model

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            Total token count including overhead
        """
        pass

    def count_sync(self, text: str) -> int:
        """
        Synchronous wrapper for count().

        Uses asyncio.run() for convenience in sync contexts.
        """
        import asyncio
        return asyncio.run(self.count(text))

    def count_messages_sync(self, messages: List[Dict[str, Any]]) -> int:
        """
        Synchronous wrapper for count_messages().

        Uses asyncio.run() for convenience in sync contexts.
        """
        import asyncio
        return asyncio.run(self.count_messages(messages))


class EstimationTokenCounter(TokenCounter):
    """
    Fallback token counter using character-based estimation.

    Uses approximately 4 characters per token, which is a reasonable
    approximation for English text across most tokenizers.

    This counter is:
    - Fast (no API calls or library dependencies)
    - Deterministic
    - Used as fallback when provider-specific counting fails
    """

    CHARS_PER_TOKEN = 4
    MESSAGE_OVERHEAD = 4  # Estimated overhead per message

    async def count(self, text: str) -> int:
        """Count tokens using character estimation."""
        if not text:
            return 0
        return max(1, len(text) // self.CHARS_PER_TOKEN)

    async def count_messages(self, messages: List[Dict[str, Any]]) -> int:
        """Count tokens in messages with estimated overhead."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += await self.count(content)
            total += self.MESSAGE_OVERHEAD
        # Add reply priming overhead
        total += 3
        return total


class ClaudeTokenCounter(TokenCounter):
    """
    Token counter for Claude models using Anthropic API.

    Uses the beta.messages.count_tokens endpoint for accurate counting.
    Falls back to EstimationTokenCounter on API failure.

    Note: Requires ANTHROPIC_API_KEY environment variable or explicit api_key.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
        fallback: Optional[TokenCounter] = None,
    ):
        """
        Initialize Claude token counter.

        Args:
            api_key: Anthropic API key (uses env var if not provided)
            model: Model to use for token counting
            fallback: Fallback counter (defaults to EstimationTokenCounter)
        """
        self.model = model
        self._api_key = api_key
        self._fallback = fallback or EstimationTokenCounter()
        self._client = None

    def _get_client(self):
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError:
                logger.warning("anthropic package not installed, using fallback")
                return None
            except Exception as e:
                logger.warning(f"Failed to initialize Anthropic client: {e}")
                return None
        return self._client

    async def count(self, text: str) -> int:
        """
        Count tokens using Anthropic API.

        Falls back to estimation on API failure.
        """
        if not text:
            return 0

        client = self._get_client()
        if client is None:
            return await self._fallback.count(text)

        try:
            # Use the messages.count_tokens endpoint
            response = client.messages.count_tokens(
                model=self.model,
                messages=[{"role": "user", "content": text}]
            )
            return response.input_tokens
        except Exception as e:
            logger.warning(f"Claude token counting failed, using fallback: {e}")
            return await self._fallback.count(text)

    async def count_messages(self, messages: List[Dict[str, Any]]) -> int:
        """
        Count tokens in message array using Anthropic API.

        Falls back to estimation on API failure.
        """
        if not messages:
            return 0

        client = self._get_client()
        if client is None:
            return await self._fallback.count_messages(messages)

        try:
            response = client.messages.count_tokens(
                model=self.model,
                messages=messages
            )
            return response.input_tokens
        except Exception as e:
            logger.warning(f"Claude token counting failed, using fallback: {e}")
            return await self._fallback.count_messages(messages)


class OpenAITokenCounter(TokenCounter):
    """
    Token counter for OpenAI models using tiktoken.

    Uses cl100k_base encoding (GPT-4, GPT-3.5-turbo).
    Includes message overhead calculation per OpenAI's documentation.
    """

    # Per-message overhead for chat models
    TOKENS_PER_MESSAGE = 3
    # Reply priming tokens
    REPLY_PRIMING_TOKENS = 3

    def __init__(self, model: str = "gpt-4"):
        """
        Initialize OpenAI token counter.

        Args:
            model: Model name (used for encoding selection)
        """
        self.model = model
        self._encoder = None

    def _get_encoder(self):
        """Lazy initialization of tiktoken encoder."""
        if self._encoder is None:
            try:
                import tiktoken
                # Use cl100k_base for GPT-4 and GPT-3.5-turbo
                try:
                    self._encoder = tiktoken.encoding_for_model(self.model)
                except KeyError:
                    # Fall back to cl100k_base for unknown models
                    self._encoder = tiktoken.get_encoding("cl100k_base")
            except ImportError:
                logger.warning("tiktoken package not installed")
                return None
        return self._encoder

    async def count(self, text: str) -> int:
        """Count tokens using tiktoken."""
        if not text:
            return 0

        encoder = self._get_encoder()
        if encoder is None:
            # Fall back to estimation
            return max(1, len(text) // 4)

        return len(encoder.encode(text))

    async def count_messages(self, messages: List[Dict[str, Any]]) -> int:
        """
        Count tokens in messages including overhead.

        Per OpenAI documentation:
        - Each message adds ~3 tokens for role/structure
        - Reply priming adds ~3 tokens
        """
        if not messages:
            return 0

        encoder = self._get_encoder()
        if encoder is None:
            # Fall back to estimation
            fallback = EstimationTokenCounter()
            return await fallback.count_messages(messages)

        total = 0
        for msg in messages:
            total += self.TOKENS_PER_MESSAGE
            content = msg.get("content", "")
            if content:
                total += len(encoder.encode(content))
            # Name field adds 1 token if present
            if msg.get("name"):
                total += 1

        # Add reply priming
        total += self.REPLY_PRIMING_TOKENS
        return total


def get_token_counter(provider: str, **kwargs) -> TokenCounter:
    """
    Factory function to get appropriate token counter.

    Args:
        provider: Provider name ('anthropic', 'openai', 'estimation')
        **kwargs: Provider-specific arguments

    Returns:
        TokenCounter instance for the provider
    """
    counters = {
        "anthropic": ClaudeTokenCounter,
        "claude": ClaudeTokenCounter,
        "openai": OpenAITokenCounter,
        "gpt": OpenAITokenCounter,
        "estimation": EstimationTokenCounter,
        "fallback": EstimationTokenCounter,
    }

    counter_class = counters.get(provider.lower(), EstimationTokenCounter)
    return counter_class(**kwargs)
