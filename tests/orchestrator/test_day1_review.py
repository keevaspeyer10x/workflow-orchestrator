"""
Day 1 Review: Quick tests to verify Day 1 implementation works
"""

import pytest


def test_workflow_yaml_fixture(test_workflow_yaml):
    """Verify test_workflow_yaml fixture provides valid structure"""
    assert "phases" in test_workflow_yaml
    assert "transitions" in test_workflow_yaml
    assert "enforcement" in test_workflow_yaml
    assert len(test_workflow_yaml["phases"]) == 4  # PLAN, TDD, IMPL, REVIEW


def test_workflow_file_fixture(test_workflow_file):
    """Verify test_workflow_file fixture creates actual file"""
    assert test_workflow_file.exists()
    assert test_workflow_file.suffix == ".yaml"


def test_jwt_secret_fixture(jwt_secret):
    """Verify JWT secret is set"""
    import os
    assert os.getenv("ORCHESTRATOR_JWT_SECRET") == jwt_secret
    assert len(jwt_secret) >= 32  # Should be long enough


def test_enforcement_engine_fixture(enforcement_engine):
    """Verify enforcement engine initializes correctly"""
    assert enforcement_engine is not None
    assert enforcement_engine.workflow is not None
    assert enforcement_engine.jwt_secret is not None


def test_enforcement_loads_phases(enforcement_engine):
    """Verify phases load correctly"""
    plan_phase = enforcement_engine._get_phase("PLAN")
    assert plan_phase is not None
    assert plan_phase["id"] == "PLAN"
    assert "allowed_tools" in plan_phase
    assert "forbidden_tools" in plan_phase


def test_enforcement_finds_transitions(enforcement_engine):
    """Verify transitions work"""
    transition = enforcement_engine._find_transition("PLAN", "TDD")
    assert transition is not None
    assert transition["from"] == "PLAN"
    assert transition["to"] == "TDD"
    assert transition["gate"] == "plan_approval"


def test_tool_permissions(enforcement_engine):
    """Verify tool permission checking works"""
    # PLAN phase should allow read_files
    allowed = enforcement_engine.get_allowed_tools("PLAN")
    assert "read_files" in allowed

    # PLAN phase should forbid write_files
    forbidden = enforcement_engine.is_tool_forbidden("PLAN", "write_files")
    assert forbidden is True

    # TDD phase should allow write_files
    forbidden_in_tdd = enforcement_engine.is_tool_forbidden("TDD", "write_files")
    assert forbidden_in_tdd is False


def test_valid_phase_token_fixture(valid_phase_token):
    """Verify valid phase token is generated"""
    assert valid_phase_token is not None
    assert isinstance(valid_phase_token, str)
    assert len(valid_phase_token) > 20  # JWTs are long


def test_expired_phase_token_fixture(expired_phase_token):
    """Verify expired token is generated"""
    assert expired_phase_token is not None
    assert isinstance(expired_phase_token, str)
