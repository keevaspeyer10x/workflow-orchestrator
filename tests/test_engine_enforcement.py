"""
Integration tests for step enforcement in WorkflowEngine.

Tests that the engine properly enforces step types:
- gate: Runs command via HardGateExecutor, cannot skip
- required: Cannot skip
- documented: Can skip with reasoning, evidence validated if provided
- flexible: Can skip with reasoning, no evidence required
"""

import pytest
import json
import yaml
import tempfile
from pathlib import Path

from src.engine import WorkflowEngine
from src.schema import (
    WorkflowDef, PhaseDef, ChecklistItemDef,
    VerificationConfig, VerificationType, StepType, ItemStatus
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for workflow tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def engine(temp_dir):
    """Create a workflow engine with temp directory."""
    return WorkflowEngine(working_dir=str(temp_dir))


def write_workflow_yaml(temp_dir: Path, workflow_dict: dict) -> Path:
    """Write a workflow definition to a YAML file."""
    yaml_path = temp_dir / "workflow.yaml"
    with open(yaml_path, 'w') as f:
        yaml.dump(workflow_dict, f)
    return yaml_path


def get_test_workflow_dict() -> dict:
    """Get a workflow definition dict with various step types for testing."""
    return {
        "name": "Test Workflow",
        "version": "1.0",
        "phases": [
            {
                "id": "TEST",
                "name": "Test Phase",
                "items": [
                    # Gate step - must run command
                    {
                        "id": "gate_step",
                        "name": "Gate Step",
                        "step_type": "gate",
                        "verification": {
                            "type": "command",
                            "command": "echo 'gate passed'"
                        }
                    },
                    # Required step - cannot skip
                    {
                        "id": "required_step",
                        "name": "Required Step",
                        "step_type": "required"
                    },
                    # Documented step - needs evidence
                    {
                        "id": "documented_step",
                        "name": "Documented Step",
                        "step_type": "documented",
                        "evidence_schema": "CodeAnalysisEvidence"
                    },
                    # Flexible step - full latitude
                    {
                        "id": "flexible_step",
                        "name": "Flexible Step",
                        "step_type": "flexible"
                    },
                ]
            }
        ]
    }


def setup_workflow(engine, temp_dir, workflow_dict: dict = None):
    """Helper to set up a workflow from a dict."""
    if workflow_dict is None:
        workflow_dict = get_test_workflow_dict()
    yaml_path = write_workflow_yaml(temp_dir, workflow_dict)
    engine.start_workflow(str(yaml_path), "Test task")
    return engine


class TestGateStepEnforcement:
    """Test gate step enforcement."""

    def test_gate_step_cannot_be_skipped(self, engine, temp_dir):
        """Gate steps should not be skippable."""
        setup_workflow(engine, temp_dir)

        success, message = engine.skip_item(
            "gate_step",
            "I want to skip this gate step because it's not needed for this test scenario"
        )

        assert not success
        assert "not skippable" in message.lower() or "gate" in message.lower()

    def test_gate_step_runs_command_on_complete(self, engine, temp_dir):
        """Gate steps should execute their command when completed."""
        setup_workflow(engine, temp_dir)

        success, message = engine.complete_item("gate_step")

        assert success
        # Check that gate_result was stored
        item_state = engine.state.phases["TEST"].items["gate_step"]
        assert item_state.gate_result is not None
        assert item_state.gate_result.get("success") is True

    def test_gate_step_fails_on_command_failure(self, engine, temp_dir):
        """Gate steps should fail if command returns non-zero."""
        workflow_dict = {
            "name": "Test",
            "version": "1.0",
            "phases": [{
                "id": "TEST",
                "name": "Test",
                "items": [{
                    "id": "failing_gate",
                    "name": "Failing Gate",
                    "step_type": "gate",
                    "verification": {
                        "type": "command",
                        "command": "bash -c 'exit 1'"
                    }
                }]
            }]
        }
        setup_workflow(engine, temp_dir, workflow_dict)

        success, message = engine.complete_item("failing_gate")

        assert not success
        assert "failed" in message.lower() or "gate" in message.lower()


class TestRequiredStepEnforcement:
    """Test required step enforcement."""

    def test_required_step_cannot_be_skipped(self, engine, temp_dir):
        """Required steps should not be skippable."""
        setup_workflow(engine, temp_dir)

        success, message = engine.skip_item(
            "required_step",
            "I want to skip this required step because it seems unnecessary for my use case"
        )

        assert not success
        assert "not skippable" in message.lower() or "required" in message.lower()

    def test_required_step_can_be_completed(self, engine, temp_dir):
        """Required steps should be completable without evidence."""
        setup_workflow(engine, temp_dir)

        success, message = engine.complete_item("required_step", notes="Completed required step")

        assert success


class TestDocumentedStepEnforcement:
    """Test documented step enforcement."""

    def test_documented_step_can_be_skipped_with_reasoning(self, engine, temp_dir):
        """Documented steps can be skipped with substantive reasoning."""
        setup_workflow(engine, temp_dir)

        success, message = engine.skip_item(
            "documented_step",
            "This step is not applicable because we are only modifying test files, "
            "not production code. No code analysis is needed for test-only changes."
        )

        assert success

    def test_documented_step_rejects_shallow_skip_reasoning(self, engine, temp_dir):
        """Documented steps should reject shallow skip reasoning."""
        setup_workflow(engine, temp_dir)

        success, message = engine.skip_item("documented_step", "not needed")

        assert not success
        assert "shallow" in message.lower() or "short" in message.lower() or "reason" in message.lower()

    def test_documented_step_validates_evidence(self, engine, temp_dir):
        """Documented steps should validate evidence when provided."""
        setup_workflow(engine, temp_dir)

        valid_evidence = {
            "files_reviewed": ["src/main.py", "src/utils.py"],
            "patterns_identified": ["Factory pattern", "Singleton"],
            "concerns_raised": ["No error handling in main.py"],
            "approach_decision": "Will use factory pattern and add proper error handling with try/except blocks"
        }

        success, message = engine.complete_item(
            "documented_step",
            notes="Analysis complete",
            evidence=valid_evidence
        )

        assert success
        # Check evidence was stored
        item_state = engine.state.phases["TEST"].items["documented_step"]
        assert item_state.evidence is not None
        assert "files_reviewed" in item_state.evidence

    def test_documented_step_rejects_invalid_evidence(self, engine, temp_dir):
        """Documented steps should reject evidence that doesn't match schema."""
        setup_workflow(engine, temp_dir)

        invalid_evidence = {
            "files_reviewed": [],  # Empty - should fail
            "patterns_identified": [],
            "concerns_raised": [],
            "approach_decision": "ok"  # Too short
        }

        success, message = engine.complete_item(
            "documented_step",
            notes="Analysis complete",
            evidence=invalid_evidence
        )

        assert not success
        assert "evidence" in message.lower() or "validation" in message.lower()

    def test_documented_step_can_complete_without_evidence(self, engine, temp_dir):
        """Documented steps can be completed without evidence (it's optional)."""
        setup_workflow(engine, temp_dir)

        success, message = engine.complete_item(
            "documented_step",
            notes="Completed documented step without evidence"
        )

        # This should succeed - evidence is recommended but not required
        assert success


class TestFlexibleStepEnforcement:
    """Test flexible step enforcement."""

    def test_flexible_step_can_be_skipped(self, engine, temp_dir):
        """Flexible steps can be skipped with reasoning."""
        setup_workflow(engine, temp_dir)

        success, message = engine.skip_item(
            "flexible_step",
            "This flexible step is being skipped because the feature we're implementing "
            "doesn't require this particular check. We've verified this is safe to skip."
        )

        assert success

    def test_flexible_step_can_be_completed(self, engine, temp_dir):
        """Flexible steps can be completed without evidence."""
        setup_workflow(engine, temp_dir)

        success, message = engine.complete_item(
            "flexible_step",
            notes="Completed flexible step"
        )

        assert success


class TestSkipContextConsidered:
    """Test that skip context is stored."""

    def test_skip_context_stored(self, engine, temp_dir):
        """Skip context should be stored in item state."""
        setup_workflow(engine, temp_dir)

        context = ["Checked file types", "Verified no production changes", "Consulted documentation"]

        success, message = engine.skip_item(
            "flexible_step",
            "This step is skipped because we're only modifying documentation files. "
            "No code changes are being made, so this step doesn't apply.",
            context_considered=context
        )

        assert success
        item_state = engine.state.phases["TEST"].items["flexible_step"]
        assert item_state.skip_context_considered == context


class TestStepTypeDefaultBehavior:
    """Test that default step type (flexible) maintains backwards compatibility."""

    def test_default_step_type_is_flexible(self, engine, temp_dir):
        """Items without step_type should default to flexible."""
        workflow_dict = {
            "name": "Test",
            "version": "1.0",
            "phases": [{
                "id": "TEST",
                "name": "Test",
                "items": [{
                    "id": "default_item",
                    "name": "Default Item"
                    # No step_type specified
                }]
            }]
        }
        yaml_path = write_workflow_yaml(temp_dir, workflow_dict)
        engine.load_workflow_def(str(yaml_path))

        assert engine.workflow_def.phases[0].items[0].step_type == StepType.FLEXIBLE

    def test_backwards_compatible_skip(self, engine, temp_dir):
        """Items without step_type should allow skipping (backwards compatibility)."""
        workflow_dict = {
            "name": "Test",
            "version": "1.0",
            "phases": [{
                "id": "TEST",
                "name": "Test",
                "items": [{
                    "id": "old_item",
                    "name": "Old Item",
                    "skippable": True
                }]
            }]
        }
        setup_workflow(engine, temp_dir, workflow_dict)

        # Old-style skip with just a reason (no strict validation for flexible)
        success, message = engine.skip_item(
            "old_item",
            "Skipping this old-style item because it's not needed for this particular task"
        )

        assert success
