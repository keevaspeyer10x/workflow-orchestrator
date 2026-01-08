"""
Persistent session registry for Claude Squad integration.

Addresses AI review concern: "In-memory session mapping will be lost
on orchestrator restart"
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
from filelock import FileLock


@dataclass
class SessionRecord:
    """Persistent record of a Claude Squad session."""
    task_id: str
    session_id: str
    session_name: str
    branch: str
    status: str  # pending, running, completed, terminated, orphaned
    created_at: str
    updated_at: str
    prompt_file: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SessionRecord":
        return cls(**data)


class SessionRegistry:
    """
    Persistent registry for task <-> session mappings.

    Features:
    - Survives orchestrator restart
    - Thread-safe via file locking
    - Auto-reconciliation with Claude Squad state
    """

    def __init__(self, working_dir: Path):
        self.working_dir = working_dir
        self.registry_file = working_dir / ".claude" / "squad_sessions.json"
        self.lock_file = self.registry_file.with_suffix(".lock")
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, SessionRecord]:
        """Load registry from disk."""
        if not self.registry_file.exists():
            return {}

        with FileLock(self.lock_file):
            data = json.loads(self.registry_file.read_text())
            return {
                task_id: SessionRecord.from_dict(record)
                for task_id, record in data.items()
            }

    def _save(self, registry: dict[str, SessionRecord]) -> None:
        """Save registry to disk."""
        with FileLock(self.lock_file):
            data = {
                task_id: record.to_dict()
                for task_id, record in registry.items()
            }
            self.registry_file.write_text(json.dumps(data, indent=2))

    def register(self, record: SessionRecord) -> None:
        """Register a new session."""
        registry = self._load()
        registry[record.task_id] = record
        self._save(registry)

    def get(self, task_id: str) -> Optional[SessionRecord]:
        """Get session record by task ID."""
        return self._load().get(task_id)

    def update_status(self, task_id: str, status: str) -> None:
        """Update session status."""
        registry = self._load()
        if task_id in registry:
            registry[task_id].status = status
            registry[task_id].updated_at = datetime.now(timezone.utc).isoformat()
            self._save(registry)

    def list_active(self) -> list[SessionRecord]:
        """List all active (non-terminated) sessions."""
        return [
            r for r in self._load().values()
            if r.status in ("pending", "running")
        ]

    def list_all(self) -> list[SessionRecord]:
        """List all sessions."""
        return list(self._load().values())

    def reconcile(self, squad_sessions: list[dict]) -> None:
        """
        Reconcile registry with Claude Squad's actual state.

        Marks sessions as 'orphaned' if they exist in registry
        but not in Claude Squad (e.g., manual termination).
        """
        registry = self._load()
        squad_names = {s["name"] for s in squad_sessions}

        for task_id, record in registry.items():
            if record.status in ("pending", "running"):
                if record.session_name not in squad_names:
                    record.status = "orphaned"
                    record.updated_at = datetime.now(timezone.utc).isoformat()

        self._save(registry)

    def cleanup_old(self, days: int = 7) -> int:
        """Remove records older than N days."""
        registry = self._load()
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)

        to_remove = []
        for task_id, record in registry.items():
            if record.status in ("completed", "terminated", "orphaned"):
                record_time = datetime.fromisoformat(record.updated_at).timestamp()
                if record_time < cutoff:
                    to_remove.append(task_id)

        for task_id in to_remove:
            del registry[task_id]

        self._save(registry)
        return len(to_remove)

    def remove(self, task_id: str) -> bool:
        """Remove a session record."""
        registry = self._load()
        if task_id in registry:
            del registry[task_id]
            self._save(registry)
            return True
        return False
