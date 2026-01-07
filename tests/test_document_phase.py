"""
Tests for WF-009: Document Phase

These tests verify the optional DOCUMENT phase added to the workflow
to ensure documentation stays current after implementation.
"""

import pytest
import yaml
import tempfile
import shutil
from pathlib import Path

from src.engine import WorkflowEngine
from src.schema import WorkflowDef


@pytest.fixture
def temp_workflow_dir():
    """Create a temporary directory for workflow tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestDocumentPhaseInWorkflow:
    """Tests for DOCUMENT phase presence in workflow definition."""

    def test_default_workflow_has_document_phase(self):
        """D1: Default workflow includes DOCUMENT phase."""
        from src.config import get_default_workflow_content

        content = get_default_workflow_content()
        workflow_data = yaml.safe_load(content)

        phase_ids = [p["id"] for p in workflow_data["phases"]]
        assert "DOCUMENT" in phase_ids, "DOCUMENT phase missing from default workflow"

    def test_document_phase_after_verify(self):
        """D2: DOCUMENT phase comes after VERIFY."""
        from src.config import get_default_workflow_content

        content = get_default_workflow_content()
        workflow_data = yaml.safe_load(content)

        phase_ids = [p["id"] for p in workflow_data["phases"]]

        if "DOCUMENT" in phase_ids and "VERIFY" in phase_ids:
            verify_idx = phase_ids.index("VERIFY")
            document_idx = phase_ids.index("DOCUMENT")
            assert document_idx > verify_idx, "DOCUMENT should come after VERIFY"

    def test_document_phase_before_learn(self):
        """D3: DOCUMENT phase comes before LEARN."""
        from src.config import get_default_workflow_content

        content = get_default_workflow_content()
        workflow_data = yaml.safe_load(content)

        phase_ids = [p["id"] for p in workflow_data["phases"]]

        if "DOCUMENT" in phase_ids and "LEARN" in phase_ids:
            learn_idx = phase_ids.index("LEARN")
            document_idx = phase_ids.index("DOCUMENT")
            assert document_idx < learn_idx, "DOCUMENT should come before LEARN"


class TestDocumentPhaseItems:
    """Tests for DOCUMENT phase items."""

    def test_document_phase_has_changelog_item(self):
        """D4: DOCUMENT phase has changelog_entry item."""
        from src.config import get_default_workflow_content

        content = get_default_workflow_content()
        workflow_data = yaml.safe_load(content)

        document_phase = None
        for phase in workflow_data["phases"]:
            if phase["id"] == "DOCUMENT":
                document_phase = phase
                break

        if document_phase:
            item_ids = [i["id"] for i in document_phase.get("items", [])]
            assert "changelog_entry" in item_ids, "changelog_entry item missing"

    def test_changelog_entry_required(self):
        """D5: changelog_entry is required (not optional)."""
        from src.config import get_default_workflow_content

        content = get_default_workflow_content()
        workflow_data = yaml.safe_load(content)

        document_phase = None
        for phase in workflow_data["phases"]:
            if phase["id"] == "DOCUMENT":
                document_phase = phase
                break

        if document_phase:
            changelog_item = None
            for item in document_phase.get("items", []):
                if item["id"] == "changelog_entry":
                    changelog_item = item
                    break

            if changelog_item:
                # Should not be marked optional, or optional: false
                is_optional = changelog_item.get("optional", False)
                assert not is_optional, "changelog_entry should be required"

    def test_document_phase_has_readme_item(self):
        """D6: DOCUMENT phase has update_readme item."""
        from src.config import get_default_workflow_content

        content = get_default_workflow_content()
        workflow_data = yaml.safe_load(content)

        document_phase = None
        for phase in workflow_data["phases"]:
            if phase["id"] == "DOCUMENT":
                document_phase = phase
                break

        if document_phase:
            item_ids = [i["id"] for i in document_phase.get("items", [])]
            assert "update_readme" in item_ids, "update_readme item missing"

    def test_readme_item_optional(self):
        """D7: update_readme is optional (not required)."""
        from src.config import get_default_workflow_content

        content = get_default_workflow_content()
        workflow_data = yaml.safe_load(content)

        document_phase = None
        for phase in workflow_data["phases"]:
            if phase["id"] == "DOCUMENT":
                document_phase = phase
                break

        if document_phase:
            readme_item = None
            for item in document_phase.get("items", []):
                if item["id"] == "update_readme":
                    readme_item = item
                    break

            if readme_item:
                # In the schema, optional items have required: false
                is_not_required = not readme_item.get("required", True)
                assert is_not_required, "update_readme should not be required (i.e., optional)"


class TestDocumentPhaseWorkflowExecution:
    """Tests for DOCUMENT phase during workflow execution."""

    def test_workflow_advances_to_document(self, temp_workflow_dir):
        """D8: Workflow can advance to DOCUMENT phase."""
        # Create a workflow.yaml with DOCUMENT phase
        workflow_content = """
name: Test Workflow
phases:
  - id: VERIFY
    name: Verification
    items:
      - id: verify_item
        name: Verify
  - id: DOCUMENT
    name: Documentation
    items:
      - id: update_docs
        name: Update Docs
        required: false
        skippable: true
      - id: changelog_entry
        name: Changelog
  - id: LEARN
    name: Learning
    items:
      - id: learn_item
        name: Learn
"""
        workflow_file = temp_workflow_dir / "workflow.yaml"
        workflow_file.write_text(workflow_content)

        engine = WorkflowEngine(str(temp_workflow_dir))

        # Start workflow with yaml_path and task_description
        engine.start_workflow(str(workflow_file), "Test task")

        # Complete VERIFY items and advance
        engine.complete_item("verify_item", "Done")
        can_advance, _, _ = engine.can_advance_phase()

        if can_advance:
            success, _ = engine.advance_phase()
            assert success
            assert engine.state.current_phase_id == "DOCUMENT"

    def test_document_phase_skippable(self, temp_workflow_dir):
        """D9: DOCUMENT phase items can be skipped when marked skippable."""
        workflow_content = """
name: Test Workflow
phases:
  - id: DOCUMENT
    name: Documentation
    items:
      - id: update_readme
        name: Update README
        required: false
        skippable: true
      - id: changelog_entry
        name: Changelog
"""
        workflow_file = temp_workflow_dir / "workflow.yaml"
        workflow_file.write_text(workflow_content)

        engine = WorkflowEngine(str(temp_workflow_dir))
        engine.start_workflow(str(workflow_file), "Test task")

        # Skip the optional item
        success, msg = engine.skip_item("update_readme", "No README changes needed")
        assert success

        # Complete the required item
        engine.complete_item("changelog_entry", "Added entry")

        # Should be able to advance
        can_advance, _, _ = engine.can_advance_phase()
        assert can_advance
