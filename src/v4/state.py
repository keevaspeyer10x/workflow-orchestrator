"""
State persistence for V4 workflows.
Uses .orchestrator/v4/ directory, separate from existing state.
"""
import json
import fcntl
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import WorkflowState, WorkflowStatus


class StateStore:
    """
    Manages workflow state persistence.

    State file: .orchestrator/v4/state_{workflow_id}.json
    Lock file:  .orchestrator/v4/state_{workflow_id}.lock
    """

    def __init__(self, working_dir: Path):
        self.working_dir = Path(working_dir)
        self.state_dir = self.working_dir / ".orchestrator" / "v4"
        self._state: Optional[WorkflowState] = None
        self._lock_fd: Optional[int] = None

    def _ensure_dir(self) -> None:
        """Create state directory if it doesn't exist"""
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Add to .gitignore
        gitignore = self.state_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n")

    def _state_file(self, workflow_id: str) -> Path:
        return self.state_dir / f"state_{workflow_id}.json"

    def _lock_file(self, workflow_id: str) -> Path:
        return self.state_dir / f"state_{workflow_id}.lock"

    def acquire_lock(self, workflow_id: str, timeout: float = 10.0) -> bool:
        """
        Acquire exclusive lock for workflow state.
        Prevents concurrent modifications.
        """
        self._ensure_dir()
        lock_path = self._lock_file(workflow_id)

        try:
            self._lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (OSError, IOError):
            if self._lock_fd is not None:
                os.close(self._lock_fd)
                self._lock_fd = None
            return False

    def release_lock(self) -> None:
        """Release the workflow lock"""
        if self._lock_fd is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            self._lock_fd = None

    def initialize(self, workflow_name: str, task_description: str) -> WorkflowState:
        """Create new workflow state"""
        self._ensure_dir()

        self._state = WorkflowState(
            workflow_name=workflow_name,
            task_description=task_description,
            status=WorkflowStatus.INITIALIZED
        )

        # Acquire lock for new workflow
        if not self.acquire_lock(self._state.workflow_id):
            raise RuntimeError(f"Could not acquire lock for workflow {self._state.workflow_id}")

        self.save()
        return self._state

    def load(self, workflow_id: str) -> WorkflowState:
        """Load existing workflow state"""
        state_file = self._state_file(workflow_id)

        if not state_file.exists():
            raise FileNotFoundError(f"No state file for workflow {workflow_id}")

        # Acquire lock
        if not self.acquire_lock(workflow_id):
            raise RuntimeError(f"Workflow {workflow_id} is locked by another process")

        data = json.loads(state_file.read_text())
        self._state = WorkflowState.from_dict(data)
        return self._state

    def save(self) -> None:
        """Save current state to disk (atomic write)"""
        if self._state is None:
            raise RuntimeError("No state to save")

        self._state.updated_at = datetime.now()
        state_file = self._state_file(self._state.workflow_id)

        # Atomic write: write to temp file, then rename
        temp_file = state_file.with_suffix('.tmp')
        temp_file.write_text(json.dumps(self._state.to_dict(), indent=2))
        temp_file.rename(state_file)

    @property
    def state(self) -> WorkflowState:
        """Get current state (raises if not loaded)"""
        if self._state is None:
            raise RuntimeError("No state loaded")
        return self._state

    def update_phase(self, phase_id: str, attempt: int) -> None:
        """Update current phase tracking"""
        self.state.current_phase_id = phase_id
        self.state.current_attempt = attempt
        self.state.status = WorkflowStatus.RUNNING
        self.save()

    def complete_phase(self, phase_id: str) -> None:
        """Mark a phase as completed"""
        if phase_id not in self.state.phases_completed:
            self.state.phases_completed.append(phase_id)
        self.state.current_attempt = 0
        self.save()

    def mark_complete(self, success: bool = True) -> None:
        """Mark workflow as complete"""
        self.state.status = WorkflowStatus.COMPLETED if success else WorkflowStatus.FAILED
        self.state.completed_at = datetime.now()
        self.state.current_phase_id = None
        self.save()

    def cleanup(self) -> None:
        """Release lock and cleanup"""
        self.release_lock()


def find_active_workflow(working_dir: Path) -> Optional[str]:
    """Find an active (non-completed) workflow in the working directory"""
    state_dir = working_dir / ".orchestrator" / "v4"
    if not state_dir.exists():
        return None

    for state_file in state_dir.glob("state_*.json"):
        try:
            data = json.loads(state_file.read_text())
            status = WorkflowStatus(data.get("status", ""))
            if status not in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
                return data["workflow_id"]
        except (json.JSONDecodeError, KeyError):
            continue

    return None
