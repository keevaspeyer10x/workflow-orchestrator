"""
Day 4: Artifact Validation Tests

Tests for JSON schema-based artifact validation.
"""

import pytest
from pathlib import Path
from src.orchestrator.enforcement import WorkflowEnforcement


class TestValidArtifacts:
    """Tests for valid artifact validation"""

    def test_validate_plan_artifact(self, enforcement_engine):
        """Should validate valid plan artifact"""
        plan_artifact = {
            "title": "Add user authentication feature",
            "acceptance_criteria": [
                {
                    "criterion": "Users can log in with email/password",
                    "how_to_verify": "Manual test with test user account"
                }
            ],
            "implementation_steps": [
                "Create login endpoint",
                "Add authentication middleware",
                "Create login UI"
            ],
            "scope": {
                "in_scope": ["Login", "Logout"],
                "out_of_scope": ["Password reset", "OAuth"]
            }
        }

        required = [{"type": "plan_document", "schema": "schemas/plan.json"}]
        artifacts = {"plan_document": plan_artifact}

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        assert valid is True
        assert len(errors) == 0

    def test_validate_scope_artifact(self, enforcement_engine):
        """Should validate valid scope artifact"""
        scope_artifact = {
            "in_scope": ["Feature A", "Feature B"],
            "out_of_scope": ["Feature C"],
            "constraints": ["No database changes", "Must be backwards compatible"]
        }

        required = [{"type": "scope_definition", "schema": "schemas/scope.json"}]
        artifacts = {"scope_definition": scope_artifact}

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        assert valid is True
        assert len(errors) == 0

    def test_validate_test_result_artifact(self, enforcement_engine):
        """Should validate valid test result artifact"""
        test_result = {
            "command": "pytest tests/",
            "exit_code": 0,
            "passed": 10,
            "failed": 0,
            "skipped": 2,
            "timestamp": "2026-01-10T10:00:00Z",
            "output": "10 passed, 2 skipped"
        }

        required = [{"type": "test_run_result", "schema": "schemas/test_result.json"}]
        artifacts = {"test_run_result": test_result}

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        assert valid is True
        assert len(errors) == 0


class TestMissingArtifacts:
    """Tests for missing artifact detection"""

    def test_missing_required_artifact(self, enforcement_engine):
        """Should detect missing required artifact"""
        required = [
            {"type": "plan_document", "schema": "schemas/plan.json"},
            {"type": "scope_definition", "schema": "schemas/scope.json"}
        ]
        artifacts = {
            "plan_document": {
                "title": "Test plan with 10+ chars",
                "acceptance_criteria": [{"criterion": "Test", "how_to_verify": "Manual"}],
                "implementation_steps": ["Step 1"],
                "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
            }
            # Missing scope_definition
        }

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        assert valid is False
        assert len(errors) > 0
        assert any("Missing required artifacts" in err for err in errors)
        assert any("scope_definition" in err for err in errors)

    def test_multiple_missing_artifacts(self, enforcement_engine):
        """Should detect multiple missing artifacts"""
        required = [
            {"type": "plan_document", "schema": "schemas/plan.json"},
            {"type": "scope_definition", "schema": "schemas/scope.json"},
            {"type": "test_run_result", "schema": "schemas/test_result.json"}
        ]
        artifacts = {}  # All missing

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        assert valid is False
        assert "plan_document" in str(errors)
        assert "scope_definition" in str(errors)
        assert "test_run_result" in str(errors)


class TestInvalidArtifacts:
    """Tests for invalid artifact structures"""

    def test_plan_missing_title(self, enforcement_engine):
        """Should reject plan without title"""
        plan_artifact = {
            # Missing title
            "acceptance_criteria": [
                {"criterion": "Test", "how_to_verify": "Manual"}
            ],
            "implementation_steps": ["Step 1"],
            "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
        }

        required = [{"type": "plan_document", "schema": "schemas/plan.json"}]
        artifacts = {"plan_document": plan_artifact}

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        assert valid is False
        assert any("title" in err.lower() for err in errors)

    def test_plan_title_too_short(self, enforcement_engine):
        """Should reject plan with title shorter than 10 chars"""
        plan_artifact = {
            "title": "Short",  # Only 5 characters
            "acceptance_criteria": [
                {"criterion": "Test", "how_to_verify": "Manual"}
            ],
            "implementation_steps": ["Step 1"],
            "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
        }

        required = [{"type": "plan_document", "schema": "schemas/plan.json"}]
        artifacts = {"plan_document": plan_artifact}

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        assert valid is False
        assert any("title" in err.lower() for err in errors)

    def test_plan_empty_acceptance_criteria(self, enforcement_engine):
        """Should reject plan with empty acceptance criteria"""
        plan_artifact = {
            "title": "Valid title with 10+ chars",
            "acceptance_criteria": [],  # Empty array
            "implementation_steps": ["Step 1"],
            "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
        }

        required = [{"type": "plan_document", "schema": "schemas/plan.json"}]
        artifacts = {"plan_document": plan_artifact}

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        assert valid is False
        assert any("acceptance_criteria" in err.lower() for err in errors)

    def test_plan_acceptance_criteria_missing_fields(self, enforcement_engine):
        """Should reject acceptance criteria without required fields"""
        plan_artifact = {
            "title": "Valid title with 10+ chars",
            "acceptance_criteria": [
                {"criterion": "Test"}  # Missing how_to_verify
            ],
            "implementation_steps": ["Step 1"],
            "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
        }

        required = [{"type": "plan_document", "schema": "schemas/plan.json"}]
        artifacts = {"plan_document": plan_artifact}

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        assert valid is False
        assert any("how_to_verify" in err.lower() for err in errors)

    def test_test_result_negative_counts(self, enforcement_engine):
        """Should reject test result with negative counts"""
        test_result = {
            "command": "pytest tests/",
            "exit_code": 0,
            "passed": -5,  # Negative!
            "failed": 0,
            "skipped": 2,
            "timestamp": "2026-01-10T10:00:00Z"
        }

        required = [{"type": "test_run_result", "schema": "schemas/test_result.json"}]
        artifacts = {"test_run_result": test_result}

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        assert valid is False

    def test_test_result_wrong_type(self, enforcement_engine):
        """Should reject test result with wrong field types"""
        test_result = {
            "command": "pytest tests/",
            "exit_code": "zero",  # Should be integer
            "passed": 10,
            "failed": 0,
            "skipped": 2,
            "timestamp": "2026-01-10T10:00:00Z"
        }

        required = [{"type": "test_run_result", "schema": "schemas/test_result.json"}]
        artifacts = {"test_run_result": test_result}

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        assert valid is False
        assert any("exit_code" in err.lower() for err in errors)


class TestMultipleArtifacts:
    """Tests for validating multiple artifacts at once"""

    def test_validate_multiple_valid_artifacts(self, enforcement_engine):
        """Should validate multiple valid artifacts"""
        artifacts = {
            "plan_document": {
                "title": "Valid plan with 10+ characters",
                "acceptance_criteria": [
                    {"criterion": "Feature works", "how_to_verify": "Test it"}
                ],
                "implementation_steps": ["Step 1", "Step 2"],
                "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
            },
            "scope_definition": {
                "in_scope": ["Feature A"],
                "out_of_scope": ["Feature B"],
                "constraints": ["No breaking changes"]
            }
        }

        required = [
            {"type": "plan_document", "schema": "schemas/plan.json"},
            {"type": "scope_definition", "schema": "schemas/scope.json"}
        ]

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        assert valid is True
        assert len(errors) == 0

    def test_multiple_artifacts_one_invalid(self, enforcement_engine):
        """Should detect invalid artifact when validating multiple"""
        artifacts = {
            "plan_document": {
                "title": "Valid plan with 10+ characters",
                "acceptance_criteria": [
                    {"criterion": "Feature works", "how_to_verify": "Test it"}
                ],
                "implementation_steps": ["Step 1", "Step 2"],
                "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
            },
            "scope_definition": {
                "in_scope": ["Feature A"],
                # Missing out_of_scope (required)
                "constraints": []
            }
        }

        required = [
            {"type": "plan_document", "schema": "schemas/plan.json"},
            {"type": "scope_definition", "schema": "schemas/scope.json"}
        ]

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        assert valid is False
        assert len(errors) > 0


class TestSchemaLoading:
    """Tests for schema loading edge cases"""

    def test_artifact_without_schema(self, enforcement_engine):
        """Should skip validation for artifact without schema"""
        artifacts = {"custom_artifact": {"data": "anything"}}
        required = [{"type": "custom_artifact"}]  # No schema specified

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        # Should pass since no schema to validate against
        assert valid is True

    def test_nonexistent_schema_file(self, enforcement_engine):
        """Should error when schema file doesn't exist"""
        artifacts = {"test_artifact": {"data": "test"}}
        required = [{"type": "test_artifact", "schema": "schemas/nonexistent.json"}]

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        assert valid is False
        assert any("Schema file not found" in err for err in errors)


class TestErrorMessages:
    """Tests for error message quality"""

    def test_error_message_includes_artifact_type(self, enforcement_engine):
        """Error should mention which artifact failed"""
        plan_artifact = {
            "title": "Valid title with 10+ chars",
            "acceptance_criteria": [],  # Invalid: empty
            "implementation_steps": ["Step 1"],
            "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
        }

        required = [{"type": "plan_document", "schema": "schemas/plan.json"}]
        artifacts = {"plan_document": plan_artifact}

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        assert valid is False
        # Error should mention plan_document
        assert any("plan_document" in err or "acceptance_criteria" in err for err in errors)

    def test_error_message_includes_field_path(self, enforcement_engine):
        """Error should include path to invalid field"""
        plan_artifact = {
            "title": "Valid title with 10+ chars",
            "acceptance_criteria": [
                {"criterion": "Test"}  # Missing how_to_verify
            ],
            "implementation_steps": ["Step 1"],
            "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
        }

        required = [{"type": "plan_document", "schema": "schemas/plan.json"}]
        artifacts = {"plan_document": plan_artifact}

        valid, errors = enforcement_engine._validate_artifacts(artifacts, required)

        assert valid is False
        # Should have helpful error pointing to the field
        error_str = " ".join(errors)
        assert "how_to_verify" in error_str.lower() or "required" in error_str.lower()
