"""
Event Bus

Simple pub/sub event bus for agent coordination.
"""

from typing import Callable, Dict, List, Any, Optional
from datetime import datetime, timezone
import threading


class EventBus:
    """
    Simple event bus for publishing and subscribing to events

    Thread-safe pub/sub pattern for agent coordination.
    """

    def __init__(self):
        """Initialize event bus"""
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()
        self._event_history: List[Dict[str, Any]] = []

    def subscribe(self, event_type: str, handler: Callable):
        """
        Subscribe to event type

        Args:
            event_type: Event type to subscribe to
            handler: Callback function
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)

    def publish(self, event_type: str, data: Dict[str, Any]):
        """
        Publish event

        Args:
            event_type: Event type
            data: Event data
        """
        event = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        with self._lock:
            # Store in history
            self._event_history.append(event)

            # Notify subscribers
            handlers = self._subscribers.get(event_type, [])

        # Call handlers outside lock to avoid deadlock
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                # Log error but continue
                print(f"Error in event handler: {e}")

    def get_history(self, event_type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get event history

        Args:
            event_type: Filter by event type (None for all)
            limit: Maximum number of events

        Returns:
            List of events (most recent first)
        """
        with self._lock:
            if event_type:
                filtered = [e for e in self._event_history if e["type"] == event_type]
            else:
                filtered = self._event_history

            return list(reversed(filtered[-limit:]))

    def clear_history(self):
        """Clear event history"""
        with self._lock:
            self._event_history.clear()


# Global event bus instance
event_bus = EventBus()


# Standard event types
class EventTypes:
    TASK_CLAIMED = "task.claimed"
    TASK_TRANSITIONED = "task.transitioned"
    TASK_COMPLETED = "task.completed"
    TOOL_EXECUTED = "tool.executed"
    GATE_BLOCKED = "gate.blocked"
    GATE_PASSED = "gate.passed"
