"""Agent SDK test fixtures"""

import pytest
import yaml
import os


@pytest.fixture
def jwt_secret():
    """JWT secret for testing"""
    secret = "test_secret_key_for_agent_sdk_testing_only_do_not_use_in_production"
    os.environ["ORCHESTRATOR_JWT_SECRET"] = secret
    yield secret
    # Cleanup
    if "ORCHESTRATOR_JWT_SECRET" in os.environ:
        del os.environ["ORCHESTRATOR_JWT_SECRET"]


@pytest.fixture
def test_workflow_yaml():
    """
    Valid test workflow YAML for agent SDK testing

    Returns:
        Dict with minimal valid workflow structure including all phases
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
