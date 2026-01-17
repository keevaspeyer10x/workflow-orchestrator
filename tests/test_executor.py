"""
Acceptance tests for control inversion.
These MUST pass before the feature is complete.
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from src.v4.models import WorkflowSpec, PhaseSpec, PhaseType, WorkflowStatus
from src.v4.state import StateStore
from src.v4.gate_engine import GateEngine
from src.v4.parser import parse_workflow
from src.executor import WorkflowExecutor
from src.runners.base import AgentRunner
from src.v4.models import PhaseInput, PhaseOutput


class MockRunner(AgentRunner):
    """Mock runner for testing"""
    def __init__(self, outputs=None):
        self.outputs = outputs or []
        self.call_count = 0

    def run_phase(self, phase_input: PhaseInput) -> PhaseOutput:
        self.call_count += 1
        return PhaseOutput(
            phase_id=phase_input.phase_id,
            success=True,
            summary="Mock execution complete"
        )


def test_workflow_completes_even_if_llm_doesnt_call_finish():
    """
    CORE REQUIREMENT: Orchestrator guarantees completion.
    The LLM cannot prevent the workflow from finishing.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)

        # Create a simple workflow
        workflow_yaml = working_dir / "workflow.yaml"
        workflow_yaml.write_text("""
workflow:
  version: "4.0"
  name: "Test Workflow"
  phases:
    - id: phase1
      name: "Phase 1"
      gates: []
      next: null
""")

        # Create required file for gate
        spec = parse_workflow(workflow_yaml)
        state_store = StateStore(working_dir)
        gate_engine = GateEngine(working_dir)
        runner = MockRunner()

        executor = WorkflowExecutor(spec, runner, state_store, gate_engine)
        result = executor.run("Test task")

        # Even though the mock LLM never called anything special,
        # the workflow completed
        assert result.status == WorkflowStatus.COMPLETED
        assert "phase1" in result.phases_completed


def test_llm_cannot_skip_phases():
    """
    Phase order is enforced programmatically.
    LLM cannot skip from phase1 to phase3.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)

        workflow_yaml = working_dir / "workflow.yaml"
        workflow_yaml.write_text("""
workflow:
  version: "4.0"
  name: "Multi-phase Workflow"
  phases:
    - id: phase1
      name: "Phase 1"
      gates: []
      next: phase2
    - id: phase2
      name: "Phase 2"
      gates: []
      next: phase3
    - id: phase3
      name: "Phase 3"
      gates: []
      next: null
""")

        spec = parse_workflow(workflow_yaml)
        state_store = StateStore(working_dir)
        gate_engine = GateEngine(working_dir)
        runner = MockRunner()

        executor = WorkflowExecutor(spec, runner, state_store, gate_engine)
        result = executor.run("Test task")

        # Phases executed in order
        assert result.phases_completed == ["phase1", "phase2", "phase3"]
        assert runner.call_count == 3  # Called once per phase


def test_gates_validated_by_code_not_llm():
    """
    Gate validation is done by code, not LLM self-report.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)

        # Workflow requires a file that doesn't exist
        workflow_yaml = working_dir / "workflow.yaml"
        workflow_yaml.write_text("""
workflow:
  version: "4.0"
  name: "Gate Test"
  phases:
    - id: phase1
      name: "Phase 1"
      max_attempts: 1
      gates:
        - type: file_exists
          path: required_file.txt
      next: null
""")

        spec = parse_workflow(workflow_yaml)
        state_store = StateStore(working_dir)
        gate_engine = GateEngine(working_dir)

        # Mock runner that claims success but doesn't create file
        runner = MockRunner()

        executor = WorkflowExecutor(spec, runner, state_store, gate_engine)
        result = executor.run("Test task")

        # Workflow fails because gate (code check) fails
        # Even though runner said it succeeded
        assert result.status == WorkflowStatus.FAILED


def test_finalize_always_called():
    """
    The finalize step (mark_complete) is always called,
    even if phases fail.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)

        workflow_yaml = working_dir / "workflow.yaml"
        workflow_yaml.write_text("""
workflow:
  version: "4.0"
  name: "Finalize Test"
  phases:
    - id: phase1
      name: "Phase 1"
      max_attempts: 1
      gates:
        - type: command
          cmd: "exit 1"
      next: null
""")

        spec = parse_workflow(workflow_yaml)
        state_store = StateStore(working_dir)
        gate_engine = GateEngine(working_dir)
        runner = MockRunner()

        executor = WorkflowExecutor(spec, runner, state_store, gate_engine)
        result = executor.run("Test task")

        # Workflow failed but state is properly marked
        assert result.status == WorkflowStatus.FAILED

        # Reload state and verify it's marked complete
        state_store_new = StateStore(working_dir)
        state = state_store_new.load(result.workflow_id)
        assert state.status == WorkflowStatus.FAILED
        assert state.completed_at is not None


# Additional unit tests for gate engine

class TestGateEngine:
    """Unit tests for gate validation"""

    def test_file_exists_gate_passes(self, tmp_path):
        """File exists gate passes when file exists"""
        from src.v4.models import FileExistsGate
        from src.v4.gate_engine import GateEngine

        # Create the file
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        gate_engine = GateEngine(tmp_path)
        gate = FileExistsGate(path="test.txt")
        result = gate_engine._validate_file_exists(gate)

        assert result.passed

    def test_file_exists_gate_fails(self, tmp_path):
        """File exists gate fails when file missing"""
        from src.v4.models import FileExistsGate
        from src.v4.gate_engine import GateEngine

        gate_engine = GateEngine(tmp_path)
        gate = FileExistsGate(path="missing.txt")
        result = gate_engine._validate_file_exists(gate)

        assert not result.passed
        assert "not found" in result.reason.lower()

    def test_command_gate_passes(self, tmp_path):
        """Command gate passes with exit code 0"""
        from src.v4.models import CommandGate
        from src.v4.gate_engine import GateEngine

        gate_engine = GateEngine(tmp_path)
        gate = CommandGate(cmd="exit 0")
        result = gate_engine._validate_command(gate)

        assert result.passed

    def test_command_gate_fails_exit_code(self, tmp_path):
        """Command gate fails with non-zero exit code"""
        from src.v4.models import CommandGate
        from src.v4.gate_engine import GateEngine

        gate_engine = GateEngine(tmp_path)
        gate = CommandGate(cmd="exit 1")
        result = gate_engine._validate_command(gate)

        assert not result.passed

    def test_no_pattern_gate_passes(self, tmp_path):
        """No pattern gate passes when pattern not found"""
        from src.v4.models import NoPatternGate
        from src.v4.gate_engine import GateEngine

        # Create a file without the pattern
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        gate_engine = GateEngine(tmp_path)
        gate = NoPatternGate(pattern="TODO", paths=["*.py"])
        result = gate_engine._validate_no_pattern(gate)

        assert result.passed

    def test_no_pattern_gate_fails(self, tmp_path):
        """No pattern gate fails when pattern found"""
        from src.v4.models import NoPatternGate
        from src.v4.gate_engine import GateEngine

        # Create a file with the pattern
        test_file = tmp_path / "test.py"
        test_file.write_text("# TODO: fix this")

        gate_engine = GateEngine(tmp_path)
        gate = NoPatternGate(pattern="TODO", paths=["*.py"])
        result = gate_engine._validate_no_pattern(gate)

        assert not result.passed

    def test_json_valid_gate_passes(self, tmp_path):
        """JSON valid gate passes with valid JSON"""
        from src.v4.models import JsonValidGate
        from src.v4.gate_engine import GateEngine

        # Create valid JSON file
        test_file = tmp_path / "data.json"
        test_file.write_text('{"key": "value"}')

        gate_engine = GateEngine(tmp_path)
        gate = JsonValidGate(path="data.json")
        result = gate_engine._validate_json_valid(gate)

        assert result.passed

    def test_json_valid_gate_fails(self, tmp_path):
        """JSON valid gate fails with invalid JSON"""
        from src.v4.models import JsonValidGate
        from src.v4.gate_engine import GateEngine

        # Create invalid JSON file
        test_file = tmp_path / "data.json"
        test_file.write_text("{invalid json")

        gate_engine = GateEngine(tmp_path)
        gate = JsonValidGate(path="data.json")
        result = gate_engine._validate_json_valid(gate)

        assert not result.passed


class TestStateStore:
    """Unit tests for state management"""

    def test_state_initialize(self, tmp_path):
        """State store creates new state"""
        from src.v4.state import StateStore
        from src.v4.models import WorkflowStatus

        store = StateStore(tmp_path)
        state = store.initialize("Test Workflow", "Test task")

        assert state.workflow_name == "Test Workflow"
        assert state.task_description == "Test task"
        assert state.status == WorkflowStatus.INITIALIZED
        store.cleanup()

    def test_state_save_load(self, tmp_path):
        """State persistence works correctly"""
        from src.v4.state import StateStore
        from src.v4.models import WorkflowStatus

        store = StateStore(tmp_path)
        state = store.initialize("Test", "Task")
        workflow_id = state.workflow_id
        store.state.status = WorkflowStatus.RUNNING
        store.save()
        store.cleanup()

        # Load in new store
        store2 = StateStore(tmp_path)
        loaded = store2.load(workflow_id)
        assert loaded.status == WorkflowStatus.RUNNING
        store2.cleanup()


class TestParser:
    """Unit tests for YAML parsing"""

    def test_parse_simple_workflow(self, tmp_path):
        """Simple workflow parses correctly"""
        from src.v4.parser import parse_workflow

        yaml_file = tmp_path / "workflow.yaml"
        yaml_file.write_text("""
workflow:
  version: "4.0"
  name: "Simple"
  phases:
    - id: plan
      name: "Plan"
      next: null
""")

        spec = parse_workflow(yaml_file)
        assert spec.name == "Simple"
        assert len(spec.phases) == 1
        assert spec.phases[0].id == "plan"

    def test_parse_invalid_yaml(self, tmp_path):
        """Invalid YAML raises error"""
        from src.v4.parser import parse_workflow, WorkflowParseError

        yaml_file = tmp_path / "workflow.yaml"
        yaml_file.write_text("invalid: [yaml: content")

        with pytest.raises(WorkflowParseError):
            parse_workflow(yaml_file)

    def test_parse_missing_name(self, tmp_path):
        """Missing required field raises error"""
        from src.v4.parser import parse_workflow, WorkflowParseError

        yaml_file = tmp_path / "workflow.yaml"
        yaml_file.write_text("""
workflow:
  version: "4.0"
  phases:
    - id: plan
      name: "Plan"
""")

        with pytest.raises(WorkflowParseError):
            parse_workflow(yaml_file)
