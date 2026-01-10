"""
Day 2: YAML Loading & Validation Tests

Tests for comprehensive workflow YAML validation.
"""

import pytest
import yaml
from pathlib import Path
from src.orchestrator.enforcement import WorkflowEnforcement


class TestValidWorkflowLoading:
    """Tests for loading valid workflow YAML"""

    def test_load_valid_workflow(self, test_workflow_file, jwt_secret):
        """Should load valid workflow without errors"""
        enforcement = WorkflowEnforcement(test_workflow_file)
        assert enforcement.workflow is not None
        assert "phases" in enforcement.workflow
        assert "transitions" in enforcement.workflow

    def test_load_real_agent_workflow(self, jwt_secret):
        """Should load real agent_workflow.yaml"""
        workflow_path = Path("agent_workflow.yaml")
        if not workflow_path.exists():
            pytest.skip("agent_workflow.yaml not found")

        enforcement = WorkflowEnforcement(workflow_path)
        assert enforcement.workflow["name"] == "Parallel Agent Workflow"
        assert len(enforcement.workflow["phases"]) == 5


class TestMissingRequiredKeys:
    """Tests for workflows missing required top-level keys"""

    def test_missing_phases_key(self, tmp_path, jwt_secret):
        """Should raise ValueError when phases key missing"""
        workflow_path = tmp_path / "bad_workflow.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        with pytest.raises(ValueError, match="missing required keys.*phases"):
            WorkflowEnforcement(workflow_path)

    def test_missing_transitions_key(self, tmp_path, jwt_secret):
        """Should raise ValueError when transitions key missing"""
        workflow_path = tmp_path / "bad_workflow.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [{"id": "PLAN", "name": "Planning", "allowed_tools": []}],
                "enforcement": {"mode": "strict"}
            }, f)

        with pytest.raises(ValueError, match="missing required keys.*transitions"):
            WorkflowEnforcement(workflow_path)

    def test_missing_enforcement_key(self, tmp_path, jwt_secret):
        """Should raise ValueError when enforcement key missing"""
        workflow_path = tmp_path / "bad_workflow.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [{"id": "PLAN", "name": "Planning", "allowed_tools": []}],
                "transitions": []
            }, f)

        with pytest.raises(ValueError, match="missing required keys.*enforcement"):
            WorkflowEnforcement(workflow_path)

    def test_empty_workflow_file(self, tmp_path, jwt_secret):
        """Should raise ValueError for empty file"""
        workflow_path = tmp_path / "empty.yaml"
        workflow_path.touch()

        with pytest.raises(ValueError, match="empty"):
            WorkflowEnforcement(workflow_path)


class TestInvalidPhases:
    """Tests for invalid phase structures"""

    def test_phases_not_list(self, tmp_path, jwt_secret):
        """Should raise ValueError when phases is not a list"""
        workflow_path = tmp_path / "bad_phases.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": "not a list",
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        with pytest.raises(ValueError, match="Phases must be a list"):
            WorkflowEnforcement(workflow_path)

    def test_empty_phases_list(self, tmp_path, jwt_secret):
        """Should raise ValueError when phases list is empty"""
        workflow_path = tmp_path / "empty_phases.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [],
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        with pytest.raises(ValueError, match="at least one phase"):
            WorkflowEnforcement(workflow_path)

    def test_phase_missing_id(self, tmp_path, jwt_secret):
        """Should raise ValueError when phase missing 'id' field"""
        workflow_path = tmp_path / "no_id.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"name": "Planning", "allowed_tools": []}
                ],
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        with pytest.raises(ValueError, match="missing required fields.*id"):
            WorkflowEnforcement(workflow_path)

    def test_phase_missing_name(self, tmp_path, jwt_secret):
        """Should raise ValueError when phase missing 'name' field"""
        workflow_path = tmp_path / "no_name.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "allowed_tools": []}
                ],
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        with pytest.raises(ValueError, match="missing required fields.*name"):
            WorkflowEnforcement(workflow_path)

    def test_phase_missing_allowed_tools(self, tmp_path, jwt_secret):
        """Should raise ValueError when phase missing 'allowed_tools'"""
        workflow_path = tmp_path / "no_tools.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning"}
                ],
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        with pytest.raises(ValueError, match="missing required fields.*allowed_tools"):
            WorkflowEnforcement(workflow_path)

    def test_duplicate_phase_ids(self, tmp_path, jwt_secret):
        """Should raise ValueError for duplicate phase IDs"""
        workflow_path = tmp_path / "dup_phases.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning 1", "allowed_tools": []},
                    {"id": "PLAN", "name": "Planning 2", "allowed_tools": []}
                ],
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        with pytest.raises(ValueError, match="Duplicate phase ID: PLAN"):
            WorkflowEnforcement(workflow_path)

    def test_allowed_tools_not_list(self, tmp_path, jwt_secret):
        """Should raise ValueError when allowed_tools is not a list"""
        workflow_path = tmp_path / "bad_tools.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": "not a list"}
                ],
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        with pytest.raises(ValueError, match="allowed_tools must be a list"):
            WorkflowEnforcement(workflow_path)

    def test_forbidden_tools_not_list(self, tmp_path, jwt_secret):
        """Should raise ValueError when forbidden_tools is not a list"""
        workflow_path = tmp_path / "bad_forbidden.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {
                        "id": "PLAN",
                        "name": "Planning",
                        "allowed_tools": [],
                        "forbidden_tools": "not a list"
                    }
                ],
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        with pytest.raises(ValueError, match="forbidden_tools must be a list"):
            WorkflowEnforcement(workflow_path)


class TestInvalidTransitions:
    """Tests for invalid transition structures"""

    def test_transitions_not_list(self, tmp_path, jwt_secret):
        """Should raise ValueError when transitions is not a list"""
        workflow_path = tmp_path / "bad_trans.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []}
                ],
                "transitions": "not a list",
                "enforcement": {"mode": "strict"}
            }, f)

        with pytest.raises(ValueError, match="Transitions must be a list"):
            WorkflowEnforcement(workflow_path)

    def test_transition_missing_from(self, tmp_path, jwt_secret):
        """Should raise ValueError when transition missing 'from' field"""
        workflow_path = tmp_path / "no_from.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []},
                    {"id": "TDD", "name": "Testing", "allowed_tools": []}
                ],
                "transitions": [
                    {"to": "TDD"}
                ],
                "enforcement": {"mode": "strict"}
            }, f)

        with pytest.raises(ValueError, match="missing required fields.*from"):
            WorkflowEnforcement(workflow_path)

    def test_transition_missing_to(self, tmp_path, jwt_secret):
        """Should raise ValueError when transition missing 'to' field"""
        workflow_path = tmp_path / "no_to.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []},
                    {"id": "TDD", "name": "Testing", "allowed_tools": []}
                ],
                "transitions": [
                    {"from": "PLAN"}
                ],
                "enforcement": {"mode": "strict"}
            }, f)

        with pytest.raises(ValueError, match="missing required fields.*to"):
            WorkflowEnforcement(workflow_path)

    def test_transition_references_nonexistent_from_phase(self, tmp_path, jwt_secret):
        """Should raise ValueError when 'from' phase doesn't exist"""
        workflow_path = tmp_path / "bad_from.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []}
                ],
                "transitions": [
                    {"from": "NONEXISTENT", "to": "PLAN"}
                ],
                "enforcement": {"mode": "strict"}
            }, f)

        with pytest.raises(ValueError, match="'from' phase 'NONEXISTENT' not defined"):
            WorkflowEnforcement(workflow_path)

    def test_transition_references_nonexistent_to_phase(self, tmp_path, jwt_secret):
        """Should raise ValueError when 'to' phase doesn't exist"""
        workflow_path = tmp_path / "bad_to.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []}
                ],
                "transitions": [
                    {"from": "PLAN", "to": "NONEXISTENT"}
                ],
                "enforcement": {"mode": "strict"}
            }, f)

        with pytest.raises(ValueError, match="'to' phase 'NONEXISTENT' not defined"):
            WorkflowEnforcement(workflow_path)


class TestInvalidEnforcement:
    """Tests for invalid enforcement configuration"""

    def test_enforcement_not_dict(self, tmp_path, jwt_secret):
        """Should raise ValueError when enforcement is not a dict"""
        workflow_path = tmp_path / "bad_enforcement.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []}
                ],
                "transitions": [],
                "enforcement": "not a dict"
            }, f)

        with pytest.raises(ValueError, match="Enforcement must be a dict"):
            WorkflowEnforcement(workflow_path)

    def test_invalid_enforcement_mode(self, tmp_path, jwt_secret):
        """Should raise ValueError for invalid enforcement mode"""
        workflow_path = tmp_path / "bad_mode.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []}
                ],
                "transitions": [],
                "enforcement": {"mode": "invalid_mode"}
            }, f)

        with pytest.raises(ValueError, match="Enforcement mode must be one of"):
            WorkflowEnforcement(workflow_path)

    def test_phase_tokens_not_dict(self, tmp_path, jwt_secret):
        """Should raise ValueError when phase_tokens is not a dict"""
        workflow_path = tmp_path / "bad_tokens.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []}
                ],
                "transitions": [],
                "enforcement": {
                    "mode": "strict",
                    "phase_tokens": "not a dict"
                }
            }, f)

        with pytest.raises(ValueError, match="phase_tokens must be a dict"):
            WorkflowEnforcement(workflow_path)

    def test_phase_tokens_enabled_not_bool(self, tmp_path, jwt_secret):
        """Should raise ValueError when enabled is not boolean"""
        workflow_path = tmp_path / "bad_enabled.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []}
                ],
                "transitions": [],
                "enforcement": {
                    "mode": "strict",
                    "phase_tokens": {"enabled": "yes"}
                }
            }, f)

        with pytest.raises(ValueError, match="enabled must be a boolean"):
            WorkflowEnforcement(workflow_path)

    def test_expiry_seconds_not_int(self, tmp_path, jwt_secret):
        """Should raise ValueError when expiry_seconds is not integer"""
        workflow_path = tmp_path / "bad_expiry.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []}
                ],
                "transitions": [],
                "enforcement": {
                    "mode": "strict",
                    "phase_tokens": {"expiry_seconds": "3600"}
                }
            }, f)

        with pytest.raises(ValueError, match="expiry_seconds must be an integer"):
            WorkflowEnforcement(workflow_path)

    def test_expiry_seconds_negative(self, tmp_path, jwt_secret):
        """Should raise ValueError when expiry_seconds is negative"""
        workflow_path = tmp_path / "neg_expiry.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []}
                ],
                "transitions": [],
                "enforcement": {
                    "mode": "strict",
                    "phase_tokens": {"expiry_seconds": -100}
                }
            }, f)

        with pytest.raises(ValueError, match="expiry_seconds must be positive"):
            WorkflowEnforcement(workflow_path)


class TestHelperMethods:
    """Tests for helper methods (_get_phase, _get_gate, _find_transition)"""

    def test_get_phase_exists(self, enforcement_engine):
        """Should return phase when it exists"""
        phase = enforcement_engine._get_phase("PLAN")
        assert phase is not None
        assert phase["id"] == "PLAN"

    def test_get_phase_not_found(self, enforcement_engine):
        """Should return None when phase doesn't exist"""
        phase = enforcement_engine._get_phase("NONEXISTENT")
        assert phase is None

    def test_find_transition_exists(self, enforcement_engine):
        """Should return transition when it exists"""
        transition = enforcement_engine._find_transition("PLAN", "TDD")
        assert transition is not None
        assert transition["from"] == "PLAN"
        assert transition["to"] == "TDD"

    def test_find_transition_not_found(self, enforcement_engine):
        """Should return None when transition doesn't exist"""
        transition = enforcement_engine._find_transition("PLAN", "NONEXISTENT")
        assert transition is None
