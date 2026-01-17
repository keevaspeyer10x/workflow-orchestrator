"""
Atomic Budget Tracker for V4.2 Token Budget System.

Provides thread-safe budget tracking with:
- Atomic reserve/commit/rollback operations
- SQLite persistence with BEGIN IMMEDIATE locking
- Event sourcing integration
- Reservation timeout handling
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import logging
import uuid

from .models import (
    TokenBudget,
    BudgetStatus,
    BudgetDecision,
    Reservation,
    ReservationResult,
)
from .events import (
    budget_created_event,
    tokens_reserved_event,
    tokens_committed_event,
    tokens_released_event,
    budget_exhausted_event,
)

logger = logging.getLogger(__name__)


class AtomicBudgetTracker:
    """
    Thread-safe budget tracking with persistence.

    Uses SQLite with BEGIN IMMEDIATE for exclusive locking,
    preventing race conditions in concurrent budget operations.

    The reserve/commit/rollback pattern ensures:
    - Tokens are reserved atomically before LLM calls
    - Actual usage is committed after the call
    - Reservations are released on failure/timeout
    """

    DEFAULT_RESERVATION_TIMEOUT_MINUTES = 5

    def __init__(
        self,
        db_path: str = ":memory:",
        event_store: Optional[Any] = None,
        reservation_timeout_minutes: int = DEFAULT_RESERVATION_TIMEOUT_MINUTES,
    ):
        """
        Initialize budget tracker.

        Args:
            db_path: Path to SQLite database (or ":memory:")
            event_store: Optional event store for event sourcing
            reservation_timeout_minutes: Default reservation timeout
        """
        self.db_path = db_path
        self._event_store = event_store
        self._reservation_timeout = reservation_timeout_minutes
        self._adapter = None
        self._initialized = False

    async def _ensure_adapter(self):
        """Lazy initialization of database adapter."""
        if self._adapter is None:
            from ..security.async_storage import SQLiteAdapter
            self._adapter = SQLiteAdapter(self.db_path)
        return self._adapter

    async def _ensure_schema(self):
        """Initialize database schema if needed."""
        if self._initialized:
            return

        adapter = await self._ensure_adapter()

        async with adapter.exclusive_transaction() as tx:
            # Budgets table
            await tx.execute("""
                CREATE TABLE IF NOT EXISTS budgets (
                    id TEXT PRIMARY KEY,
                    limit_tokens INTEGER NOT NULL,
                    used INTEGER NOT NULL DEFAULT 0,
                    reserved INTEGER NOT NULL DEFAULT 0,
                    soft_threshold REAL NOT NULL DEFAULT 0.8,
                    hard_threshold REAL NOT NULL DEFAULT 1.0,
                    emergency_threshold REAL NOT NULL DEFAULT 1.2,
                    workflow_id TEXT,
                    phase_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Reservations table
            await tx.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id TEXT PRIMARY KEY,
                    budget_id TEXT NOT NULL,
                    tokens INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (budget_id) REFERENCES budgets(id)
                )
            """)

            # Indexes
            await tx.execute("""
                CREATE INDEX IF NOT EXISTS idx_reservations_budget
                ON reservations(budget_id)
            """)

            await tx.execute("""
                CREATE INDEX IF NOT EXISTS idx_reservations_expires
                ON reservations(expires_at)
            """)

        self._initialized = True

    async def create_budget(
        self,
        budget_id: str,
        limit: int,
        workflow_id: Optional[str] = None,
        phase_id: Optional[str] = None,
        soft_threshold: float = 0.8,
        hard_threshold: float = 1.0,
        emergency_threshold: float = 1.2,
    ) -> TokenBudget:
        """
        Create a new budget.

        Args:
            budget_id: Unique budget identifier
            limit: Maximum tokens allowed
            workflow_id: Associated workflow (optional)
            phase_id: Associated phase (optional)
            soft_threshold: Warning threshold (default 80%)
            hard_threshold: Block threshold (default 100%)
            emergency_threshold: Emergency stop threshold (default 120%)

        Returns:
            Created TokenBudget
        """
        await self._ensure_schema()
        adapter = await self._ensure_adapter()

        now = datetime.now()
        budget = TokenBudget(
            id=budget_id,
            limit=limit,
            soft_threshold=soft_threshold,
            hard_threshold=hard_threshold,
            emergency_threshold=emergency_threshold,
            created_at=now,
            updated_at=now,
        )

        async with adapter.exclusive_transaction() as tx:
            await tx.execute(
                """
                INSERT INTO budgets
                (id, limit_tokens, used, reserved, soft_threshold,
                 hard_threshold, emergency_threshold, workflow_id, phase_id,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    budget_id,
                    limit,
                    0,
                    0,
                    soft_threshold,
                    hard_threshold,
                    emergency_threshold,
                    workflow_id,
                    phase_id,
                    now.isoformat(),
                    now.isoformat(),
                )
            )

        # Record event
        if self._event_store:
            event = budget_created_event(
                budget_id=budget_id,
                limit=limit,
                workflow_id=workflow_id,
                phase_id=phase_id,
            )
            await self._event_store.append(
                f"budget:{budget_id}",
                [event.to_storage_event()]
            )

        return budget

    async def reserve(
        self,
        budget_id: str,
        tokens: int,
        correlation_id: Optional[str] = None,
    ) -> ReservationResult:
        """
        Atomically reserve tokens from budget.

        Args:
            budget_id: Budget to reserve from
            tokens: Number of tokens to reserve
            correlation_id: Correlation ID for tracing

        Returns:
            ReservationResult with success status and reservation_id
        """
        await self._ensure_schema()
        adapter = await self._ensure_adapter()

        # Clean up expired reservations first
        await self._cleanup_expired_reservations(budget_id)

        async with adapter.exclusive_transaction() as tx:
            # Fetch budget with lock
            row = await tx.fetch_one(
                adapter.select_for_update("budgets", "id = ?"),
                (budget_id,)
            )

            if not row:
                return ReservationResult(
                    success=False,
                    reason=f"Budget not found: {budget_id}"
                )

            # Calculate available
            limit = row["limit_tokens"]
            used = row["used"]
            reserved = row["reserved"]
            available = limit - used - reserved

            # Check if we can reserve
            if tokens > available:
                status = self._build_status(row)
                return ReservationResult(
                    success=False,
                    reason=f"Insufficient budget: need {tokens}, have {available}",
                    budget_status=status,
                )

            # Create reservation
            now = datetime.now()
            expires_at = now + timedelta(minutes=self._reservation_timeout)
            reservation_id = f"res_{uuid.uuid4().hex[:12]}"

            await tx.execute(
                """
                INSERT INTO reservations
                (id, budget_id, tokens, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    reservation_id,
                    budget_id,
                    tokens,
                    now.isoformat(),
                    expires_at.isoformat(),
                )
            )

            # Update reserved count
            await tx.execute(
                """
                UPDATE budgets
                SET reserved = reserved + ?, updated_at = ?
                WHERE id = ?
                """,
                (tokens, now.isoformat(), budget_id)
            )

        # Record event
        if self._event_store:
            version = await self._get_event_version(budget_id)
            event = tokens_reserved_event(
                budget_id=budget_id,
                reservation_id=reservation_id,
                tokens=tokens,
                version=version,
                expires_at=expires_at,
                correlation_id=correlation_id,
            )
            await self._event_store.append(
                f"budget:{budget_id}",
                [event.to_storage_event()]
            )

        return ReservationResult(
            success=True,
            reservation_id=reservation_id,
        )

    async def commit(
        self,
        reservation_id: str,
        actual_tokens: int,
        correlation_id: Optional[str] = None,
    ) -> None:
        """
        Commit reservation with actual token usage.

        Args:
            reservation_id: Reservation to commit
            actual_tokens: Actual tokens used (may differ from reserved)
            correlation_id: Correlation ID for tracing

        Raises:
            ValueError: If reservation not found
        """
        await self._ensure_schema()
        adapter = await self._ensure_adapter()

        async with adapter.exclusive_transaction() as tx:
            # Fetch reservation
            res_row = await tx.fetch_one(
                "SELECT * FROM reservations WHERE id = ?",
                (reservation_id,)
            )

            if not res_row:
                raise ValueError(f"Reservation not found: {reservation_id}")

            budget_id = res_row["budget_id"]
            reserved_tokens = res_row["tokens"]
            now = datetime.now()

            # Update budget: move from reserved to used
            await tx.execute(
                """
                UPDATE budgets
                SET reserved = reserved - ?,
                    used = used + ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (reserved_tokens, actual_tokens, now.isoformat(), budget_id)
            )

            # Delete reservation
            await tx.execute(
                "DELETE FROM reservations WHERE id = ?",
                (reservation_id,)
            )

            # Check if budget exhausted
            budget_row = await tx.fetch_one(
                "SELECT * FROM budgets WHERE id = ?",
                (budget_id,)
            )

        # Record events
        if self._event_store and budget_row:
            version = await self._get_event_version(budget_id)
            event = tokens_committed_event(
                budget_id=budget_id,
                reservation_id=reservation_id,
                reserved_tokens=reserved_tokens,
                actual_tokens=actual_tokens,
                version=version,
                correlation_id=correlation_id,
            )
            await self._event_store.append(
                f"budget:{budget_id}",
                [event.to_storage_event()]
            )

            # Check if exhausted
            if budget_row["used"] >= budget_row["limit_tokens"]:
                version += 1
                exhausted_event = budget_exhausted_event(
                    budget_id=budget_id,
                    limit=budget_row["limit_tokens"],
                    used=budget_row["used"],
                    version=version,
                    correlation_id=correlation_id,
                )
                await self._event_store.append(
                    f"budget:{budget_id}",
                    [exhausted_event.to_storage_event()]
                )

    async def rollback(
        self,
        reservation_id: str,
        reason: str = "rollback",
        correlation_id: Optional[str] = None,
    ) -> None:
        """
        Release reservation without using tokens.

        Args:
            reservation_id: Reservation to release
            reason: Reason for rollback
            correlation_id: Correlation ID for tracing
        """
        await self._ensure_schema()
        adapter = await self._ensure_adapter()

        async with adapter.exclusive_transaction() as tx:
            # Fetch reservation
            res_row = await tx.fetch_one(
                "SELECT * FROM reservations WHERE id = ?",
                (reservation_id,)
            )

            if not res_row:
                # Idempotent - already rolled back or never existed
                return

            budget_id = res_row["budget_id"]
            tokens = res_row["tokens"]
            now = datetime.now()

            # Release reserved tokens
            await tx.execute(
                """
                UPDATE budgets
                SET reserved = reserved - ?, updated_at = ?
                WHERE id = ?
                """,
                (tokens, now.isoformat(), budget_id)
            )

            # Delete reservation
            await tx.execute(
                "DELETE FROM reservations WHERE id = ?",
                (reservation_id,)
            )

        # Record event
        if self._event_store:
            version = await self._get_event_version(budget_id)
            event = tokens_released_event(
                budget_id=budget_id,
                reservation_id=reservation_id,
                tokens=tokens,
                version=version,
                reason=reason,
                correlation_id=correlation_id,
            )
            await self._event_store.append(
                f"budget:{budget_id}",
                [event.to_storage_event()]
            )

    async def get_status(self, budget_id: str) -> Optional[BudgetStatus]:
        """
        Get current budget status.

        Args:
            budget_id: Budget to check

        Returns:
            BudgetStatus or None if not found
        """
        await self._ensure_schema()
        adapter = await self._ensure_adapter()

        # Clean up expired reservations first
        await self._cleanup_expired_reservations(budget_id)

        async with adapter.exclusive_transaction() as tx:
            row = await tx.fetch_one(
                "SELECT * FROM budgets WHERE id = ?",
                (budget_id,)
            )

            if not row:
                return None

            return self._build_status(row)

    async def pre_check(
        self,
        budget_id: str,
        estimated_tokens: int,
    ) -> BudgetDecision:
        """
        Pre-flight check before LLM call.

        Args:
            budget_id: Budget to check
            estimated_tokens: Estimated tokens for the operation

        Returns:
            BudgetDecision indicating whether to proceed
        """
        status = await self.get_status(budget_id)

        if status is None:
            return BudgetDecision.BLOCKED

        budget = TokenBudget(
            id=budget_id,
            limit=status.limit,
            used=status.used,
            reserved=status.reserved,
        )

        return budget.check(estimated_tokens)

    async def _cleanup_expired_reservations(self, budget_id: str) -> int:
        """
        Clean up expired reservations for a budget.

        Returns number of reservations cleaned up.
        """
        adapter = await self._ensure_adapter()
        now = datetime.now()

        async with adapter.exclusive_transaction() as tx:
            # Find expired reservations
            rows = await tx.fetch_all(
                """
                SELECT id, tokens FROM reservations
                WHERE budget_id = ? AND expires_at < ?
                """,
                (budget_id, now.isoformat())
            )

            if not rows:
                return 0

            total_tokens = sum(row["tokens"] for row in rows)

            # Release reserved tokens
            await tx.execute(
                """
                UPDATE budgets
                SET reserved = reserved - ?, updated_at = ?
                WHERE id = ?
                """,
                (total_tokens, now.isoformat(), budget_id)
            )

            # Delete expired reservations
            await tx.execute(
                """
                DELETE FROM reservations
                WHERE budget_id = ? AND expires_at < ?
                """,
                (budget_id, now.isoformat())
            )

        # Record events for each expired reservation
        if self._event_store:
            for row in rows:
                version = await self._get_event_version(budget_id)
                event = tokens_released_event(
                    budget_id=budget_id,
                    reservation_id=row["id"],
                    tokens=row["tokens"],
                    version=version,
                    reason="timeout",
                )
                await self._event_store.append(
                    f"budget:{budget_id}",
                    [event.to_storage_event()]
                )

        return len(rows)

    async def _get_event_version(self, budget_id: str) -> int:
        """Get next event version for budget stream."""
        if self._event_store is None:
            return 1
        return await self._event_store.get_stream_version(f"budget:{budget_id}") + 1

    def _build_status(self, row: Dict[str, Any]) -> BudgetStatus:
        """Build BudgetStatus from database row."""
        limit = row["limit_tokens"]
        used = row["used"]
        reserved = row["reserved"]
        available = limit - used - reserved
        percent_used = (used / limit * 100) if limit > 0 else 0

        budget = TokenBudget(
            id=row["id"],
            limit=limit,
            used=used,
            reserved=reserved,
            soft_threshold=row.get("soft_threshold", 0.8),
            hard_threshold=row.get("hard_threshold", 1.0),
            emergency_threshold=row.get("emergency_threshold", 1.2),
        )
        decision = budget.check()

        return BudgetStatus(
            budget_id=row["id"],
            limit=limit,
            used=used,
            reserved=reserved,
            available=available,
            percent_used=percent_used,
            decision=decision,
            exceeded=decision in (BudgetDecision.BLOCKED, BudgetDecision.EMERGENCY_STOP),
            warning=decision == BudgetDecision.WARNING,
        )

    async def close(self) -> None:
        """Close database connection."""
        if self._adapter:
            await self._adapter.close()
            self._adapter = None
