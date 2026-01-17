"""
V4.2 LLM Call Interceptor Module.

This module provides interception of LLM API calls with:
- Budget tracking (reserve/commit/rollback)
- Token estimation and counting
- Provider-specific adapters (Anthropic, OpenAI, Gemini)
- Budget-aware retry logic

Usage:
    from src.v4.interceptor import (
        LLMCallWrapper,
        LLMRequest,
        LLMResponse,
        AnthropicAdapter,
        OpenAIAdapter,
        GeminiAdapter,
    )

    # Create wrapper with budget tracking
    wrapper = LLMCallWrapper(
        budget_tracker=tracker,
        token_counter=counter,
        adapter=AnthropicAdapter(),
        budget_id="workflow_budget",
    )

    # Make LLM call (budget is tracked automatically)
    response = await wrapper.call(request)
"""

from .models import (
    LLMRequest,
    LLMResponse,
    StreamChunk,
    InterceptorConfig,
    InterceptorError,
    BudgetExhaustedError,
)

from .adapters import (
    LLMAdapter,
    AnthropicAdapter,
    OpenAIAdapter,
    GeminiAdapter,
)

from .retry import BudgetAwareRetry

from .wrapper import LLMCallWrapper

__all__ = [
    # Models
    "LLMRequest",
    "LLMResponse",
    "StreamChunk",
    "InterceptorConfig",
    "InterceptorError",
    "BudgetExhaustedError",
    # Adapters
    "LLMAdapter",
    "AnthropicAdapter",
    "OpenAIAdapter",
    "GeminiAdapter",
    # Retry
    "BudgetAwareRetry",
    # Wrapper
    "LLMCallWrapper",
]
