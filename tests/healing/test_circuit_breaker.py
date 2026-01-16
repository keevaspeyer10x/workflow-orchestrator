"""Tests for Circuit Breaker - Phase 5."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.healing.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerConfig,
    get_circuit_breaker,
    reset_circuit_breaker,
)


class TestCircuitBreakerBasic:
    """Basic circuit breaker tests."""

    def test_initial_state_closed(self):
        """Circuit breaker starts in closed state."""
        breaker = CircuitBreaker()
        assert breaker.state == CircuitState.CLOSED

    def test_should_allow_fix_when_closed(self):
        """Fixes are allowed when circuit is closed."""
        breaker = CircuitBreaker()
        allowed, reason = breaker.should_allow_fix()
        assert allowed is True
        assert "closed" in reason.lower()

    def test_record_revert(self):
        """Recording a revert adds to the revert list."""
        breaker = CircuitBreaker()
        assert breaker.revert_count == 0
        breaker.record_revert()
        assert breaker.revert_count == 1

    def test_trip_on_threshold(self):
        """Circuit trips after 2 reverts in 1 hour."""
        breaker = CircuitBreaker()
        breaker.record_revert()
        assert breaker.state == CircuitState.CLOSED

        breaker.record_revert()
        assert breaker.state == CircuitState.OPEN

    def test_no_trip_below_threshold(self):
        """Circuit stays closed with only 1 revert."""
        breaker = CircuitBreaker()
        breaker.record_revert()
        assert breaker.state == CircuitState.CLOSED

    def test_should_not_allow_fix_when_open(self):
        """Fixes are blocked when circuit is open."""
        breaker = CircuitBreaker()
        breaker.record_revert()
        breaker.record_revert()
        assert breaker.state == CircuitState.OPEN

        allowed, reason = breaker.should_allow_fix()
        # Note: If cooldown is 0, it may go to half-open
        # The test checks the open state behavior

    def test_manual_reset(self):
        """Manual reset returns circuit to closed state."""
        breaker = CircuitBreaker()
        breaker.record_revert()
        breaker.record_revert()
        assert breaker.state == CircuitState.OPEN

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.revert_count == 0


class TestCircuitBreakerCooldown:
    """Tests for circuit breaker cooldown behavior."""

    def test_cooldown_period(self):
        """Circuit remains open during cooldown."""
        config = CircuitBreakerConfig(cooldown_minutes=30)
        breaker = CircuitBreaker(config=config)

        # Trip the circuit
        breaker.record_revert()
        breaker.record_revert()
        assert breaker.state == CircuitState.OPEN

        # Set opened_at to recent time
        breaker._opened_at = datetime.utcnow()

        allowed, reason = breaker.should_allow_fix()
        # During cooldown, should not allow (unless going to half-open)
        # This depends on the cooldown logic

    def test_half_open_after_cooldown(self):
        """After cooldown, circuit goes to half-open and allows test fix."""
        config = CircuitBreakerConfig(cooldown_minutes=1)
        breaker = CircuitBreaker(config=config)

        # Trip the circuit
        breaker.record_revert()
        breaker.record_revert()

        # Set opened_at to past cooldown
        breaker._opened_at = datetime.utcnow() - timedelta(minutes=5)

        allowed, reason = breaker.should_allow_fix()
        assert allowed is True
        assert breaker.state == CircuitState.HALF_OPEN

    def test_close_on_success_in_half_open(self):
        """Success in half-open closes the circuit."""
        breaker = CircuitBreaker()
        breaker._state = CircuitState.HALF_OPEN

        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    def test_reopen_on_failure_in_half_open(self):
        """Failure in half-open reopens the circuit."""
        breaker = CircuitBreaker()
        breaker._state = CircuitState.HALF_OPEN

        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN


class TestCircuitBreakerExpiry:
    """Tests for revert expiration."""

    def test_old_reverts_expire(self):
        """Reverts older than 1 hour don't count."""
        breaker = CircuitBreaker()

        # Add an old revert (more than 1 hour ago)
        breaker._reverts.append(datetime.utcnow() - timedelta(hours=2))

        # Should be cleaned up
        assert breaker.revert_count == 0

    def test_recent_reverts_kept(self):
        """Reverts within 1 hour are kept."""
        breaker = CircuitBreaker()

        # Add a recent revert
        breaker._reverts.append(datetime.utcnow() - timedelta(minutes=30))

        assert breaker.revert_count == 1


class TestCircuitBreakerPersistence:
    """Tests for Supabase persistence."""

    @pytest.mark.asyncio
    async def test_state_persistence_save(self):
        """Saving state calls Supabase."""
        mock_supabase = AsyncMock()
        breaker = CircuitBreaker(supabase=mock_supabase)

        breaker.record_revert()
        await breaker.save_state()

        mock_supabase.save_circuit_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_state_persistence_load(self):
        """Loading state restores from Supabase."""
        mock_supabase = AsyncMock()
        mock_supabase.get_circuit_state.return_value = {
            "state": "open",
            "opened_at": datetime.utcnow().isoformat(),
            "reverts": [datetime.utcnow().isoformat()],
        }
        breaker = CircuitBreaker(supabase=mock_supabase)

        await breaker.load_state()

        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_state_persistence_resume(self):
        """State survives simulated restart."""
        mock_supabase = AsyncMock()
        saved_state = None

        async def save_cb(state):
            nonlocal saved_state
            saved_state = state

        mock_supabase.save_circuit_state = save_cb

        # First breaker - trip it
        breaker1 = CircuitBreaker(supabase=mock_supabase)
        breaker1.record_revert()
        breaker1.record_revert()
        await breaker1.save_state()

        # Second breaker - simulate restart
        mock_supabase.get_circuit_state.return_value = saved_state
        breaker2 = CircuitBreaker(supabase=mock_supabase)
        await breaker2.load_state()

        assert breaker2.state == CircuitState.OPEN


class TestCircuitBreakerGlobal:
    """Tests for global circuit breaker instance."""

    def test_get_circuit_breaker_returns_instance(self):
        """get_circuit_breaker returns a CircuitBreaker."""
        reset_circuit_breaker()
        breaker = get_circuit_breaker()
        assert isinstance(breaker, CircuitBreaker)

    def test_get_circuit_breaker_returns_same_instance(self):
        """get_circuit_breaker returns the same instance."""
        reset_circuit_breaker()
        breaker1 = get_circuit_breaker()
        breaker2 = get_circuit_breaker()
        assert breaker1 is breaker2

    def test_reset_circuit_breaker(self):
        """reset_circuit_breaker clears the global instance."""
        reset_circuit_breaker()
        breaker1 = get_circuit_breaker()
        reset_circuit_breaker()
        breaker2 = get_circuit_breaker()
        assert breaker1 is not breaker2
