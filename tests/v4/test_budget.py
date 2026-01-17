"""
Tests for V4.2 Phase 2: Token Budget System.

Tests cover:
- TokenCounter implementations (Claude, OpenAI, Estimation)
- AtomicBudgetTracker operations (reserve, commit, rollback)
- Concurrent budget operations
- Event sourcing integration
- Reservation timeout handling
"""
import asyncio
import os
import pytest
import tempfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.v4.budget import (
    TokenBudget,
    BudgetStatus,
    BudgetDecision,
    BudgetEventType,
    Reservation,
    ReservationResult,
    TokenUsage,
    TokenCounter,
    ClaudeTokenCounter,
    OpenAITokenCounter,
    EstimationTokenCounter,
    get_token_counter,
    AtomicBudgetTracker,
)


# ============================================================
# Test Fixtures
# ============================================================


@pytest.fixture
def temp_db_path():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def in_memory_db():
    """Use in-memory database for fast tests."""
    return ":memory:"


# ============================================================
# TokenBudget Model Tests
# ============================================================


class TestTokenBudget:
    """Test TokenBudget dataclass."""

    def test_available_calculation(self):
        """Test available tokens calculation."""
        budget = TokenBudget(id="test", limit=1000, used=300, reserved=200)
        assert budget.available == 500

    def test_remaining_calculation(self):
        """Test remaining tokens (not counting reserved)."""
        budget = TokenBudget(id="test", limit=1000, used=300, reserved=200)
        assert budget.remaining == 700

    def test_percent_used(self):
        """Test percentage used calculation."""
        budget = TokenBudget(id="test", limit=1000, used=250)
        assert budget.percent_used == 25.0

    def test_percent_used_zero_limit(self):
        """Test percentage with zero limit."""
        budget = TokenBudget(id="test", limit=0, used=0)
        assert budget.percent_used == 0

    def test_check_ok(self):
        """Test budget check returns OK when under threshold."""
        budget = TokenBudget(id="test", limit=1000, used=0)
        assert budget.check(500) == BudgetDecision.OK

    def test_check_warning(self):
        """Test budget check returns WARNING at soft threshold."""
        budget = TokenBudget(id="test", limit=1000, used=750)
        assert budget.check(50) == BudgetDecision.WARNING

    def test_check_blocked(self):
        """Test budget check returns BLOCKED at hard threshold."""
        budget = TokenBudget(id="test", limit=1000, used=950)
        assert budget.check(50) == BudgetDecision.BLOCKED

    def test_check_emergency_stop(self):
        """Test budget check returns EMERGENCY_STOP at emergency threshold."""
        budget = TokenBudget(id="test", limit=1000, used=1100)
        assert budget.check(100) == BudgetDecision.EMERGENCY_STOP


# ============================================================
# Reservation Tests
# ============================================================


class TestReservation:
    """Test Reservation dataclass."""

    def test_create_reservation(self):
        """Test reservation creation."""
        res = Reservation.create("budget_1", tokens=500)
        assert res.budget_id == "budget_1"
        assert res.tokens == 500
        assert res.id.startswith("res_")
        assert res.expires_at > res.created_at

    def test_is_expired_false(self):
        """Test reservation not expired."""
        res = Reservation.create("budget_1", tokens=500, timeout_minutes=5)
        assert res.is_expired is False

    def test_is_expired_true(self):
        """Test reservation expired."""
        res = Reservation(
            id="res_test",
            budget_id="budget_1",
            tokens=500,
            created_at=datetime.now() - timedelta(minutes=10),
            expires_at=datetime.now() - timedelta(minutes=5),
        )
        assert res.is_expired is True


# ============================================================
# EstimationTokenCounter Tests
# ============================================================


class TestEstimationTokenCounter:
    """Test estimation-based token counter."""

    @pytest.mark.asyncio
    async def test_count_empty_string(self):
        """Test counting empty string returns 0."""
        counter = EstimationTokenCounter()
        assert await counter.count("") == 0

    @pytest.mark.asyncio
    async def test_count_short_text(self):
        """Test counting short text."""
        counter = EstimationTokenCounter()
        # "hello" = 5 chars / 4 = 1.25 -> 1
        assert await counter.count("hello") == 1

    @pytest.mark.asyncio
    async def test_count_longer_text(self):
        """Test counting longer text."""
        counter = EstimationTokenCounter()
        text = "This is a longer piece of text for testing"
        # 43 chars / 4 = 10.75 -> 10
        assert await counter.count(text) == 10

    @pytest.mark.asyncio
    async def test_count_uses_4_chars_per_token(self):
        """Test ~4 chars per token rule."""
        counter = EstimationTokenCounter()
        # 400 chars should be ~100 tokens
        text = "x" * 400
        result = await counter.count(text)
        assert result == 100

    @pytest.mark.asyncio
    async def test_count_messages(self):
        """Test counting messages with overhead."""
        counter = EstimationTokenCounter()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        # "Hello" = 1 token + 4 overhead = 5
        # "Hi there" = 2 tokens + 4 overhead = 6
        # + 3 reply priming = 14
        result = await counter.count_messages(messages)
        assert result == 14


# ============================================================
# OpenAITokenCounter Tests
# ============================================================


class TestOpenAITokenCounter:
    """Test tiktoken-based token counter."""

    @pytest.mark.asyncio
    async def test_count_without_tiktoken(self):
        """Test fallback when tiktoken not installed."""
        counter = OpenAITokenCounter()
        counter._encoder = None  # Force fallback

        with patch.dict("sys.modules", {"tiktoken": None}):
            # Should fall back to estimation
            result = await counter.count("hello")
            assert result >= 1

    @pytest.mark.asyncio
    async def test_count_empty_string(self):
        """Test counting empty string."""
        counter = OpenAITokenCounter()
        assert await counter.count("") == 0

    @pytest.mark.asyncio
    async def test_count_messages_empty(self):
        """Test counting empty message list."""
        counter = OpenAITokenCounter()
        assert await counter.count_messages([]) == 0

    @pytest.mark.asyncio
    async def test_count_basic_text(self):
        """Test counting basic text (if tiktoken available)."""
        counter = OpenAITokenCounter()
        try:
            import tiktoken
            result = await counter.count("Hello, world!")
            # tiktoken should give exact count
            assert result > 0
        except ImportError:
            # Skip if tiktoken not installed
            pytest.skip("tiktoken not installed")


# ============================================================
# ClaudeTokenCounter Tests
# ============================================================


class TestClaudeTokenCounter:
    """Test Anthropic API-based token counter."""

    @pytest.mark.asyncio
    async def test_fallback_on_missing_anthropic(self):
        """Test fallback when anthropic package not available."""
        counter = ClaudeTokenCounter()

        with patch.dict("sys.modules", {"anthropic": None}):
            counter._client = None
            result = await counter.count("Hello")
            # Should fall back to estimation
            assert result >= 1

    @pytest.mark.asyncio
    async def test_fallback_on_api_error(self):
        """Test fallback on API error."""
        counter = ClaudeTokenCounter()

        mock_client = MagicMock()
        mock_client.messages.count_tokens.side_effect = Exception("API Error")
        counter._client = mock_client

        result = await counter.count("Hello")
        # Should fall back to estimation
        assert result >= 1

    @pytest.mark.asyncio
    async def test_count_empty_string(self):
        """Test counting empty string."""
        counter = ClaudeTokenCounter()
        assert await counter.count("") == 0

    @pytest.mark.asyncio
    async def test_count_messages_empty(self):
        """Test counting empty message list."""
        counter = ClaudeTokenCounter()
        assert await counter.count_messages([]) == 0


# ============================================================
# get_token_counter Factory Tests
# ============================================================


class TestGetTokenCounter:
    """Test token counter factory function."""

    def test_get_anthropic_counter(self):
        """Test getting Claude counter."""
        counter = get_token_counter("anthropic")
        assert isinstance(counter, ClaudeTokenCounter)

    def test_get_claude_counter(self):
        """Test getting Claude counter via alias."""
        counter = get_token_counter("claude")
        assert isinstance(counter, ClaudeTokenCounter)

    def test_get_openai_counter(self):
        """Test getting OpenAI counter."""
        counter = get_token_counter("openai")
        assert isinstance(counter, OpenAITokenCounter)

    def test_get_estimation_counter(self):
        """Test getting estimation counter."""
        counter = get_token_counter("estimation")
        assert isinstance(counter, EstimationTokenCounter)

    def test_get_unknown_defaults_to_estimation(self):
        """Test unknown provider defaults to estimation."""
        counter = get_token_counter("unknown_provider")
        assert isinstance(counter, EstimationTokenCounter)


# ============================================================
# AtomicBudgetTracker Tests
# ============================================================


class TestAtomicBudgetTracker:
    """Test atomic budget tracking operations."""

    @pytest.mark.asyncio
    async def test_create_budget(self, in_memory_db):
        """Test creating a new budget."""
        tracker = AtomicBudgetTracker(db_path=in_memory_db)

        budget = await tracker.create_budget(
            budget_id="test_budget",
            limit=10000,
            workflow_id="wf_123",
        )

        assert budget.id == "test_budget"
        assert budget.limit == 10000
        assert budget.used == 0
        assert budget.reserved == 0

        await tracker.close()

    @pytest.mark.asyncio
    async def test_reserve_success(self, in_memory_db):
        """Test successful token reservation."""
        tracker = AtomicBudgetTracker(db_path=in_memory_db)
        await tracker.create_budget("test_budget", limit=10000)

        result = await tracker.reserve("test_budget", tokens=5000)

        assert result.success is True
        assert result.reservation_id is not None
        assert result.reservation_id.startswith("res_")

        await tracker.close()

    @pytest.mark.asyncio
    async def test_reserve_exceeds_budget(self, in_memory_db):
        """Test reservation fails when exceeding budget."""
        tracker = AtomicBudgetTracker(db_path=in_memory_db)
        await tracker.create_budget("test_budget", limit=1000)

        result = await tracker.reserve("test_budget", tokens=2000)

        assert result.success is False
        assert "Insufficient budget" in result.reason

        await tracker.close()

    @pytest.mark.asyncio
    async def test_reserve_nonexistent_budget(self, in_memory_db):
        """Test reservation fails for nonexistent budget."""
        tracker = AtomicBudgetTracker(db_path=in_memory_db)

        result = await tracker.reserve("nonexistent", tokens=100)

        assert result.success is False
        assert "not found" in result.reason

        await tracker.close()

    @pytest.mark.asyncio
    async def test_commit_updates_used(self, in_memory_db):
        """Test commit updates used tokens correctly."""
        tracker = AtomicBudgetTracker(db_path=in_memory_db)
        await tracker.create_budget("test_budget", limit=10000)

        result = await tracker.reserve("test_budget", tokens=5000)
        await tracker.commit(result.reservation_id, actual_tokens=4500)

        status = await tracker.get_status("test_budget")
        assert status.used == 4500
        assert status.reserved == 0

        await tracker.close()

    @pytest.mark.asyncio
    async def test_commit_different_actual_tokens(self, in_memory_db):
        """Test commit uses actual tokens, not reserved."""
        tracker = AtomicBudgetTracker(db_path=in_memory_db)
        await tracker.create_budget("test_budget", limit=10000)

        result = await tracker.reserve("test_budget", tokens=5000)
        await tracker.commit(result.reservation_id, actual_tokens=3000)

        status = await tracker.get_status("test_budget")
        assert status.used == 3000  # Not 5000

        await tracker.close()

    @pytest.mark.asyncio
    async def test_commit_invalid_reservation(self, in_memory_db):
        """Test commit fails for invalid reservation."""
        tracker = AtomicBudgetTracker(db_path=in_memory_db)
        await tracker.create_budget("test_budget", limit=10000)

        with pytest.raises(ValueError) as exc:
            await tracker.commit("invalid_reservation", actual_tokens=100)

        assert "not found" in str(exc.value)

        await tracker.close()

    @pytest.mark.asyncio
    async def test_rollback_releases_tokens(self, in_memory_db):
        """Test rollback releases reserved tokens."""
        tracker = AtomicBudgetTracker(db_path=in_memory_db)
        await tracker.create_budget("test_budget", limit=10000)

        result = await tracker.reserve("test_budget", tokens=5000)
        status_before = await tracker.get_status("test_budget")
        assert status_before.reserved == 5000

        await tracker.rollback(result.reservation_id)

        status_after = await tracker.get_status("test_budget")
        assert status_after.reserved == 0
        assert status_after.used == 0

        await tracker.close()

    @pytest.mark.asyncio
    async def test_rollback_idempotent(self, in_memory_db):
        """Test rollback is idempotent (no error on double rollback)."""
        tracker = AtomicBudgetTracker(db_path=in_memory_db)
        await tracker.create_budget("test_budget", limit=10000)

        result = await tracker.reserve("test_budget", tokens=5000)
        await tracker.rollback(result.reservation_id)
        # Second rollback should not raise
        await tracker.rollback(result.reservation_id)

        await tracker.close()

    @pytest.mark.asyncio
    async def test_get_status(self, in_memory_db):
        """Test getting budget status."""
        tracker = AtomicBudgetTracker(db_path=in_memory_db)
        await tracker.create_budget("test_budget", limit=10000)
        await tracker.reserve("test_budget", tokens=2000)

        status = await tracker.get_status("test_budget")

        assert status.budget_id == "test_budget"
        assert status.limit == 10000
        assert status.reserved == 2000
        assert status.available == 8000

        await tracker.close()

    @pytest.mark.asyncio
    async def test_get_status_nonexistent(self, in_memory_db):
        """Test getting status for nonexistent budget."""
        tracker = AtomicBudgetTracker(db_path=in_memory_db)

        status = await tracker.get_status("nonexistent")
        assert status is None

        await tracker.close()

    @pytest.mark.asyncio
    async def test_pre_check_ok(self, in_memory_db):
        """Test pre-flight check returns OK."""
        tracker = AtomicBudgetTracker(db_path=in_memory_db)
        await tracker.create_budget("test_budget", limit=10000)

        decision = await tracker.pre_check("test_budget", estimated_tokens=5000)
        assert decision == BudgetDecision.OK

        await tracker.close()

    @pytest.mark.asyncio
    async def test_pre_check_blocked(self, in_memory_db):
        """Test pre-flight check returns BLOCKED."""
        tracker = AtomicBudgetTracker(db_path=in_memory_db)
        await tracker.create_budget("test_budget", limit=1000)

        # Use most of the budget
        result = await tracker.reserve("test_budget", tokens=900)
        await tracker.commit(result.reservation_id, actual_tokens=900)

        decision = await tracker.pre_check("test_budget", estimated_tokens=200)
        assert decision == BudgetDecision.BLOCKED

        await tracker.close()


# ============================================================
# Concurrency Tests
# ============================================================


class TestConcurrency:
    """Test concurrent budget operations."""

    @pytest.mark.asyncio
    async def test_concurrent_reserves_same_budget(self, temp_db_path):
        """Test concurrent reserves don't cause overdraft."""
        tracker = AtomicBudgetTracker(db_path=temp_db_path)
        await tracker.create_budget("test_budget", limit=10000)

        async def reserve_tokens(n: int):
            """Attempt to reserve tokens."""
            for _ in range(3):
                result = await tracker.reserve("test_budget", tokens=2000)
                if result.success:
                    return result
                await asyncio.sleep(0.01)
            return None

        # Run 5 concurrent reservations of 2000 each
        results = await asyncio.gather(*[reserve_tokens(i) for i in range(5)])

        # All should succeed (5 * 2000 = 10000 = limit)
        successful = [r for r in results if r and r.success]
        assert len(successful) == 5

        status = await tracker.get_status("test_budget")
        assert status.reserved == 10000
        assert status.available == 0

        await tracker.close()

    @pytest.mark.asyncio
    async def test_concurrent_reserves_exceed_budget(self, temp_db_path):
        """Test concurrent reserves respect budget limit."""
        tracker = AtomicBudgetTracker(db_path=temp_db_path)
        await tracker.create_budget("test_budget", limit=5000)

        async def reserve_tokens():
            """Attempt to reserve 2000 tokens."""
            return await tracker.reserve("test_budget", tokens=2000)

        # Run 5 concurrent reservations of 2000 each (total 10000 > 5000)
        results = await asyncio.gather(*[reserve_tokens() for _ in range(5)])

        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        # Only 2 should succeed (2 * 2000 = 4000 <= 5000)
        assert len(successful) == 2
        assert len(failed) == 3

        status = await tracker.get_status("test_budget")
        assert status.reserved <= status.limit

        await tracker.close()

    @pytest.mark.asyncio
    async def test_concurrent_different_budgets(self, temp_db_path):
        """Test concurrent operations on different budgets."""
        tracker = AtomicBudgetTracker(db_path=temp_db_path)

        # Create 3 budgets
        for i in range(3):
            await tracker.create_budget(f"budget_{i}", limit=10000)

        async def reserve_from_budget(budget_id: str):
            """Reserve from a specific budget."""
            return await tracker.reserve(budget_id, tokens=5000)

        # Concurrent reservations to different budgets
        results = await asyncio.gather(*[
            reserve_from_budget(f"budget_{i}") for i in range(3)
        ])

        # All should succeed
        assert all(r.success for r in results)

        await tracker.close()


# ============================================================
# Reservation Timeout Tests
# ============================================================


class TestReservationTimeout:
    """Test reservation timeout handling."""

    @pytest.mark.asyncio
    async def test_expired_reservations_cleaned_up(self, in_memory_db):
        """Test expired reservations are cleaned up."""
        tracker = AtomicBudgetTracker(
            db_path=in_memory_db,
            reservation_timeout_minutes=0,  # Expire immediately
        )
        await tracker.create_budget("test_budget", limit=10000)

        # Make a reservation (will expire immediately with timeout=0)
        result = await tracker.reserve("test_budget", tokens=5000)
        assert result.success

        # Wait a bit and check status (triggers cleanup)
        await asyncio.sleep(0.1)
        status = await tracker.get_status("test_budget")

        # Reservation should be cleaned up
        assert status.reserved == 0
        assert status.available == 10000

        await tracker.close()


# ============================================================
# Event Sourcing Integration Tests
# ============================================================


class TestEventSourcingIntegration:
    """Test budget tracking with event store."""

    @pytest.mark.asyncio
    async def test_budget_events_recorded(self, in_memory_db):
        """Test budget events are recorded to event store."""
        from src.v4.security.async_storage import SQLiteAsyncEventStore

        event_store = SQLiteAsyncEventStore(in_memory_db)
        tracker = AtomicBudgetTracker(
            db_path=in_memory_db,
            event_store=event_store,
        )

        # Create budget
        await tracker.create_budget("test_budget", limit=10000)

        # Reserve
        result = await tracker.reserve("test_budget", tokens=5000)

        # Commit
        await tracker.commit(result.reservation_id, actual_tokens=4500)

        # Read events
        events = []
        async for event in event_store.read("budget:test_budget"):
            events.append(event)

        # Should have: CREATED, RESERVED, COMMITTED
        assert len(events) == 3
        assert events[0].type == "budget_created"
        assert events[1].type == "tokens_reserved"
        assert events[2].type == "tokens_committed"

        await tracker.close()
        await event_store.close()

    @pytest.mark.asyncio
    async def test_rollback_event_recorded(self, in_memory_db):
        """Test rollback event is recorded."""
        from src.v4.security.async_storage import SQLiteAsyncEventStore

        event_store = SQLiteAsyncEventStore(in_memory_db)
        tracker = AtomicBudgetTracker(
            db_path=in_memory_db,
            event_store=event_store,
        )

        await tracker.create_budget("test_budget", limit=10000)
        result = await tracker.reserve("test_budget", tokens=5000)
        await tracker.rollback(result.reservation_id)

        events = []
        async for event in event_store.read("budget:test_budget"):
            events.append(event)

        # Should have: CREATED, RESERVED, RELEASED
        assert len(events) == 3
        assert events[2].type == "tokens_released"
        assert events[2].data["reason"] == "rollback"

        await tracker.close()
        await event_store.close()


# ============================================================
# Integration Tests
# ============================================================


class TestIntegration:
    """Integration tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_full_reserve_commit_cycle(self, in_memory_db):
        """Test complete reserve -> commit cycle."""
        tracker = AtomicBudgetTracker(db_path=in_memory_db)
        await tracker.create_budget("workflow_1", limit=100000)

        # Pre-check
        decision = await tracker.pre_check("workflow_1", estimated_tokens=5000)
        assert decision == BudgetDecision.OK

        # Reserve
        result = await tracker.reserve("workflow_1", tokens=5000)
        assert result.success

        # Commit with actual (less than estimated)
        await tracker.commit(result.reservation_id, actual_tokens=4500)

        # Verify final state
        status = await tracker.get_status("workflow_1")
        assert status.used == 4500
        assert status.reserved == 0
        assert status.available == 95500

        await tracker.close()

    @pytest.mark.asyncio
    async def test_full_reserve_rollback_cycle(self, in_memory_db):
        """Test complete reserve -> rollback cycle."""
        tracker = AtomicBudgetTracker(db_path=in_memory_db)
        await tracker.create_budget("workflow_1", limit=100000)

        # Reserve
        result = await tracker.reserve("workflow_1", tokens=5000)
        assert result.success

        # Rollback (simulating LLM call failure)
        await tracker.rollback(result.reservation_id, reason="llm_error")

        # Verify tokens returned
        status = await tracker.get_status("workflow_1")
        assert status.used == 0
        assert status.reserved == 0
        assert status.available == 100000

        await tracker.close()

    @pytest.mark.asyncio
    async def test_budget_persists_across_tracker_instances(self, temp_db_path):
        """Test budget state persists across tracker instances."""
        # First tracker instance
        tracker1 = AtomicBudgetTracker(db_path=temp_db_path)
        await tracker1.create_budget("persistent_budget", limit=50000)
        result = await tracker1.reserve("persistent_budget", tokens=10000)
        await tracker1.commit(result.reservation_id, actual_tokens=8000)
        await tracker1.close()

        # Second tracker instance (same DB)
        tracker2 = AtomicBudgetTracker(db_path=temp_db_path)
        status = await tracker2.get_status("persistent_budget")

        assert status is not None
        assert status.limit == 50000
        assert status.used == 8000
        assert status.available == 42000

        await tracker2.close()
