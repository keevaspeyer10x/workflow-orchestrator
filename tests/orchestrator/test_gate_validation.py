"""
Day 5: Gate Validation Tests

Tests for gate checker methods and gate validation logic.
"""

import pytest
from src.orchestrator.enforcement import WorkflowEnforcement


class TestPlanAcceptanceCriteriaChecker:
    """Tests for _check_plan_has_acceptance_criteria"""

    def test_valid_plan_with_criteria(self, enforcement_engine):
        """Should pass for valid plan with acceptance criteria"""
        artifacts = {
            "plan_document": {
                "title": "Test plan",
                "acceptance_criteria": [
                    {
                        "criterion": "Feature works",
                        "how_to_verify": "Manual test"
                    }
                ],
                "implementation_steps": ["Step 1"],
                "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
            }
        }

        passes, error = enforcement_engine._check_plan_has_acceptance_criteria(artifacts)

        assert passes is True
        assert error is None

    def test_multiple_acceptance_criteria(self, enforcement_engine):
        """Should pass for plan with multiple criteria"""
        artifacts = {
            "plan_document": {
                "title": "Test plan",
                "acceptance_criteria": [
                    {"criterion": "Feature 1", "how_to_verify": "Test 1"},
                    {"criterion": "Feature 2", "how_to_verify": "Test 2"},
                    {"criterion": "Feature 3", "how_to_verify": "Test 3"}
                ],
                "implementation_steps": ["Step 1"],
                "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
            }
        }

        passes, error = enforcement_engine._check_plan_has_acceptance_criteria(artifacts)

        assert passes is True
        assert error is None

    def test_missing_plan_artifact(self, enforcement_engine):
        """Should fail when plan_document artifact is missing"""
        artifacts = {}

        passes, error = enforcement_engine._check_plan_has_acceptance_criteria(artifacts)

        assert passes is False
        assert "Missing plan_document artifact" in error

    def test_empty_acceptance_criteria(self, enforcement_engine):
        """Should fail when acceptance_criteria is empty"""
        artifacts = {
            "plan_document": {
                "title": "Test plan",
                "acceptance_criteria": [],
                "implementation_steps": ["Step 1"],
                "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
            }
        }

        passes, error = enforcement_engine._check_plan_has_acceptance_criteria(artifacts)

        assert passes is False
        assert "at least one acceptance criterion" in error

    def test_missing_acceptance_criteria_field(self, enforcement_engine):
        """Should fail when acceptance_criteria field is missing"""
        artifacts = {
            "plan_document": {
                "title": "Test plan",
                "implementation_steps": ["Step 1"],
                "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
            }
        }

        passes, error = enforcement_engine._check_plan_has_acceptance_criteria(artifacts)

        assert passes is False
        assert "at least one acceptance criterion" in error

    def test_criterion_missing_criterion_field(self, enforcement_engine):
        """Should fail when criterion is missing 'criterion' field"""
        artifacts = {
            "plan_document": {
                "title": "Test plan",
                "acceptance_criteria": [
                    {"how_to_verify": "Test it"}  # Missing 'criterion'
                ],
                "implementation_steps": ["Step 1"],
                "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
            }
        }

        passes, error = enforcement_engine._check_plan_has_acceptance_criteria(artifacts)

        assert passes is False
        assert "criterion" in error.lower()

    def test_criterion_missing_how_to_verify(self, enforcement_engine):
        """Should fail when criterion is missing 'how_to_verify' field"""
        artifacts = {
            "plan_document": {
                "title": "Test plan",
                "acceptance_criteria": [
                    {"criterion": "Feature works"}  # Missing 'how_to_verify'
                ],
                "implementation_steps": ["Step 1"],
                "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
            }
        }

        passes, error = enforcement_engine._check_plan_has_acceptance_criteria(artifacts)

        assert passes is False
        assert "how_to_verify" in error


class TestTestsAreFailingChecker:
    """Tests for _check_tests_are_failing (TDD RED phase)"""

    def test_tests_failing_correctly(self, enforcement_engine):
        """Should pass when tests are failing"""
        artifacts = {
            "test_run_result": {
                "command": "pytest tests/",
                "exit_code": 1,
                "passed": 0,
                "failed": 5,
                "skipped": 0,
                "timestamp": "2026-01-10T10:00:00Z"
            }
        }

        passes, error = enforcement_engine._check_tests_are_failing(artifacts)

        assert passes is True
        assert error is None

    def test_some_passing_some_failing(self, enforcement_engine):
        """Should pass when some tests fail (even if some pass)"""
        artifacts = {
            "test_run_result": {
                "command": "pytest tests/",
                "exit_code": 1,
                "passed": 3,
                "failed": 2,
                "skipped": 0,
                "timestamp": "2026-01-10T10:00:00Z"
            }
        }

        passes, error = enforcement_engine._check_tests_are_failing(artifacts)

        assert passes is True
        assert error is None

    def test_missing_test_result_artifact(self, enforcement_engine):
        """Should fail when test_run_result artifact is missing"""
        artifacts = {}

        passes, error = enforcement_engine._check_tests_are_failing(artifacts)

        assert passes is False
        assert "Missing test_run_result artifact" in error

    def test_all_tests_passing(self, enforcement_engine):
        """Should fail when all tests pass (not TDD RED phase)"""
        artifacts = {
            "test_run_result": {
                "command": "pytest tests/",
                "exit_code": 0,
                "passed": 10,
                "failed": 0,
                "skipped": 0,
                "timestamp": "2026-01-10T10:00:00Z"
            }
        }

        passes, error = enforcement_engine._check_tests_are_failing(artifacts)

        assert passes is False
        assert "failing for TDD RED phase" in error

    def test_no_test_failures(self, enforcement_engine):
        """Should fail when no tests are failing"""
        artifacts = {
            "test_run_result": {
                "command": "pytest tests/",
                "exit_code": 1,  # Exit code says failure
                "passed": 10,
                "failed": 0,  # But no actual failures
                "skipped": 0,
                "timestamp": "2026-01-10T10:00:00Z"
            }
        }

        passes, error = enforcement_engine._check_tests_are_failing(artifacts)

        assert passes is False
        assert "No failing tests detected" in error


class TestAllTestsPassChecker:
    """Tests for _check_all_tests_pass (TDD GREEN phase)"""

    def test_all_tests_passing(self, enforcement_engine):
        """Should pass when all tests pass"""
        artifacts = {
            "test_run_result": {
                "command": "pytest tests/",
                "exit_code": 0,
                "passed": 10,
                "failed": 0,
                "skipped": 2,
                "timestamp": "2026-01-10T10:00:00Z"
            }
        }

        passes, error = enforcement_engine._check_all_tests_pass(artifacts)

        assert passes is True
        assert error is None

    def test_missing_test_result_artifact(self, enforcement_engine):
        """Should fail when test_run_result artifact is missing"""
        artifacts = {}

        passes, error = enforcement_engine._check_all_tests_pass(artifacts)

        assert passes is False
        assert "Missing test_run_result artifact" in error

    def test_some_tests_failing(self, enforcement_engine):
        """Should fail when any tests fail"""
        artifacts = {
            "test_run_result": {
                "command": "pytest tests/",
                "exit_code": 1,
                "passed": 8,
                "failed": 2,
                "skipped": 0,
                "timestamp": "2026-01-10T10:00:00Z"
            }
        }

        passes, error = enforcement_engine._check_all_tests_pass(artifacts)

        assert passes is False
        assert "2 test(s) failed" in error

    def test_non_zero_exit_code(self, enforcement_engine):
        """Should fail when exit code is non-zero"""
        artifacts = {
            "test_run_result": {
                "command": "pytest tests/",
                "exit_code": 1,
                "passed": 10,
                "failed": 0,
                "skipped": 0,
                "timestamp": "2026-01-10T10:00:00Z"
            }
        }

        passes, error = enforcement_engine._check_all_tests_pass(artifacts)

        assert passes is False
        assert "exit code 1" in error

    def test_no_passing_tests(self, enforcement_engine):
        """Should fail when there are no passing tests"""
        artifacts = {
            "test_run_result": {
                "command": "pytest tests/",
                "exit_code": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "timestamp": "2026-01-10T10:00:00Z"
            }
        }

        passes, error = enforcement_engine._check_all_tests_pass(artifacts)

        assert passes is False
        assert "at least one passing test" in error


class TestNoBlockingIssuesChecker:
    """Tests for _check_no_blocking_issues"""

    def test_no_blocking_issues(self, enforcement_engine):
        """Should pass when there are no blocking issues"""
        artifacts = {
            "review_results": {
                "reviews": {
                    "security": {"status": "passed", "issues": []},
                    "quality": {"status": "passed", "issues": []},
                    "consistency": {"status": "passed", "issues": []},
                    "holistic": {"status": "passed", "issues": []},
                    "vibe_coding": {"status": "passed", "issues": []}
                },
                "consolidated_issues": [],
                "blocking_issues": []
            }
        }

        passes, error = enforcement_engine._check_no_blocking_issues(artifacts)

        assert passes is True
        assert error is None

    def test_missing_review_artifact(self, enforcement_engine):
        """Should fail when review_results artifact is missing"""
        artifacts = {}

        passes, error = enforcement_engine._check_no_blocking_issues(artifacts)

        assert passes is False
        assert "Missing review_results artifact" in error

    def test_single_blocking_issue(self, enforcement_engine):
        """Should fail when there is one blocking issue"""
        artifacts = {
            "review_results": {
                "reviews": {
                    "security": {"status": "failed", "issues": [{"severity": "critical", "description": "SQL injection"}]},
                    "quality": {"status": "passed", "issues": []},
                    "consistency": {"status": "passed", "issues": []},
                    "holistic": {"status": "passed", "issues": []},
                    "vibe_coding": {"status": "passed", "issues": []}
                },
                "consolidated_issues": [],
                "blocking_issues": [
                    {"description": "SQL injection vulnerability must be fixed"}
                ]
            }
        }

        passes, error = enforcement_engine._check_no_blocking_issues(artifacts)

        assert passes is False
        assert "1 blocking issue(s)" in error
        assert "SQL injection" in error

    def test_multiple_blocking_issues(self, enforcement_engine):
        """Should fail and list all blocking issues"""
        artifacts = {
            "review_results": {
                "reviews": {
                    "security": {"status": "failed", "issues": []},
                    "quality": {"status": "failed", "issues": []},
                    "consistency": {"status": "passed", "issues": []},
                    "holistic": {"status": "passed", "issues": []},
                    "vibe_coding": {"status": "passed", "issues": []}
                },
                "consolidated_issues": [],
                "blocking_issues": [
                    {"description": "SQL injection vulnerability"},
                    {"description": "Missing input validation"},
                    {"description": "Hardcoded credentials"}
                ]
            }
        }

        passes, error = enforcement_engine._check_no_blocking_issues(artifacts)

        assert passes is False
        assert "3 blocking issue(s)" in error
        assert "SQL injection" in error
        assert "input validation" in error
        assert "credentials" in error


class TestValidateGate:
    """Tests for _validate_gate integration"""

    def test_plan_approval_gate_passes(self, enforcement_engine):
        """Should pass plan_approval gate with valid plan"""
        artifacts = {
            "plan_document": {
                "title": "Valid plan with 10+ characters",
                "acceptance_criteria": [
                    {"criterion": "Feature works", "how_to_verify": "Test it"}
                ],
                "implementation_steps": ["Step 1", "Step 2"],
                "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
            }
        }

        passes, blockers = enforcement_engine._validate_gate("plan_approval", artifacts)

        assert passes is True
        assert len(blockers) == 0

    def test_plan_approval_gate_fails(self, enforcement_engine):
        """Should fail plan_approval gate with invalid plan"""
        artifacts = {
            "plan_document": {
                "title": "Valid plan",
                "acceptance_criteria": [],  # Empty!
                "implementation_steps": ["Step 1"],
                "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
            }
        }

        passes, blockers = enforcement_engine._validate_gate("plan_approval", artifacts)

        assert passes is False
        assert len(blockers) > 0
        assert any("acceptance criteria" in b.lower() for b in blockers)

    def test_tests_written_gate_passes(self, enforcement_engine):
        """Should pass tests_written gate when tests are failing"""
        artifacts = {
            "test_run_result": {
                "command": "pytest tests/",
                "exit_code": 1,
                "passed": 0,
                "failed": 5,
                "skipped": 0,
                "timestamp": "2026-01-10T10:00:00Z"
            }
        }

        passes, blockers = enforcement_engine._validate_gate("tests_written", artifacts)

        assert passes is True
        assert len(blockers) == 0

    def test_tests_written_gate_fails_when_passing(self, enforcement_engine):
        """Should fail tests_written gate when tests are passing"""
        artifacts = {
            "test_run_result": {
                "command": "pytest tests/",
                "exit_code": 0,
                "passed": 5,
                "failed": 0,
                "skipped": 0,
                "timestamp": "2026-01-10T10:00:00Z"
            }
        }

        passes, blockers = enforcement_engine._validate_gate("tests_written", artifacts)

        assert passes is False
        assert len(blockers) > 0
        assert any("fail" in b.lower() for b in blockers)

    def test_tests_passing_gate_passes(self, enforcement_engine):
        """Should pass tests_passing gate when all tests pass"""
        artifacts = {
            "test_run_result": {
                "command": "pytest tests/",
                "exit_code": 0,
                "passed": 10,
                "failed": 0,
                "skipped": 2,
                "timestamp": "2026-01-10T10:00:00Z"
            }
        }

        passes, blockers = enforcement_engine._validate_gate("tests_passing", artifacts)

        assert passes is True
        assert len(blockers) == 0

    def test_tests_passing_gate_fails(self, enforcement_engine):
        """Should fail tests_passing gate when tests fail"""
        artifacts = {
            "test_run_result": {
                "command": "pytest tests/",
                "exit_code": 1,
                "passed": 8,
                "failed": 2,
                "skipped": 0,
                "timestamp": "2026-01-10T10:00:00Z"
            }
        }

        passes, blockers = enforcement_engine._validate_gate("tests_passing", artifacts)

        assert passes is False
        assert len(blockers) > 0

    def test_review_approved_gate_passes(self, enforcement_engine):
        """Should pass review_approved gate with no blocking issues"""
        artifacts = {
            "review_results": {
                "reviews": {
                    "security": {"status": "passed", "issues": []},
                    "quality": {"status": "passed", "issues": []},
                    "consistency": {"status": "passed", "issues": []},
                    "holistic": {"status": "passed", "issues": []},
                    "vibe_coding": {"status": "passed", "issues": []}
                },
                "consolidated_issues": [],
                "blocking_issues": []
            }
        }

        passes, blockers = enforcement_engine._validate_gate("review_approved", artifacts)

        assert passes is True
        assert len(blockers) == 0

    def test_review_approved_gate_fails(self, enforcement_engine):
        """Should fail review_approved gate with blocking issues"""
        artifacts = {
            "review_results": {
                "reviews": {
                    "security": {"status": "failed", "issues": []},
                    "quality": {"status": "passed", "issues": []},
                    "consistency": {"status": "passed", "issues": []},
                    "holistic": {"status": "passed", "issues": []},
                    "vibe_coding": {"status": "passed", "issues": []}
                },
                "consolidated_issues": [],
                "blocking_issues": [
                    {"description": "Critical security issue"}
                ]
            }
        }

        passes, blockers = enforcement_engine._validate_gate("review_approved", artifacts)

        assert passes is False
        assert len(blockers) > 0
        assert any("blocking issue" in b.lower() for b in blockers)

    def test_nonexistent_gate(self, enforcement_engine):
        """Should fail for nonexistent gate"""
        artifacts = {}

        passes, blockers = enforcement_engine._validate_gate("nonexistent_gate", artifacts)

        assert passes is False
        assert len(blockers) == 1
        assert "Gate not found" in blockers[0]

    def test_gate_with_unknown_checker(self, enforcement_engine):
        """Should skip unknown checkers gracefully"""
        # The gate might have checkers we haven't implemented yet
        # Those should be skipped without failing the gate
        # This tests the checker_map fallback logic
        pass  # Implementation will evolve as we add more checkers


class TestGateEdgeCases:
    """Edge cases for gate validation"""

    def test_gate_with_multiple_blockers_all_pass(self, enforcement_engine):
        """Should pass gate when all blockers pass"""
        # plan_approval has multiple blockers (plan_has_acceptance_criteria, scope_is_bounded)
        # We only implemented plan_has_acceptance_criteria, so scope_is_bounded will be skipped
        artifacts = {
            "plan_document": {
                "title": "Valid plan",
                "acceptance_criteria": [
                    {"criterion": "Test", "how_to_verify": "Manual"}
                ],
                "implementation_steps": ["Step 1"],
                "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
            }
        }

        passes, blockers = enforcement_engine._validate_gate("plan_approval", artifacts)

        # Should pass because implemented checker passes, and unknown checkers are skipped
        assert passes is True
        assert len(blockers) == 0

    def test_gate_with_multiple_blockers_some_fail(self, enforcement_engine):
        """Should fail gate if any implemented blocker fails"""
        artifacts = {
            "plan_document": {
                "title": "Invalid plan",
                "acceptance_criteria": [],  # Fails!
                "implementation_steps": ["Step 1"],
                "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
            }
        }

        passes, blockers = enforcement_engine._validate_gate("plan_approval", artifacts)

        assert passes is False
        assert len(blockers) > 0
