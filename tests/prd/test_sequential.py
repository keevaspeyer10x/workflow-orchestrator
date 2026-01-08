"""
Tests for sequential execution backend.

Tests cover:
- Environment detection
- Sequential task yielding
- Task completion tracking
"""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch


class TestEnvironmentDetection:
    """Tests for detecting Claude Code environment."""

    def test_detects_claude_code_env_var(self):
        """Detects CLAUDE_CODE=1 environment variable."""
        from src.prd._deprecated.sequential import is_inside_claude_code

        with patch.dict(os.environ, {'CLAUDE_CODE': '1'}, clear=True):
            assert is_inside_claude_code() is True

    def test_detects_claudecode_env_var(self):
        """Detects CLAUDECODE=1 environment variable (no underscore)."""
        from src.prd._deprecated.sequential import is_inside_claude_code

        with patch.dict(os.environ, {'CLAUDECODE': '1'}, clear=True):
            assert is_inside_claude_code() is True

    def test_detects_claude_code_entrypoint(self):
        """Detects CLAUDE_CODE_ENTRYPOINT environment variable."""
        from src.prd._deprecated.sequential import is_inside_claude_code

        with patch.dict(os.environ, {'CLAUDE_CODE_ENTRYPOINT': 'cli'}, clear=True):
            assert is_inside_claude_code() is True

    def test_detects_claude_in_path(self):
        """Detects 'claude' in the command path."""
        from src.prd._deprecated.sequential import is_inside_claude_code

        with patch.dict(os.environ, {'_': '/usr/bin/claude'}, clear=True):
            assert is_inside_claude_code() is True

    def test_returns_false_outside_claude(self):
        """Returns False when not in Claude Code."""
        from src.prd._deprecated.sequential import is_inside_claude_code

        with patch.dict(os.environ, {'_': '/usr/bin/python'}, clear=True):
            assert is_inside_claude_code() is False


class TestSequentialBackend:
    """Tests for SequentialBackend."""

    @pytest.fixture
    def backend(self):
        """Create a SequentialBackend."""
        from src.prd._deprecated.sequential import SequentialBackend
        return SequentialBackend()

    @pytest.fixture
    def sample_job(self):
        """Create a sample job message."""
        from src.prd.schema import JobMessage
        return JobMessage(
            job_id="job-123",
            task_id="task-1",
            prd_id="prd-test",
            prompt="Implement feature X",
        )

    def test_spawn_returns_starting_handle(self, backend, sample_job):
        """Spawn returns a handle with starting status."""
        from src.prd.backends.base import WorkerStatus

        handle = backend.spawn(sample_job)

        assert handle is not None
        assert handle.status == WorkerStatus.STARTING
        assert handle.manual_instructions is not None

    def test_spawn_includes_prompt(self, backend, sample_job):
        """Spawned handle includes the task prompt."""
        handle = backend.spawn(sample_job)

        assert sample_job.prompt in handle.manual_instructions
        assert sample_job.task_id in handle.manual_instructions

    def test_get_pending_tasks(self, backend, sample_job):
        """Can get list of pending tasks."""
        backend.spawn(sample_job)

        pending = backend.get_pending_tasks()

        assert len(pending) == 1
        assert pending[0].task_id == sample_job.task_id

    def test_mark_task_complete(self, backend, sample_job):
        """Can mark a task as complete."""
        from src.prd.backends.base import WorkerStatus

        handle = backend.spawn(sample_job)
        backend.mark_complete(handle.worker_id, branch="main", commit_sha="abc123")

        status = backend.get_status(handle)
        assert status == WorkerStatus.COMPLETED

    def test_mark_task_failed(self, backend, sample_job):
        """Can mark a task as failed."""
        from src.prd.backends.base import WorkerStatus

        handle = backend.spawn(sample_job)
        backend.mark_failed(handle.worker_id, error="Test failed")

        status = backend.get_status(handle)
        assert status == WorkerStatus.FAILED

    def test_is_available_always_true(self, backend):
        """Sequential backend is always available."""
        assert backend.is_available() is True

    def test_max_parallel_is_one(self, backend):
        """Max parallel is 1 for sequential execution."""
        assert backend.max_parallel() == 1


class TestSequentialExecutionFlow:
    """Tests for the full sequential execution flow."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temp directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_sequential_mode_queues_tasks(self, temp_dir):
        """In sequential mode, tasks are queued not executed."""
        from src.prd._deprecated.sequential import SequentialBackend
        from src.prd.schema import JobMessage

        backend = SequentialBackend()

        jobs = [
            JobMessage(job_id=f"job-{i}", task_id=f"task-{i}", prd_id="prd", prompt=f"Task {i}")
            for i in range(3)
        ]

        for job in jobs:
            backend.spawn(job)

        # All should be pending
        pending = backend.get_pending_tasks()
        assert len(pending) == 3

    def test_get_next_task_returns_first_pending(self, temp_dir):
        """get_next_task returns the first pending task."""
        from src.prd._deprecated.sequential import SequentialBackend
        from src.prd.schema import JobMessage

        backend = SequentialBackend()

        backend.spawn(JobMessage(job_id="j1", task_id="t1", prd_id="p", prompt="First"))
        backend.spawn(JobMessage(job_id="j2", task_id="t2", prd_id="p", prompt="Second"))

        next_task = backend.get_next_task()
        assert next_task is not None
        assert next_task.task_id == "t1"
