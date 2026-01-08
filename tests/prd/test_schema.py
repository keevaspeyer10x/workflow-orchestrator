"""
Tests for PRD schema and data models.
"""

import pytest
from dataclasses import asdict
from datetime import datetime

from src.prd.schema import (
    # Enums
    TaskStatus,
    WorkerBackend,
    # Config
    PRDConfig,
    BackendConfig,
    LocalBackendConfig,
    ModalBackendConfig,
    RenderBackendConfig,
    # Task models
    PRDTask,
    PRDDocument,
    TaskResult,
    # Queue models
    JobMessage,
    JobStatus,
)


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_pending_is_default(self):
        """PENDING should be a valid status."""
        assert TaskStatus.PENDING.value == "pending"

    def test_all_statuses_exist(self):
        """All expected statuses should exist."""
        expected = ["pending", "assigned", "running", "completed", "failed", "cancelled"]
        actual = [s.value for s in TaskStatus]
        assert set(expected) == set(actual)


class TestWorkerBackend:
    """Tests for WorkerBackend enum."""

    def test_all_backends_exist(self):
        """All worker backends should be defined."""
        expected = ["auto", "local", "modal", "render", "github_actions", "manual"]
        actual = [b.value for b in WorkerBackend]
        assert set(expected) == set(actual)


class TestPRDConfig:
    """Tests for PRDConfig."""

    def test_default_config(self):
        """Default config should have sensible values."""
        config = PRDConfig()
        assert config.enabled is False
        assert config.worker_backend == WorkerBackend.AUTO
        assert config.auto_scale is True
        assert config.checkpoint_interval == 5
        assert config.max_concurrent_agents == 20

    def test_custom_config(self):
        """Custom config values should be respected."""
        config = PRDConfig(
            enabled=True,
            worker_backend=WorkerBackend.MODAL,
            auto_scale=False,
            checkpoint_interval=10,
            max_concurrent_agents=50,
        )
        assert config.enabled is True
        assert config.worker_backend == WorkerBackend.MODAL
        assert config.auto_scale is False
        assert config.checkpoint_interval == 10
        assert config.max_concurrent_agents == 50

    def test_backend_configs(self):
        """Backend-specific configs should be accessible."""
        config = PRDConfig(
            backends=BackendConfig(
                local=LocalBackendConfig(max_parallel=8),
                modal=ModalBackendConfig(max_parallel=100),
            )
        )
        assert config.backends.local.max_parallel == 8
        assert config.backends.modal.max_parallel == 100


class TestPRDTask:
    """Tests for PRDTask."""

    def test_create_task(self):
        """Should create a task with required fields."""
        task = PRDTask(
            id="task-1",
            description="Implement user authentication",
        )
        assert task.id == "task-1"
        assert task.description == "Implement user authentication"
        assert task.status == TaskStatus.PENDING
        assert task.dependencies == []
        assert task.agent_id is None
        assert task.branch is None

    def test_task_with_dependencies(self):
        """Tasks can have dependencies."""
        task = PRDTask(
            id="task-2",
            description="Add login form",
            dependencies=["task-1"],
        )
        assert task.dependencies == ["task-1"]

    def test_task_is_ready_no_deps(self):
        """Task with no dependencies is always ready."""
        task = PRDTask(id="t1", description="Test")
        assert task.is_ready(completed_tasks=set())

    def test_task_is_ready_with_completed_deps(self):
        """Task is ready when all dependencies are completed."""
        task = PRDTask(id="t2", description="Test", dependencies=["t1"])
        assert not task.is_ready(completed_tasks=set())
        assert task.is_ready(completed_tasks={"t1"})

    def test_task_not_ready_with_pending_deps(self):
        """Task is not ready when dependencies are pending."""
        task = PRDTask(id="t3", description="Test", dependencies=["t1", "t2"])
        assert not task.is_ready(completed_tasks={"t1"})
        assert task.is_ready(completed_tasks={"t1", "t2"})


class TestPRDDocument:
    """Tests for PRDDocument."""

    def test_create_prd(self):
        """Should create a PRD with tasks."""
        prd = PRDDocument(
            id="prd-1",
            title="E-commerce Platform",
            tasks=[
                PRDTask(id="t1", description="Set up database"),
                PRDTask(id="t2", description="Create user model", dependencies=["t1"]),
            ],
        )
        assert prd.id == "prd-1"
        assert prd.title == "E-commerce Platform"
        assert len(prd.tasks) == 2

    def test_get_ready_tasks(self):
        """Should return tasks that are ready to execute."""
        prd = PRDDocument(
            id="prd-1",
            title="Test",
            tasks=[
                PRDTask(id="t1", description="First"),
                PRDTask(id="t2", description="Second", dependencies=["t1"]),
                PRDTask(id="t3", description="Third", dependencies=["t2"]),
            ],
        )

        # Initially only t1 is ready
        ready = prd.get_ready_tasks()
        assert [t.id for t in ready] == ["t1"]

        # After t1 completes, t2 is ready
        prd.tasks[0].status = TaskStatus.COMPLETED
        ready = prd.get_ready_tasks()
        assert [t.id for t in ready] == ["t2"]

    def test_get_task_by_id(self):
        """Should find task by ID."""
        prd = PRDDocument(
            id="prd-1",
            title="Test",
            tasks=[PRDTask(id="t1", description="First")],
        )
        assert prd.get_task("t1") is not None
        assert prd.get_task("nonexistent") is None

    def test_integration_branch_name(self):
        """Should generate correct integration branch name."""
        prd = PRDDocument(id="prd-ecommerce", title="Test", tasks=[])
        assert prd.integration_branch == "integration/prd-ecommerce"

    def test_all_complete(self):
        """Should detect when all tasks are complete."""
        prd = PRDDocument(
            id="prd-1",
            title="Test",
            tasks=[
                PRDTask(id="t1", description="First"),
                PRDTask(id="t2", description="Second"),
            ],
        )
        assert not prd.all_complete()

        prd.tasks[0].status = TaskStatus.COMPLETED
        assert not prd.all_complete()

        prd.tasks[1].status = TaskStatus.COMPLETED
        assert prd.all_complete()


class TestJobMessage:
    """Tests for JobMessage (queue messages)."""

    def test_create_job(self):
        """Should create a job message."""
        job = JobMessage(
            job_id="job-1",
            task_id="t1",
            prd_id="prd-1",
            prompt="Implement the feature",
        )
        assert job.job_id == "job-1"
        assert job.status == JobStatus.PENDING
        assert job.created_at is not None

    def test_job_serialization(self):
        """Job should be serializable to dict."""
        job = JobMessage(
            job_id="job-1",
            task_id="t1",
            prd_id="prd-1",
            prompt="Test",
        )
        data = job.to_dict()
        assert data["job_id"] == "job-1"
        assert data["task_id"] == "t1"

    def test_job_deserialization(self):
        """Job should be deserializable from dict."""
        data = {
            "job_id": "job-1",
            "task_id": "t1",
            "prd_id": "prd-1",
            "prompt": "Test",
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }
        job = JobMessage.from_dict(data)
        assert job.job_id == "job-1"
        assert job.status == JobStatus.PENDING


class TestTaskResult:
    """Tests for TaskResult."""

    def test_success_result(self):
        """Should create a success result."""
        result = TaskResult(
            task_id="t1",
            success=True,
            branch="claude/t1-abc123",
            commit_sha="abc123",
        )
        assert result.success is True
        assert result.error is None

    def test_failure_result(self):
        """Should create a failure result."""
        result = TaskResult(
            task_id="t1",
            success=False,
            error="Build failed",
        )
        assert result.success is False
        assert result.error == "Build failed"
