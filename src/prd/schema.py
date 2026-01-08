"""
PRD schema and data models.

Defines the structure for PRD documents, tasks, configuration,
and job queue messages.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any


class TaskStatus(str, Enum):
    """Status of a PRD task."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkerBackend(str, Enum):
    """Available worker backends."""

    AUTO = "auto"
    LOCAL = "local"
    MODAL = "modal"
    RENDER = "render"
    GITHUB_ACTIONS = "github_actions"
    MANUAL = "manual"


class JobStatus(str, Enum):
    """Status of a job in the queue."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class LocalBackendConfig:
    """Configuration for local worker backend."""

    max_parallel: int = 4
    timeout_minutes: int = 30


@dataclass
class ModalBackendConfig:
    """Configuration for Modal serverless backend."""

    enabled: bool = True
    max_parallel: int = 50
    timeout_minutes: int = 30
    gpu: Optional[str] = None  # e.g., "T4" for GPU workloads


@dataclass
class RenderBackendConfig:
    """Configuration for Render backend."""

    enabled: bool = True
    max_parallel: int = 20
    instance_type: str = "standard"
    region: str = "oregon"


@dataclass
class GitHubActionsConfig:
    """Configuration for GitHub Actions backend."""

    enabled: bool = True
    max_parallel: int = 10
    workflow_file: str = ".github/workflows/prd-worker.yml"


@dataclass
class BackendConfig:
    """Configuration for all worker backends."""

    local: LocalBackendConfig = field(default_factory=LocalBackendConfig)
    modal: ModalBackendConfig = field(default_factory=ModalBackendConfig)
    render: RenderBackendConfig = field(default_factory=RenderBackendConfig)
    github_actions: GitHubActionsConfig = field(default_factory=GitHubActionsConfig)


@dataclass
class PRDConfig:
    """Configuration for PRD execution mode."""

    # Master switch
    enabled: bool = False

    # Worker selection
    worker_backend: WorkerBackend = WorkerBackend.AUTO
    auto_scale: bool = True

    # Execution settings
    checkpoint_interval: int = 5  # Create checkpoint PR every N completed features
    max_concurrent_agents: int = 20
    cluster_resolution_timeout_minutes: int = 30

    # Integration branch settings
    auto_merge_to_integration: bool = True
    require_human_for_main: bool = True

    # Backend-specific configs
    backends: BackendConfig = field(default_factory=BackendConfig)


# =============================================================================
# Task Models
# =============================================================================


@dataclass
class PRDTask:
    """A single task within a PRD."""

    id: str
    description: str
    dependencies: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    agent_id: Optional[str] = None
    branch: Optional[str] = None
    commit_sha: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None  # Additional task info (e.g., expected files)

    def is_ready(self, completed_tasks: set[str]) -> bool:
        """Check if this task is ready to execute (all dependencies met)."""
        if self.status != TaskStatus.PENDING:
            return False
        return all(dep in completed_tasks for dep in self.dependencies)

    def mark_running(self, agent_id: str, branch: str) -> None:
        """Mark task as running."""
        self.status = TaskStatus.RUNNING
        self.agent_id = agent_id
        self.branch = branch
        self.started_at = lambda: datetime.now(timezone.utc)()

    def mark_completed(self, commit_sha: str) -> None:
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
        self.commit_sha = commit_sha
        self.completed_at = lambda: datetime.now(timezone.utc)()

    def mark_failed(self, error: str) -> None:
        """Mark task as failed."""
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = lambda: datetime.now(timezone.utc)()


@dataclass
class PRDDocument:
    """A PRD document containing multiple tasks."""

    id: str
    title: str
    tasks: list[PRDTask] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def integration_branch(self) -> str:
        """Get the integration branch name for this PRD."""
        return f"integration/{self.id}"

    def get_task(self, task_id: str) -> Optional[PRDTask]:
        """Get a task by ID."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def get_ready_tasks(self) -> list[PRDTask]:
        """Get tasks that are ready to execute."""
        completed = {t.id for t in self.tasks if t.status == TaskStatus.COMPLETED}
        return [t for t in self.tasks if t.is_ready(completed)]

    def get_completed_tasks(self) -> list[PRDTask]:
        """Get all completed tasks."""
        return [t for t in self.tasks if t.status == TaskStatus.COMPLETED]

    def get_failed_tasks(self) -> list[PRDTask]:
        """Get all failed tasks."""
        return [t for t in self.tasks if t.status == TaskStatus.FAILED]

    def all_complete(self) -> bool:
        """Check if all tasks are complete (or failed)."""
        return all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            for t in self.tasks
        )

    def progress_summary(self) -> dict[str, int]:
        """Get a summary of task progress."""
        return {
            "total": len(self.tasks),
            "pending": sum(1 for t in self.tasks if t.status == TaskStatus.PENDING),
            "running": sum(1 for t in self.tasks if t.status == TaskStatus.RUNNING),
            "completed": sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED),
            "failed": sum(1 for t in self.tasks if t.status == TaskStatus.FAILED),
        }


@dataclass
class TaskResult:
    """Result of a completed task."""

    task_id: str
    success: bool
    branch: Optional[str] = None
    commit_sha: Optional[str] = None
    error: Optional[str] = None
    duration_seconds: Optional[float] = None
    output: Optional[str] = None


# =============================================================================
# Job Queue Models
# =============================================================================


@dataclass
class JobMessage:
    """A job message for the queue."""

    job_id: str
    task_id: str
    prd_id: str
    prompt: str
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    worker_id: Optional[str] = None
    backend: Optional[WorkerBackend] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "job_id": self.job_id,
            "task_id": self.task_id,
            "prd_id": self.prd_id,
            "prompt": self.prompt,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "worker_id": self.worker_id,
            "backend": self.backend.value if self.backend else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobMessage":
        """Deserialize from dictionary."""
        return cls(
            job_id=data["job_id"],
            task_id=data["task_id"],
            prd_id=data["prd_id"],
            prompt=data["prompt"],
            status=JobStatus(data.get("status", "pending")),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else lambda: datetime.now(timezone.utc)(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            result=data.get("result"),
            error=data.get("error"),
            worker_id=data.get("worker_id"),
            backend=WorkerBackend(data["backend"]) if data.get("backend") else None,
        )
