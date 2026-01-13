"""Tests for PathResolver - CORE-025 Multi-Repo Containment Strategy"""

import tempfile
from pathlib import Path

import pytest


class TestOrchestratorPaths:
    """Tests for OrchestratorPaths class"""

    def test_repo_root_detection_git(self, tmp_path):
        """CWD subdirectory with .git/ in parent -> base_dir points to parent"""
        from src.path_resolver import OrchestratorPaths

        # Create repo structure
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        subdir = tmp_path / "src" / "components"
        subdir.mkdir(parents=True)

        # Change to subdirectory and create OrchestratorPaths
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(subdir)
            paths = OrchestratorPaths()
            assert paths.base_dir == tmp_path
        finally:
            os.chdir(original_cwd)

    def test_repo_root_detection_workflow_yaml(self, tmp_path):
        """workflow.yaml found before .git/ -> uses that directory"""
        from src.path_resolver import OrchestratorPaths

        # Create workflow.yaml in parent
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("version: '1.0'")
        subdir = tmp_path / "src"
        subdir.mkdir()

        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(subdir)
            paths = OrchestratorPaths()
            assert paths.base_dir == tmp_path
        finally:
            os.chdir(original_cwd)

    def test_repo_root_fallback_cwd(self, tmp_path):
        """No .git/ or workflow.yaml -> falls back to CWD"""
        from src.path_resolver import OrchestratorPaths

        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            paths = OrchestratorPaths()
            assert paths.base_dir == tmp_path
        finally:
            os.chdir(original_cwd)

    def test_explicit_base_dir(self, tmp_path):
        """Explicit base_dir parameter is used"""
        from src.path_resolver import OrchestratorPaths

        paths = OrchestratorPaths(base_dir=tmp_path)
        assert paths.base_dir == tmp_path

    def test_session_dir_path(self, tmp_path):
        """session_id='abc12345' returns .orchestrator/sessions/abc12345/"""
        from src.path_resolver import OrchestratorPaths

        paths = OrchestratorPaths(base_dir=tmp_path, session_id="abc12345")
        expected = tmp_path / ".orchestrator" / "sessions" / "abc12345"
        assert paths.session_dir() == expected

    def test_session_dir_no_id_raises(self, tmp_path):
        """session_id=None raises ValueError"""
        from src.path_resolver import OrchestratorPaths

        paths = OrchestratorPaths(base_dir=tmp_path)
        with pytest.raises(ValueError, match="No session ID set"):
            paths.session_dir()

    def test_state_file_with_session(self, tmp_path):
        """Returns .orchestrator/sessions/<id>/state.json"""
        from src.path_resolver import OrchestratorPaths

        paths = OrchestratorPaths(base_dir=tmp_path, session_id="test123")
        expected = tmp_path / ".orchestrator" / "sessions" / "test123" / "state.json"
        assert paths.state_file() == expected

    def test_state_file_without_session(self, tmp_path):
        """Returns .orchestrator/state.json when no session"""
        from src.path_resolver import OrchestratorPaths

        paths = OrchestratorPaths(base_dir=tmp_path)
        expected = tmp_path / ".orchestrator" / "state.json"
        assert paths.state_file() == expected

    def test_log_file_path_with_session(self, tmp_path):
        """Returns correct log path with session"""
        from src.path_resolver import OrchestratorPaths

        paths = OrchestratorPaths(base_dir=tmp_path, session_id="sess1")
        expected = tmp_path / ".orchestrator" / "sessions" / "sess1" / "log.jsonl"
        assert paths.log_file() == expected

    def test_log_file_path_without_session(self, tmp_path):
        """Returns correct log path without session"""
        from src.path_resolver import OrchestratorPaths

        paths = OrchestratorPaths(base_dir=tmp_path)
        expected = tmp_path / ".orchestrator" / "log.jsonl"
        assert paths.log_file() == expected

    def test_checkpoints_dir_path(self, tmp_path):
        """Returns correct checkpoints directory"""
        from src.path_resolver import OrchestratorPaths

        paths = OrchestratorPaths(base_dir=tmp_path, session_id="sess1")
        expected = tmp_path / ".orchestrator" / "sessions" / "sess1" / "checkpoints"
        assert paths.checkpoints_dir() == expected

    def test_feedback_dir_path(self, tmp_path):
        """Returns correct feedback directory"""
        from src.path_resolver import OrchestratorPaths

        paths = OrchestratorPaths(base_dir=tmp_path, session_id="sess1")
        expected = tmp_path / ".orchestrator" / "sessions" / "sess1" / "feedback"
        assert paths.feedback_dir() == expected

    def test_meta_file_path(self, tmp_path):
        """Returns .orchestrator/meta.json"""
        from src.path_resolver import OrchestratorPaths

        paths = OrchestratorPaths(base_dir=tmp_path)
        expected = tmp_path / ".orchestrator" / "meta.json"
        assert paths.meta_file() == expected

    def test_migration_marker_path(self, tmp_path):
        """Returns .orchestrator/.migration_complete"""
        from src.path_resolver import OrchestratorPaths

        paths = OrchestratorPaths(base_dir=tmp_path)
        expected = tmp_path / ".orchestrator" / ".migration_complete"
        assert paths.migration_marker() == expected

    def test_find_legacy_state_exists(self, tmp_path):
        """.workflow_state.json exists -> returns path"""
        from src.path_resolver import OrchestratorPaths

        legacy_file = tmp_path / ".workflow_state.json"
        legacy_file.write_text('{"test": true}')

        paths = OrchestratorPaths(base_dir=tmp_path)
        assert paths.find_legacy_state_file() == legacy_file

    def test_find_legacy_state_not_exists(self, tmp_path):
        """No legacy file -> returns None"""
        from src.path_resolver import OrchestratorPaths

        paths = OrchestratorPaths(base_dir=tmp_path)
        assert paths.find_legacy_state_file() is None

    def test_find_legacy_log_exists(self, tmp_path):
        """.workflow_log.jsonl exists -> returns path"""
        from src.path_resolver import OrchestratorPaths

        legacy_file = tmp_path / ".workflow_log.jsonl"
        legacy_file.write_text('{"event": "test"}\n')

        paths = OrchestratorPaths(base_dir=tmp_path)
        assert paths.find_legacy_log_file() == legacy_file

    def test_find_legacy_log_not_exists(self, tmp_path):
        """No legacy log file -> returns None"""
        from src.path_resolver import OrchestratorPaths

        paths = OrchestratorPaths(base_dir=tmp_path)
        assert paths.find_legacy_log_file() is None

    def test_orchestrator_dir_property(self, tmp_path):
        """orchestrator_dir returns .orchestrator/ path"""
        from src.path_resolver import OrchestratorPaths

        paths = OrchestratorPaths(base_dir=tmp_path)
        expected = tmp_path / ".orchestrator"
        assert paths.orchestrator_dir == expected

    def test_web_mode_flag(self, tmp_path):
        """web_mode flag is stored"""
        from src.path_resolver import OrchestratorPaths

        paths = OrchestratorPaths(base_dir=tmp_path, web_mode=True)
        assert paths.web_mode is True

        paths2 = OrchestratorPaths(base_dir=tmp_path, web_mode=False)
        assert paths2.web_mode is False
