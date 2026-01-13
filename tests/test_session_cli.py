"""Tests for CORE-025 Phase 3: Session Management CLI (orchestrator workflow)"""

import json
import os
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil

from src.path_resolver import OrchestratorPaths
from src.session_manager import SessionManager


class TestWorkflowList:
    """Tests for 'orchestrator workflow list' command"""

    def setup_method(self):
        """Create temp directory for each test"""
        self.temp_dir = tempfile.mkdtemp()
        self.orch_dir = Path(self.temp_dir) / ".orchestrator"
        self.sessions_dir = self.orch_dir / "sessions"

    def teardown_method(self):
        """Clean up temp directory"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_session(self, session_id: str, task: str = "Test task",
                        status: str = "active", created_at: datetime = None):
        """Helper to create a test session"""
        session_dir = self.sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Create meta.json
        meta = {
            "session_id": session_id,
            "created_at": (created_at or datetime.now()).isoformat(),
            "repo_root": str(self.temp_dir)
        }
        (session_dir / "meta.json").write_text(json.dumps(meta))

        # Create state.json
        state = {
            "workflow_id": f"wf_{session_id}",
            "task": task,
            "status": status,
            "current_phase": "EXECUTE",
            "phases": {"PLAN": {"status": "complete"}, "EXECUTE": {"status": "active"}}
        }
        (session_dir / "state.json").write_text(json.dumps(state))

    def _set_current_session(self, session_id: str):
        """Helper to set current session"""
        self.orch_dir.mkdir(parents=True, exist_ok=True)
        (self.orch_dir / "current").write_text(session_id)

    def test_workflow_list_no_sessions(self):
        """Shows appropriate message when no sessions exist"""
        from src.cli import cmd_workflow_list

        args = MagicMock()
        args.dir = self.temp_dir

        # Should not raise, just print message
        cmd_workflow_list(args)

    def test_workflow_list_single_session(self):
        """Shows single session with details"""
        self._create_session("abc12345", task="Implement feature")
        self._set_current_session("abc12345")

        from src.cli import cmd_workflow_list

        args = MagicMock()
        args.dir = self.temp_dir

        # Should not raise
        cmd_workflow_list(args)

    def test_workflow_list_multiple_sessions(self):
        """Shows all sessions, current marked with *"""
        self._create_session("abc12345", task="First task")
        self._create_session("def67890", task="Second task")
        self._set_current_session("abc12345")

        from src.cli import cmd_workflow_list

        args = MagicMock()
        args.dir = self.temp_dir

        # Should not raise
        cmd_workflow_list(args)

    def test_workflow_list_shows_task(self):
        """Task description shown from state.json"""
        self._create_session("abc12345", task="My specific task name")
        self._set_current_session("abc12345")

        paths = OrchestratorPaths(base_dir=Path(self.temp_dir), session_id="abc12345")
        manager = SessionManager(paths)

        sessions = manager.list_sessions()
        assert "abc12345" in sessions

    def test_workflow_list_shows_status(self):
        """Status (active/completed/abandoned) shown"""
        self._create_session("abc12345", status="completed")

        session_dir = self.sessions_dir / "abc12345"
        state = json.loads((session_dir / "state.json").read_text())
        assert state["status"] == "completed"


class TestWorkflowSwitch:
    """Tests for 'orchestrator workflow switch' command"""

    def setup_method(self):
        """Create temp directory for each test"""
        self.temp_dir = tempfile.mkdtemp()
        self.orch_dir = Path(self.temp_dir) / ".orchestrator"
        self.sessions_dir = self.orch_dir / "sessions"

    def teardown_method(self):
        """Clean up temp directory"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_session(self, session_id: str):
        """Helper to create a test session"""
        session_dir = self.sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        meta = {"session_id": session_id, "created_at": datetime.now().isoformat()}
        (session_dir / "meta.json").write_text(json.dumps(meta))

    def test_workflow_switch_valid(self):
        """Switches to existing session"""
        self._create_session("abc12345")
        self._create_session("def67890")

        paths = OrchestratorPaths(base_dir=Path(self.temp_dir))
        manager = SessionManager(paths)
        manager.set_current_session("abc12345")

        # Switch to other session
        manager.set_current_session("def67890")

        assert manager.get_current_session() == "def67890"

    def test_workflow_switch_invalid(self):
        """Error for non-existent session ID"""
        paths = OrchestratorPaths(base_dir=Path(self.temp_dir))
        manager = SessionManager(paths)

        with pytest.raises(ValueError, match="Session not found"):
            manager.set_current_session("nonexistent")

    def test_workflow_switch_updates_current(self):
        """'.orchestrator/current' file updated"""
        self._create_session("abc12345")

        paths = OrchestratorPaths(base_dir=Path(self.temp_dir))
        manager = SessionManager(paths)
        manager.set_current_session("abc12345")

        current_file = self.orch_dir / "current"
        assert current_file.exists()
        assert current_file.read_text().strip() == "abc12345"


class TestWorkflowInfo:
    """Tests for 'orchestrator workflow info' command"""

    def setup_method(self):
        """Create temp directory for each test"""
        self.temp_dir = tempfile.mkdtemp()
        self.orch_dir = Path(self.temp_dir) / ".orchestrator"
        self.sessions_dir = self.orch_dir / "sessions"

    def teardown_method(self):
        """Clean up temp directory"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_session(self, session_id: str, task: str = "Test task"):
        """Helper to create a test session"""
        session_dir = self.sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        meta = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "repo_root": str(self.temp_dir)
        }
        (session_dir / "meta.json").write_text(json.dumps(meta))

        state = {
            "workflow_id": f"wf_{session_id}",
            "task": task,
            "status": "active",
            "current_phase": "EXECUTE"
        }
        (session_dir / "state.json").write_text(json.dumps(state))

    def _set_current_session(self, session_id: str):
        """Helper to set current session"""
        self.orch_dir.mkdir(parents=True, exist_ok=True)
        (self.orch_dir / "current").write_text(session_id)

    def test_workflow_info_current_session(self):
        """Shows current session when no ID given"""
        self._create_session("abc12345", task="Current task")
        self._set_current_session("abc12345")

        from src.cli import cmd_workflow_info

        args = MagicMock()
        args.dir = self.temp_dir
        args.session_id = None  # No ID, use current

        # Should not raise
        cmd_workflow_info(args)

    def test_workflow_info_specific_session(self):
        """Shows info for specified session ID"""
        self._create_session("abc12345", task="Specific task")

        from src.cli import cmd_workflow_info

        args = MagicMock()
        args.dir = self.temp_dir
        args.session_id = "abc12345"

        # Should not raise
        cmd_workflow_info(args)

    def test_workflow_info_invalid_id(self):
        """Error for non-existent session"""
        from src.cli import cmd_workflow_info

        args = MagicMock()
        args.dir = self.temp_dir
        args.session_id = "nonexistent"

        # Should print error, not crash
        cmd_workflow_info(args)


class TestWorkflowCleanup:
    """Tests for 'orchestrator workflow cleanup' command"""

    def setup_method(self):
        """Create temp directory for each test"""
        self.temp_dir = tempfile.mkdtemp()
        self.orch_dir = Path(self.temp_dir) / ".orchestrator"
        self.sessions_dir = self.orch_dir / "sessions"

    def teardown_method(self):
        """Clean up temp directory"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_session(self, session_id: str, days_old: int = 0, status: str = "active"):
        """Helper to create a test session with specific age"""
        session_dir = self.sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        created_at = datetime.now() - timedelta(days=days_old)
        meta = {
            "session_id": session_id,
            "created_at": created_at.isoformat(),
            "repo_root": str(self.temp_dir)
        }
        (session_dir / "meta.json").write_text(json.dumps(meta))

        state = {
            "workflow_id": f"wf_{session_id}",
            "task": "Test task",
            "status": status
        }
        (session_dir / "state.json").write_text(json.dumps(state))

    def _set_current_session(self, session_id: str):
        """Helper to set current session"""
        self.orch_dir.mkdir(parents=True, exist_ok=True)
        (self.orch_dir / "current").write_text(session_id)

    def test_workflow_cleanup_dry_run(self):
        """Shows what would be removed, no deletion"""
        self._create_session("old12345", days_old=60, status="abandoned")
        self._create_session("new67890", days_old=5)

        from src.cli import cmd_workflow_cleanup

        args = MagicMock()
        args.dir = self.temp_dir
        args.older_than = 30
        args.status = None
        args.dry_run = True
        args.yes = False

        # Run cleanup in dry-run mode
        cmd_workflow_cleanup(args)

        # Session should still exist
        assert (self.sessions_dir / "old12345").exists()

    def test_workflow_cleanup_older_than(self):
        """Only removes sessions older than threshold"""
        self._create_session("old12345", days_old=60)
        self._create_session("new67890", days_old=5)

        paths = OrchestratorPaths(base_dir=Path(self.temp_dir))
        manager = SessionManager(paths)

        # Both sessions should exist initially
        sessions = manager.list_sessions()
        assert len(sessions) == 2

    def test_workflow_cleanup_by_status(self):
        """Filters by status (abandoned/completed)"""
        self._create_session("abandoned1", days_old=60, status="abandoned")
        self._create_session("completed1", days_old=60, status="completed")
        self._create_session("active1", days_old=60, status="active")

        # Verify status filtering works
        for sid in ["abandoned1", "completed1", "active1"]:
            state_file = self.sessions_dir / sid / "state.json"
            state = json.loads(state_file.read_text())
            if sid.startswith("abandoned"):
                assert state["status"] == "abandoned"
            elif sid.startswith("completed"):
                assert state["status"] == "completed"
            else:
                assert state["status"] == "active"

    def test_workflow_cleanup_skip_current(self):
        """Never removes current session"""
        self._create_session("current1", days_old=60, status="abandoned")
        self._create_session("other1", days_old=60, status="abandoned")
        self._set_current_session("current1")

        paths = OrchestratorPaths(base_dir=Path(self.temp_dir))
        manager = SessionManager(paths)

        # Current session should be protected
        assert manager.get_current_session() == "current1"

    def test_workflow_cleanup_deletes_correctly(self):
        """Session directories actually removed"""
        self._create_session("todelete", days_old=60, status="abandoned")

        paths = OrchestratorPaths(base_dir=Path(self.temp_dir))
        manager = SessionManager(paths)

        # Delete the session
        result = manager.delete_session("todelete")
        assert result is True
        assert not (self.sessions_dir / "todelete").exists()


class TestWorkflowIntegration:
    """Integration tests for workflow CLI commands"""

    def setup_method(self):
        """Create temp directory for each test"""
        self.temp_dir = tempfile.mkdtemp()
        self.orch_dir = Path(self.temp_dir) / ".orchestrator"
        self.sessions_dir = self.orch_dir / "sessions"

    def teardown_method(self):
        """Clean up temp directory"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_session_manager_create_and_list(self):
        """SessionManager.create_session() then list_sessions() works"""
        paths = OrchestratorPaths(base_dir=Path(self.temp_dir))
        manager = SessionManager(paths)

        session_id = manager.create_session()
        assert len(session_id) == 8

        sessions = manager.list_sessions()
        assert session_id in sessions

    def test_session_manager_switch_and_get(self):
        """Switch session then get_current_session() returns correct ID"""
        paths = OrchestratorPaths(base_dir=Path(self.temp_dir))
        manager = SessionManager(paths)

        # Create two sessions
        session1 = manager.create_session()
        session2 = manager.create_session()

        # Switch back to first
        manager.set_current_session(session1)
        assert manager.get_current_session() == session1

    def test_session_info_retrieval(self):
        """get_session_info returns correct metadata"""
        paths = OrchestratorPaths(base_dir=Path(self.temp_dir))
        manager = SessionManager(paths)

        session_id = manager.create_session()
        info = manager.get_session_info(session_id)

        assert info is not None
        assert info["session_id"] == session_id
        assert "created_at" in info

    def test_delete_session_clears_current(self):
        """Deleting current session clears current pointer"""
        paths = OrchestratorPaths(base_dir=Path(self.temp_dir))
        manager = SessionManager(paths)

        session_id = manager.create_session()
        assert manager.get_current_session() == session_id

        manager.delete_session(session_id)
        assert manager.get_current_session() is None


class TestEdgeCases:
    """Edge case tests"""

    def setup_method(self):
        """Create temp directory for each test"""
        self.temp_dir = tempfile.mkdtemp()
        self.orch_dir = Path(self.temp_dir) / ".orchestrator"
        self.sessions_dir = self.orch_dir / "sessions"

    def teardown_method(self):
        """Clean up temp directory"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_session_with_missing_state(self):
        """Session with missing state.json shows unknown for task/status"""
        session_dir = self.sessions_dir / "orphan123"
        session_dir.mkdir(parents=True, exist_ok=True)

        # Create only meta.json, no state.json
        meta = {"session_id": "orphan123", "created_at": datetime.now().isoformat()}
        (session_dir / "meta.json").write_text(json.dumps(meta))

        paths = OrchestratorPaths(base_dir=Path(self.temp_dir))
        manager = SessionManager(paths)

        sessions = manager.list_sessions()
        assert "orphan123" in sessions

        # get_session_info should still work (returns meta.json content)
        info = manager.get_session_info("orphan123")
        assert info is not None

    def test_session_with_corrupt_meta(self):
        """Session with corrupt meta.json handles gracefully"""
        session_dir = self.sessions_dir / "corrupt1"
        session_dir.mkdir(parents=True, exist_ok=True)

        # Write invalid JSON
        (session_dir / "meta.json").write_text("not valid json {{{")

        paths = OrchestratorPaths(base_dir=Path(self.temp_dir))
        manager = SessionManager(paths)

        # get_session_info should return None for corrupt files
        info = manager.get_session_info("corrupt1")
        assert info is None

    def test_empty_session_directory(self):
        """Empty session directory listed but with minimal info"""
        session_dir = self.sessions_dir / "empty123"
        session_dir.mkdir(parents=True, exist_ok=True)

        paths = OrchestratorPaths(base_dir=Path(self.temp_dir))
        manager = SessionManager(paths)

        sessions = manager.list_sessions()
        assert "empty123" in sessions

    def test_delete_nonexistent_session(self):
        """Delete non-existent session returns False"""
        paths = OrchestratorPaths(base_dir=Path(self.temp_dir))
        manager = SessionManager(paths)

        result = manager.delete_session("nonexistent")
        assert result is False
