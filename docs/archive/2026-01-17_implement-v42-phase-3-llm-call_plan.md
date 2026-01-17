# V4.2 Phase 2: Token Budget System Implementation Plan

## Overview

Implement token budget tracking and enforcement for the V4 Control Inversion architecture.

## Design Decisions (User Approved)

1. **Budget Hierarchy**: Start with workflow > phase levels (minimal)
2. **Token Counter**: Async interface with sync wrapper
3. **Event Storage**: Budget events in shared event store
4. **Fallback**: Fail-open with estimation + warning log

## Module Structure

```
src/v4/budget/
├── __init__.py     # Module exports
├── counters.py     # TokenCounter ABC + implementations
├── manager.py      # AtomicBudgetTracker
├── models.py       # Budget dataclasses and enums
└── events.py       # Budget event types
```

## Components

### 1. TokenCounter (Abstract Base Class)

```python
class TokenCounter(ABC):
    @abstractmethod
    async def count(self, text: str) -> int: ...
    
    @abstractmethod
    async def count_messages(self, messages: list[dict]) -> int: ...
```

### 2. ClaudeTokenCounter

- Uses `anthropic.beta.messages.count_tokens` API
- Async implementation (network call required)
- Falls back to EstimationTokenCounter on API failure
- Logs warning when falling back

### 3. OpenAITokenCounter

- Uses tiktoken with `cl100k_base` encoding
- Includes message overhead (3 tokens per message + 3 reply priming)
- Sync implementation (no network call)

### 4. EstimationTokenCounter

- Approximately 4 characters per token
- Used as universal fallback
- Fast, no dependencies

### 5. AtomicBudgetTracker

```python
class AtomicBudgetTracker:
    async def reserve(budget_id: str, tokens: int) -> ReservationResult
    async def commit(reservation_id: str, actual_tokens: int) -> None
    async def rollback(reservation_id: str) -> None
    async def get_status(budget_id: str) -> BudgetStatus
```

- Thread-safe with SQLite BEGIN IMMEDIATE locking
- Reservation timeout (default 5 minutes)
- Integrates with AsyncEventStore for event sourcing

### 6. Budget Event Types

- `BUDGET_CREATED` - New budget initialized
- `TOKENS_RESERVED` - Tokens reserved for operation
- `TOKENS_COMMITTED` - Reservation committed with actual usage
- `TOKENS_RELEASED` - Reservation rolled back
- `BUDGET_EXHAUSTED` - Budget limit reached

## Execution Plan

**Sequential execution** - Components have dependencies:
1. models.py (no deps)
2. events.py (depends on models)
3. counters.py (depends on models)
4. manager.py (depends on all above + async_storage)
5. __init__.py (exports)
6. tests (depends on all)

## Acceptance Criteria

- [ ] Token counting accurate within 5% for each provider
- [ ] Concurrent budget updates don't cause overdraft
- [ ] Reservation timeout releases held tokens
- [ ] Budget events recorded in event store
- [ ] Tests for concurrency and provider-specific counting
