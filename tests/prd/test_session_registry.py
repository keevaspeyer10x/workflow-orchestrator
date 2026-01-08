"""
Tests for session registry - persistent Claude Squad session tracking.
"""

import pytest
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from src.prd.session_registry import SessionRegistry, SessionRecord


class TestSessionRecord:
    """Tests for SessionRecord dataclass."""

    def test_to_dict(self):
        """SessionRecord should serialize to dictionary."""
        record = SessionRecord(
            task_id="task-1",
            session_id="sess-abc",
            session_name="wfo-task-1",
            branch="claude/task-1",
            status="running",
            created_at="2026-01-09T10:00:00+00:00",
            updated_at="2026-01-09T10:00:00+00:00",
            prompt_file="/tmp/prompt.md"
        )

        d = record.to_dict()

        assert d["task_id"] == "task-1"
        assert d["session_id"] == "sess-abc"
        assert d["session_name"] == "wfo-task-1"
        assert d["branch"] == "claude/task-1"
        assert d["status"] == "running"
        assert d["prompt_file"] == "/tmp/prompt.md"

    def test_from_dict(self):
        """SessionRecord should deserialize from dictionary."""
        data = {
            "task_id": "task-2",
            "session_id": "sess-xyz",
            "session_name": "wfo-task-2",
            "branch": "claude/task-2",
            "status": "completed",
            "created_at": "2026-01-09T10:00:00+00:00",
            "updated_at": "2026-01-09T11:00:00+00:00",
            "prompt_file": None
        }

        record = SessionRecord.from_dict(data)

        assert record.task_id == "task-2"
        assert record.session_id == "sess-xyz"
        assert record.status == "completed"
        assert record.prompt_file is None


class TestSessionRegistry:
    """Tests for SessionRegistry persistence."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temporary working directory."""
        return tmp_path

    @pytest.fixture
    def registry(self, temp_dir):
        """Create a SessionRegistry instance."""
        return SessionRegistry(temp_dir)

    def test_init_creates_directory(self, temp_dir):
        """Registry should create .claude directory on init."""
        registry = SessionRegistry(temp_dir)
        assert (temp_dir / ".claude").exists()

    def test_register_and_get(self, registry):
        """Should register and retrieve sessions."""
        record = SessionRecord(
            task_id="task-1",
            session_id="sess-abc",
            session_name="wfo-task-1",
            branch="claude/task-1",
            status="running",
            created_at="2026-01-09T10:00:00+00:00",
            updated_at="2026-01-09T10:00:00+00:00"
        )

        registry.register(record)
        retrieved = registry.get("task-1")

        assert retrieved is not None
        assert retrieved.task_id == "task-1"
        assert retrieved.session_id == "sess-abc"
        assert retrieved.status == "running"

    def test_get_returns_none_for_missing(self, registry):
        """Should return None for non-existent task."""
        result = registry.get("nonexistent")
        assert result is None

    def test_update_status(self, registry):
        """Should update session status."""
        record = SessionRecord(
            task_id="task-1",
            session_id="sess-abc",
            session_name="wfo-task-1",
            branch="claude/task-1",
            status="running",
            created_at="2026-01-09T10:00:00+00:00",
            updated_at="2026-01-09T10:00:00+00:00"
        )
        registry.register(record)

        registry.update_status("task-1", "completed")

        updated = registry.get("task-1")
        assert updated.status == "completed"
        # updated_at should have changed
        assert updated.updated_at != record.updated_at

    def test_list_active(self, registry):
        """Should list only active sessions."""
        records = [
            SessionRecord(
                task_id="task-1", session_id="s1", session_name="wfo-1",
                branch="b1", status="running",
                created_at="2026-01-09T10:00:00+00:00",
                updated_at="2026-01-09T10:00:00+00:00"
            ),
            SessionRecord(
                task_id="task-2", session_id="s2", session_name="wfo-2",
                branch="b2", status="completed",
                created_at="2026-01-09T10:00:00+00:00",
                updated_at="2026-01-09T10:00:00+00:00"
            ),
            SessionRecord(
                task_id="task-3", session_id="s3", session_name="wfo-3",
                branch="b3", status="pending",
                created_at="2026-01-09T10:00:00+00:00",
                updated_at="2026-01-09T10:00:00+00:00"
            ),
        ]

        for r in records:
            registry.register(r)

        active = registry.list_active()

        assert len(active) == 2
        task_ids = {r.task_id for r in active}
        assert task_ids == {"task-1", "task-3"}

    def test_persistence_across_instances(self, temp_dir):
        """Registry should persist data across instances."""
        # First instance - register
        registry1 = SessionRegistry(temp_dir)
        record = SessionRecord(
            task_id="persist-test",
            session_id="sess-persist",
            session_name="wfo-persist",
            branch="claude/persist",
            status="running",
            created_at="2026-01-09T10:00:00+00:00",
            updated_at="2026-01-09T10:00:00+00:00"
        )
        registry1.register(record)

        # Second instance - should see the same data
        registry2 = SessionRegistry(temp_dir)
        retrieved = registry2.get("persist-test")

        assert retrieved is not None
        assert retrieved.session_id == "sess-persist"

    def test_reconcile_marks_orphaned(self, registry):
        """Reconcile should mark missing sessions as orphaned."""
        # Register a session
        record = SessionRecord(
            task_id="orphan-test",
            session_id="sess-orphan",
            session_name="wfo-orphan-test",
            branch="claude/orphan",
            status="running",
            created_at="2026-01-09T10:00:00+00:00",
            updated_at="2026-01-09T10:00:00+00:00"
        )
        registry.register(record)

        # Reconcile with empty squad sessions (session not found)
        registry.reconcile([])

        updated = registry.get("orphan-test")
        assert updated.status == "orphaned"

    def test_reconcile_keeps_existing(self, registry):
        """Reconcile should keep sessions that exist in squad."""
        record = SessionRecord(
            task_id="keep-test",
            session_id="sess-keep",
            session_name="wfo-keep-test",
            branch="claude/keep",
            status="running",
            created_at="2026-01-09T10:00:00+00:00",
            updated_at="2026-01-09T10:00:00+00:00"
        )
        registry.register(record)

        # Reconcile with session present
        registry.reconcile([{"name": "wfo-keep-test", "status": "running"}])

        updated = registry.get("keep-test")
        assert updated.status == "running"

    def test_cleanup_old_removes_stale(self, registry):
        """Cleanup should remove old completed sessions."""
        # Create an old completed session
        old_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        record = SessionRecord(
            task_id="old-task",
            session_id="sess-old",
            session_name="wfo-old",
            branch="claude/old",
            status="completed",
            created_at=old_time,
            updated_at=old_time
        )
        registry.register(record)

        # Cleanup with 7 day threshold
        removed = registry.cleanup_old(days=7)

        assert removed == 1
        assert registry.get("old-task") is None

    def test_cleanup_keeps_recent(self, registry):
        """Cleanup should keep recent sessions."""
        now = datetime.now(timezone.utc).isoformat()
        record = SessionRecord(
            task_id="recent-task",
            session_id="sess-recent",
            session_name="wfo-recent",
            branch="claude/recent",
            status="completed",
            created_at=now,
            updated_at=now
        )
        registry.register(record)

        removed = registry.cleanup_old(days=7)

        assert removed == 0
        assert registry.get("recent-task") is not None

    def test_remove(self, registry):
        """Should remove a session record."""
        record = SessionRecord(
            task_id="remove-test",
            session_id="sess-remove",
            session_name="wfo-remove",
            branch="claude/remove",
            status="running",
            created_at="2026-01-09T10:00:00+00:00",
            updated_at="2026-01-09T10:00:00+00:00"
        )
        registry.register(record)

        result = registry.remove("remove-test")

        assert result is True
        assert registry.get("remove-test") is None

    def test_remove_nonexistent(self, registry):
        """Remove should return False for nonexistent task."""
        result = registry.remove("nonexistent")
        assert result is False

    def test_list_all(self, registry):
        """Should list all sessions regardless of status."""
        records = [
            SessionRecord(
                task_id=f"task-{i}", session_id=f"s{i}", session_name=f"wfo-{i}",
                branch=f"b{i}", status=status,
                created_at="2026-01-09T10:00:00+00:00",
                updated_at="2026-01-09T10:00:00+00:00"
            )
            for i, status in enumerate(["running", "completed", "orphaned", "pending"])
        ]

        for r in records:
            registry.register(r)

        all_sessions = registry.list_all()
        assert len(all_sessions) == 4
