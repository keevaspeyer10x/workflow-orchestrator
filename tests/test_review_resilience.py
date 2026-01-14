"""
Tests for CORE-026: Review Failure Resilience & API Key Recovery.

Tests cover:
1. ReviewErrorType classification
2. API key validation (proactive checks)
3. Required reviews from workflow.yaml
4. Recovery instructions
5. Retry mechanism
6. Finish validation
"""

import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from src.review.result import ReviewResult, Severity, ReviewFinding


# =============================================================================
# Test 1: ReviewErrorType Classification
# =============================================================================

class TestReviewErrorType:
    """Tests for ReviewErrorType enum and error classification."""

    def test_error_type_enum_exists(self):
        """ReviewErrorType enum should exist with expected values."""
        from src.review.result import ReviewErrorType
        assert hasattr(ReviewErrorType, "NONE")
        assert hasattr(ReviewErrorType, "KEY_MISSING")
        assert hasattr(ReviewErrorType, "KEY_INVALID")
        assert hasattr(ReviewErrorType, "RATE_LIMITED")
        assert hasattr(ReviewErrorType, "NETWORK_ERROR")
        assert hasattr(ReviewErrorType, "TIMEOUT")
        assert hasattr(ReviewErrorType, "PARSE_ERROR")
        assert hasattr(ReviewErrorType, "REVIEW_FAILED")

    def test_http_401_classified_as_key_invalid(self):
        """HTTP 401 Unauthorized should be KEY_INVALID."""
        from src.review.result import ReviewErrorType, classify_http_error
        result = classify_http_error(401, "Invalid API key")
        assert result == ReviewErrorType.KEY_INVALID

    def test_http_403_classified_as_key_invalid(self):
        """HTTP 403 Forbidden should be KEY_INVALID."""
        from src.review.result import ReviewErrorType, classify_http_error
        result = classify_http_error(403, "Access denied")
        assert result == ReviewErrorType.KEY_INVALID

    def test_http_429_classified_as_rate_limited(self):
        """HTTP 429 Too Many Requests should be RATE_LIMITED."""
        from src.review.result import ReviewErrorType, classify_http_error
        result = classify_http_error(429, "Rate limit exceeded")
        assert result == ReviewErrorType.RATE_LIMITED

    def test_http_500_classified_as_network_error(self):
        """HTTP 500+ should be classified as transient NETWORK_ERROR."""
        from src.review.result import ReviewErrorType, classify_http_error
        result = classify_http_error(500, "Internal server error")
        assert result == ReviewErrorType.NETWORK_ERROR

    def test_review_result_has_error_type_field(self):
        """ReviewResult should have error_type field."""
        from src.review.result import ReviewErrorType
        result = ReviewResult(
            review_type="security",
            success=False,
            model_used="codex",
            method_used="api",
            error="API key invalid",
            error_type=ReviewErrorType.KEY_INVALID,
        )
        assert result.error_type == ReviewErrorType.KEY_INVALID

    def test_review_result_error_type_default(self):
        """ReviewResult error_type should default to NONE."""
        from src.review.result import ReviewErrorType
        result = ReviewResult(
            review_type="security",
            success=True,
            model_used="codex",
            method_used="api",
        )
        assert result.error_type == ReviewErrorType.NONE

    def test_review_result_to_dict_includes_error_type(self):
        """ReviewResult.to_dict() should include error_type."""
        from src.review.result import ReviewErrorType
        result = ReviewResult(
            review_type="security",
            success=False,
            model_used="codex",
            method_used="api",
            error="Rate limited",
            error_type=ReviewErrorType.RATE_LIMITED,
        )
        d = result.to_dict()
        assert "error_type" in d
        assert d["error_type"] == "rate_limited"

    def test_review_result_from_dict_loads_error_type(self):
        """ReviewResult.from_dict() should load error_type."""
        from src.review.result import ReviewErrorType
        data = {
            "review_type": "security",
            "success": False,
            "model_used": "codex",
            "method_used": "api",
            "error_type": "key_invalid",
        }
        result = ReviewResult.from_dict(data)
        assert result.error_type == ReviewErrorType.KEY_INVALID


# =============================================================================
# Test 2: API Key Validation
# =============================================================================

class TestAPIKeyValidation:
    """Tests for proactive API key validation."""

    def test_validate_api_keys_function_exists(self):
        """validate_api_keys function should exist in router."""
        from src.review.router import validate_api_keys
        assert callable(validate_api_keys)

    def test_validate_missing_key(self):
        """Missing API key should return error."""
        from src.review.router import validate_api_keys
        with patch.dict(os.environ, {}, clear=True):
            valid, errors = validate_api_keys(["gemini"])
            assert not valid
            assert "gemini" in errors
            assert "GEMINI_API_KEY" in errors["gemini"]

    def test_validate_present_key_no_ping(self):
        """Present API key without ping should pass presence check."""
        from src.review.router import validate_api_keys
        # Use a key that's at least 10 characters
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345-valid"}, clear=True):
            valid, errors = validate_api_keys(["gemini"], ping=False)
            assert valid
            assert not errors

    def test_validate_multiple_keys_partial_failure(self):
        """One missing key should fail whole validation."""
        from src.review.router import validate_api_keys
        # Use valid-length key for gemini, missing for openai
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345-valid"}, clear=True):
            valid, errors = validate_api_keys(["gemini", "openai"], ping=False)
            assert not valid
            assert "openai" in errors
            assert "gemini" not in errors

    def test_validate_all_keys_present(self):
        """All keys present should pass validation."""
        from src.review.router import validate_api_keys
        env = {
            "GEMINI_API_KEY": "gem-key-12345-valid",
            "OPENAI_API_KEY": "oai-key-12345-valid",
            "XAI_API_KEY": "xai-key-12345-valid",
        }
        with patch.dict(os.environ, env, clear=True):
            valid, errors = validate_api_keys(["gemini", "openai", "grok"], ping=False)
            assert valid
            assert not errors


# =============================================================================
# Test 3: Required Reviews from Workflow Definition
# =============================================================================

class TestRequiredReviewsFromWorkflow:
    """Tests for reading required_reviews from workflow.yaml."""

    def test_get_required_reviews_from_workflow(self, tmp_path):
        """Engine should read required_reviews from workflow definition."""
        from src.engine import WorkflowEngine

        # Create workflow.yaml with required_reviews
        workflow_content = """
name: test
version: "1.0"
phases:
  - id: REVIEW
    name: Review
    required_reviews:
      - security
      - quality
      - consistency
    items: []
"""
        (tmp_path / "workflow.yaml").write_text(workflow_content)

        engine = WorkflowEngine(working_dir=str(tmp_path))
        engine.load_workflow_def(tmp_path / "workflow.yaml")
        required = engine.get_required_reviews()
        assert required == {"security", "quality", "consistency"}

    def test_get_required_reviews_defaults_empty(self, tmp_path):
        """Missing required_reviews field should default to empty set."""
        from src.engine import WorkflowEngine

        workflow_content = """
name: test
version: "1.0"
phases:
  - id: REVIEW
    name: Review
    items: []
"""
        (tmp_path / "workflow.yaml").write_text(workflow_content)

        engine = WorkflowEngine(working_dir=str(tmp_path))
        engine.load_workflow_def(tmp_path / "workflow.yaml")
        required = engine.get_required_reviews()
        assert required == set()

    def test_validate_reviews_checks_completed(self, tmp_path):
        """validate_reviews_completed should check workflow required_reviews."""
        from src.engine import WorkflowEngine, WorkflowEvent, EventType

        workflow_content = """
name: test
version: "1.0"
phases:
  - id: PLAN
    name: Plan
    items: []
  - id: REVIEW
    name: Review
    required_reviews:
      - security
      - quality
    items: []
"""
        (tmp_path / "workflow.yaml").write_text(workflow_content)

        engine = WorkflowEngine(working_dir=str(tmp_path))
        engine.load_workflow_def(tmp_path / "workflow.yaml")
        engine.start_workflow(str(tmp_path / "workflow.yaml"), "Test workflow for CORE-026")

        # Simulate completing only security review
        engine.log_event(WorkflowEvent(
            event_type=EventType.REVIEW_COMPLETED,
            workflow_id=engine.state.workflow_id,
            phase_id="REVIEW",
            item_id="security_review",
            message="Security review passed",
            details={"review_type": "security"}
        ))

        valid, missing = engine.validate_reviews_completed()
        assert not valid
        assert "quality" in missing


# =============================================================================
# Test 4: Recovery Instructions
# =============================================================================

class TestRecoveryInstructions:
    """Tests for API key recovery instructions."""

    def test_recovery_module_exists(self):
        """Recovery module should exist."""
        from src.review import recovery
        assert hasattr(recovery, "get_recovery_instructions")

    def test_recovery_instructions_for_gemini(self):
        """Gemini recovery instructions should include key name and reload method."""
        from src.review.recovery import get_recovery_instructions
        instructions = get_recovery_instructions("gemini")
        assert "GEMINI_API_KEY" in instructions
        assert "sops" in instructions.lower() or "export" in instructions.lower()

    def test_recovery_instructions_for_openai(self):
        """OpenAI recovery instructions should exist."""
        from src.review.recovery import get_recovery_instructions
        instructions = get_recovery_instructions("openai")
        assert "OPENAI_API_KEY" in instructions

    def test_recovery_instructions_for_grok(self):
        """Grok recovery instructions should exist."""
        from src.review.recovery import get_recovery_instructions
        instructions = get_recovery_instructions("grok")
        assert "XAI_API_KEY" in instructions

    def test_recovery_instructions_include_retry_hint(self):
        """Recovery instructions should mention retry command."""
        from src.review.recovery import get_recovery_instructions
        instructions = get_recovery_instructions("gemini")
        assert "retry" in instructions.lower()

    def test_format_review_error_includes_recovery(self):
        """Formatted review error should include recovery guidance."""
        from src.review.result import ReviewErrorType
        from src.review.recovery import format_review_error

        result = ReviewResult(
            review_type="consistency",
            success=False,
            model_used="gemini",
            method_used="api",
            error="API key invalid",
            error_type=ReviewErrorType.KEY_INVALID,
        )
        output = format_review_error(result)
        assert "GEMINI_API_KEY" in output
        assert "retry" in output.lower()


# =============================================================================
# Test 5: Retry Command
# =============================================================================

class TestRetryCommand:
    """Tests for orchestrator review-retry command."""

    def test_retry_subcommand_exists(self):
        """orchestrator review-retry command should be registered."""
        import subprocess
        result = subprocess.run(
            ["python", "-m", "src.cli", "review-retry", "--help"],
            capture_output=True, text=True, cwd=str(Path(__file__).parent.parent)
        )
        assert result.returncode == 0
        assert "retry" in result.stdout.lower() or "review" in result.stdout.lower()

    def test_get_failed_reviews_function_exists(self):
        """Engine should have get_failed_reviews method."""
        from src.engine import WorkflowEngine
        assert hasattr(WorkflowEngine, "get_failed_reviews")

    def test_get_failed_reviews_returns_failed(self, tmp_path):
        """get_failed_reviews should return reviews that failed."""
        from src.engine import WorkflowEngine, WorkflowEvent, EventType

        workflow_content = """
name: test
version: "1.0"
phases:
  - id: REVIEW
    name: Review
    items: []
"""
        (tmp_path / "workflow.yaml").write_text(workflow_content)

        engine = WorkflowEngine(working_dir=str(tmp_path))
        engine.load_workflow_def(tmp_path / "workflow.yaml")
        engine.start_workflow(str(tmp_path / "workflow.yaml"), "Test workflow for CORE-026")

        # Log a failed review
        engine.log_event(WorkflowEvent(
            event_type=EventType.REVIEW_FAILED,
            workflow_id=engine.state.workflow_id,
            phase_id="REVIEW",
            item_id="security_review",
            message="Review failed",
            details={"review_type": "security", "error_type": "key_missing"}
        ))

        failed = engine.get_failed_reviews()
        assert "security" in failed


# =============================================================================
# Test 6: Backward Compatibility
# =============================================================================

class TestBackwardCompatibility:
    """Tests for backward compatibility with existing workflows."""

    def test_old_workflow_without_required_reviews(self, tmp_path):
        """Workflows without required_reviews field should still work."""
        from src.engine import WorkflowEngine

        # Old-style workflow without required_reviews
        workflow_content = """
name: old-workflow
version: "1.0"
phases:
  - id: REVIEW
    name: Review
    items:
      - id: security_review
        name: Security Review
"""
        (tmp_path / "workflow.yaml").write_text(workflow_content)

        engine = WorkflowEngine(working_dir=str(tmp_path))
        engine.load_workflow_def(tmp_path / "workflow.yaml")

        # Should not raise, defaults to empty
        required = engine.get_required_reviews()
        assert required == set()

    def test_review_result_without_error_type_loads(self):
        """Old ReviewResult dicts without error_type should load."""
        from src.review.result import ReviewErrorType

        # Old format without error_type
        data = {
            "review_type": "security",
            "success": True,
            "model_used": "codex",
            "method_used": "cli",
        }
        result = ReviewResult.from_dict(data)
        # Should default to NONE
        assert result.error_type == ReviewErrorType.NONE


# =============================================================================
# Test 7: Error Type in Workflow Events
# =============================================================================

class TestErrorTypeInEvents:
    """Tests for error_type tracking in workflow events."""

    def test_review_failed_event_includes_error_type(self):
        """REVIEW_FAILED events should include error_type in details."""
        from src.engine import WorkflowEvent, EventType

        event = WorkflowEvent(
            event_type=EventType.REVIEW_FAILED,
            workflow_id="test-workflow-123",
            phase_id="REVIEW",
            item_id="security_review",
            message="API key missing",
            details={
                "review_type": "security",
                "error_type": "key_missing",
                "error": "OPENAI_API_KEY not set"
            }
        )
        assert event.details["error_type"] == "key_missing"

    def test_get_failed_reviews_includes_error_type(self, tmp_path):
        """get_failed_reviews should return error types."""
        from src.engine import WorkflowEngine, WorkflowEvent, EventType

        workflow_content = """
name: test
version: "1.0"
phases:
  - id: REVIEW
    name: Review
    items: []
"""
        (tmp_path / "workflow.yaml").write_text(workflow_content)

        engine = WorkflowEngine(working_dir=str(tmp_path))
        engine.load_workflow_def(tmp_path / "workflow.yaml")
        engine.start_workflow(str(tmp_path / "workflow.yaml"), "Test workflow for CORE-026")

        engine.log_event(WorkflowEvent(
            event_type=EventType.REVIEW_FAILED,
            workflow_id=engine.state.workflow_id,
            phase_id="REVIEW",
            item_id="security_review",
            message="Key invalid",
            details={"review_type": "security", "error_type": "key_invalid"}
        ))

        failed = engine.get_failed_reviews()
        assert "security" in failed
        # Should include error type info
        assert failed["security"]["error_type"] == "key_invalid"
