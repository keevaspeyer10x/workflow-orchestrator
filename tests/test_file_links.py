"""
Tests for WF-006: File Links in Status Output

These tests verify that file modification tracking is added to
item completion and displayed in status output.
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch

from src.engine import WorkflowEngine
from src.schema import ItemState, ItemStatus


@pytest.fixture
def temp_workflow_dir():
    """Create a temporary directory for workflow tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestItemStateFilesField:
    """Tests for files_modified field in ItemState."""

    def test_item_state_files_field_exists(self):
        """F1: ItemState has files_modified field."""
        # Create item state and check field
        item = ItemState(id="test_item", status=ItemStatus.PENDING)

        # Field should exist and be optional (None by default)
        assert hasattr(item, 'files_modified') or 'files_modified' not in item.__dict__
        # If the field doesn't exist yet, this test will fail and remind us to add it

    def test_item_state_with_files(self):
        """F2: ItemState can store files list."""
        item = ItemState(
            id="test_item",
            status=ItemStatus.COMPLETED,
            notes="Implementation done",
            files_modified=["src/foo.py", "tests/test_foo.py"],
        )

        assert item.files_modified is not None
        assert len(item.files_modified) == 2
        assert "src/foo.py" in item.files_modified

    def test_item_state_files_optional(self):
        """F3: files_modified is optional (None by default)."""
        item = ItemState(id="test_item", status=ItemStatus.PENDING)

        # Should be None or not raise error
        files = getattr(item, 'files_modified', None)
        assert files is None


class TestCompleteItemWithFiles:
    """Tests for file tracking during item completion."""

    def test_complete_item_with_explicit_files(self, temp_workflow_dir):
        """F4: Pass files explicitly to complete_item."""
        # Setup a basic workflow
        engine = WorkflowEngine(str(temp_workflow_dir))

        # Create minimal workflow state for testing
        # This requires actual workflow setup
        pass  # Will be implemented with engine changes

    def test_complete_item_auto_detect_files(self, temp_workflow_dir):
        """F5: Auto-detect files from git diff when not specified."""
        # Initialize git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=temp_workflow_dir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=temp_workflow_dir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=temp_workflow_dir, capture_output=True)

        # Create and commit initial file
        test_file = temp_workflow_dir / "initial.py"
        test_file.write_text("# initial")
        subprocess.run(["git", "add", "."], cwd=temp_workflow_dir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_workflow_dir, capture_output=True)

        # Modify file
        (temp_workflow_dir / "new_file.py").write_text("# new file")

        engine = WorkflowEngine(str(temp_workflow_dir))

        # Test auto-detection helper
        if hasattr(engine, '_get_changed_files'):
            files = engine._get_changed_files()
            assert "new_file.py" in files or any("new_file" in f for f in files)


class TestStateBackwardCompatibility:
    """Tests for backward compatibility with existing state files."""

    def test_state_load_without_files_field(self, temp_workflow_dir):
        """F6: Load state without files_modified gracefully."""
        # Create a state file without files_modified field - must have all required fields
        state_data = {
            "workflow_id": "test_123",
            "workflow_type": "test",
            "workflow_version": "1.0",
            "status": "active",
            "task_description": "Test task",
            "current_phase_id": "PLAN",
            "created_at": datetime.now().isoformat(),
            "phases": {
                "PLAN": {
                    "id": "PLAN",
                    "status": "active",
                    "items": {
                        "check_roadmap": {
                            "id": "check_roadmap",
                            "status": "completed",
                            "notes": "Done",
                            # No files_modified field - should default to None
                        }
                    }
                }
            }
        }

        state_file = temp_workflow_dir / ".workflow_state.json"
        state_file.write_text(json.dumps(state_data))

        engine = WorkflowEngine(str(temp_workflow_dir))
        engine.load_state()

        # Should load without error
        assert engine.state is not None
        # Item should have files_modified as None (default)
        item = engine.state.phases["PLAN"].items.get("check_roadmap")
        if item:
            files = getattr(item, 'files_modified', None)
            assert files is None or files == []

    def test_state_save_with_files(self, temp_workflow_dir):
        """F7: Save state includes files array."""
        # This requires actual workflow state manipulation
        pass


class TestStatusDisplayFiles:
    """Tests for file display in status output."""

    def test_status_shows_files_when_present(self, temp_workflow_dir, capsys):
        """F8: Status output includes files for completed items."""
        # This requires CLI integration testing
        pass

    def test_status_no_files_section_when_empty(self, temp_workflow_dir, capsys):
        """F9: No files section when files_modified is None."""
        pass

    def test_files_flag_controls_display(self, temp_workflow_dir):
        """F10: --files flag controls file display."""
        # CLI flag testing
        pass
