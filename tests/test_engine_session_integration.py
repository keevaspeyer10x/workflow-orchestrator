"""
Tests for CORE-025 Phase 2: WorkflowEngine Session Integration

Tests the integration of OrchestratorPaths and SessionManager with WorkflowEngine,
ensuring state files are stored in .orchestrator/sessions/<id>/ with backward
compatibility for legacy .workflow_state.json files.
"""

import json
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

from src.engine import WorkflowEngine
from src.path_resolver import OrchestratorPaths
from src.session_manager import SessionManager
from src.schema import WorkflowState, WorkflowStatus


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    shutil.rmtree(tmp)


@pytest.fixture
def workflow_yaml(temp_dir):
    """Create a minimal workflow.yaml for testing."""
    content = """
name: test-workflow
version: "1.0.0"
phases:
  - id: PLAN
    name: Planning
    items:
      - id: check_roadmap
        name: Review Roadmap
        verification:
          type: none
"""
    yaml_path = temp_dir / "workflow.yaml"
    yaml_path.write_text(content)
    return yaml_path


class TestEngineInitialization:
    """Tests for WorkflowEngine initialization with session support."""

    def test_engine_init_with_session_id(self, temp_dir):
        """Engine with session_id sets up paths correctly."""
        engine = WorkflowEngine(working_dir=str(temp_dir), session_id="abc12345")

        assert engine.paths is not None
        assert engine.paths.session_id == "abc12345"
        assert "sessions/abc12345" in str(engine.state_file)

    def test_engine_init_without_session_id(self, temp_dir):
        """Engine without session_id uses default paths."""
        engine = WorkflowEngine(working_dir=str(temp_dir))

        assert engine.paths is not None
        assert engine.paths.session_id is None
        # Should use orchestrator dir but not session-specific
        assert ".orchestrator" in str(engine.state_file)

    def test_engine_state_file_uses_paths(self, temp_dir):
        """engine.state_file matches paths.state_file()."""
        engine = WorkflowEngine(working_dir=str(temp_dir), session_id="test123")

        assert engine.state_file == engine.paths.state_file()

    def test_engine_log_file_uses_paths(self, temp_dir):
        """engine.log_file matches paths.log_file()."""
        engine = WorkflowEngine(working_dir=str(temp_dir), session_id="test123")

        assert engine.log_file == engine.paths.log_file()


class TestStateHandling:
    """Tests for state handling with session-based paths."""

    def test_load_state_prefers_new_path(self, temp_dir, workflow_yaml):
        """New path preferred when both exist."""
        # Create legacy state
        legacy_data = {
            "workflow_id": "wf_legacy",
            "workflow_type": "test",
            "workflow_version": "1.0.0",
            "task_description": "Legacy task",
            "current_phase_id": "PLAN",
            "status": "active",
            "phases": {"PLAN": {"id": "PLAN", "status": "active", "items": {}}}
        }
        (temp_dir / ".workflow_state.json").write_text(json.dumps(legacy_data))

        # Create new session state
        session_id = "newsess1"
        session_dir = temp_dir / ".orchestrator" / "sessions" / session_id
        session_dir.mkdir(parents=True)
        new_data = {
            "workflow_id": "wf_new123",
            "workflow_type": "test",
            "workflow_version": "1.0.0",
            "task_description": "New session task",
            "current_phase_id": "PLAN",
            "status": "active",
            "phases": {"PLAN": {"id": "PLAN", "status": "active", "items": {}}}
        }
        (session_dir / "state.json").write_text(json.dumps(new_data))

        engine = WorkflowEngine(working_dir=str(temp_dir), session_id=session_id)
        state = engine.load_state()

        assert state is not None
        assert state.workflow_id == "wf_new123"
        assert state.task_description == "New session task"

    def test_save_state_uses_new_path(self, temp_dir, workflow_yaml):
        """State saved to new path only."""
        session_id = "savetes1"
        engine = WorkflowEngine(working_dir=str(temp_dir), session_id=session_id)

        # Start a workflow (this creates state)
        engine.start_workflow(str(workflow_yaml), "Test task")

        # Verify written to new path
        session_state = temp_dir / ".orchestrator" / "sessions" / session_id / "state.json"
        assert session_state.exists()

        # Legacy path NOT created
        legacy_path = temp_dir / ".workflow_state.json"
        assert not legacy_path.exists()

    def test_save_state_creates_session_dir(self, temp_dir, workflow_yaml):
        """Session directory created on first save."""
        session_id = "newdir12"
        engine = WorkflowEngine(working_dir=str(temp_dir), session_id=session_id)

        # Session dir shouldn't exist yet
        session_dir = temp_dir / ".orchestrator" / "sessions" / session_id
        assert not session_dir.exists()

        # Start workflow (triggers save)
        engine.start_workflow(str(workflow_yaml), "Test task")

        # Now it should exist
        assert session_dir.exists()
        assert (session_dir / "state.json").exists()

    def test_legacy_not_modified_on_save(self, temp_dir, workflow_yaml):
        """Legacy file unchanged when writing to new path."""
        # Create legacy state with COMPLETED status (not active)
        legacy_data = {
            "workflow_id": "wf_oldone",
            "workflow_type": "test",
            "workflow_version": "1.0.0",
            "task_description": "Old completed task",
            "current_phase_id": "PLAN",
            "status": "completed",  # COMPLETED so it doesn't block new workflow
            "phases": {"PLAN": {"id": "PLAN", "status": "completed", "items": {}}}
        }
        legacy_file = temp_dir / ".workflow_state.json"
        legacy_content = json.dumps(legacy_data)
        legacy_file.write_text(legacy_content)

        # Create engine with session and start new workflow
        session_id = "nomod123"
        engine = WorkflowEngine(working_dir=str(temp_dir), session_id=session_id)
        engine.start_workflow(str(workflow_yaml), "New task")

        # Legacy file should be unchanged
        assert legacy_file.read_text() == legacy_content


class TestLogFileHandling:
    """Tests for log file handling with sessions."""

    def test_log_event_uses_new_path(self, temp_dir, workflow_yaml):
        """Events logged to session log file."""
        session_id = "logtest1"
        engine = WorkflowEngine(working_dir=str(temp_dir), session_id=session_id)
        engine.start_workflow(str(workflow_yaml), "Test task")

        # Log file should be in session directory
        session_log = temp_dir / ".orchestrator" / "sessions" / session_id / "log.jsonl"
        assert session_log.exists()

        # Should have events logged (event_type is lowercase in JSON)
        content = session_log.read_text()
        assert "workflow_started" in content

    def test_get_events_reads_from_new_path(self, temp_dir, workflow_yaml):
        """Events read from session log file."""
        session_id = "readlog1"
        engine = WorkflowEngine(working_dir=str(temp_dir), session_id=session_id)
        engine.start_workflow(str(workflow_yaml), "Test task")

        events = engine.get_events()
        assert len(events) > 0
        assert any(e.message and "Started workflow" in e.message for e in events)


class TestWorkflowLifecycle:
    """Integration tests for full workflow lifecycle with sessions."""

    def test_full_workflow_with_sessions(self, temp_dir, workflow_yaml):
        """Complete workflow in session directory."""
        session_id = "fullwf01"
        engine = WorkflowEngine(working_dir=str(temp_dir), session_id=session_id)

        # Start workflow
        state = engine.start_workflow(str(workflow_yaml), "Integration test")
        assert state.workflow_id.startswith("wf_")

        # Complete an item
        success, msg = engine.complete_item("check_roadmap", notes="Done")
        assert success

        # Advance phase
        success, msg = engine.advance_phase()
        assert success or "All phases completed" in msg

        # Verify state in session directory
        session_dir = temp_dir / ".orchestrator" / "sessions" / session_id
        assert (session_dir / "state.json").exists()
        assert (session_dir / "log.jsonl").exists()

    def test_workflow_state_in_session_dir(self, temp_dir, workflow_yaml):
        """State file in .orchestrator/sessions/<id>/state.json."""
        session_id = "statedir"
        engine = WorkflowEngine(working_dir=str(temp_dir), session_id=session_id)
        engine.start_workflow(str(workflow_yaml), "Test")

        expected_path = temp_dir / ".orchestrator" / "sessions" / session_id / "state.json"
        assert expected_path.exists()

        # Verify content
        data = json.loads(expected_path.read_text())
        assert data["task_description"] == "Test"

    def test_workflow_log_in_session_dir(self, temp_dir, workflow_yaml):
        """Log file in .orchestrator/sessions/<id>/log.jsonl."""
        session_id = "logdir01"
        engine = WorkflowEngine(working_dir=str(temp_dir), session_id=session_id)
        engine.start_workflow(str(workflow_yaml), "Test")

        expected_path = temp_dir / ".orchestrator" / "sessions" / session_id / "log.jsonl"
        assert expected_path.exists()


class TestSessionIsolation:
    """Tests for session isolation."""

    def test_concurrent_sessions(self, temp_dir, workflow_yaml):
        """Two workflows in different sessions don't conflict."""
        # Create two separate temp dirs simulating different repos
        dir1 = temp_dir / "repo1"
        dir2 = temp_dir / "repo2"
        dir1.mkdir()
        dir2.mkdir()

        # Copy workflow.yaml to both
        shutil.copy(workflow_yaml, dir1 / "workflow.yaml")
        shutil.copy(workflow_yaml, dir2 / "workflow.yaml")

        # Start workflows in each
        engine1 = WorkflowEngine(working_dir=str(dir1), session_id="sess0001")
        engine2 = WorkflowEngine(working_dir=str(dir2), session_id="sess0002")

        state1 = engine1.start_workflow(str(dir1 / "workflow.yaml"), "Task 1")
        state2 = engine2.start_workflow(str(dir2 / "workflow.yaml"), "Task 2")

        # Both should have independent state
        assert state1.workflow_id != state2.workflow_id
        assert state1.task_description == "Task 1"
        assert state2.task_description == "Task 2"

        # Completing one shouldn't affect the other
        engine1.complete_item("check_roadmap", notes="Done 1")

        # Reload engine2's state
        engine2.reload()
        item_state = engine2.get_item_state("check_roadmap")
        assert item_state.status.value == "pending"  # Still pending in engine2


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_session_id_string(self, temp_dir):
        """Empty session_id string raises ValueError."""
        with pytest.raises(ValueError):
            engine = WorkflowEngine(working_dir=str(temp_dir), session_id="")
            # Force path resolution
            _ = engine.paths.session_dir()

    def test_session_directory_created_automatically(self, temp_dir, workflow_yaml):
        """Session directory created when starting workflow."""
        session_id = "autodir1"
        session_dir = temp_dir / ".orchestrator" / "sessions" / session_id

        assert not session_dir.exists()

        engine = WorkflowEngine(working_dir=str(temp_dir), session_id=session_id)
        engine.start_workflow(str(workflow_yaml), "Test")

        assert session_dir.exists()
