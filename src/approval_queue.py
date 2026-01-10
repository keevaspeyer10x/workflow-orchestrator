"""
Approval Queue - SQLite-backed approval system for parallel agents.

Implements the consensus recommendations from multi-model review:
- SQLite with WAL mode (not JSON) for concurrent access
- State machine: PENDING → APPROVED|REJECTED → CONSUMED
- Heartbeat tracking for stuck agent detection
- Unique request IDs with consume-once semantics

Usage:
    queue = ApprovalQueue()

    # Agent submits request
    request_id = queue.submit(ApprovalRequest.create(
        agent_id="task-1",
        phase="PLAN",
        operation="Implement feature X",
        risk_level="medium",
        context={"files": ["src/foo.py"], "lines_changed": 50}
    ))

    # Orchestrator reviews
    pending = queue.pending()
    queue.decide(request_id, "approved", reason="Looks good")

    # Agent checks and consumes
    status = queue.check(request_id)  # "approved"
    queue.consume(request_id)  # Mark as consumed
"""

import sqlite3
import json
import uuid
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List
from contextlib import contextmanager
from enum import Enum

logger = logging.getLogger(__name__)


class ApprovalStatus(Enum):
    """State machine for approval requests."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONSUMED = "consumed"  # Agent has acknowledged the decision
    EXPIRED = "expired"    # TTL exceeded


class RiskLevel(Enum):
    """Risk levels for auto-approval decisions."""
    LOW = "low"           # Auto-approve: read files, run tests, lint
    MEDIUM = "medium"     # Log but approve: create files, small edits
    HIGH = "high"         # Require human: >100 lines, configs, deps
    CRITICAL = "critical" # Never auto: rm -rf, force push, prod deploy


@dataclass
class ApprovalRequest:
    """A request for human approval at a workflow gate."""
    id: str
    agent_id: str
    phase: str  # PLAN, EXECUTE, REVIEW, VERIFY, LEARN
    operation: str  # Human-readable description
    risk_level: str  # low, medium, high, critical
    context: dict  # Additional context (files, diff summary, etc.)
    status: str = "pending"
    created_at: str = ""
    decided_at: Optional[str] = None
    decision_reason: Optional[str] = None
    last_heartbeat: Optional[str] = None

    @classmethod
    def create(
        cls,
        agent_id: str,
        phase: str,
        operation: str,
        risk_level: str = "medium",
        context: Optional[dict] = None
    ) -> "ApprovalRequest":
        """Create a new approval request with generated ID."""
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=f"{agent_id}-{uuid.uuid4().hex[:8]}",
            agent_id=agent_id,
            phase=phase,
            operation=operation,
            risk_level=risk_level,
            context=context or {},
            status="pending",
            created_at=now,
            last_heartbeat=now,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ApprovalRequest":
        """Create from database row."""
        return cls(
            id=row["id"],
            agent_id=row["agent_id"],
            phase=row["phase"],
            operation=row["operation"],
            risk_level=row["risk_level"],
            context=json.loads(row["context"]) if row["context"] else {},
            status=row["status"],
            created_at=row["created_at"],
            decided_at=row["decided_at"],
            decision_reason=row["decision_reason"],
            last_heartbeat=row["last_heartbeat"],
        )


class ApprovalQueue:
    """
    SQLite-backed approval queue for parallel agent coordination.

    Features:
    - WAL mode for concurrent read/write access
    - Atomic operations with proper locking
    - Heartbeat tracking for stuck agent detection
    - State machine with consume-once semantics
    """

    DEFAULT_PATH = ".workflow_approvals.db"
    SCHEMA_VERSION = 1

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize the approval queue.

        Args:
            db_path: Path to SQLite database (default: .workflow_approvals.db)
        """
        self.db_path = Path(db_path) if db_path else Path(self.DEFAULT_PATH)
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with self._connection() as conn:
            # Enable WAL mode for concurrent access
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")  # 5s timeout on locks

            conn.execute("""
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    context TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    decided_at TEXT,
                    decision_reason TEXT,
                    last_heartbeat TEXT,

                    -- Indexes for common queries
                    CHECK (status IN ('pending', 'approved', 'rejected', 'consumed', 'expired', 'auto_approved'))
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_approvals_status
                ON approvals(status)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_approvals_agent
                ON approvals(agent_id, status)
            """)

            # Schema version tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                )
            """)

            conn.execute("""
                INSERT OR IGNORE INTO schema_version (version) VALUES (?)
            """, (self.SCHEMA_VERSION,))

            conn.commit()

    @contextmanager
    def _connection(self):
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # =========================================================================
    # Agent Operations
    # =========================================================================

    def submit(self, request: ApprovalRequest) -> str:
        """
        Submit an approval request.

        Args:
            request: The approval request to submit

        Returns:
            The request ID
        """
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO approvals
                (id, agent_id, phase, operation, risk_level, context,
                 status, created_at, last_heartbeat)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request.id,
                request.agent_id,
                request.phase,
                request.operation,
                request.risk_level,
                json.dumps(request.context),
                request.status,
                request.created_at,
                request.last_heartbeat,
            ))
            conn.commit()

        logger.info(f"Submitted approval request: {request.id} ({request.operation})")
        return request.id

    def check(self, request_id: str) -> Optional[str]:
        """
        Check the status of an approval request.

        Args:
            request_id: The request ID to check

        Returns:
            Status string or None if not found
        """
        with self._connection() as conn:
            row = conn.execute(
                "SELECT status FROM approvals WHERE id = ?",
                (request_id,)
            ).fetchone()

            return row["status"] if row else None

    def consume(self, request_id: str) -> bool:
        """
        Mark an approved/rejected request as consumed.

        This implements "consume exactly once" semantics - once consumed,
        the request cannot be re-consumed.

        Args:
            request_id: The request ID to consume

        Returns:
            True if successfully consumed, False if not found or already consumed
        """
        with self._connection() as conn:
            cursor = conn.execute("""
                UPDATE approvals
                SET status = 'consumed'
                WHERE id = ? AND status IN ('approved', 'rejected')
            """, (request_id,))
            conn.commit()

            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Consumed approval request: {request_id}")
            return success

    def heartbeat(self, request_id: str) -> bool:
        """
        Update the heartbeat timestamp for a pending request.

        Args:
            request_id: The request ID to update

        Returns:
            True if updated, False if not found
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            cursor = conn.execute("""
                UPDATE approvals
                SET last_heartbeat = ?
                WHERE id = ? AND status = 'pending'
            """, (now, request_id))
            conn.commit()
            return cursor.rowcount > 0

    def get(self, request_id: str) -> Optional[ApprovalRequest]:
        """
        Get a specific approval request.

        Args:
            request_id: The request ID

        Returns:
            ApprovalRequest or None if not found
        """
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM approvals WHERE id = ?",
                (request_id,)
            ).fetchone()

            return ApprovalRequest.from_row(row) if row else None

    # =========================================================================
    # Orchestrator Operations
    # =========================================================================

    def pending(self, agent_id: Optional[str] = None) -> List[ApprovalRequest]:
        """
        List all pending approval requests.

        Args:
            agent_id: Optionally filter by agent

        Returns:
            List of pending ApprovalRequests
        """
        with self._connection() as conn:
            if agent_id:
                rows = conn.execute("""
                    SELECT * FROM approvals
                    WHERE status = 'pending' AND agent_id = ?
                    ORDER BY created_at ASC
                """, (agent_id,)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM approvals
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                """).fetchall()

            return [ApprovalRequest.from_row(row) for row in rows]

    def decide(
        self,
        request_id: str,
        status: str,
        reason: str = ""
    ) -> bool:
        """
        Record a decision on an approval request.

        Args:
            request_id: The request ID
            status: "approved" or "rejected"
            reason: Optional reason for the decision

        Returns:
            True if decision recorded, False if not found or already decided
        """
        if status not in ("approved", "rejected"):
            raise ValueError(f"Invalid status: {status}")

        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            cursor = conn.execute("""
                UPDATE approvals
                SET status = ?, decided_at = ?, decision_reason = ?
                WHERE id = ? AND status = 'pending'
            """, (status, now, reason, request_id))
            conn.commit()

            success = cursor.rowcount > 0
            if success:
                logger.info(f"Decided on {request_id}: {status} ({reason})")
            return success

    def approve(self, request_id: str, reason: str = "") -> bool:
        """Convenience method to approve a request."""
        return self.decide(request_id, "approved", reason)

    def reject(self, request_id: str, reason: str = "") -> bool:
        """Convenience method to reject a request."""
        return self.decide(request_id, "rejected", reason)

    def approve_all(self, reason: str = "Batch approved") -> int:
        """
        Approve all pending requests.

        Returns:
            Number of requests approved
        """
        pending = self.pending()
        count = 0
        for req in pending:
            if self.approve(req.id, reason):
                count += 1
        return count

    # =========================================================================
    # Maintenance Operations
    # =========================================================================

    def expire_stale(self, timeout_minutes: int = 60) -> int:
        """
        Expire requests that have been pending too long without heartbeat.

        Args:
            timeout_minutes: Minutes since last heartbeat to consider stale

        Returns:
            Number of requests expired
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        ).isoformat()

        with self._connection() as conn:
            cursor = conn.execute("""
                UPDATE approvals
                SET status = 'expired'
                WHERE status = 'pending' AND last_heartbeat < ?
            """, (cutoff,))
            conn.commit()

            count = cursor.rowcount
            if count > 0:
                logger.warning(f"Expired {count} stale approval requests")
            return count

    def cleanup(self, days: int = 30) -> int:
        """
        Delete old consumed/expired requests.

        Args:
            days: Delete requests older than this many days

        Returns:
            Number of requests deleted
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).isoformat()

        with self._connection() as conn:
            cursor = conn.execute("""
                DELETE FROM approvals
                WHERE status IN ('consumed', 'expired')
                AND created_at < ?
            """, (cutoff,))
            conn.commit()

            count = cursor.rowcount
            if count > 0:
                logger.info(f"Cleaned up {count} old approval requests")
            return count

    def stats(self) -> dict:
        """
        Get queue statistics.

        Returns:
            Dict with counts by status
        """
        with self._connection() as conn:
            rows = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM approvals
                GROUP BY status
            """).fetchall()

            return {row["status"]: row["count"] for row in rows}

    def by_agent(self) -> dict:
        """
        Get pending requests grouped by agent.

        Returns:
            Dict of agent_id -> list of ApprovalRequests
        """
        pending = self.pending()
        result = {}
        for req in pending:
            if req.agent_id not in result:
                result[req.agent_id] = []
            result[req.agent_id].append(req)
        return result

    def mark_auto_approved(self, request_id: str, reason: str = "") -> bool:
        """
        Mark a request as auto-approved (for transparency logging).

        Args:
            request_id: The request ID
            reason: Reason/rationale for auto-approval

        Returns:
            True if marked, False if not found
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            cursor = conn.execute("""
                UPDATE approvals
                SET status = 'auto_approved', decided_at = ?, decision_reason = ?
                WHERE id = ? AND status = 'pending'
            """, (now, reason, request_id))
            conn.commit()

            success = cursor.rowcount > 0
            if success:
                logger.info(f"Auto-approved {request_id}: {reason}")
            return success

    def decision_summary(self) -> dict:
        """
        Get a summary of all decisions grouped by type.

        Returns:
            Dict with 'auto_approved', 'human_approved', 'rejected' lists
        """
        with self._connection() as conn:
            rows = conn.execute("""
                SELECT * FROM approvals
                WHERE status IN ('auto_approved', 'approved', 'rejected', 'consumed')
                ORDER BY decided_at DESC
            """).fetchall()

            summary = {
                "auto_approved": [],
                "human_approved": [],
                "rejected": [],
            }

            for row in rows:
                req = ApprovalRequest.from_row(row)
                entry = {
                    "id": req.id,
                    "agent_id": req.agent_id,
                    "operation": req.operation,
                    "phase": req.phase,
                    "risk_level": req.risk_level,
                    "reason": req.decision_reason or "",
                    "rationale": req.decision_reason or "",
                    "decided_at": req.decided_at,
                }

                if row["status"] == "auto_approved":
                    summary["auto_approved"].append(entry)
                elif row["status"] in ("approved", "consumed"):
                    summary["human_approved"].append(entry)
                elif row["status"] == "rejected":
                    summary["rejected"].append(entry)

            return summary
