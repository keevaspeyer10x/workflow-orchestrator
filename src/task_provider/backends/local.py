"""
Local Task Provider - JSON file backend.

Stores tasks in a local JSON file for offline/standalone use.
Default path: ~/.config/orchestrator/tasks.json
"""

import json
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from ..interface import (
    TaskProvider,
    Task,
    TaskTemplate,
    TaskStatus,
    TaskPriority,
)


class LocalTaskProvider(TaskProvider):
    """
    Task provider that stores tasks in a local JSON file.

    This is the default/fallback provider for environments without
    GitHub access or for purely local task management.
    """

    DEFAULT_PATH = "~/.config/orchestrator/tasks.json"

    def __init__(self, path: Optional[str] = None):
        """
        Initialize local task provider.

        Args:
            path: Path to JSON file (default: ~/.config/orchestrator/tasks.json)
        """
        self.path = Path(path or self.DEFAULT_PATH).expanduser()
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Create parent directories and file if not exists."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({"tasks": [], "next_id": 1})

    def _load(self) -> dict:
        """Load data from JSON file."""
        return json.loads(self.path.read_text())

    def _save(self, data: dict) -> None:
        """Save data to JSON file atomically."""
        # Write to temp file then rename for atomicity
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(data, indent=2, default=str))
        temp_path.rename(self.path)

    def _render_body(self, template: TaskTemplate) -> str:
        """Render TaskTemplate to markdown body."""
        sections = [
            f"## Status\n**{template.recommendation}**\n",
            f"## Priority\n{template.priority.value}\n",
            f"## Description\n{template.description}\n",
            f"## Problem Solved\n{template.problem_solved}\n",
        ]

        if template.proposed_solution:
            sections.append(f"## Proposed Solution\n{template.proposed_solution}\n")

        if template.tasks:
            task_list = "\n".join(f"- [ ] {t}" for t in template.tasks)
            sections.append(f"## Tasks\n{task_list}\n")

        # YAGNI section
        actual = "actually have" if template.yagni_actual_problem else "hypothetical"
        ok_without = "NOT okay" if template.yagni_ok_without == "0" else f"okay for {template.yagni_ok_without}"
        current = "fails" if not template.yagni_current_works else "works"

        sections.append(f"""## YAGNI Check
- Solving a problem we **{actual}**
- Would be **{ok_without}** without this
- Current solution **{current}**
""")

        return "\n".join(sections)

    def name(self) -> str:
        """Return provider identifier."""
        return "local"

    def is_available(self) -> bool:
        """Check if provider can be used (always true for local)."""
        return True

    def create_task(self, template: TaskTemplate) -> Task:
        """Create a new task from template."""
        data = self._load()
        task_id = str(data["next_id"])
        data["next_id"] += 1

        task = Task(
            id=task_id,
            title=template.title,
            body=self._render_body(template),
            status=TaskStatus.OPEN,
            priority=template.priority,
            labels=template.labels,
            metadata={"created_at": datetime.now().isoformat()},
        )

        data["tasks"].append(task.to_dict())
        self._save(data)

        return task

    def update_task(self, task_id: str, updates: dict) -> Task:
        """Update an existing task."""
        data = self._load()

        for i, task_data in enumerate(data["tasks"]):
            if task_data["id"] == task_id:
                # Apply updates
                for key, value in updates.items():
                    if key == "status" and isinstance(value, TaskStatus):
                        task_data["status"] = value.value
                    elif key == "priority" and isinstance(value, TaskPriority):
                        task_data["priority"] = value.value
                    else:
                        task_data[key] = value

                task_data.setdefault("metadata", {})
                task_data["metadata"]["updated_at"] = datetime.now().isoformat()
                data["tasks"][i] = task_data
                self._save(data)
                return Task.from_dict(task_data)

        raise KeyError(f"Task not found: {task_id}")

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None
    ) -> List[Task]:
        """List tasks with optional filters."""
        data = self._load()
        tasks = []

        for task_data in data["tasks"]:
            task = Task.from_dict(task_data)

            # Apply filters
            if status and task.status != status:
                continue
            if priority and task.priority != priority:
                continue

            tasks.append(task)

        return tasks

    def get_next_task(self) -> Optional[Task]:
        """Get highest priority open task."""
        open_tasks = self.list_tasks(status=TaskStatus.OPEN)

        if not open_tasks:
            return None

        # Sort by priority (P0 < P1 < P2 < P3)
        def priority_sort_key(task: Task) -> str:
            if task.priority is None:
                return "P9"  # Treat None as lowest priority
            return task.priority.value

        sorted_tasks = sorted(open_tasks, key=priority_sort_key)
        return sorted_tasks[0]

    def close_task(self, task_id: str, comment: Optional[str] = None) -> Task:
        """Close a task."""
        updates = {"status": TaskStatus.CLOSED}
        if comment:
            # Get current task to preserve metadata
            task = self.get_task(task_id)
            if task:
                metadata = task.metadata.copy()
                metadata["close_comment"] = comment
                updates["metadata"] = metadata

        return self.update_task(task_id, updates)

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a specific task by ID."""
        data = self._load()
        for task_data in data["tasks"]:
            if task_data["id"] == task_id:
                return Task.from_dict(task_data)
        return None
