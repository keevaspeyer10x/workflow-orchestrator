"""Tests for SessionManager - CORE-025 Multi-Repo Containment Strategy"""

import json
from pathlib import Path

import pytest


class TestSessionManager:
    """Tests for SessionManager class"""

    def test_create_session_returns_id(self, tmp_path):
        """Returns 8-char UUID"""
        from src.path_resolver import OrchestratorPaths
        from src.session_manager import SessionManager

        paths = OrchestratorPaths(base_dir=tmp_path)
        manager = SessionManager(paths)

        session_id = manager.create_session()

        assert len(session_id) == 8
        assert session_id.isalnum()

    def test_create_session_creates_directory(self, tmp_path):
        """Session directory created"""
        from src.path_resolver import OrchestratorPaths
        from src.session_manager import SessionManager

        paths = OrchestratorPaths(base_dir=tmp_path)
        manager = SessionManager(paths)

        session_id = manager.create_session()

        session_dir = tmp_path / ".orchestrator" / "sessions" / session_id
        assert session_dir.exists()
        assert session_dir.is_dir()

    def test_create_session_creates_meta_json(self, tmp_path):
        """meta.json created with session info"""
        from src.path_resolver import OrchestratorPaths
        from src.session_manager import SessionManager

        paths = OrchestratorPaths(base_dir=tmp_path)
        manager = SessionManager(paths)

        session_id = manager.create_session()

        meta_file = tmp_path / ".orchestrator" / "sessions" / session_id / "meta.json"
        assert meta_file.exists()

        meta = json.loads(meta_file.read_text())
        assert meta["session_id"] == session_id
        assert "created_at" in meta
        assert "repo_root" in meta

    def test_create_session_sets_current(self, tmp_path):
        """current file updated"""
        from src.path_resolver import OrchestratorPaths
        from src.session_manager import SessionManager

        paths = OrchestratorPaths(base_dir=tmp_path)
        manager = SessionManager(paths)

        session_id = manager.create_session()

        current_file = tmp_path / ".orchestrator" / "current"
        assert current_file.exists()
        assert current_file.read_text().strip() == session_id

    def test_get_current_session_exists(self, tmp_path):
        """Returns session ID from current file"""
        from src.path_resolver import OrchestratorPaths
        from src.session_manager import SessionManager

        # Setup current file
        orch_dir = tmp_path / ".orchestrator"
        orch_dir.mkdir(parents=True)
        current_file = orch_dir / "current"
        current_file.write_text("abc12345")

        paths = OrchestratorPaths(base_dir=tmp_path)
        manager = SessionManager(paths)

        assert manager.get_current_session() == "abc12345"

    def test_get_current_session_not_exists(self, tmp_path):
        """No current file -> returns None"""
        from src.path_resolver import OrchestratorPaths
        from src.session_manager import SessionManager

        paths = OrchestratorPaths(base_dir=tmp_path)
        manager = SessionManager(paths)

        assert manager.get_current_session() is None

    def test_list_sessions_multiple(self, tmp_path):
        """Returns list of all session directories"""
        from src.path_resolver import OrchestratorPaths
        from src.session_manager import SessionManager

        # Create some session directories
        sessions_dir = tmp_path / ".orchestrator" / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "sess001").mkdir()
        (sessions_dir / "sess002").mkdir()
        (sessions_dir / "sess003").mkdir()

        paths = OrchestratorPaths(base_dir=tmp_path)
        manager = SessionManager(paths)

        sessions = manager.list_sessions()
        assert set(sessions) == {"sess001", "sess002", "sess003"}

    def test_list_sessions_empty(self, tmp_path):
        """No sessions -> returns empty list"""
        from src.path_resolver import OrchestratorPaths
        from src.session_manager import SessionManager

        paths = OrchestratorPaths(base_dir=tmp_path)
        manager = SessionManager(paths)

        assert manager.list_sessions() == []

    def test_list_sessions_ignores_files(self, tmp_path):
        """Files in sessions dir are ignored"""
        from src.path_resolver import OrchestratorPaths
        from src.session_manager import SessionManager

        sessions_dir = tmp_path / ".orchestrator" / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "sess001").mkdir()
        (sessions_dir / "not_a_session.txt").write_text("file")

        paths = OrchestratorPaths(base_dir=tmp_path)
        manager = SessionManager(paths)

        sessions = manager.list_sessions()
        assert sessions == ["sess001"]

    def test_get_session_info(self, tmp_path):
        """Get session metadata"""
        from src.path_resolver import OrchestratorPaths
        from src.session_manager import SessionManager

        paths = OrchestratorPaths(base_dir=tmp_path)
        manager = SessionManager(paths)

        session_id = manager.create_session()
        info = manager.get_session_info(session_id)

        assert info is not None
        assert info["session_id"] == session_id
        assert "created_at" in info

    def test_get_session_info_not_found(self, tmp_path):
        """Session doesn't exist -> returns None"""
        from src.path_resolver import OrchestratorPaths
        from src.session_manager import SessionManager

        paths = OrchestratorPaths(base_dir=tmp_path)
        manager = SessionManager(paths)

        assert manager.get_session_info("nonexistent") is None

    def test_create_multiple_sessions(self, tmp_path):
        """Multiple sessions can be created"""
        from src.path_resolver import OrchestratorPaths
        from src.session_manager import SessionManager

        paths = OrchestratorPaths(base_dir=tmp_path)
        manager = SessionManager(paths)

        session1 = manager.create_session()
        session2 = manager.create_session()
        session3 = manager.create_session()

        # All unique
        assert len({session1, session2, session3}) == 3

        # All exist
        sessions = manager.list_sessions()
        assert session1 in sessions
        assert session2 in sessions
        assert session3 in sessions

        # Current is the last one
        assert manager.get_current_session() == session3

    def test_switch_session(self, tmp_path):
        """Can switch to a different session"""
        from src.path_resolver import OrchestratorPaths
        from src.session_manager import SessionManager

        paths = OrchestratorPaths(base_dir=tmp_path)
        manager = SessionManager(paths)

        session1 = manager.create_session()
        session2 = manager.create_session()

        # Current is session2
        assert manager.get_current_session() == session2

        # Switch to session1
        manager.set_current_session(session1)
        assert manager.get_current_session() == session1

    def test_switch_to_nonexistent_session_raises(self, tmp_path):
        """Cannot switch to nonexistent session"""
        from src.path_resolver import OrchestratorPaths
        from src.session_manager import SessionManager

        paths = OrchestratorPaths(base_dir=tmp_path)
        manager = SessionManager(paths)

        with pytest.raises(ValueError, match="Session not found"):
            manager.set_current_session("nonexistent")
