"""
Tests for Issue #91: Automated Design Validation

Tests cover:
1. DesignValidationResult dataclass
2. Lenient vs strict validation modes
3. Plan vs diff comparison
4. CLI integration
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import os


# =============================================================================
# Result Schema Tests
# =============================================================================

class TestDesignValidationResult:
    """Test DesignValidationResult dataclass."""

    def test_result_dataclass_exists(self):
        """DesignValidationResult should be importable."""
        from src.review.design_validator import DesignValidationResult

        result = DesignValidationResult(
            status="PASS",
            planned_items_implemented=["item1", "item2"],
            unplanned_additions=[],
            deviations=[],
            notes="All planned items implemented",
            confidence=0.95,
        )

        assert result.status == "PASS"
        assert len(result.planned_items_implemented) == 2
        assert result.confidence == 0.95

    def test_result_status_values(self):
        """Status should be one of PASS, PASS_WITH_NOTES, NEEDS_REVISION."""
        from src.review.design_validator import DesignValidationResult

        valid_statuses = ["PASS", "PASS_WITH_NOTES", "NEEDS_REVISION"]

        for status in valid_statuses:
            result = DesignValidationResult(
                status=status,
                planned_items_implemented=[],
                unplanned_additions=[],
                deviations=[],
                notes="",
                confidence=0.5,
            )
            assert result.status == status

    def test_result_to_dict(self):
        """Result should be convertible to dict."""
        from src.review.design_validator import DesignValidationResult

        result = DesignValidationResult(
            status="PASS",
            planned_items_implemented=["feature A"],
            unplanned_additions=["logging"],
            deviations=[],
            notes="Good implementation",
            confidence=0.9,
        )

        result_dict = result.to_dict()

        assert result_dict["status"] == "PASS"
        assert result_dict["planned_items_implemented"] == ["feature A"]
        assert result_dict["confidence"] == 0.9


# =============================================================================
# Validation Logic Tests
# =============================================================================

class TestValidationLogic:
    """Test validate_design function logic."""

    def test_validate_design_function_exists(self):
        """validate_design function should be importable."""
        from src.review.design_validator import validate_design

        assert callable(validate_design)

    @patch('src.review.design_validator.call_with_fallback')
    def test_basic_plan_comparison(self, mock_call):
        """Validate plan items are detected in implementation."""
        from src.review.design_validator import validate_design

        # Mock LLM response
        mock_call.return_value = Mock(
            content='{"status": "PASS", "planned_items_implemented": ["login button", "logout handler"], "unplanned_additions": [], "deviations": [], "notes": "All items found", "confidence": 0.9}'
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Plan\n1. Add login button\n2. Add logout handler")
            plan_path = Path(f.name)

        try:
            result = validate_design(
                plan_path=plan_path,
                diff="+ <button>Login</button>\n+ def logout():",
            )

            assert result.status == "PASS"
            assert "login button" in str(result.planned_items_implemented).lower()
        finally:
            os.unlink(plan_path)

    @patch('src.review.design_validator.call_with_fallback')
    def test_lenient_mode_allows_minor_additions(self, mock_call):
        """Lenient mode should not flag logging, tests, error handling."""
        from src.review.design_validator import validate_design

        # In lenient mode, minor additions should not be flagged
        mock_call.return_value = Mock(
            content='{"status": "PASS", "planned_items_implemented": ["API endpoint"], "unplanned_additions": [], "deviations": [], "notes": "Logging additions allowed in lenient mode", "confidence": 0.85}'
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Plan\n1. Add user API endpoint")
            plan_path = Path(f.name)

        try:
            result = validate_design(
                plan_path=plan_path,
                diff="+ @app.route('/user')\n+ logger.info('Request received')",
                lenient=True,
            )

            # Logging should not be flagged as unplanned
            assert result.status in ("PASS", "PASS_WITH_NOTES")
            assert len(result.unplanned_additions) == 0
        finally:
            os.unlink(plan_path)

    @patch('src.review.design_validator.call_with_fallback')
    def test_lenient_mode_flags_major_scope_creep(self, mock_call):
        """Lenient mode should still flag significant unplanned features."""
        from src.review.design_validator import validate_design

        # Major additions should still be flagged
        mock_call.return_value = Mock(
            content='{"status": "NEEDS_REVISION", "planned_items_implemented": ["user endpoint"], "unplanned_additions": ["admin panel"], "deviations": ["Added unplanned admin feature"], "notes": "Admin panel was not in plan", "confidence": 0.9}'
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Plan\n1. Add user API endpoint")
            plan_path = Path(f.name)

        try:
            result = validate_design(
                plan_path=plan_path,
                diff="+ @app.route('/user')\n+ @app.route('/admin')\n+ class AdminPanel:",
                lenient=True,
            )

            assert result.status == "NEEDS_REVISION"
            assert "admin" in str(result.unplanned_additions).lower()
        finally:
            os.unlink(plan_path)

    @patch('src.review.design_validator.call_with_fallback')
    def test_missing_planned_items_detected(self, mock_call):
        """Should flag when planned items are not implemented."""
        from src.review.design_validator import validate_design

        mock_call.return_value = Mock(
            content='{"status": "NEEDS_REVISION", "planned_items_implemented": ["login", "logout"], "unplanned_additions": [], "deviations": ["password reset not implemented"], "notes": "Missing: password reset", "confidence": 0.95}'
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Plan\n1. Add login\n2. Add logout\n3. Add password reset")
            plan_path = Path(f.name)

        try:
            result = validate_design(
                plan_path=plan_path,
                diff="+ def login():\n+ def logout():",
            )

            # Only 2 of 3 items implemented
            assert result.status == "NEEDS_REVISION"
            assert "password reset" in result.notes.lower() or len(result.planned_items_implemented) < 3
        finally:
            os.unlink(plan_path)


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_no_plan_file_returns_none_or_skip(self):
        """Should handle missing plan file gracefully."""
        from src.review.design_validator import validate_design

        # Non-existent path
        result = validate_design(
            plan_path=Path("/nonexistent/plan.md"),
            diff="some diff",
        )

        # Should return None or result with SKIP status
        assert result is None or result.status == "SKIP"

    def test_empty_diff_handled(self):
        """Should handle empty diff gracefully."""
        from src.review.design_validator import validate_design

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Plan\n1. Add feature")
            plan_path = Path(f.name)

        try:
            result = validate_design(
                plan_path=plan_path,
                diff="",
            )

            # Empty diff likely means nothing implemented
            assert result is not None
        finally:
            os.unlink(plan_path)

    @patch('src.review.design_validator.call_with_fallback')
    def test_invalid_llm_response_handled(self, mock_call):
        """Should handle invalid JSON from LLM gracefully."""
        from src.review.design_validator import validate_design

        # Mock invalid JSON response
        mock_call.return_value = Mock(content="This is not valid JSON")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Plan\n1. Add feature")
            plan_path = Path(f.name)

        try:
            # Should not crash
            result = validate_design(
                plan_path=plan_path,
                diff="+ some code",
            )

            # Should return error result or None (SKIP status with notes about failure)
            assert result is None or result.status == "SKIP" or "failed" in str(result.notes).lower()
        finally:
            os.unlink(plan_path)


# =============================================================================
# Strict Mode Tests
# =============================================================================

class TestStrictMode:
    """Test strict validation mode."""

    @patch('src.review.design_validator.call_with_fallback')
    def test_strict_mode_flags_all_deviations(self, mock_call):
        """Strict mode should flag all deviations including minor ones."""
        from src.review.design_validator import validate_design

        mock_call.return_value = Mock(
            content='{"status": "PASS_WITH_NOTES", "planned_items_implemented": ["login"], "unplanned_additions": ["extra logging"], "deviations": ["used username instead of email"], "notes": "Minor deviation in parameter name", "confidence": 0.8}'
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Plan\n1. Add login with email")
            plan_path = Path(f.name)

        try:
            result = validate_design(
                plan_path=plan_path,
                diff="+ def login(username):",
                lenient=False,  # Strict mode
            )

            # Strict mode should flag parameter name difference
            assert result.status in ("PASS_WITH_NOTES", "NEEDS_REVISION")
            assert len(result.deviations) > 0
        finally:
            os.unlink(plan_path)


# =============================================================================
# Git Diff Integration
# =============================================================================

class TestGitDiffIntegration:
    """Test git diff integration."""

    def test_get_git_diff_function_exists(self):
        """get_git_diff helper should exist."""
        from src.review.design_validator import get_git_diff

        assert callable(get_git_diff)

    @patch('subprocess.run')
    def test_get_git_diff_calls_git(self, mock_run):
        """get_git_diff should call git diff command."""
        from src.review.design_validator import get_git_diff

        mock_run.return_value = Mock(
            stdout="+ added line\n- removed line",
            returncode=0,
        )

        diff = get_git_diff("main")

        mock_run.assert_called()
        assert "main" in str(mock_run.call_args)


# =============================================================================
# Uses Fallback Chain (#89 Integration)
# =============================================================================

class TestFallbackIntegration:
    """Test that design validation uses #89 fallback chains."""

    @patch('src.review.design_validator.call_with_fallback')
    def test_uses_fallback_chain(self, mock_call):
        """validate_design should use call_with_fallback for resilience."""
        from src.review.design_validator import validate_design

        mock_call.return_value = Mock(
            content='{"status": "PASS", "planned_items_implemented": [], "unplanned_additions": [], "deviations": [], "notes": "", "confidence": 0.9}'
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Plan")
            plan_path = Path(f.name)

        try:
            validate_design(plan_path=plan_path, diff="diff")

            # Should have called call_with_fallback
            mock_call.assert_called()
        finally:
            os.unlink(plan_path)
