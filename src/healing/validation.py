"""Validation pipeline for fix approval.

This module provides the 3-phase validation pipeline for fixes.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, TYPE_CHECKING

from .adapters.base import ExecutionAdapter, TestResult, BuildResult, LintResult
from .cascade import CascadeDetector, get_cascade_detector
from .config import get_config
from .costs import CostTracker, get_cost_tracker
from .judges import JudgeVote, JudgeResult, MultiModelJudge, SuggestedFix
from .safety import SafetyCategory, SafetyCategorizer

if TYPE_CHECKING:
    from .models import ErrorEvent


logger = logging.getLogger(__name__)


class ValidationPhase(Enum):
    """Phases of the validation pipeline."""

    PRE_FLIGHT = "pre_flight"  # Fast parallel checks
    VERIFICATION = "verification"  # Build/test/lint
    APPROVAL = "approval"  # Multi-model judging


@dataclass
class VerificationOutput:
    """Output from verification phase."""

    build: Optional[BuildResult] = None
    test: Optional[TestResult] = None
    lint: Optional[LintResult] = None


@dataclass
class ValidationResult:
    """Result of the validation pipeline."""

    approved: bool
    phase: ValidationPhase
    reason: str
    votes: List[JudgeVote] = field(default_factory=list)
    verification_output: Optional[VerificationOutput] = None
    estimated_cost: float = 0.0

    @property
    def passed_preflight(self) -> bool:
        """Check if preflight checks passed."""
        return self.phase != ValidationPhase.PRE_FLIGHT or self.approved

    @property
    def passed_verification(self) -> bool:
        """Check if verification passed."""
        if self.phase == ValidationPhase.PRE_FLIGHT:
            return False
        if self.phase == ValidationPhase.VERIFICATION:
            return self.approved
        return True  # Got past verification

    @property
    def passed_approval(self) -> bool:
        """Check if approval passed."""
        return self.phase == ValidationPhase.APPROVAL and self.approved


class ValidationPipeline:
    """3-phase validation pipeline for fixes.

    The pipeline runs three phases:
    1. PRE_FLIGHT: Fast parallel checks (kill switch, constraints, precedent, cascade)
    2. VERIFICATION: Parallel build/test/lint
    3. APPROVAL: Multi-model judging (tiered by safety)

    Each phase can short-circuit the pipeline if validation fails.
    """

    def __init__(
        self,
        config=None,
        judge: Optional[MultiModelJudge] = None,
        execution: Optional[ExecutionAdapter] = None,
        cascade_detector: Optional[CascadeDetector] = None,
        cost_tracker: Optional[CostTracker] = None,
        safety_categorizer: Optional[SafetyCategorizer] = None,
    ):
        """Initialize the validation pipeline.

        Args:
            config: Optional config override
            judge: Multi-model judge (created if not provided)
            execution: Execution adapter for build/test/lint
            cascade_detector: Cascade detector (uses global if not provided)
            cost_tracker: Cost tracker (uses global if not provided)
            safety_categorizer: Safety categorizer (created if not provided)
        """
        self._config = config
        self.judge = judge or MultiModelJudge()
        self.execution = execution
        self.cascade = cascade_detector or get_cascade_detector()
        self.costs = cost_tracker or get_cost_tracker()
        self.safety = safety_categorizer or SafetyCategorizer()

    @property
    def config(self):
        """Get configuration (lazy load)."""
        if self._config is None:
            self._config = get_config()
        return self._config

    async def validate(
        self,
        fix: SuggestedFix,
        error: "ErrorEvent",
        skip_verification: bool = False,
    ) -> ValidationResult:
        """Run all validation phases.

        Args:
            fix: The suggested fix to validate
            error: The original error
            skip_verification: Skip build/test/lint (for testing)

        Returns:
            ValidationResult with approval status and details
        """
        # PHASE 1: Pre-flight (parallel fast checks)
        preflight = await self._run_preflight(fix, error)
        if not preflight.approved:
            return preflight

        # PHASE 2: Verification (parallel build/test/lint)
        if not skip_verification and self.execution:
            verification = await self._run_verification(fix)
            if not verification.approved:
                return verification
        else:
            verification = None

        # PHASE 3: Approval (tiered multi-model)
        approval = await self._run_approval(fix, error)

        # Include verification output if available
        if verification:
            approval.verification_output = verification.verification_output

        return approval

    async def _run_preflight(
        self,
        fix: SuggestedFix,
        error: "ErrorEvent",
    ) -> ValidationResult:
        """Phase 1: Fast parallel checks."""
        # Run all checks in parallel
        checks = await asyncio.gather(
            self._check_kill_switch(),
            self._check_hard_constraints(fix),
            self._check_precedent(fix),
            self._check_cascade(error),
            self._check_cost_budget(fix.safety_category),
            return_exceptions=True,
        )

        check_names = [
            "kill_switch",
            "hard_constraints",
            "precedent",
            "cascade",
            "cost_budget",
        ]

        # Process results
        for name, result in zip(check_names, checks):
            if isinstance(result, Exception):
                logger.error(f"Preflight check {name} failed with exception: {result}")
                return ValidationResult(
                    approved=False,
                    phase=ValidationPhase.PRE_FLIGHT,
                    reason=f"Check '{name}' failed with error: {result}",
                )

            passed, reason = result
            if not passed:
                return ValidationResult(
                    approved=False,
                    phase=ValidationPhase.PRE_FLIGHT,
                    reason=f"[{name}] {reason}",
                )

        return ValidationResult(
            approved=True,
            phase=ValidationPhase.PRE_FLIGHT,
            reason="All pre-flight checks passed",
        )

    async def _run_verification(self, fix: SuggestedFix) -> ValidationResult:
        """Phase 2: Parallel build/test/lint."""
        if not self.execution:
            return ValidationResult(
                approved=True,
                phase=ValidationPhase.VERIFICATION,
                reason="No execution adapter configured (skipped)",
            )

        # Run all verifications in parallel
        results = await asyncio.gather(
            self._run_build_check(),
            self._run_test_check(),
            self._run_lint_check(),
            return_exceptions=True,
        )

        output = VerificationOutput()
        check_names = ["build", "test", "lint"]

        for name, result in zip(check_names, results):
            if isinstance(result, Exception):
                logger.error(f"Verification {name} failed with exception: {result}")
                return ValidationResult(
                    approved=False,
                    phase=ValidationPhase.VERIFICATION,
                    reason=f"{name} failed with error: {result}",
                    verification_output=output,
                )

            # Store the result
            if name == "build":
                output.build = result
            elif name == "test":
                output.test = result
            elif name == "lint":
                output.lint = result

            if not result.passed:
                return ValidationResult(
                    approved=False,
                    phase=ValidationPhase.VERIFICATION,
                    reason=f"{name} failed: {result.message}",
                    verification_output=output,
                )

        return ValidationResult(
            approved=True,
            phase=ValidationPhase.VERIFICATION,
            reason="All verification checks passed",
            verification_output=output,
        )

    async def _run_approval(
        self,
        fix: SuggestedFix,
        error: "ErrorEvent",
    ) -> ValidationResult:
        """Phase 3: Multi-model approval."""
        # RISKY never auto-applies
        if fix.safety_category == SafetyCategory.RISKY:
            return ValidationResult(
                approved=False,
                phase=ValidationPhase.APPROVAL,
                reason="RISKY category - requires human review",
            )

        # Get multi-model votes
        judge_result = await self.judge.judge(fix, error, fix.safety_category)

        # Record cost - map model names to cost tracker keys
        MODEL_TO_COST_KEY = {
            "claude-opus-4-5": "judge_claude",
            "gemini-3-pro": "judge_gemini",
            "gpt-5.2": "judge_gpt",
            "grok-4.1": "judge_grok",
        }
        for vote in judge_result.votes:
            if vote.error is None:
                cost_key = MODEL_TO_COST_KEY.get(vote.model, f"judge_{vote.model.split('-')[0]}")
                self.costs.record(cost_key)

        approval_status = f"{judge_result.approval_count}/{len(judge_result.votes)} judges approved"

        return ValidationResult(
            approved=judge_result.approved,
            phase=ValidationPhase.APPROVAL,
            reason=approval_status,
            votes=judge_result.votes,
            estimated_cost=self.costs.estimate_cost(fix.safety_category),
        )

    # Pre-flight check implementations

    async def _check_kill_switch(self) -> tuple[bool, str]:
        """Check if kill switch is active."""
        if self.config.kill_switch_active:
            return False, "Kill switch is active"
        return True, "OK"

    async def _check_hard_constraints(self, fix: SuggestedFix) -> tuple[bool, str]:
        """Check hard constraints on fix scope."""
        # Max files affected
        if len(fix.affected_files) > 2:
            return False, f"Too many files affected ({len(fix.affected_files)} > 2)"

        # Max lines changed
        if fix.lines_changed > 30:
            return False, f"Too many lines changed ({fix.lines_changed} > 30)"

        return True, "OK"

    async def _check_precedent(self, fix: SuggestedFix) -> tuple[bool, str]:
        """Check if fix has established precedent."""
        pattern = fix.pattern
        if not pattern:
            return False, "No pattern found"

        # Pre-seeded patterns are trusted
        if pattern.get("is_preseeded"):
            return True, "Pre-seeded pattern"

        # Verified applies (AI precedent)
        if pattern.get("verified_apply_count", 0) >= 5:
            return True, "Verified AI precedent (5+ applies)"

        # Human corrections (human precedent)
        if pattern.get("human_correction_count", 0) >= 1:
            return True, "Human precedent established"

        return False, "No precedent established (needs 5+ verified applies or 1+ human corrections)"

    async def _check_cascade(self, error: "ErrorEvent") -> tuple[bool, str]:
        """Check for cascade/hot file detection."""
        if error.file_path and self.cascade.is_file_hot(error.file_path):
            return False, f"File {error.file_path} is hot (modified {self.cascade.max_mods_per_hour}+ times/hour)"
        return True, "OK"

    async def _check_cost_budget(self, safety: SafetyCategory) -> tuple[bool, str]:
        """Check if we have budget for this validation."""
        return self.costs.can_validate(safety)

    # Verification implementations

    async def _run_build_check(self) -> BuildResult:
        """Run build verification."""
        try:
            return await self.execution.run_build(
                timeout_seconds=self.config.build_timeout_seconds
            )
        except asyncio.TimeoutError:
            return BuildResult(
                passed=False,
                message=f"Build timed out after {self.config.build_timeout_seconds}s",
            )

    async def _run_test_check(self) -> TestResult:
        """Run test verification."""
        try:
            return await self.execution.run_tests(
                timeout_seconds=self.config.test_timeout_seconds
            )
        except asyncio.TimeoutError:
            return TestResult(
                passed=False,
                message=f"Tests timed out after {self.config.test_timeout_seconds}s",
            )

    async def _run_lint_check(self) -> LintResult:
        """Run lint verification."""
        try:
            return await self.execution.run_lint(
                timeout_seconds=self.config.lint_timeout_seconds
            )
        except asyncio.TimeoutError:
            return LintResult(
                passed=False,
                message=f"Lint timed out after {self.config.lint_timeout_seconds}s",
            )


async def validate_fix(
    fix: SuggestedFix,
    error: "ErrorEvent",
    execution: Optional[ExecutionAdapter] = None,
    skip_verification: bool = False,
) -> ValidationResult:
    """Convenience function to validate a fix.

    Args:
        fix: The suggested fix
        error: The original error
        execution: Optional execution adapter
        skip_verification: Skip build/test/lint

    Returns:
        ValidationResult
    """
    pipeline = ValidationPipeline(execution=execution)
    return await pipeline.validate(fix, error, skip_verification=skip_verification)
