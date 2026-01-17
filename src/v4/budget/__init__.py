"""
V4.2 Token Budget System.

This module provides token budget tracking and enforcement:
- Provider-specific token counting (Claude, OpenAI, estimation)
- Atomic budget operations (reserve/commit/rollback)
- Event sourcing integration

Usage:
    from src.v4.budget import (
        AtomicBudgetTracker,
        ClaudeTokenCounter,
        OpenAITokenCounter,
        get_token_counter,
    )

    # Create budget tracker
    tracker = AtomicBudgetTracker(db_path=":memory:")
    await tracker.create_budget("workflow_1", limit=100000)

    # Reserve tokens before LLM call
    result = await tracker.reserve("workflow_1", tokens=5000)
    if result.success:
        # Make LLM call...
        # Commit with actual usage
        await tracker.commit(result.reservation_id, actual_tokens=4500)
    else:
        print(f"Budget exceeded: {result.reason}")
"""

from .models import (
    TokenBudget,
    BudgetStatus,
    BudgetDecision,
    BudgetEventType,
    Reservation,
    ReservationResult,
    TokenUsage,
)

from .events import (
    BudgetEvent,
    create_budget_event,
    budget_created_event,
    tokens_reserved_event,
    tokens_committed_event,
    tokens_released_event,
    budget_exhausted_event,
)

from .counters import (
    TokenCounter,
    ClaudeTokenCounter,
    OpenAITokenCounter,
    EstimationTokenCounter,
    get_token_counter,
)

from .manager import AtomicBudgetTracker

__all__ = [
    # Models
    "TokenBudget",
    "BudgetStatus",
    "BudgetDecision",
    "BudgetEventType",
    "Reservation",
    "ReservationResult",
    "TokenUsage",
    # Events
    "BudgetEvent",
    "create_budget_event",
    "budget_created_event",
    "tokens_reserved_event",
    "tokens_committed_event",
    "tokens_released_event",
    "budget_exhausted_event",
    # Counters
    "TokenCounter",
    "ClaudeTokenCounter",
    "OpenAITokenCounter",
    "EstimationTokenCounter",
    "get_token_counter",
    # Manager
    "AtomicBudgetTracker",
]
