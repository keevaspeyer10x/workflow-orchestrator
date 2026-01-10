"""
Day 2 Review: Edge case tests for YAML validation

Testing corner cases and boundary conditions.
"""

import pytest
import yaml
from pathlib import Path
from src.orchestrator.enforcement import WorkflowEnforcement


class TestEdgeCases:
    """Edge case tests for workflow validation"""

    def test_single_phase_workflow(self, tmp_path, jwt_secret):
        """Should allow workflow with single phase"""
        workflow_path = tmp_path / "single_phase.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "ONLY", "name": "Only Phase", "allowed_tools": ["read_files"]}
                ],
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        enforcement = WorkflowEnforcement(workflow_path)
        assert len(enforcement.workflow["phases"]) == 1

    def test_empty_allowed_tools(self, tmp_path, jwt_secret):
        """Should allow empty allowed_tools list"""
        workflow_path = tmp_path / "empty_tools.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []}
                ],
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        enforcement = WorkflowEnforcement(workflow_path)
        assert enforcement.get_allowed_tools("PLAN") == []

    def test_no_forbidden_tools_is_ok(self, tmp_path, jwt_secret):
        """Should allow phase without forbidden_tools (it's optional)"""
        workflow_path = tmp_path / "no_forbidden.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": ["read_files"]}
                ],
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        enforcement = WorkflowEnforcement(workflow_path)
        phase = enforcement._get_phase("PLAN")
        assert "forbidden_tools" not in phase or phase.get("forbidden_tools") is None

    def test_empty_transitions_list(self, tmp_path, jwt_secret):
        """Should allow workflow with no transitions"""
        workflow_path = tmp_path / "no_trans.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []}
                ],
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        enforcement = WorkflowEnforcement(workflow_path)
        assert enforcement.workflow["transitions"] == []

    def test_enforcement_minimal_config(self, tmp_path, jwt_secret):
        """Should allow enforcement with just mode"""
        workflow_path = tmp_path / "minimal_enforcement.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []}
                ],
                "transitions": [],
                "enforcement": {"mode": "permissive"}
            }, f)

        enforcement = WorkflowEnforcement(workflow_path)
        assert enforcement.workflow["enforcement"]["mode"] == "permissive"

    def test_enforcement_no_mode_is_ok(self, tmp_path, jwt_secret):
        """Should allow enforcement section without mode (mode is optional)"""
        workflow_path = tmp_path / "no_mode.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []}
                ],
                "transitions": [],
                "enforcement": {}
            }, f)

        enforcement = WorkflowEnforcement(workflow_path)
        assert "mode" not in enforcement.workflow["enforcement"]

    def test_phase_with_extra_fields(self, tmp_path, jwt_secret):
        """Should allow phases with extra fields beyond required ones"""
        workflow_path = tmp_path / "extra_fields.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {
                        "id": "PLAN",
                        "name": "Planning",
                        "allowed_tools": [],
                        "description": "Extra description field",
                        "custom_field": "custom value",
                        "gates": []
                    }
                ],
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        enforcement = WorkflowEnforcement(workflow_path)
        phase = enforcement._get_phase("PLAN")
        assert phase["description"] == "Extra description field"
        assert phase["custom_field"] == "custom value"

    def test_circular_transition(self, tmp_path, jwt_secret):
        """Should allow circular transition (phase back to itself)"""
        workflow_path = tmp_path / "circular.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []}
                ],
                "transitions": [
                    {"from": "PLAN", "to": "PLAN"}
                ],
                "enforcement": {"mode": "strict"}
            }, f)

        enforcement = WorkflowEnforcement(workflow_path)
        transition = enforcement._find_transition("PLAN", "PLAN")
        assert transition is not None

    def test_long_phase_id(self, tmp_path, jwt_secret):
        """Should allow long phase IDs"""
        long_id = "VERY_LONG_PHASE_ID_WITH_MANY_UNDERSCORES_AND_WORDS"
        workflow_path = tmp_path / "long_id.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": long_id, "name": "Planning", "allowed_tools": []}
                ],
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        enforcement = WorkflowEnforcement(workflow_path)
        phase = enforcement._get_phase(long_id)
        assert phase is not None

    def test_special_characters_in_phase_name(self, tmp_path, jwt_secret):
        """Should allow special characters in phase names"""
        workflow_path = tmp_path / "special_chars.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning & Approval (Phase 1)", "allowed_tools": []}
                ],
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        enforcement = WorkflowEnforcement(workflow_path)
        phase = enforcement._get_phase("PLAN")
        assert "Planning & Approval (Phase 1)" in phase["name"]

    def test_zero_expiry_seconds(self, tmp_path, jwt_secret):
        """Should reject zero expiry_seconds"""
        workflow_path = tmp_path / "zero_expiry.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []}
                ],
                "transitions": [],
                "enforcement": {
                    "mode": "strict",
                    "phase_tokens": {"expiry_seconds": 0}
                }
            }, f)

        with pytest.raises(ValueError, match="expiry_seconds must be positive"):
            WorkflowEnforcement(workflow_path)

    def test_multiple_transitions_same_from_phase(self, tmp_path, jwt_secret):
        """Should allow multiple transitions from same phase"""
        workflow_path = tmp_path / "multi_trans.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": []},
                    {"id": "TDD", "name": "Testing", "allowed_tools": []},
                    {"id": "IMPL", "name": "Implementation", "allowed_tools": []}
                ],
                "transitions": [
                    {"from": "PLAN", "to": "TDD"},
                    {"from": "PLAN", "to": "IMPL"}  # Fork
                ],
                "enforcement": {"mode": "strict"}
            }, f)

        enforcement = WorkflowEnforcement(workflow_path)
        assert len(enforcement.workflow["transitions"]) == 2


class TestErrorMessageQuality:
    """Tests to verify error messages are helpful"""

    def test_missing_multiple_keys_error_message(self, tmp_path, jwt_secret):
        """Error should list all missing keys"""
        workflow_path = tmp_path / "missing_all.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({"name": "Test"}, f)

        try:
            WorkflowEnforcement(workflow_path)
            pytest.fail("Should have raised ValueError")
        except ValueError as e:
            error_msg = str(e)
            assert "phases" in error_msg
            assert "transitions" in error_msg
            assert "enforcement" in error_msg

    def test_phase_missing_multiple_fields_error_message(self, tmp_path, jwt_secret):
        """Error should list all missing phase fields"""
        workflow_path = tmp_path / "bad_phase.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [{}],
                "transitions": [],
                "enforcement": {"mode": "strict"}
            }, f)

        try:
            WorkflowEnforcement(workflow_path)
            pytest.fail("Should have raised ValueError")
        except ValueError as e:
            error_msg = str(e)
            assert "id" in error_msg
            assert "name" in error_msg
            assert "allowed_tools" in error_msg


class TestRealWorldScenarios:
    """Tests based on real-world usage patterns"""

    def test_advisor_mode_workflow(self, tmp_path, jwt_secret):
        """Should work with advisory mode"""
        workflow_path = tmp_path / "advisory.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": ["read_files"]}
                ],
                "transitions": [],
                "enforcement": {"mode": "advisory"}
            }, f)

        enforcement = WorkflowEnforcement(workflow_path)
        assert enforcement.workflow["enforcement"]["mode"] == "advisory"

    def test_permissive_mode_workflow(self, tmp_path, jwt_secret):
        """Should work with permissive mode"""
        workflow_path = tmp_path / "permissive.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump({
                "phases": [
                    {"id": "PLAN", "name": "Planning", "allowed_tools": ["read_files"]}
                ],
                "transitions": [],
                "enforcement": {"mode": "permissive"}
            }, f)

        enforcement = WorkflowEnforcement(workflow_path)
        assert enforcement.workflow["enforcement"]["mode"] == "permissive"
