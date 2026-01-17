"""
Data models for V4.2 LLM Call Interceptor.

Defines standardized request/response types and configuration.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..budget.models import TokenUsage


class InterceptorError(Exception):
    """Base exception for interceptor errors."""
    pass


class BudgetExhaustedError(InterceptorError):
    """Raised when budget is exhausted and call cannot proceed."""

    def __init__(
        self,
        budget_id: str,
        requested: int,
        available: int,
        message: Optional[str] = None,
    ):
        self.budget_id = budget_id
        self.requested = requested
        self.available = available
        self.message = message or (
            f"Budget exhausted: requested {requested} tokens, "
            f"only {available} available in budget '{budget_id}'"
        )
        super().__init__(self.message)


@dataclass
class LLMRequest:
    """
    Standardized LLM request format.

    Works across providers (Anthropic, OpenAI, Gemini).
    Provider-specific adapters translate this to native API formats.

    Attributes:
        messages: Conversation messages in OpenAI format
        model: Model identifier (e.g., "claude-sonnet-4-20250514")
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature (0.0-2.0)
        metadata: Additional metadata (workflow_id, phase_id, etc.)
        system: Optional system prompt (added as first message for some providers)
    """
    messages: List[Dict[str, Any]]
    model: str
    max_tokens: int = 4096
    temperature: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    system: Optional[str] = None

    def estimate_input_tokens(self, chars_per_token: int = 4) -> int:
        """
        Estimate input tokens based on message content.

        This is a rough estimation - use TokenCounter for accuracy.
        """
        total_chars = 0
        for msg in self.messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                # Handle multimodal content
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total_chars += len(part["text"])
        if self.system:
            total_chars += len(self.system)
        return max(1, total_chars // chars_per_token)


@dataclass
class LLMResponse:
    """
    Standardized LLM response format.

    Attributes:
        content: Text content of the response
        usage: Token usage (input and output)
        model: Model that generated the response
        finish_reason: Why generation stopped
        raw_response: Original provider response (for debugging)
    """
    content: str
    usage: TokenUsage
    model: str
    finish_reason: str
    raw_response: Any = None


@dataclass
class StreamChunk:
    """
    A chunk of a streaming response.

    Attributes:
        content: Text content of this chunk
        is_final: True if this is the last chunk
        usage: Token usage (only present on final chunk)
    """
    content: str
    is_final: bool = False
    usage: Optional[TokenUsage] = None


@dataclass
class InterceptorConfig:
    """
    Configuration for the LLM call interceptor.

    Attributes:
        max_retries: Maximum retry attempts on transient failure
        retry_delay_base: Base delay for exponential backoff (seconds)
        retry_delay_max: Maximum delay between retries (seconds)
        budget_buffer_percent: Extra buffer when estimating tokens (0.1 = 10%)
        timeout: Request timeout in seconds
    """
    max_retries: int = 3
    retry_delay_base: float = 1.0
    retry_delay_max: float = 30.0
    budget_buffer_percent: float = 0.1
    timeout: int = 300

    def estimate_with_buffer(self, tokens: int) -> int:
        """Apply buffer to token estimate."""
        return int(tokens * (1 + self.budget_buffer_percent))
