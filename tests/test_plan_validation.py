"""
Tests for Issue #88 - Plan Validation Review in PLAN phase.
"""

import pytest
import yaml
from pathlib import Path


@pytest.fixture
def default_workflow():
    """Load the default workflow YAML."""
    workflow_path = Path(__file__).parent.parent / "src" / "default_workflow.yaml"
    with open(workflow_path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def plan_phase(default_workflow):
    """Get the PLAN phase from the workflow."""
    for phase in default_workflow["phases"]:
        if phase["id"] == "PLAN":
            return phase
    pytest.fail("PLAN phase not found in workflow")


@pytest.fixture
def plan_validation_item(plan_phase):
    """Get the plan_validation item from PLAN phase."""
    for item in plan_phase["items"]:
        if item["id"] == "plan_validation":
            return item
    pytest.fail("plan_validation item not found in PLAN phase")


class TestPlanValidationExists:
    """Tests that plan_validation item exists and is properly positioned."""

    def test_plan_validation_in_plan_phase(self, plan_validation_item):
        """TC1: plan_validation item exists in PLAN phase."""
        assert plan_validation_item["id"] == "plan_validation"
        assert plan_validation_item["name"] == "Plan Validation Review"

    def test_plan_validation_position(self, plan_phase):
        """TC2: plan_validation is after risk_analysis and before user_approval."""
        item_ids = [item["id"] for item in plan_phase["items"]]

        # Find positions
        risk_idx = item_ids.index("risk_analysis")
        pv_idx = item_ids.index("plan_validation")
        ua_idx = item_ids.index("user_approval")

        assert risk_idx < pv_idx < ua_idx, (
            f"Position error: risk_analysis({risk_idx}) < "
            f"plan_validation({pv_idx}) < user_approval({ua_idx})"
        )


class TestPlanValidationFields:
    """Tests that plan_validation has all required fields."""

    def test_required_fields_present(self, plan_validation_item):
        """TC3: Required fields are present."""
        required_fields = ["id", "name", "description", "required", "skippable", "skip_conditions", "notes"]
        for field in required_fields:
            assert field in plan_validation_item, f"Missing required field: {field}"

    def test_skip_conditions_defined(self, plan_validation_item):
        """TC4: Skip conditions are properly defined."""
        skip_conditions = plan_validation_item["skip_conditions"]
        expected_conditions = ["trivial_change", "simple_bug_fix", "well_understood_pattern"]

        for condition in expected_conditions:
            assert condition in skip_conditions, f"Missing skip condition: {condition}"

    def test_required_and_skippable_flags(self, plan_validation_item):
        """plan_validation is required but skippable."""
        assert plan_validation_item["required"] is True
        assert plan_validation_item["skippable"] is True


class TestPlanValidationCheckpoints:
    """Tests that all checkpoints are present in the description."""

    @pytest.mark.parametrize("checkpoint", [
        "Request Completeness",
        "Requirements Alignment",
        "Security",
        "Risk Mitigation",
        "Objective-Driven Optimality",
        "Dependencies",
        "Edge Cases",
        "Testing",
        "Implementability",
        "Operational Readiness",
    ])
    def test_checkpoint_in_description(self, plan_validation_item, checkpoint):
        """TC6: All 10 checkpoints are in the description."""
        description = plan_validation_item["description"]
        assert checkpoint in description, f"Checkpoint '{checkpoint}' not found in description"


class TestPlanValidationVerdicts:
    """Tests that all verdicts are defined."""

    @pytest.mark.parametrize("verdict", [
        "APPROVED",
        "APPROVED_WITH_NOTES",
        "NEEDS_REVISION",
        "BLOCKED",
        "ESCALATE",
    ])
    def test_verdict_in_description(self, plan_validation_item, verdict):
        """TC7: All 5 verdicts are defined in description."""
        description = plan_validation_item["description"]
        assert verdict in description, f"Verdict '{verdict}' not found in description"
