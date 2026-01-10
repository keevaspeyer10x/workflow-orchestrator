"""
State Management

Tracks workflow state including task dependencies, completions, and blockers.
"""

from typing import Dict, List, Set, Optional, Any
from datetime import datetime, timezone
import threading
import json
from pathlib import Path


class StateManager:
    """
    Manages workflow state across multiple tasks

    Thread-safe state tracking for task coordination.
    """

    def __init__(self, state_file: Path = Path(".orchestrator/state.json")):
        """
        Initialize state manager

        Args:
            state_file: Path to state persistence file
        """
        self.state_file = state_file
        self._lock = threading.Lock()
        self._state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        """
        Load state from file

        Returns:
            State dictionary
        """
        if not self.state_file.exists():
            return {
                "tasks": {},
                "dependencies": {},
                "completed": set(),
                "blockers": []
            }

        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
                # Convert completed list back to set
                data["completed"] = set(data.get("completed", []))
                return data
        except Exception:
            return {
                "tasks": {},
                "dependencies": {},
                "completed": set(),
                "blockers": []
            }

    def _save_state(self):
        """Save state to file"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # Convert set to list for JSON serialization
        data = dict(self._state)
        data["completed"] = list(data["completed"])

        with open(self.state_file, 'w') as f:
            json.dump(data, f, indent=2)

    def register_task(
        self,
        task_id: str,
        agent_id: str,
        phase: str,
        dependencies: Optional[List[str]] = None
    ):
        """
        Register a new task

        Args:
            task_id: Task identifier
            agent_id: Agent claiming the task
            phase: Initial phase
            dependencies: List of task IDs this task depends on
        """
        with self._lock:
            self._state["tasks"][task_id] = {
                "agent_id": agent_id,
                "phase": phase,
                "claimed_at": datetime.now(timezone.utc).isoformat(),
                "transitions": []
            }

            if dependencies:
                self._state["dependencies"][task_id] = dependencies

            self._save_state()

    def update_phase(self, task_id: str, new_phase: str):
        """
        Update task phase

        Args:
            task_id: Task identifier
            new_phase: New phase
        """
        with self._lock:
            if task_id in self._state["tasks"]:
                self._state["tasks"][task_id]["phase"] = new_phase
                self._state["tasks"][task_id]["transitions"].append({
                    "phase": new_phase,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                self._save_state()

    def mark_completed(self, task_id: str):
        """
        Mark task as completed

        Args:
            task_id: Task identifier
        """
        with self._lock:
            self._state["completed"].add(task_id)
            if task_id in self._state["tasks"]:
                self._state["tasks"][task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._save_state()

    def add_blocker(self, task_id: str, blocker: str):
        """
        Add blocker for a task

        Args:
            task_id: Task identifier
            blocker: Blocker description
        """
        with self._lock:
            self._state["blockers"].append({
                "task_id": task_id,
                "blocker": blocker,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            self._save_state()

    def get_snapshot(self, task_id: str) -> Dict[str, Any]:
        """
        Get state snapshot for a task

        Args:
            task_id: Task identifier

        Returns:
            State snapshot with dependencies, completed tasks, blockers
        """
        with self._lock:
            dependencies = self._state["dependencies"].get(task_id, [])
            completed = [t for t in dependencies if t in self._state["completed"]]

            task_info = self._state["tasks"].get(task_id, {})
            current_phase = task_info.get("phase", "UNKNOWN")

            task_blockers = [
                b["blocker"]
                for b in self._state["blockers"]
                if b["task_id"] == task_id
            ]

            return {
                "task_dependencies": dependencies,
                "completed_tasks": completed,
                "current_phase": current_phase,
                "blockers": task_blockers
            }

    def get_all_tasks(self) -> Dict[str, Any]:
        """
        Get all tasks

        Returns:
            All tasks in the system
        """
        with self._lock:
            return dict(self._state["tasks"])

    def is_task_unblocked(self, task_id: str) -> bool:
        """
        Check if task dependencies are satisfied

        Args:
            task_id: Task identifier

        Returns:
            True if all dependencies completed
        """
        with self._lock:
            dependencies = self._state["dependencies"].get(task_id, [])
            return all(dep in self._state["completed"] for dep in dependencies)


# Global state manager instance
state_manager = StateManager()
