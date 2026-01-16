"""Fix application logic.

This module applies validated fixes using environment-aware adapters.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING


def _utcnow() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)

from .adapters.base import (
    GitAdapter,
    StorageAdapter,
    ExecutionAdapter,
    TestResult,
    BuildResult,
)
from .cascade import get_cascade_detector, AppliedFix
from .context import ContextRetriever
from .environment import Environment, get_environment
from .judges import SuggestedFix
from .safety import SafetyCategory
from .validation import ValidationResult, ValidationPhase

if TYPE_CHECKING:
    from .models import ErrorEvent
    from .supabase_client import HealingSupabaseClient


logger = logging.getLogger(__name__)


@dataclass
class VerifyResult:
    """Result of verification after fix application."""

    passed: bool
    message: str
    build_result: Optional[BuildResult] = None
    test_result: Optional[TestResult] = None


@dataclass
class ApplyResult:
    """Result of applying a fix."""

    success: bool
    fix_id: str
    branch: Optional[str] = None
    pr_url: Optional[str] = None
    commit_sha: Optional[str] = None
    error: Optional[str] = None
    rollback_available: bool = False
    verification: Optional[VerifyResult] = None

    @property
    def needs_pr_review(self) -> bool:
        """Check if PR was created for review."""
        return self.pr_url is not None


class FixApplicator:
    """Apply fixes using environment-appropriate adapters.

    This class handles the full lifecycle of fix application:
    1. Create a branch
    2. Apply the fix (diff, command, or file edit)
    3. Verify the fix (build/test)
    4. Create PR or merge directly
    5. Record results

    Environment awareness:
    - LOCAL: Uses git CLI, can merge directly for SAFE fixes
    - CLOUD: Uses GitHub API, always creates PRs
    """

    def __init__(
        self,
        git: GitAdapter,
        storage: StorageAdapter,
        execution: ExecutionAdapter,
        supabase: Optional["HealingSupabaseClient"] = None,
        context_retriever: Optional[ContextRetriever] = None,
    ):
        """Initialize the fix applicator.

        Args:
            git: Git adapter for branch/commit operations
            storage: Storage adapter for file operations
            execution: Execution adapter for build/test
            supabase: Optional Supabase client for recording results
            context_retriever: Optional context retriever
        """
        self.git = git
        self.storage = storage
        self.execution = execution
        self.supabase = supabase
        self.context = context_retriever or ContextRetriever(storage)
        self._cascade = get_cascade_detector()

    async def apply(
        self,
        fix: SuggestedFix,
        error: "ErrorEvent",
        validation_result: ValidationResult,
    ) -> ApplyResult:
        """Apply fix and verify.

        Args:
            fix: The suggested fix to apply
            error: The original error
            validation_result: Result of validation (must be approved)

        Returns:
            ApplyResult with success status and details
        """
        if not validation_result.approved:
            return ApplyResult(
                success=False,
                fix_id=fix.fix_id,
                error="Validation not approved",
            )

        # Generate unique fix ID and branch name
        fix_id = fix.fix_id or self._generate_fix_id(error)
        branch = f"fix/auto-{fix_id}"

        try:
            # 1. Create branch
            logger.info(f"Creating branch: {branch}")
            await self.git.create_branch(branch)

            # 2. Apply the fix
            commit_sha = await self._apply_fix_action(fix, error)

            # 3. Run verification
            verify_result = await self._verify()

            if not verify_result.passed:
                # Rollback
                logger.warning(f"Verification failed: {verify_result.message}")
                await self._rollback(branch)
                await self._record_result(error.fingerprint, success=False)
                return ApplyResult(
                    success=False,
                    fix_id=fix_id,
                    error=f"Verification failed: {verify_result.message}",
                    verification=verify_result,
                )

            # 4. Create PR or merge directly
            result = await self._finalize(
                fix=fix,
                error=error,
                validation_result=validation_result,
                fix_id=fix_id,
                branch=branch,
                commit_sha=commit_sha,
                verify_result=verify_result,
            )

            # 5. Record success
            await self._record_result(error.fingerprint, success=True)

            # 6. Track for cascade detection
            self._cascade.record_fix(
                AppliedFix(
                    fix_id=fix_id,
                    fingerprint=error.fingerprint,
                    affected_files=fix.affected_files,
                    applied_at=_utcnow(),
                    commit_sha=commit_sha,
                )
            )

            return result

        except Exception as e:
            logger.error(f"Fix application failed: {e}")

            # Attempt cleanup
            await self._cleanup(branch)

            # Record failure
            await self._audit_log(
                "fix_failed",
                {
                    "fix_id": fix_id,
                    "fingerprint": error.fingerprint,
                    "error": str(e),
                },
            )

            return ApplyResult(
                success=False,
                fix_id=fix_id,
                error=str(e),
            )

    async def _apply_fix_action(
        self,
        fix: SuggestedFix,
        error: "ErrorEvent",
    ) -> str:
        """Apply the fix action and return commit SHA."""
        action = fix.action

        if action.action_type == "diff":
            # Apply diff directly
            return await self.git.apply_diff(
                action.diff or "",
                f"fix: {fix.title}",
            )

        elif action.action_type == "command":
            # Validate command is in allowlist
            if not self._is_command_allowed(action.command):
                raise ValueError(
                    f"Command not in allowlist: {action.command}. "
                    "Only safe package install commands are allowed."
                )

            # Run command
            exit_code, stdout, stderr = await self.execution.run_command(
                action.command
            )
            if exit_code != 0:
                raise RuntimeError(f"Command failed: {stderr}")

            # Commit any changes
            return await self.git.apply_diff(
                "",
                f"fix: ran `{action.command}`",
            )

        elif action.action_type == "file_edit":
            # Read file, apply edit, write back
            if not action.file_path:
                raise ValueError("file_edit action requires file_path")

            content = await self.storage.read_file(action.file_path)

            if action.find and action.replace is not None:
                # Only replace first occurrence to avoid unintended changes
                if content.count(action.find) > 1:
                    logger.warning(
                        f"Multiple occurrences of find string in {action.file_path}. "
                        "Only replacing first occurrence."
                    )
                new_content = content.replace(action.find, action.replace, 1)
            else:
                raise ValueError("file_edit requires find and replace")

            await self.storage.write_file(action.file_path, new_content)

            return await self.git.apply_diff(
                "",
                f"fix: edit {action.file_path}",
            )

        elif action.action_type == "multi_step":
            # Execute steps sequentially
            if not action.steps:
                raise ValueError("multi_step action requires steps")

            for i, step in enumerate(action.steps):
                # Create a sub-fix for each step
                from .models import FixAction

                step_action = FixAction.from_dict(step) if isinstance(step, dict) else step
                step_fix = SuggestedFix(
                    fix_id=f"{fix.fix_id}_step{i}",
                    title=f"Step {i+1}",
                    action=step_action,
                    safety_category=fix.safety_category,
                )
                await self._apply_fix_action(step_fix, error)

            return await self.git.apply_diff(
                "",
                f"fix: {fix.title} (multi-step)",
            )

        else:
            raise ValueError(f"Unknown action type: {action.action_type}")

    async def _verify(self) -> VerifyResult:
        """Run verification suite."""
        # Run build first
        build_result = await self.execution.run_build()
        if not build_result.passed:
            return VerifyResult(
                passed=False,
                message=f"Build failed: {build_result.message}",
                build_result=build_result,
            )

        # Run tests
        test_result = await self.execution.run_tests()
        if not test_result.passed:
            return VerifyResult(
                passed=False,
                message=f"Tests failed: {test_result.message}",
                build_result=build_result,
                test_result=test_result,
            )

        return VerifyResult(
            passed=True,
            message="All checks passed",
            build_result=build_result,
            test_result=test_result,
        )

    async def _finalize(
        self,
        fix: SuggestedFix,
        error: "ErrorEvent",
        validation_result: ValidationResult,
        fix_id: str,
        branch: str,
        commit_sha: str,
        verify_result: VerifyResult,
    ) -> ApplyResult:
        """Finalize the fix (PR or direct merge)."""
        environment = get_environment()

        # Determine if we should create a PR or merge directly
        should_create_pr = (
            environment == Environment.CLOUD
            or fix.safety_category != SafetyCategory.SAFE
        )

        if should_create_pr:
            # Create PR for review
            pr_body = self._build_pr_body(fix, error, validation_result)
            pr_url = await self.git.create_pr(
                title=f"fix: {fix.title}",
                body=pr_body,
                head=branch,
                base="main",
            )

            await self._audit_log(
                "pr_created",
                {
                    "fix_id": fix_id,
                    "fingerprint": error.fingerprint,
                    "pr_url": pr_url,
                },
            )

            return ApplyResult(
                success=True,
                fix_id=fix_id,
                branch=branch,
                pr_url=pr_url,
                commit_sha=commit_sha,
                rollback_available=True,
                verification=verify_result,
            )
        else:
            # Merge directly (local + SAFE)
            await self.git.merge_branch(branch, into="main")
            await self.git.delete_branch(branch)

            await self._audit_log(
                "fix_merged",
                {
                    "fix_id": fix_id,
                    "fingerprint": error.fingerprint,
                    "commit_sha": commit_sha,
                },
            )

            return ApplyResult(
                success=True,
                fix_id=fix_id,
                commit_sha=commit_sha,
                rollback_available=True,
                verification=verify_result,
            )

    async def rollback(self, fix_id: str) -> bool:
        """Rollback a previously applied fix.

        Args:
            fix_id: The fix ID to rollback

        Returns:
            True if rollback succeeded
        """
        # TODO: Implement rollback logic
        # This requires tracking what was changed and how to revert it
        logger.warning(f"Rollback not yet implemented for {fix_id}")
        return False

    async def _rollback(self, branch: str) -> None:
        """Rollback by deleting the branch."""
        try:
            await self.git.delete_branch(branch)
        except Exception as e:
            logger.warning(f"Failed to delete branch {branch}: {e}")

    async def _cleanup(self, branch: str) -> None:
        """Clean up after a failed fix attempt."""
        try:
            await self.git.delete_branch(branch)
        except Exception:
            pass  # Best effort cleanup

    async def _record_result(self, fingerprint: str, success: bool) -> None:
        """Record fix result in Supabase."""
        if self.supabase:
            try:
                await self.supabase.record_fix_result(fingerprint, success)
            except Exception as e:
                logger.warning(f"Failed to record result: {e}")

    async def _audit_log(self, action: str, details: dict) -> None:
        """Write to audit log."""
        if self.supabase:
            try:
                await self.supabase.audit_log(action, details)
            except Exception as e:
                logger.warning(f"Failed to write audit log: {e}")

    # Allowlisted command prefixes for command-type fixes
    ALLOWED_COMMANDS = [
        "pip install",
        "pip3 install",
        "npm install",
        "npm i",
        "yarn add",
        "pnpm add",
        "go get",
        "cargo add",
        "bundle install",
        "poetry add",
    ]

    def _is_command_allowed(self, command: str) -> bool:
        """Check if a command is in the allowlist.

        Only safe package install commands are allowed to prevent
        arbitrary command execution from malicious fix patterns.

        Args:
            command: The command to check

        Returns:
            True if command is allowed
        """
        if not command:
            return False

        cmd_lower = command.lower().strip()
        return any(cmd_lower.startswith(allowed) for allowed in self.ALLOWED_COMMANDS)

    def _generate_fix_id(self, error: "ErrorEvent") -> str:
        """Generate a unique fix ID."""
        fingerprint = error.fingerprint[:8] if error.fingerprint else "unknown"
        timestamp = _utcnow().strftime("%Y%m%d%H%M%S")
        return f"{fingerprint}-{timestamp}"

    def _build_pr_body(
        self,
        fix: SuggestedFix,
        error: "ErrorEvent",
        validation: ValidationResult,
    ) -> str:
        """Build PR body with fix details."""
        votes_summary = ""
        if validation.votes:
            for vote in validation.votes:
                status = "✅" if vote.approved else "❌"
                votes_summary += f"- {vote.model}: {status} ({vote.confidence:.0%}) - {vote.reasoning[:50]}...\n"
        else:
            votes_summary = "No votes recorded"

        return f"""## Automated Fix

**Error:** {error.description[:200]}

**Fix:** {fix.title}

**Safety Category:** {fix.safety_category.value}

**Affected Files:**
{chr(10).join(f"- {f}" for f in fix.affected_files) if fix.affected_files else "None specified"}

**Validation:**
- Pre-flight: ✅
- Verification: {validation.phase.value}
- Approval: {validation.reason}

**Judge Votes:**
{votes_summary}

---
*Generated by Self-Healing Infrastructure*
"""
