"""
Tests for ApprovalQueue - SQLite-backed approval system.
"""

import pytest
import tempfile
import threading
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

from src.approval_queue import (
    ApprovalQueue,
    ApprovalRequest,
    ApprovalStatus,
    RiskLevel,
)


class TestApprovalRequest:
    """Tests for ApprovalRequest dataclass."""

    def test_create_generates_unique_id(self):
        """Create should generate unique IDs."""
        req1 = ApprovalRequest.create("agent-1", "PLAN", "Test operation")
        req2 = ApprovalRequest.create("agent-1", "PLAN", "Test operation")
        assert req1.id != req2.id

    def test_create_sets_pending_status(self):
        """Create should set status to pending."""
        req = ApprovalRequest.create("agent-1", "PLAN", "Test operation")
        assert req.status == "pending"

    def test_create_sets_timestamps(self):
        """Create should set created_at and last_heartbeat."""
        req = ApprovalRequest.create("agent-1", "PLAN", "Test operation")
        assert req.created_at != ""
        assert req.last_heartbeat != ""

    def test_create_with_context(self):
        """Create should accept context dict."""
        context = {"files": ["a.py", "b.py"], "lines": 100}
        req = ApprovalRequest.create(
            "agent-1", "EXECUTE", "Modify files",
            risk_level="high", context=context
        )
        assert req.context == context
        assert req.risk_level == "high"


class TestApprovalQueueBasic:
    """Basic tests for ApprovalQueue operations."""

    @pytest.fixture
    def queue(self, tmp_path):
        """Create a queue with temp database."""
        db_path = tmp_path / "test_approvals.db"
        return ApprovalQueue(db_path)

    def test_submit_creates_pending_request(self, queue):
        """Submit should create a pending request."""
        req = ApprovalRequest.create("agent-1", "PLAN", "Test operation")
        request_id = queue.submit(req)

        assert request_id == req.id
        status = queue.check(request_id)
        assert status == "pending"

    def test_check_returns_status(self, queue):
        """Check should return correct status."""
        req = ApprovalRequest.create("agent-1", "PLAN", "Test")
        queue.submit(req)

        assert queue.check(req.id) == "pending"

        queue.approve(req.id)
        assert queue.check(req.id) == "approved"

    def test_check_returns_none_for_unknown(self, queue):
        """Check should return None for unknown ID."""
        assert queue.check("nonexistent-id") is None

    def test_decide_approves_request(self, queue):
        """Decide should change status to approved."""
        req = ApprovalRequest.create("agent-1", "PLAN", "Test")
        queue.submit(req)

        result = queue.decide(req.id, "approved", "Looks good")
        assert result is True
        assert queue.check(req.id) == "approved"

    def test_decide_rejects_request(self, queue):
        """Decide should change status to rejected."""
        req = ApprovalRequest.create("agent-1", "PLAN", "Test")
        queue.submit(req)

        result = queue.decide(req.id, "rejected", "Not safe")
        assert result is True
        assert queue.check(req.id) == "rejected"

    def test_decide_invalid_status_raises(self, queue):
        """Decide should raise for invalid status."""
        req = ApprovalRequest.create("agent-1", "PLAN", "Test")
        queue.submit(req)

        with pytest.raises(ValueError):
            queue.decide(req.id, "invalid_status")

    def test_consume_marks_consumed(self, queue):
        """Consume should mark approved request as consumed."""
        req = ApprovalRequest.create("agent-1", "PLAN", "Test")
        queue.submit(req)
        queue.approve(req.id)

        result = queue.consume(req.id)
        assert result is True
        assert queue.check(req.id) == "consumed"

    def test_consume_fails_for_pending(self, queue):
        """Cannot consume pending request."""
        req = ApprovalRequest.create("agent-1", "PLAN", "Test")
        queue.submit(req)

        result = queue.consume(req.id)
        assert result is False
        assert queue.check(req.id) == "pending"

    def test_consume_once_semantics(self, queue):
        """Cannot consume same request twice."""
        req = ApprovalRequest.create("agent-1", "PLAN", "Test")
        queue.submit(req)
        queue.approve(req.id)

        assert queue.consume(req.id) is True
        assert queue.consume(req.id) is False  # Already consumed


class TestApprovalQueuePending:
    """Tests for pending request listing."""

    @pytest.fixture
    def queue(self, tmp_path):
        """Create a queue with temp database."""
        db_path = tmp_path / "test_approvals.db"
        return ApprovalQueue(db_path)

    def test_pending_returns_all_pending(self, queue):
        """Pending should return all pending requests."""
        req1 = ApprovalRequest.create("agent-1", "PLAN", "Op 1")
        req2 = ApprovalRequest.create("agent-2", "PLAN", "Op 2")
        queue.submit(req1)
        queue.submit(req2)

        pending = queue.pending()
        assert len(pending) == 2
        ids = [r.id for r in pending]
        assert req1.id in ids
        assert req2.id in ids

    def test_pending_excludes_decided(self, queue):
        """Pending should exclude approved/rejected requests."""
        req1 = ApprovalRequest.create("agent-1", "PLAN", "Op 1")
        req2 = ApprovalRequest.create("agent-2", "PLAN", "Op 2")
        queue.submit(req1)
        queue.submit(req2)
        queue.approve(req1.id)

        pending = queue.pending()
        assert len(pending) == 1
        assert pending[0].id == req2.id

    def test_pending_filters_by_agent(self, queue):
        """Pending should filter by agent_id."""
        req1 = ApprovalRequest.create("agent-1", "PLAN", "Op 1")
        req2 = ApprovalRequest.create("agent-2", "PLAN", "Op 2")
        queue.submit(req1)
        queue.submit(req2)

        pending = queue.pending(agent_id="agent-1")
        assert len(pending) == 1
        assert pending[0].id == req1.id

    def test_pending_empty_when_no_requests(self, queue):
        """Pending should return empty list when no requests."""
        assert queue.pending() == []


class TestApprovalQueueMaintenance:
    """Tests for maintenance operations."""

    @pytest.fixture
    def queue(self, tmp_path):
        """Create a queue with temp database."""
        db_path = tmp_path / "test_approvals.db"
        return ApprovalQueue(db_path)

    def test_heartbeat_updates_timestamp(self, queue):
        """Heartbeat should update last_heartbeat."""
        req = ApprovalRequest.create("agent-1", "PLAN", "Test")
        queue.submit(req)

        original = queue.get(req.id).last_heartbeat
        time.sleep(0.1)
        queue.heartbeat(req.id)
        updated = queue.get(req.id).last_heartbeat

        assert updated > original

    def test_expire_stale_marks_expired(self, queue):
        """Expire stale should mark old requests as expired."""
        req = ApprovalRequest.create("agent-1", "PLAN", "Test")
        # Manually set old heartbeat
        req.last_heartbeat = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()
        queue.submit(req)

        count = queue.expire_stale(timeout_minutes=60)
        assert count == 1
        assert queue.check(req.id) == "expired"

    def test_cleanup_removes_old_consumed(self, queue):
        """Cleanup should remove old consumed requests."""
        req = ApprovalRequest.create("agent-1", "PLAN", "Test")
        queue.submit(req)
        queue.approve(req.id)
        queue.consume(req.id)

        # Recent - should not be cleaned
        count = queue.cleanup(days=30)
        assert count == 0

    def test_stats_returns_counts(self, queue):
        """Stats should return correct counts by status."""
        req1 = ApprovalRequest.create("agent-1", "PLAN", "Op 1")
        req2 = ApprovalRequest.create("agent-2", "PLAN", "Op 2")
        req3 = ApprovalRequest.create("agent-3", "PLAN", "Op 3")
        queue.submit(req1)
        queue.submit(req2)
        queue.submit(req3)
        queue.approve(req1.id)
        queue.reject(req2.id)

        stats = queue.stats()
        assert stats.get("pending", 0) == 1
        assert stats.get("approved", 0) == 1
        assert stats.get("rejected", 0) == 1

    def test_by_agent_groups_correctly(self, queue):
        """by_agent should group requests by agent_id."""
        req1 = ApprovalRequest.create("agent-1", "PLAN", "Op 1")
        req2 = ApprovalRequest.create("agent-1", "EXECUTE", "Op 2")
        req3 = ApprovalRequest.create("agent-2", "PLAN", "Op 3")
        queue.submit(req1)
        queue.submit(req2)
        queue.submit(req3)

        grouped = queue.by_agent()
        assert len(grouped["agent-1"]) == 2
        assert len(grouped["agent-2"]) == 1


class TestApprovalQueueConcurrency:
    """Tests for concurrent access."""

    @pytest.fixture
    def queue(self, tmp_path):
        """Create a queue with temp database."""
        db_path = tmp_path / "test_approvals.db"
        return ApprovalQueue(db_path)

    def test_concurrent_submits(self, queue):
        """Multiple threads can submit simultaneously."""
        results = []

        def submit_request(agent_id):
            req = ApprovalRequest.create(agent_id, "PLAN", f"Op from {agent_id}")
            request_id = queue.submit(req)
            results.append(request_id)

        threads = [
            threading.Thread(target=submit_request, args=(f"agent-{i}",))
            for i in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        assert len(set(results)) == 10  # All unique IDs
        assert len(queue.pending()) == 10

    def test_concurrent_reads(self, queue):
        """Multiple threads can check status simultaneously."""
        req = ApprovalRequest.create("agent-1", "PLAN", "Test")
        queue.submit(req)

        results = []

        def check_status():
            status = queue.check(req.id)
            results.append(status)

        threads = [
            threading.Thread(target=check_status)
            for _ in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(s == "pending" for s in results)

    def test_wal_mode_enabled(self, queue):
        """WAL journal mode should be active."""
        import sqlite3
        conn = sqlite3.connect(queue.db_path)
        result = conn.execute("PRAGMA journal_mode").fetchone()
        conn.close()
        assert result[0].lower() == "wal"


class TestApprovalQueueGet:
    """Tests for get() method."""

    @pytest.fixture
    def queue(self, tmp_path):
        """Create a queue with temp database."""
        db_path = tmp_path / "test_approvals.db"
        return ApprovalQueue(db_path)

    def test_get_returns_request(self, queue):
        """Get should return full request object."""
        context = {"files": ["test.py"]}
        req = ApprovalRequest.create(
            "agent-1", "PLAN", "Test operation",
            risk_level="high", context=context
        )
        queue.submit(req)

        retrieved = queue.get(req.id)
        assert retrieved is not None
        assert retrieved.id == req.id
        assert retrieved.agent_id == "agent-1"
        assert retrieved.phase == "PLAN"
        assert retrieved.operation == "Test operation"
        assert retrieved.risk_level == "high"
        assert retrieved.context == context

    def test_get_returns_none_for_unknown(self, queue):
        """Get should return None for unknown ID."""
        assert queue.get("nonexistent") is None


class TestApprovalQueueApproveAll:
    """Tests for batch approval."""

    @pytest.fixture
    def queue(self, tmp_path):
        """Create a queue with temp database."""
        db_path = tmp_path / "test_approvals.db"
        return ApprovalQueue(db_path)

    def test_approve_all_approves_all_pending(self, queue):
        """approve_all should approve all pending requests."""
        for i in range(5):
            req = ApprovalRequest.create(f"agent-{i}", "PLAN", f"Op {i}")
            queue.submit(req)

        count = queue.approve_all("Batch approved")
        assert count == 5
        assert len(queue.pending()) == 0

    def test_approve_all_returns_zero_when_empty(self, queue):
        """approve_all should return 0 when no pending."""
        count = queue.approve_all()
        assert count == 0
