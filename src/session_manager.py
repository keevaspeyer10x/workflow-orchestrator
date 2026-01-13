"""Session management for orchestrator - CORE-025 Multi-Repo Containment Strategy

This module manages orchestrator sessions, providing isolation for concurrent
workflows and safe state management.

Each session has:
    - Unique 8-character ID (UUID4 prefix)
    - Own state file
    - Own log file
    - Own feedback and checkpoint directories
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from .path_resolver import OrchestratorPaths


class SessionManager:
    """Manage orchestrator sessions"""

    def __init__(self, paths: OrchestratorPaths):
        """Initialize session manager.

        Args:
            paths: OrchestratorPaths instance for path resolution
        """
        self.paths = paths

    def create_session(self) -> str:
        """Create a new session.

        Creates:
            - Session directory at .orchestrator/sessions/<id>/
            - Session meta.json with creation info
            - Updates current pointer

        Returns:
            8-character session ID
        """
        # Generate unique session ID (first 8 chars of UUID4)
        session_id = str(uuid.uuid4())[:8]

        # Create session directory
        session_dir = self.paths.orchestrator_dir / "sessions" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Create session metadata
        meta = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "repo_root": str(self.paths.base_dir),
        }

        meta_file = session_dir / "meta.json"
        meta_file.write_text(json.dumps(meta, indent=2))

        # Set as current session
        self._set_current_session(session_id)

        return session_id

    def _set_current_session(self, session_id: str) -> None:
        """Set current active session (internal).

        Args:
            session_id: Session ID to set as current
        """
        # Ensure orchestrator directory exists
        self.paths.orchestrator_dir.mkdir(parents=True, exist_ok=True)

        current_file = self.paths.orchestrator_dir / "current"
        current_file.write_text(session_id)

    def set_current_session(self, session_id: str) -> None:
        """Set current active session (public).

        Args:
            session_id: Session ID to set as current

        Raises:
            ValueError: If session doesn't exist
        """
        session_dir = self.paths.orchestrator_dir / "sessions" / session_id
        if not session_dir.exists():
            raise ValueError(f"Session not found: {session_id}")

        self._set_current_session(session_id)

    def get_current_session(self) -> Optional[str]:
        """Get current active session ID.

        Returns:
            Session ID string if current file exists, None otherwise
        """
        current_file = self.paths.orchestrator_dir / "current"
        if current_file.exists():
            return current_file.read_text().strip()
        return None

    def list_sessions(self) -> List[str]:
        """List all session IDs.

        Returns:
            List of session ID strings (directory names)
        """
        sessions_dir = self.paths.orchestrator_dir / "sessions"
        if not sessions_dir.exists():
            return []

        return [d.name for d in sessions_dir.iterdir() if d.is_dir()]

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session metadata.

        Args:
            session_id: Session ID to get info for

        Returns:
            Session metadata dict if exists and valid, None otherwise
        """
        session_dir = self.paths.orchestrator_dir / "sessions" / session_id
        meta_file = session_dir / "meta.json"

        if not meta_file.exists():
            return None

        try:
            return json.loads(meta_file.read_text())
        except json.JSONDecodeError:
            return None

    def update_session_info(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update session metadata.

        Args:
            session_id: Session ID to update
            updates: Dictionary of fields to update/add

        Returns:
            True if successful, False if session or meta file not found
        """
        session_dir = self.paths.orchestrator_dir / "sessions" / session_id
        meta_file = session_dir / "meta.json"

        if not meta_file.exists():
            return False

        try:
            # Read existing
            data = json.loads(meta_file.read_text())
            # Update
            data.update(updates)
            # Write back
            meta_file.write_text(json.dumps(data, indent=2))
            return True
        except (json.JSONDecodeError, OSError):
            return False

    def delete_session(self, session_id: str) -> bool:
        """Delete a session.

        Args:
            session_id: Session ID to delete

        Returns:
            True if deleted, False if not found
        """
        import shutil

        session_dir = self.paths.orchestrator_dir / "sessions" / session_id
        if not session_dir.exists():
            return False

        shutil.rmtree(session_dir)

        # Clear current if this was the current session
        if self.get_current_session() == session_id:
            current_file = self.paths.orchestrator_dir / "current"
            if current_file.exists():
                current_file.unlink()

        return True

    def get_or_create_session(self) -> str:
        """Get current session or create a new one.

        Returns:
            Session ID (existing current or newly created)
        """
        current = self.get_current_session()
        if current:
            # Verify session exists
            session_dir = self.paths.orchestrator_dir / "sessions" / current
            if session_dir.exists():
                return current

        # Create new session
        return self.create_session()
