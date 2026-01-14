"""
Task Provider Interface - Abstract base class for task/issue backends.

This module defines the abstract interface that all task providers must implement,
as well as the core data structures (Task, TaskTemplate, enums).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


class TaskStatus(Enum):
    """Status of a task."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    CLOSED = "closed"


class TaskPriority(Enum):
    """Priority level for tasks (P0 is highest)."""
    CRITICAL = "P0"
    HIGH = "P1"
    MEDIUM = "P2"
    LOW = "P3"


@dataclass
class Task:
    """
    A task/issue from any backend.

    This is the canonical representation that all backends convert to/from.
    """
    id: str
    title: str
    body: str
    status: TaskStatus
    priority: Optional[TaskPriority] = None
    labels: List[str] = field(default_factory=list)
    url: Optional[str] = None  # For GitHub/external links
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "status": self.status.value,
            "priority": self.priority.value if self.priority else None,
            "labels": self.labels,
            "url": self.url,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Create Task from dictionary."""
        return cls(
            id=data["id"],
            title=data["title"],
            body=data["body"],
            status=TaskStatus(data["status"]),
            priority=TaskPriority(data["priority"]) if data.get("priority") else None,
            labels=data.get("labels", []),
            url=data.get("url"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class TaskTemplate:
    """
    Template for creating a new task with YAGNI analysis.

    This provides a standard format for creating tasks that includes
    problem analysis, recommendations, and implementation tasks.
    """
    title: str
    description: str
    problem_solved: str
    proposed_solution: Optional[str] = None
    tasks: List[str] = field(default_factory=list)
    yagni_actual_problem: bool = True
    yagni_ok_without: str = "6 months"
    yagni_current_works: bool = False
    recommendation: str = "IMPLEMENT"  # IMPLEMENT, DEFER, INVESTIGATE
    priority: TaskPriority = TaskPriority.MEDIUM
    labels: List[str] = field(default_factory=list)


class TaskProvider(ABC):
    """
    Abstract base class for task/issue backends.

    All providers must implement these methods to be usable
    by the orchestrator's task management system.
    """

    @abstractmethod
    def name(self) -> str:
        """
        Return the provider identifier.

        Returns:
            str: Provider name (e.g., 'local', 'github', 'notion')
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this provider can be used.

        Returns:
            bool: True if the provider is ready to use
        """
        pass

    @abstractmethod
    def create_task(self, template: TaskTemplate) -> Task:
        """
        Create a new task from template.

        Args:
            template: TaskTemplate with task details

        Returns:
            Task: The created task with ID assigned
        """
        pass

    @abstractmethod
    def update_task(self, task_id: str, updates: dict) -> Task:
        """
        Update an existing task.

        Args:
            task_id: ID of task to update
            updates: Dictionary of fields to update

        Returns:
            Task: The updated task

        Raises:
            KeyError: If task_id not found
        """
        pass

    @abstractmethod
    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None
    ) -> List[Task]:
        """
        List tasks with optional filters.

        Args:
            status: Filter by status (optional)
            priority: Filter by priority (optional)

        Returns:
            List[Task]: Matching tasks
        """
        pass

    @abstractmethod
    def get_next_task(self) -> Optional[Task]:
        """
        Get the highest priority open task.

        Returns:
            Optional[Task]: Highest priority open task, or None if no open tasks
        """
        pass

    @abstractmethod
    def close_task(self, task_id: str, comment: Optional[str] = None) -> Task:
        """
        Close/complete a task.

        Args:
            task_id: ID of task to close
            comment: Optional completion comment

        Returns:
            Task: The closed task

        Raises:
            KeyError: If task_id not found
        """
        pass

    def get_task(self, task_id: str) -> Optional[Task]:
        """
        Get a specific task by ID.

        Default implementation searches through list_tasks().
        Backends may override for efficiency.

        Args:
            task_id: ID of task to get

        Returns:
            Optional[Task]: The task, or None if not found
        """
        for task in self.list_tasks():
            if task.id == task_id:
                return task
        return None
