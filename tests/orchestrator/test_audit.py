"""
Day 9: Audit Logging Tests

Tests for audit logging system and API endpoints.
"""

import pytest
from pathlib import Path
import json
import time

from src.orchestrator.audit import AuditEntry, AuditLogger


class TestAuditEntry:
    """Tests for AuditEntry"""

    def test_create_audit_entry(self):
        """Should create audit entry with all fields"""
        entry = AuditEntry(
            task_id="task-123",
            phase="PLAN",
            tool_name="read_files",
            args={"path": "/test/file.txt"},
            result={"content": "test content"},
            duration_ms=15.5,
            success=True
        )

        assert entry.task_id == "task-123"
        assert entry.phase == "PLAN"
        assert entry.tool_name == "read_files"
        assert entry.success is True
        assert entry.duration_ms == 15.5
        assert entry.timestamp is not None

    def test_audit_entry_to_dict(self):
        """Should convert audit entry to dict"""
        entry = AuditEntry(
            task_id="task-456",
            phase="IMPL",
            tool_name="write_files",
            args={"path": "/output.txt"},
            success=True
        )

        data = entry.to_dict()

        assert isinstance(data, dict)
        assert data["task_id"] == "task-456"
        assert data["phase"] == "IMPL"
        assert data["tool_name"] == "write_files"
        assert "timestamp" in data

    def test_audit_entry_to_json(self):
        """Should convert audit entry to JSON string"""
        entry = AuditEntry(
            task_id="task-789",
            phase="TDD",
            tool_name="bash",
            args={"command": "pytest"},
            success=True
        )

        json_str = entry.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["task_id"] == "task-789"
        assert parsed["tool_name"] == "bash"

    def test_failed_execution_entry(self):
        """Should create entry for failed execution"""
        entry = AuditEntry(
            task_id="task-fail",
            phase="PLAN",
            tool_name="read_files",
            args={"path": "/nonexistent.txt"},
            duration_ms=5.0,
            success=False,
            error="File not found"
        )

        assert entry.success is False
        assert entry.error == "File not found"
        assert entry.result is None


class TestAuditLogger:
    """Tests for AuditLogger"""

    def test_logger_creates_log_file(self, tmp_path):
        """Should create log file on first write"""
        log_file = tmp_path / "test_audit.jsonl"
        logger = AuditLogger(log_file)

        entry = AuditEntry(
            task_id="task-001",
            phase="PLAN",
            tool_name="read_files",
            args={"path": "/test.txt"},
            success=True
        )

        logger.log(entry)

        assert log_file.exists()

    def test_log_tool_execution_convenience_method(self, tmp_path):
        """Should log tool execution using convenience method"""
        log_file = tmp_path / "test_audit.jsonl"
        logger = AuditLogger(log_file)

        logger.log_tool_execution(
            task_id="task-002",
            phase="IMPL",
            tool_name="write_files",
            args={"path": "/output.txt", "content": "test"},
            result={"status": "success"},
            duration_ms=12.3,
            success=True
        )

        assert log_file.exists()

        # Verify log content
        with open(log_file, 'r') as f:
            line = f.readline()
            data = json.loads(line)

        assert data["task_id"] == "task-002"
        assert data["tool_name"] == "write_files"
        assert data["success"] is True

    def test_log_multiple_entries(self, tmp_path):
        """Should log multiple entries"""
        log_file = tmp_path / "test_audit.jsonl"
        logger = AuditLogger(log_file)

        for i in range(5):
            logger.log_tool_execution(
                task_id=f"task-{i}",
                phase="PLAN",
                tool_name="read_files",
                args={"path": f"/file{i}.txt"},
                success=True
            )

        # Should have 5 lines
        with open(log_file, 'r') as f:
            lines = f.readlines()

        assert len(lines) == 5

    def test_query_by_task_id(self, tmp_path):
        """Should query entries by task ID"""
        log_file = tmp_path / "test_audit.jsonl"
        logger = AuditLogger(log_file)

        # Log entries for different tasks
        logger.log_tool_execution(task_id="task-A", phase="PLAN", tool_name="read_files", args={}, success=True)
        logger.log_tool_execution(task_id="task-B", phase="PLAN", tool_name="read_files", args={}, success=True)
        logger.log_tool_execution(task_id="task-A", phase="IMPL", tool_name="write_files", args={}, success=True)

        results = logger.query(task_id="task-A")

        assert len(results) == 2
        assert all(entry["task_id"] == "task-A" for entry in results)

    def test_query_by_phase(self, tmp_path):
        """Should query entries by phase"""
        log_file = tmp_path / "test_audit.jsonl"
        logger = AuditLogger(log_file)

        logger.log_tool_execution(task_id="task-1", phase="PLAN", tool_name="read_files", args={}, success=True)
        logger.log_tool_execution(task_id="task-2", phase="IMPL", tool_name="write_files", args={}, success=True)
        logger.log_tool_execution(task_id="task-3", phase="PLAN", tool_name="grep", args={}, success=True)

        results = logger.query(phase="PLAN")

        assert len(results) == 2
        assert all(entry["phase"] == "PLAN" for entry in results)

    def test_query_by_tool_name(self, tmp_path):
        """Should query entries by tool name"""
        log_file = tmp_path / "test_audit.jsonl"
        logger = AuditLogger(log_file)

        logger.log_tool_execution(task_id="task-1", phase="PLAN", tool_name="read_files", args={}, success=True)
        logger.log_tool_execution(task_id="task-2", phase="PLAN", tool_name="grep", args={}, success=True)
        logger.log_tool_execution(task_id="task-3", phase="PLAN", tool_name="read_files", args={}, success=True)

        results = logger.query(tool_name="read_files")

        assert len(results) == 2
        assert all(entry["tool_name"] == "read_files" for entry in results)

    def test_query_by_success_status(self, tmp_path):
        """Should query entries by success status"""
        log_file = tmp_path / "test_audit.jsonl"
        logger = AuditLogger(log_file)

        logger.log_tool_execution(task_id="task-1", phase="PLAN", tool_name="read_files", args={}, success=True)
        logger.log_tool_execution(task_id="task-2", phase="PLAN", tool_name="read_files", args={}, success=False, error="Failed")
        logger.log_tool_execution(task_id="task-3", phase="PLAN", tool_name="read_files", args={}, success=True)

        # Query failures
        failures = logger.query(success=False)
        assert len(failures) == 1
        assert failures[0]["task_id"] == "task-2"

        # Query successes
        successes = logger.query(success=True)
        assert len(successes) == 2

    def test_query_with_limit(self, tmp_path):
        """Should respect query limit"""
        log_file = tmp_path / "test_audit.jsonl"
        logger = AuditLogger(log_file)

        for i in range(10):
            logger.log_tool_execution(
                task_id=f"task-{i}",
                phase="PLAN",
                tool_name="read_files",
                args={},
                success=True
            )

        results = logger.query(limit=5)

        assert len(results) == 5

    def test_query_multiple_filters(self, tmp_path):
        """Should combine multiple query filters"""
        log_file = tmp_path / "test_audit.jsonl"
        logger = AuditLogger(log_file)

        logger.log_tool_execution(task_id="task-1", phase="PLAN", tool_name="read_files", args={}, success=True)
        logger.log_tool_execution(task_id="task-1", phase="PLAN", tool_name="grep", args={}, success=True)
        logger.log_tool_execution(task_id="task-2", phase="PLAN", tool_name="read_files", args={}, success=True)
        logger.log_tool_execution(task_id="task-1", phase="IMPL", tool_name="read_files", args={}, success=True)

        results = logger.query(task_id="task-1", phase="PLAN", tool_name="read_files")

        assert len(results) == 1
        assert results[0]["task_id"] == "task-1"
        assert results[0]["phase"] == "PLAN"
        assert results[0]["tool_name"] == "read_files"

    def test_get_recent_entries(self, tmp_path):
        """Should get most recent entries"""
        log_file = tmp_path / "test_audit.jsonl"
        logger = AuditLogger(log_file)

        for i in range(10):
            logger.log_tool_execution(
                task_id=f"task-{i}",
                phase="PLAN",
                tool_name="read_files",
                args={},
                success=True
            )
            time.sleep(0.001)  # Small delay to ensure different timestamps

        recent = logger.get_recent(count=3)

        assert len(recent) == 3
        # Should be in reverse order (newest first)
        assert recent[0]["task_id"] == "task-9"
        assert recent[1]["task_id"] == "task-8"
        assert recent[2]["task_id"] == "task-7"

    def test_get_stats(self, tmp_path):
        """Should calculate audit log statistics"""
        log_file = tmp_path / "test_audit.jsonl"
        logger = AuditLogger(log_file)

        # Log 7 successes
        for i in range(7):
            logger.log_tool_execution(
                task_id=f"task-{i}",
                phase="PLAN" if i < 4 else "IMPL",
                tool_name="read_files" if i < 5 else "write_files",
                args={},
                success=True
            )

        # Log 3 failures
        for i in range(3):
            logger.log_tool_execution(
                task_id=f"task-fail-{i}",
                phase="PLAN",
                tool_name="bash",
                args={},
                success=False,
                error="Failed"
            )

        stats = logger.get_stats()

        assert stats["total_entries"] == 10
        assert stats["total_successes"] == 7
        assert stats["total_failures"] == 3
        assert stats["success_rate"] == 0.7
        assert stats["tools_used"]["read_files"] == 5
        assert stats["tools_used"]["write_files"] == 2
        assert stats["tools_used"]["bash"] == 3
        assert stats["phases"]["PLAN"] == 7
        assert stats["phases"]["IMPL"] == 3

    def test_stats_empty_log(self, tmp_path):
        """Should return zero stats for empty log"""
        log_file = tmp_path / "empty_audit.jsonl"
        logger = AuditLogger(log_file)

        stats = logger.get_stats()

        assert stats["total_entries"] == 0
        assert stats["total_successes"] == 0
        assert stats["total_failures"] == 0
        assert stats["tools_used"] == {}
        assert stats["phases"] == {}

    def test_thread_safety(self, tmp_path):
        """Should handle concurrent logging safely"""
        import threading

        log_file = tmp_path / "concurrent_audit.jsonl"
        logger = AuditLogger(log_file)

        def log_entries(thread_id):
            for i in range(10):
                logger.log_tool_execution(
                    task_id=f"task-{thread_id}-{i}",
                    phase="PLAN",
                    tool_name="read_files",
                    args={},
                    success=True
                )

        # Create multiple threads
        threads = [threading.Thread(target=log_entries, args=(i,)) for i in range(5)]

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Should have 50 entries (5 threads * 10 entries)
        with open(log_file, 'r') as f:
            lines = f.readlines()

        assert len(lines) == 50
