"""
Budget event definitions for event sourcing.

These events are stored in the shared event store and provide
a complete audit trail of all budget operations.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
import uuid

from .models import BudgetEventType


def create_budget_event(
    stream_id: str,
    event_type: BudgetEventType,
    version: int,
    data: Dict[str, Any],
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
) -> "BudgetEvent":
    """
    Create a budget event for the event store.

    Args:
        stream_id: Budget ID (stream identifier)
        event_type: Type of budget event
        version: Event version in stream
        data: Event payload data
        correlation_id: Correlation ID for tracing
        causation_id: ID of event that caused this one

    Returns:
        BudgetEvent ready for storage
    """
    return BudgetEvent(
        id=f"evt_{uuid.uuid4().hex[:12]}",
        stream_id=stream_id,
        type=event_type.value,
        version=version,
        timestamp=datetime.now(),
        correlation_id=correlation_id or f"corr_{uuid.uuid4().hex[:8]}",
        causation_id=causation_id,
        data=data,
        metadata={"event_category": "budget"},
    )


@dataclass
class BudgetEvent:
    """
    Budget event for event sourcing.

    Compatible with the Event dataclass from storage module.
    """
    id: str
    stream_id: str
    type: str
    version: int
    timestamp: datetime
    correlation_id: str
    causation_id: Optional[str]
    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    global_position: Optional[int] = None

    def to_storage_event(self):
        """Convert to storage Event format."""
        from ..security.storage import Event
        return Event(
            id=self.id,
            stream_id=self.stream_id,
            type=self.type,
            version=self.version,
            timestamp=self.timestamp,
            correlation_id=self.correlation_id,
            causation_id=self.causation_id,
            data=self.data,
            metadata=self.metadata,
        )


def budget_created_event(
    budget_id: str,
    limit: int,
    workflow_id: Optional[str] = None,
    phase_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> BudgetEvent:
    """Create a BUDGET_CREATED event."""
    return create_budget_event(
        stream_id=f"budget:{budget_id}",
        event_type=BudgetEventType.BUDGET_CREATED,
        version=1,
        data={
            "budget_id": budget_id,
            "limit": limit,
            "workflow_id": workflow_id,
            "phase_id": phase_id,
        },
        correlation_id=correlation_id,
    )


def tokens_reserved_event(
    budget_id: str,
    reservation_id: str,
    tokens: int,
    version: int,
    expires_at: datetime,
    correlation_id: Optional[str] = None,
) -> BudgetEvent:
    """Create a TOKENS_RESERVED event."""
    return create_budget_event(
        stream_id=f"budget:{budget_id}",
        event_type=BudgetEventType.TOKENS_RESERVED,
        version=version,
        data={
            "reservation_id": reservation_id,
            "tokens": tokens,
            "expires_at": expires_at.isoformat(),
        },
        correlation_id=correlation_id,
    )


def tokens_committed_event(
    budget_id: str,
    reservation_id: str,
    reserved_tokens: int,
    actual_tokens: int,
    version: int,
    correlation_id: Optional[str] = None,
) -> BudgetEvent:
    """Create a TOKENS_COMMITTED event."""
    return create_budget_event(
        stream_id=f"budget:{budget_id}",
        event_type=BudgetEventType.TOKENS_COMMITTED,
        version=version,
        data={
            "reservation_id": reservation_id,
            "reserved_tokens": reserved_tokens,
            "actual_tokens": actual_tokens,
        },
        correlation_id=correlation_id,
    )


def tokens_released_event(
    budget_id: str,
    reservation_id: str,
    tokens: int,
    version: int,
    reason: str = "rollback",
    correlation_id: Optional[str] = None,
) -> BudgetEvent:
    """Create a TOKENS_RELEASED event."""
    return create_budget_event(
        stream_id=f"budget:{budget_id}",
        event_type=BudgetEventType.TOKENS_RELEASED,
        version=version,
        data={
            "reservation_id": reservation_id,
            "tokens": tokens,
            "reason": reason,
        },
        correlation_id=correlation_id,
    )


def budget_exhausted_event(
    budget_id: str,
    limit: int,
    used: int,
    version: int,
    correlation_id: Optional[str] = None,
) -> BudgetEvent:
    """Create a BUDGET_EXHAUSTED event."""
    return create_budget_event(
        stream_id=f"budget:{budget_id}",
        event_type=BudgetEventType.BUDGET_EXHAUSTED,
        version=version,
        data={
            "limit": limit,
            "used": used,
            "percent_used": (used / limit * 100) if limit > 0 else 0,
        },
        correlation_id=correlation_id,
    )
