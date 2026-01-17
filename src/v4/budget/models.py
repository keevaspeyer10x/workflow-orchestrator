"""
Budget data models for V4.2 Token Budget System.

Defines core dataclasses and enums for budget tracking:
- TokenBudget: Budget with soft/hard limits
- BudgetStatus: Current budget state
- ReservationResult: Result of reserve operation
- BudgetDecision: Pre-flight check decision
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import uuid


class BudgetDecision(Enum):
    """Decision from pre-flight budget check."""
    OK = "ok"
    WARNING = "warning"
    BLOCKED = "blocked"
    EMERGENCY_STOP = "emergency_stop"


class BudgetEventType(str, Enum):
    """Types of budget events for event sourcing."""
    BUDGET_CREATED = "budget_created"
    TOKENS_RESERVED = "tokens_reserved"
    TOKENS_COMMITTED = "tokens_committed"
    TOKENS_RELEASED = "tokens_released"
    BUDGET_EXHAUSTED = "budget_exhausted"
    BUDGET_UPDATED = "budget_updated"


@dataclass
class TokenBudget:
    """
    Token budget with soft/hard limits.

    Attributes:
        id: Unique budget identifier
        limit: Maximum tokens allowed
        used: Tokens already consumed
        reserved: Tokens reserved but not yet committed
        soft_threshold: Warning threshold (default 80%)
        hard_threshold: Block threshold (default 100%)
        emergency_threshold: Emergency stop threshold (default 120%)
    """
    id: str
    limit: int
    used: int = 0
    reserved: int = 0
    soft_threshold: float = 0.8
    hard_threshold: float = 1.0
    emergency_threshold: float = 1.2
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def available(self) -> int:
        """Tokens available for reservation."""
        return max(0, self.limit - self.used - self.reserved)

    @property
    def remaining(self) -> int:
        """Tokens remaining (not counting reserved)."""
        return max(0, self.limit - self.used)

    @property
    def percent_used(self) -> float:
        """Percentage of budget used."""
        return (self.used / self.limit) * 100 if self.limit > 0 else 0

    def check(self, requested: int = 0) -> BudgetDecision:
        """
        Check if requested tokens can be allocated.

        Args:
            requested: Number of tokens requested

        Returns:
            BudgetDecision indicating whether to proceed
        """
        projected = self.used + self.reserved + requested
        ratio = projected / self.limit if self.limit > 0 else float('inf')

        if ratio >= self.emergency_threshold:
            return BudgetDecision.EMERGENCY_STOP
        elif ratio >= self.hard_threshold:
            return BudgetDecision.BLOCKED
        elif ratio >= self.soft_threshold:
            return BudgetDecision.WARNING
        return BudgetDecision.OK


@dataclass
class BudgetStatus:
    """Current state of a budget."""
    budget_id: str
    limit: int
    used: int
    reserved: int
    available: int
    percent_used: float
    decision: BudgetDecision
    exceeded: bool
    warning: bool


@dataclass
class Reservation:
    """Token reservation record."""
    id: str
    budget_id: str
    tokens: int
    created_at: datetime
    expires_at: datetime

    @classmethod
    def create(
        cls,
        budget_id: str,
        tokens: int,
        timeout_minutes: int = 5,
    ) -> "Reservation":
        """Create a new reservation."""
        now = datetime.now()
        return cls(
            id=f"res_{uuid.uuid4().hex[:12]}",
            budget_id=budget_id,
            tokens=tokens,
            created_at=now,
            expires_at=now + timedelta(minutes=timeout_minutes),
        )

    @property
    def is_expired(self) -> bool:
        """Check if reservation has expired."""
        return datetime.now() > self.expires_at


@dataclass
class ReservationResult:
    """Result of a reserve operation."""
    success: bool
    reservation_id: Optional[str] = None
    reason: Optional[str] = None
    budget_status: Optional[BudgetStatus] = None


@dataclass
class TokenUsage:
    """Token usage record for a single operation."""
    input_tokens: int
    output_tokens: int

    @property
    def total(self) -> int:
        """Total tokens used."""
        return self.input_tokens + self.output_tokens
