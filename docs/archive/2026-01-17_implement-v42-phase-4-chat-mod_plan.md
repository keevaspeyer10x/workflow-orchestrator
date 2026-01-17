# V4.2 Phase 3: LLM Call Interceptor - Implementation Plan

**Issue:** #102
**Phase:** 3 - LLM Call Interceptor
**Status:** Planning

## Overview

Create an interceptor module that wraps all LLM API calls with budget tracking, token estimation/counting, and automatic retry handling.

## Decisions from Clarifying Questions

1. **Streaming:** Yes, support streaming responses (keep implementation focused)
2. **Retry Budget:** Same reservation for retries (prevents budget exhaustion)
3. **Error Handling:** Rollback on any error (conservative approach)
4. **Providers:** Anthropic and OpenAI only (extensible interface for future)

## Directory Structure

```
src/v4/interceptor/
├── __init__.py         # Public exports
├── wrapper.py          # LLMCallWrapper class
├── adapters.py         # Provider adapters (Anthropic, OpenAI)
├── models.py           # Data models (LLMRequest, LLMResponse)
└── retry.py            # Retry logic with budget awareness
```

## Components

### 1. LLMCallWrapper (`wrapper.py`)

Core interceptor that:
- Intercepts all LLM calls (sync and async)
- Pre-call: estimates tokens using TokenCounter, reserves budget
- Post-call: extracts actual usage from response, commits to budget
- On failure: rolls back reservation
- Supports both streaming and non-streaming responses

```python
class LLMCallWrapper:
    def __init__(
        self,
        budget_tracker: AtomicBudgetTracker,
        token_counter: TokenCounter,
        adapter: LLMAdapter,
        budget_id: str,
        config: InterceptorConfig = None,
    ): ...

    async def call(self, request: LLMRequest) -> LLMResponse: ...
    async def call_streaming(self, request: LLMRequest) -> AsyncIterator[StreamChunk]: ...
```

### 2. Provider Adapters (`adapters.py`)

Abstract base and concrete implementations:

```python
class LLMAdapter(ABC):
    @abstractmethod
    async def call(self, request: LLMRequest) -> LLMResponse: ...

    @abstractmethod
    async def call_streaming(self, request: LLMRequest) -> AsyncIterator[StreamChunk]: ...

    @abstractmethod
    def extract_usage(self, response: Any) -> TokenUsage: ...

class AnthropicAdapter(LLMAdapter):
    # Uses anthropic.Anthropic client
    # Extracts usage from response.usage

class OpenAIAdapter(LLMAdapter):
    # Uses openai.OpenAI client
    # Extracts usage from response.usage
```

### 3. Models (`models.py`)

Standardized data types:

```python
@dataclass
class LLMRequest:
    messages: List[Dict[str, Any]]
    model: str
    max_tokens: int = 4096
    temperature: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class LLMResponse:
    content: str
    usage: TokenUsage
    model: str
    finish_reason: str
    raw_response: Any = None

@dataclass
class StreamChunk:
    content: str
    is_final: bool = False
    usage: Optional[TokenUsage] = None

@dataclass
class InterceptorConfig:
    max_retries: int = 3
    retry_delay_base: float = 1.0
    retry_delay_max: float = 30.0
    budget_buffer_percent: float = 0.1  # Reserve 10% extra for safety
```

### 4. Retry Logic (`retry.py`)

Budget-aware retry handling:

```python
class BudgetAwareRetry:
    def __init__(
        self,
        max_retries: int = 3,
        delay_base: float = 1.0,
        delay_max: float = 30.0,
    ): ...

    async def execute(
        self,
        operation: Callable[[], Awaitable[T]],
        reservation_id: str,
        budget_tracker: AtomicBudgetTracker,
    ) -> T: ...
```

## Integration Points

From Phase 2 Budget Module:
- `AtomicBudgetTracker.reserve()` - Reserve tokens before LLM call
- `AtomicBudgetTracker.commit()` - Commit actual usage after success
- `AtomicBudgetTracker.rollback()` - Release reservation on failure
- `TokenCounter` classes - Estimate tokens before call

## Execution Approach

**Sequential execution** because:
- Components are tightly coupled (wrapper → adapters → models)
- Each file depends on previous ones
- Single developer flow is more efficient than parallel for this scope
- Total scope is 4 files + tests - not large enough to benefit from parallelism

**Parallel assessment:**
- Could potentially parallelize adapters.py and retry.py (both depend only on models.py)
- But overhead of coordination exceeds benefit for this small scope
- Sequential is more predictable and easier to debug

**Decision:** Will use **sequential** execution because the tight coupling and small scope make parallel execution unnecessary. The dependency chain (models → adapters/retry → wrapper → tests) naturally flows sequentially.

## Test Cases

1. **Wrapper Tests:**
   - Successful call with budget tracking
   - Budget exhaustion blocks call
   - Rollback on API error
   - Retry with same reservation

2. **Adapter Tests:**
   - Token extraction from Anthropic response
   - Token extraction from OpenAI response
   - Streaming response handling

3. **Integration Tests:**
   - End-to-end flow with mocked LLM
   - Budget depletion over multiple calls

## Acceptance Criteria

- [ ] All LLM calls go through the interceptor
- [ ] Budget is checked before each call
- [ ] Actual usage committed after successful calls
- [ ] Failed calls trigger budget rollback
- [ ] Works with existing budget module from Phase 2
- [ ] Tests pass with mocked LLM responses
