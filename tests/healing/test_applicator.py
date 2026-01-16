"""Tests for fix applicator."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _utcnow() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)

from src.healing.applicator import (
    FixApplicator,
    ApplyResult,
    VerifyResult,
)
from src.healing.judges import SuggestedFix
from src.healing.safety import SafetyCategory
from src.healing.validation import ValidationResult, ValidationPhase
from src.healing.adapters.base import TestResult, BuildResult
from src.healing.models import ErrorEvent, FixAction
from src.healing.cascade import reset_cascade_detector


class TestApplyResult:
    """Tests for ApplyResult dataclass."""

    def test_apply_result_success(self):
        """Should create successful result."""
        result = ApplyResult(
            success=True,
            fix_id="fix-123",
            commit_sha="abc123",
            rollback_available=True,
        )
        assert result.success
        assert not result.needs_pr_review

    def test_apply_result_with_pr(self):
        """Should indicate PR review needed."""
        result = ApplyResult(
            success=True,
            fix_id="fix-123",
            branch="fix/auto-fix-123",
            pr_url="https://github.com/repo/pull/1",
            rollback_available=True,
        )
        assert result.needs_pr_review

    def test_apply_result_failure(self):
        """Should create failure result."""
        result = ApplyResult(
            success=False,
            fix_id="fix-123",
            error="Build failed",
        )
        assert not result.success


class TestVerifyResult:
    """Tests for VerifyResult dataclass."""

    def test_verify_result_passed(self):
        """Should create passed result."""
        result = VerifyResult(
            passed=True,
            message="All checks passed",
            build_result=BuildResult(passed=True),
            test_result=TestResult(passed=True),
        )
        assert result.passed

    def test_verify_result_failed(self):
        """Should create failed result."""
        result = VerifyResult(
            passed=False,
            message="Tests failed",
            build_result=BuildResult(passed=True),
            test_result=TestResult(passed=False, message="1 test failed"),
        )
        assert not result.passed


class TestFixApplicator:
    """Tests for FixApplicator."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset global state."""
        reset_cascade_detector()
        yield

    @pytest.fixture
    def mock_git(self):
        """Create mock git adapter."""
        git = MagicMock()
        git.create_branch = AsyncMock()
        git.apply_diff = AsyncMock(return_value="abc123")
        git.create_pr = AsyncMock(return_value="https://github.com/repo/pull/1")
        git.merge_branch = AsyncMock()
        git.delete_branch = AsyncMock()
        return git

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage adapter."""
        storage = MagicMock()
        storage.read_file = AsyncMock(return_value="content")
        storage.write_file = AsyncMock()
        storage.file_exists = AsyncMock(return_value=True)
        return storage

    @pytest.fixture
    def mock_execution(self):
        """Create mock execution adapter."""
        execution = MagicMock()
        execution.run_build = AsyncMock(return_value=BuildResult(passed=True))
        execution.run_tests = AsyncMock(return_value=TestResult(passed=True))
        execution.run_command = AsyncMock(return_value=(0, "output", ""))
        return execution

    @pytest.fixture
    def mock_supabase(self):
        """Create mock supabase client."""
        supabase = MagicMock()
        supabase.record_fix_result = AsyncMock()
        supabase.audit_log = AsyncMock()
        return supabase

    @pytest.fixture
    def applicator(self, mock_git, mock_storage, mock_execution, mock_supabase):
        """Create FixApplicator with mocks."""
        return FixApplicator(
            git=mock_git,
            storage=mock_storage,
            execution=mock_execution,
            supabase=mock_supabase,
        )

    @pytest.fixture
    def sample_fix(self):
        """Create sample fix."""
        action = FixAction(action_type="diff", diff="+import os\n")
        return SuggestedFix(
            fix_id="fix-test",
            title="Add import",
            action=action,
            safety_category=SafetyCategory.SAFE,
            affected_files=["src/utils.py"],
            lines_changed=1,
        )

    @pytest.fixture
    def sample_error(self):
        """Create sample error."""
        return ErrorEvent(
            error_id="err-1",
            timestamp=_utcnow(),
            source="subprocess",
            description="ModuleNotFoundError",
            fingerprint="abc123",
        )

    @pytest.fixture
    def approved_validation(self):
        """Create approved validation result."""
        return ValidationResult(
            approved=True,
            phase=ValidationPhase.APPROVAL,
            reason="1/1 judges approved",
        )

    @pytest.mark.asyncio
    async def test_apply_not_approved(self, applicator, sample_fix, sample_error):
        """Should reject unapproved fixes."""
        validation = ValidationResult(
            approved=False,
            phase=ValidationPhase.PRE_FLIGHT,
            reason="Kill switch active",
        )

        result = await applicator.apply(sample_fix, sample_error, validation)

        assert not result.success
        assert "not approved" in result.error.lower()

    @pytest.mark.asyncio
    async def test_apply_diff_success(
        self, applicator, sample_fix, sample_error, approved_validation, mock_git
    ):
        """Should apply diff successfully."""
        with patch("src.healing.applicator.get_environment") as mock_env:
            from src.healing.environment import Environment
            mock_env.return_value = Environment.LOCAL

            result = await applicator.apply(sample_fix, sample_error, approved_validation)

        assert result.success
        assert result.commit_sha == "abc123"
        mock_git.create_branch.assert_called_once()
        mock_git.apply_diff.assert_called()

    @pytest.mark.asyncio
    async def test_apply_command(
        self, applicator, sample_error, approved_validation, mock_execution
    ):
        """Should run command and commit."""
        action = FixAction(action_type="command", command="pip install pkg")
        fix = SuggestedFix(
            fix_id="fix-cmd",
            title="Install package",
            action=action,
            safety_category=SafetyCategory.SAFE,
            affected_files=[],
            lines_changed=0,
        )

        with patch("src.healing.applicator.get_environment") as mock_env:
            from src.healing.environment import Environment
            mock_env.return_value = Environment.LOCAL

            result = await applicator.apply(fix, sample_error, approved_validation)

        mock_execution.run_command.assert_called_with("pip install pkg")
        assert result.success

    @pytest.mark.asyncio
    async def test_apply_file_edit(
        self, applicator, sample_error, approved_validation, mock_storage
    ):
        """Should apply file edit."""
        action = FixAction(
            action_type="file_edit",
            file_path="src/config.py",
            find="old_value",
            replace="new_value",
        )
        fix = SuggestedFix(
            fix_id="fix-edit",
            title="Update config",
            action=action,
            safety_category=SafetyCategory.SAFE,
            affected_files=["src/config.py"],
            lines_changed=1,
        )
        mock_storage.read_file.return_value = "old_value = 1"

        with patch("src.healing.applicator.get_environment") as mock_env:
            from src.healing.environment import Environment
            mock_env.return_value = Environment.LOCAL

            result = await applicator.apply(fix, sample_error, approved_validation)

        mock_storage.write_file.assert_called_with("src/config.py", "new_value = 1")
        assert result.success

    @pytest.mark.asyncio
    async def test_apply_verification_failure(
        self, applicator, sample_fix, sample_error, approved_validation, mock_execution, mock_git
    ):
        """Should rollback on verification failure."""
        mock_execution.run_build.return_value = BuildResult(
            passed=False, message="Compilation error"
        )

        result = await applicator.apply(sample_fix, sample_error, approved_validation)

        assert not result.success
        assert "Verification failed" in result.error
        mock_git.delete_branch.assert_called()  # Rollback

    @pytest.mark.asyncio
    async def test_apply_creates_pr_in_cloud(
        self, applicator, sample_fix, sample_error, approved_validation
    ):
        """Should create PR in cloud environment."""
        with patch("src.healing.applicator.get_environment") as mock_env:
            from src.healing.environment import Environment
            mock_env.return_value = Environment.CLOUD

            result = await applicator.apply(sample_fix, sample_error, approved_validation)

        assert result.success
        assert result.pr_url is not None
        assert result.needs_pr_review

    @pytest.mark.asyncio
    async def test_apply_creates_pr_for_moderate(
        self, applicator, sample_error, approved_validation, mock_git
    ):
        """Should create PR for MODERATE fixes even locally."""
        action = FixAction(action_type="diff", diff="+x\n")
        fix = SuggestedFix(
            fix_id="fix-mod",
            title="Moderate fix",
            action=action,
            safety_category=SafetyCategory.MODERATE,
            affected_files=["src/utils.py"],
            lines_changed=1,
        )

        with patch("src.healing.applicator.get_environment") as mock_env:
            from src.healing.environment import Environment
            mock_env.return_value = Environment.LOCAL

            result = await applicator.apply(fix, sample_error, approved_validation)

        assert result.success
        assert result.pr_url is not None
        mock_git.create_pr.assert_called()

    @pytest.mark.asyncio
    async def test_apply_direct_merge_for_safe_local(
        self, applicator, sample_fix, sample_error, approved_validation, mock_git
    ):
        """Should merge directly for SAFE fixes in local environment."""
        with patch("src.healing.applicator.get_environment") as mock_env:
            from src.healing.environment import Environment
            mock_env.return_value = Environment.LOCAL

            result = await applicator.apply(sample_fix, sample_error, approved_validation)

        assert result.success
        assert result.pr_url is None
        mock_git.merge_branch.assert_called()
        mock_git.delete_branch.assert_called()

    @pytest.mark.asyncio
    async def test_apply_records_cascade(
        self, applicator, sample_fix, sample_error, approved_validation
    ):
        """Should record fix in cascade detector."""
        with patch("src.healing.applicator.get_environment") as mock_env:
            from src.healing.environment import Environment
            mock_env.return_value = Environment.LOCAL

            result = await applicator.apply(sample_fix, sample_error, approved_validation)

        assert result.success
        # Cascade detector should have the fix
        recent = applicator._cascade.get_recent_fixes()
        assert len(recent) == 1
        assert recent[0].fingerprint == "abc123"

    def test_build_pr_body(self, applicator, sample_fix, sample_error, approved_validation):
        """Should build PR body with details."""
        body = applicator._build_pr_body(sample_fix, sample_error, approved_validation)

        assert "Automated Fix" in body
        assert "ModuleNotFoundError" in body
        assert "Add import" in body
        assert "safe" in body.lower()
        assert "Validation:" in body
