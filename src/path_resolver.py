"""Path resolution for orchestrator files - CORE-025 Multi-Repo Containment Strategy

This module provides centralized path resolution for all orchestrator files,
supporting the session-first architecture where each session has its own
isolated directory.

Directory structure:
    .orchestrator/
    ├── sessions/
    │   ├── <session-id>/
    │   │   ├── state.json
    │   │   ├── log.jsonl
    │   │   ├── meta.json
    │   │   ├── feedback/
    │   │   └── checkpoints/
    │   └── <another-session>/
    ├── current          # Points to active session
    ├── meta.json        # Repo identity
    ├── prd/             # PRD state
    └── config.yaml      # Repo config

Legacy paths (for backward compatibility):
    .workflow_state.json
    .workflow_log.jsonl
    .workflow_checkpoints/
    .workflow_tool_feedback.jsonl
    .workflow_process_feedback.jsonl
"""

from pathlib import Path
from typing import Optional


class OrchestratorPaths:
    """Centralized path resolution with session support"""

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        session_id: Optional[str] = None,
        web_mode: bool = False
    ):
        """Initialize path resolver.

        Args:
            base_dir: Repository root directory. If None, auto-detects by
                     walking up to find .git/ or workflow.yaml
            session_id: Current session ID. If None, session-specific paths
                       raise ValueError
            web_mode: Whether running in web/ephemeral environment
        """
        self.base_dir = base_dir or self._find_repo_root()
        self.session_id = session_id
        self.web_mode = web_mode
        self.orchestrator_dir = self.base_dir / ".orchestrator"

    def _find_repo_root(self) -> Path:
        """Walk up to find repo root.

        Looks for .git/ or workflow.yaml in current directory and parents.
        Falls back to cwd if neither found.

        Returns:
            Path to repository root
        """
        cwd = Path.cwd()
        for parent in [cwd, *cwd.parents]:
            if (parent / ".git").exists():
                return parent
            if (parent / "workflow.yaml").exists():
                return parent
        return cwd

    def session_dir(self) -> Path:
        """Get current session directory.

        Returns:
            Path to .orchestrator/sessions/<session-id>/

        Raises:
            ValueError: If no session ID is set
        """
        if not self.session_id:
            raise ValueError("No session ID set")
        return self.orchestrator_dir / "sessions" / self.session_id

    def state_file(self) -> Path:
        """Get state file path (new structure).

        Returns:
            .orchestrator/sessions/<id>/state.json if session set
            .orchestrator/state.json otherwise
        """
        if self.session_id:
            return self.session_dir() / "state.json"
        return self.orchestrator_dir / "state.json"

    def find_legacy_state_file(self) -> Optional[Path]:
        """Find old state file if it exists.

        Returns:
            Path to .workflow_state.json if exists, None otherwise
        """
        old = self.base_dir / ".workflow_state.json"
        return old if old.exists() else None

    def log_file(self) -> Path:
        """Get log file path.

        Returns:
            .orchestrator/sessions/<id>/log.jsonl if session set
            .orchestrator/log.jsonl otherwise
        """
        if self.session_id:
            return self.session_dir() / "log.jsonl"
        return self.orchestrator_dir / "log.jsonl"

    def find_legacy_log_file(self) -> Optional[Path]:
        """Find old log file if it exists.

        Returns:
            Path to .workflow_log.jsonl if exists, None otherwise
        """
        old = self.base_dir / ".workflow_log.jsonl"
        return old if old.exists() else None

    def checkpoints_dir(self) -> Path:
        """Get checkpoints directory.

        Returns:
            .orchestrator/sessions/<id>/checkpoints if session set
            .orchestrator/checkpoints otherwise
        """
        if self.session_id:
            return self.session_dir() / "checkpoints"
        return self.orchestrator_dir / "checkpoints"

    def find_legacy_checkpoints_dir(self) -> Optional[Path]:
        """Find old checkpoints directory if it exists.

        Returns:
            Path to .workflow_checkpoints/ if exists, None otherwise
        """
        old = self.base_dir / ".workflow_checkpoints"
        return old if old.exists() else None

    def feedback_dir(self) -> Path:
        """Get feedback directory.

        Returns:
            .orchestrator/sessions/<id>/feedback if session set
            .orchestrator/feedback otherwise
        """
        if self.session_id:
            return self.session_dir() / "feedback"
        return self.orchestrator_dir / "feedback"

    def meta_file(self) -> Path:
        """Get repo metadata file.

        Returns:
            .orchestrator/meta.json
        """
        return self.orchestrator_dir / "meta.json"

    def migration_marker(self) -> Path:
        """Get migration completion marker.

        Returns:
            .orchestrator/.migration_complete
        """
        return self.orchestrator_dir / ".migration_complete"

    def prd_dir(self) -> Path:
        """Get PRD state directory.

        Returns:
            .orchestrator/prd/
        """
        return self.orchestrator_dir / "prd"

    def config_file(self) -> Path:
        """Get repo config file.

        Returns:
            .orchestrator/config.yaml
        """
        return self.orchestrator_dir / "config.yaml"

    def current_file(self) -> Path:
        """Get current session pointer file.

        Returns:
            .orchestrator/current
        """
        return self.orchestrator_dir / "current"

    def sessions_dir(self) -> Path:
        """Get sessions parent directory.

        Returns:
            .orchestrator/sessions/
        """
        return self.orchestrator_dir / "sessions"

    def ensure_dirs(self) -> None:
        """Create all necessary directories.

        Creates .orchestrator/ and session directory if session_id is set.
        """
        self.orchestrator_dir.mkdir(parents=True, exist_ok=True)
        if self.session_id:
            self.session_dir().mkdir(parents=True, exist_ok=True)
            self.feedback_dir().mkdir(parents=True, exist_ok=True)
            self.checkpoints_dir().mkdir(parents=True, exist_ok=True)
