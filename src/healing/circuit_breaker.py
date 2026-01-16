"""Circuit Breaker - Phase 5 Observability & Hardening.

Prevents runaway auto-fixing by tracking reverts and pausing auto-healing
when too many fixes fail.

State transitions:
    CLOSED -> (2+ reverts/hour) -> OPEN
    OPEN -> (30 min cooldown) -> HALF_OPEN
    HALF_OPEN -> (success) -> CLOSED
    HALF_OPEN -> (failure) -> OPEN
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .supabase_client import HealingSupabaseClient


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation - fixes allowed
    OPEN = "open"          # Tripped - fixes blocked
    HALF_OPEN = "half_open"  # Testing - one fix allowed


@dataclass
class CircuitBreakerConfig:
    """Configuration for the circuit breaker."""
    max_reverts_per_hour: int = 2
    cooldown_minutes: int = 30


@dataclass
class CircuitBreaker:
    """Circuit breaker to prevent runaway auto-fixing.

    Persists state to Supabase for cross-session recovery.

    Usage:
        breaker = CircuitBreaker(supabase_client)
        await breaker.load_state()

        allowed, reason = breaker.should_allow_fix()
        if not allowed:
            print(f"Fix blocked: {reason}")
            return

        # Apply fix...

        if fix_failed:
            breaker.record_revert()
            await breaker.save_state()
    """

    supabase: Optional["HealingSupabaseClient"] = None
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)

    # State
    _state: CircuitState = field(default=CircuitState.CLOSED)
    _reverts: list[datetime] = field(default_factory=list)
    _opened_at: Optional[datetime] = field(default=None)
    _last_test_at: Optional[datetime] = field(default=None)

    def should_allow_fix(self) -> tuple[bool, str]:
        """Check if fixes are allowed.

        Returns:
            Tuple of (allowed, reason)
        """
        self._cleanup_old_reverts()

        if self._state == CircuitState.CLOSED:
            return True, "Circuit closed - normal operation"

        if self._state == CircuitState.OPEN:
            if self._should_try_half_open():
                self._state = CircuitState.HALF_OPEN
                self._last_test_at = datetime.utcnow()
                return True, "Circuit half-open - allowing test fix"

            cooldown_remaining = self._get_cooldown_remaining()
            return False, f"Circuit open - cooling down ({cooldown_remaining}s remaining)"

        if self._state == CircuitState.HALF_OPEN:
            # In half-open, allow one test fix
            if self._last_test_at and (datetime.utcnow() - self._last_test_at) < timedelta(minutes=5):
                return False, "Circuit half-open - test fix in progress"
            self._last_test_at = datetime.utcnow()
            return True, "Circuit half-open - allowing test fix"

        return False, "Unknown circuit state"

    def record_revert(self) -> None:
        """Record that a fix was reverted."""
        self._reverts.append(datetime.utcnow())
        self._check_threshold()

    def record_success(self) -> None:
        """Record that a fix succeeded (for half-open state)."""
        if self._state == CircuitState.HALF_OPEN:
            # Success in half-open closes the circuit
            self._state = CircuitState.CLOSED
            self._opened_at = None
            self._last_test_at = None

    def record_failure(self) -> None:
        """Record that a fix failed (for half-open state)."""
        if self._state == CircuitState.HALF_OPEN:
            # Failure in half-open reopens the circuit
            self._state = CircuitState.OPEN
            self._opened_at = datetime.utcnow()
            self._last_test_at = None

    def reset(self) -> None:
        """Manually reset the circuit to closed state."""
        self._state = CircuitState.CLOSED
        self._reverts.clear()
        self._opened_at = None
        self._last_test_at = None

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def revert_count(self) -> int:
        """Get count of recent reverts."""
        self._cleanup_old_reverts()
        return len(self._reverts)

    def _check_threshold(self) -> None:
        """Trip circuit if too many reverts."""
        self._cleanup_old_reverts()

        if len(self._reverts) >= self.config.max_reverts_per_hour:
            if self._state != CircuitState.OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = datetime.utcnow()

    def _cleanup_old_reverts(self) -> None:
        """Remove reverts older than 1 hour."""
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        self._reverts = [r for r in self._reverts if r > one_hour_ago]

    def _should_try_half_open(self) -> bool:
        """Check if we should try a test fix."""
        if not self._opened_at:
            return True
        cooldown_end = self._opened_at + timedelta(minutes=self.config.cooldown_minutes)
        return datetime.utcnow() >= cooldown_end

    def _get_cooldown_remaining(self) -> int:
        """Get seconds remaining in cooldown."""
        if not self._opened_at:
            return 0
        cooldown_end = self._opened_at + timedelta(minutes=self.config.cooldown_minutes)
        remaining = (cooldown_end - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))

    async def load_state(self) -> None:
        """Load state from Supabase."""
        if not self.supabase:
            return

        try:
            state_data = await self.supabase.get_circuit_state()
            if state_data:
                self._state = CircuitState(state_data.get("state", "closed"))
                self._opened_at = state_data.get("opened_at")
                if isinstance(self._opened_at, str):
                    self._opened_at = datetime.fromisoformat(self._opened_at.replace("Z", "+00:00")).replace(tzinfo=None)

                reverts = state_data.get("reverts", [])
                self._reverts = [
                    datetime.fromisoformat(r.replace("Z", "+00:00")).replace(tzinfo=None)
                    if isinstance(r, str) else r
                    for r in reverts
                ]
        except Exception:
            # If load fails, start fresh
            pass

    async def save_state(self) -> None:
        """Save state to Supabase."""
        if not self.supabase:
            return

        try:
            state_data = {
                "state": self._state.value,
                "opened_at": self._opened_at.isoformat() if self._opened_at else None,
                "reverts": [r.isoformat() for r in self._reverts],
            }
            await self.supabase.save_circuit_state(state_data)
        except Exception:
            # Log but don't fail
            pass


# Global circuit breaker instance
_circuit_breaker: Optional[CircuitBreaker] = None


def get_circuit_breaker() -> CircuitBreaker:
    """Get the global circuit breaker instance."""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker()
    return _circuit_breaker


def reset_circuit_breaker() -> None:
    """Reset the global circuit breaker (for testing)."""
    global _circuit_breaker
    _circuit_breaker = None
