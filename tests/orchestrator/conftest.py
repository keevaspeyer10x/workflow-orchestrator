"""
Pytest fixtures for orchestrator tests
"""

import pytest
import os
from pathlib import Path
import tempfile
import yaml


@pytest.fixture
def test_workflow_yaml():
    """
    Valid test workflow YAML for testing

    Returns:
        Dict with minimal valid workflow structure
    """
    return {
        "name": "Test Workflow",
        "version": "1.0",
        "phases": [
            {
                "id": "PLAN",
                "name": "Planning",
                "allowed_tools": ["read_files", "grep"],
                "forbidden_tools": ["write_files"],
                "required_artifacts": [
                    {
                        "type": "plan_document",
                        "schema": "schemas/plan.json"
                    }
                ],
                "gates": [
                    {
                        "id": "plan_approval",
                        "type": "approval",
                        "blockers": [
                            {
                                "check": "plan_has_acceptance_criteria",
                                "severity": "blocking",
                                "message": "Plan must have acceptance criteria"
                            }
                        ]
                    }
                ]
            },
            {
                "id": "TDD",
                "name": "Write Tests",
                "allowed_tools": ["read_files", "write_files", "bash"],
                "forbidden_tools": ["git_commit"],
                "required_artifacts": [
                    {
                        "type": "test_files",
                        "schema": "schemas/tests.json"
                    }
                ],
                "gates": [
                    {
                        "id": "tests_written",
                        "type": "validation",
                        "blockers": [
                            {
                                "check": "tests_are_failing",
                                "severity": "blocking",
                                "message": "Tests must be failing (TDD RED phase)"
                            }
                        ]
                    }
                ]
            },
            {
                "id": "IMPL",
                "name": "Implementation",
                "allowed_tools": ["read_files", "write_files", "bash"],
                "forbidden_tools": [],
                "required_artifacts": [
                    {
                        "type": "implementation",
                        "schema": "schemas/implementation.json"
                    }
                ],
                "gates": [
                    {
                        "id": "tests_passing",
                        "type": "validation",
                        "blockers": [
                            {
                                "check": "all_tests_pass",
                                "severity": "blocking",
                                "message": "All tests must pass"
                            }
                        ]
                    }
                ]
            },
            {
                "id": "REVIEW",
                "name": "Review",
                "allowed_tools": ["read_files"],
                "forbidden_tools": ["write_files"],
                "required_artifacts": [
                    {
                        "type": "review_results",
                        "schema": "schemas/review.json"
                    }
                ],
                "gates": [
                    {
                        "id": "review_approved",
                        "type": "approval",
                        "blockers": [
                            {
                                "check": "no_blocking_issues",
                                "severity": "blocking",
                                "message": "Review found blocking issues"
                            }
                        ]
                    }
                ]
            }
        ],
        "transitions": [
            {
                "from": "PLAN",
                "to": "TDD",
                "gate": "plan_approval",
                "requires_token": True
            },
            {
                "from": "TDD",
                "to": "IMPL",
                "gate": "tests_written",
                "requires_token": True
            },
            {
                "from": "IMPL",
                "to": "REVIEW",
                "gate": "tests_passing",
                "requires_token": True
            }
        ],
        "enforcement": {
            "mode": "strict",
            "phase_tokens": {
                "enabled": True,
                "algorithm": "HS256",
                "secret_env_var": "ORCHESTRATOR_JWT_SECRET",
                "expiry_seconds": 7200
            }
        }
    }


@pytest.fixture
def test_workflow_file(test_workflow_yaml, tmp_path):
    """
    Create temporary workflow file for testing

    Args:
        test_workflow_yaml: Workflow YAML dict
        tmp_path: Pytest tmp_path fixture

    Returns:
        Path to temporary workflow file
    """
    workflow_path = tmp_path / "test_workflow.yaml"
    with open(workflow_path, 'w') as f:
        yaml.dump(test_workflow_yaml, f)
    return workflow_path


@pytest.fixture
def jwt_secret(monkeypatch):
    """
    Set JWT secret for testing

    Returns:
        Test JWT secret
    """
    secret = "test_secret_do_not_use_in_production_0123456789abcdef"
    monkeypatch.setenv("ORCHESTRATOR_JWT_SECRET", secret)
    return secret


@pytest.fixture
def enforcement_engine(test_workflow_file, jwt_secret):
    """
    Create WorkflowEnforcement instance for testing

    Args:
        test_workflow_file: Path to test workflow
        jwt_secret: JWT secret

    Returns:
        WorkflowEnforcement instance
    """
    from src.orchestrator.enforcement import WorkflowEnforcement
    return WorkflowEnforcement(test_workflow_file)


@pytest.fixture
def valid_phase_token(enforcement_engine):
    """
    Generate valid phase token for testing

    Args:
        enforcement_engine: WorkflowEnforcement fixture

    Returns:
        Valid JWT token for PLAN phase
    """
    return enforcement_engine.generate_phase_token("test-task-123", "PLAN")


@pytest.fixture
def expired_phase_token(enforcement_engine, monkeypatch):
    """
    Generate expired phase token for testing

    Returns:
        Expired JWT token
    """
    # Temporarily set expiry to -1 seconds (already expired)
    original_expiry = enforcement_engine.workflow["enforcement"]["phase_tokens"]["expiry_seconds"]
    enforcement_engine.workflow["enforcement"]["phase_tokens"]["expiry_seconds"] = -1

    token = enforcement_engine.generate_phase_token("test-task-123", "PLAN")

    # Restore original expiry
    enforcement_engine.workflow["enforcement"]["phase_tokens"]["expiry_seconds"] = original_expiry

    return token


@pytest.fixture
def mock_orchestrator_server(tmp_path, test_workflow_yaml, jwt_secret):
    """
    Start mock orchestrator server for testing

    Uses the actual FastAPI app with test workflow

    Args:
        tmp_path: Pytest tmp_path fixture
        test_workflow_yaml: Test workflow dict
        jwt_secret: JWT secret

    Returns:
        FastAPI app instance
    """
    from src.orchestrator.api import app
    from src.orchestrator.enforcement import WorkflowEnforcement
    from src.orchestrator import api

    # Create test workflow file
    test_workflow_file = tmp_path / "test_workflow.yaml"
    with open(test_workflow_file, 'w') as f:
        yaml.dump(test_workflow_yaml, f)

    # Initialize enforcement with test workflow
    api.enforcement = WorkflowEnforcement(test_workflow_file)

    # Return app for test client
    return app
