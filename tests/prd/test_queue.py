"""
Tests for the job queue system.
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from src.prd.queue import (
    JobQueue,
    FileJobQueue,
    JobMessage,
    JobStatus,
)


class TestFileJobQueue:
    """Tests for file-based job queue."""

    @pytest.fixture
    def temp_queue_dir(self):
        """Create a temporary directory for the queue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def queue(self, temp_queue_dir):
        """Create a FileJobQueue instance."""
        return FileJobQueue(queue_dir=temp_queue_dir)

    def test_enqueue_creates_job_file(self, queue, temp_queue_dir):
        """Enqueueing a job should create a file."""
        job = JobMessage(
            job_id="job-1",
            task_id="t1",
            prd_id="prd-1",
            prompt="Test prompt",
        )
        queue.enqueue(job)

        # Check file exists
        pending_dir = temp_queue_dir / "pending"
        assert pending_dir.exists()
        assert len(list(pending_dir.glob("*.json"))) == 1

    def test_dequeue_returns_oldest_job(self, queue):
        """Dequeueing should return the oldest pending job."""
        job1 = JobMessage(job_id="job-1", task_id="t1", prd_id="prd-1", prompt="First")
        job2 = JobMessage(job_id="job-2", task_id="t2", prd_id="prd-1", prompt="Second")

        queue.enqueue(job1)
        queue.enqueue(job2)

        dequeued = queue.dequeue()
        assert dequeued is not None
        assert dequeued.job_id == "job-1"

    def test_dequeue_returns_none_when_empty(self, queue):
        """Dequeueing an empty queue should return None."""
        assert queue.dequeue() is None

    def test_dequeue_moves_job_to_processing(self, queue, temp_queue_dir):
        """Dequeueing should move job from pending to processing."""
        job = JobMessage(job_id="job-1", task_id="t1", prd_id="prd-1", prompt="Test")
        queue.enqueue(job)

        queue.dequeue()

        pending_dir = temp_queue_dir / "pending"
        processing_dir = temp_queue_dir / "processing"
        assert len(list(pending_dir.glob("*.json"))) == 0
        assert len(list(processing_dir.glob("*.json"))) == 1

    def test_complete_job(self, queue, temp_queue_dir):
        """Completing a job should move it to completed."""
        job = JobMessage(job_id="job-1", task_id="t1", prd_id="prd-1", prompt="Test")
        queue.enqueue(job)
        queue.dequeue()

        queue.complete(job.job_id, success=True, result={"branch": "test-branch"})

        completed_dir = temp_queue_dir / "completed"
        assert len(list(completed_dir.glob("*.json"))) == 1

    def test_fail_job(self, queue, temp_queue_dir):
        """Failing a job should move it to failed."""
        job = JobMessage(job_id="job-1", task_id="t1", prd_id="prd-1", prompt="Test")
        queue.enqueue(job)
        queue.dequeue()

        queue.fail(job.job_id, error="Something went wrong")

        failed_dir = temp_queue_dir / "failed"
        assert len(list(failed_dir.glob("*.json"))) == 1

    def test_get_pending_count(self, queue):
        """Should return count of pending jobs."""
        assert queue.pending_count() == 0

        queue.enqueue(JobMessage(job_id="j1", task_id="t1", prd_id="p1", prompt="1"))
        queue.enqueue(JobMessage(job_id="j2", task_id="t2", prd_id="p1", prompt="2"))

        assert queue.pending_count() == 2

    def test_get_processing_count(self, queue):
        """Should return count of processing jobs."""
        queue.enqueue(JobMessage(job_id="j1", task_id="t1", prd_id="p1", prompt="1"))
        queue.enqueue(JobMessage(job_id="j2", task_id="t2", prd_id="p1", prompt="2"))

        queue.dequeue()
        assert queue.processing_count() == 1
        assert queue.pending_count() == 1

    def test_list_completed_jobs(self, queue):
        """Should list completed jobs."""
        job = JobMessage(job_id="j1", task_id="t1", prd_id="p1", prompt="1")
        queue.enqueue(job)
        queue.dequeue()
        queue.complete(job.job_id, success=True)

        completed = queue.list_completed()
        assert len(completed) == 1
        assert completed[0].job_id == "j1"

    def test_queue_is_empty(self, queue):
        """Should detect when queue is empty."""
        assert queue.is_empty()

        queue.enqueue(JobMessage(job_id="j1", task_id="t1", prd_id="p1", prompt="1"))
        assert not queue.is_empty()

    def test_get_job_by_id(self, queue):
        """Should retrieve a job by ID."""
        job = JobMessage(job_id="j1", task_id="t1", prd_id="p1", prompt="1")
        queue.enqueue(job)

        retrieved = queue.get_job("j1")
        assert retrieved is not None
        assert retrieved.job_id == "j1"

    def test_get_job_not_found(self, queue):
        """Should return None for non-existent job."""
        assert queue.get_job("nonexistent") is None

    def test_clear_completed(self, queue):
        """Should clear completed jobs."""
        job = JobMessage(job_id="j1", task_id="t1", prd_id="p1", prompt="1")
        queue.enqueue(job)
        queue.dequeue()
        queue.complete(job.job_id, success=True)

        assert len(queue.list_completed()) == 1
        queue.clear_completed()
        assert len(queue.list_completed()) == 0


class TestJobQueueInterface:
    """Tests for the JobQueue interface."""

    def test_interface_methods(self):
        """JobQueue should define all required methods."""
        required_methods = [
            "enqueue",
            "dequeue",
            "complete",
            "fail",
            "pending_count",
            "processing_count",
            "is_empty",
            "get_job",
        ]

        for method in required_methods:
            assert hasattr(JobQueue, method)
