"""
Review Orchestrator

Coordinates multi-model code reviews with dynamic tier selection.
Biased toward more thorough reviews - gold-plating is encouraged.
"""

import asyncio
import fnmatch
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from .schema import (
    ReviewConfig,
    ReviewTier,
    TierConfig,
    ModelSpec,
    ReviewFocus,
    ChangeContext,
    ModelReview,
    SynthesizedReview,
    ReviewIssue,
    IssueSeverity,
    ConfidenceLevel,
)
from .models import ReviewerFactory, SelfReviewer

logger = logging.getLogger(__name__)


# ============================================================================
# Default Configuration (Gold-Plated)
# ============================================================================

def get_default_config() -> ReviewConfig:
    """
    Get default review configuration.

    This is intentionally gold-plated - we prefer more reviews over fewer.
    The cost of missing an issue is much higher than extra review time.
    """
    return ReviewConfig(
        self_review_enabled=True,
        self_review_focus=[
            ReviewFocus.EDGE_CASES,
            ReviewFocus.UX,
            ReviewFocus.COMPLETENESS,
        ],

        # Lower thresholds = more comprehensive reviews
        simple_change_max_files=2,       # Only very small changes are "simple"
        standard_change_max_files=10,    # Moderate changes get 2 reviewers
        comprehensive_change_max_files=20,  # Most changes get 3 reviewers

        bias="more_review",  # When uncertain, escalate

        tiers={
            # Minimal: Self-review only (very rare)
            ReviewTier.MINIMAL: TierConfig(
                conditions=[
                    "files_changed <= 2",
                    "no_security_files",
                    "no_api_changes",
                    "no_critical_paths",
                ],
                reviewers=[],
                require_consensus=False,
            ),

            # Standard: Self + GPT-5.2 Max
            ReviewTier.STANDARD: TierConfig(
                conditions=[
                    "files_changed <= 10",
                    "no_critical_paths",
                ],
                reviewers=[
                    ModelSpec(
                        provider="openai",
                        model_id="gpt-5.2-max",
                        focus=[ReviewFocus.SECURITY, ReviewFocus.CORRECTNESS],
                    ),
                ],
                require_consensus=False,
            ),

            # Comprehensive: Self + GPT-5.2 Max + Gemini + Codex
            ReviewTier.COMPREHENSIVE: TierConfig(
                conditions=[
                    "files_changed <= 20",
                    "OR complexity >= medium",
                ],
                reviewers=[
                    ModelSpec(
                        provider="openai",
                        model_id="gpt-5.2-max",
                        focus=[ReviewFocus.SECURITY, ReviewFocus.CORRECTNESS],
                    ),
                    ModelSpec(
                        provider="google",
                        model_id="gemini-2.5-pro",
                        focus=[ReviewFocus.ARCHITECTURE, ReviewFocus.DESIGN],
                    ),
                    ModelSpec(
                        provider="openai",
                        model_id="codex",
                        focus=[ReviewFocus.CORRECTNESS, ReviewFocus.PERFORMANCE],
                    ),
                ],
                require_consensus=True,
            ),

            # Critical: Self + GPT-5.2 Max + Gemini + Grok + Codex (ALL models)
            ReviewTier.CRITICAL: TierConfig(
                conditions=[
                    "files_changed > 20",
                    "OR touches_critical_paths",
                    "OR is_merge_conflict_resolution",
                    "OR is_security_related",
                    "OR touches_api_surface",
                ],
                reviewers=[
                    ModelSpec(
                        provider="openai",
                        model_id="gpt-5.2-max",
                        focus=[ReviewFocus.SECURITY, ReviewFocus.CORRECTNESS],
                    ),
                    ModelSpec(
                        provider="google",
                        model_id="gemini-2.5-pro",
                        focus=[ReviewFocus.ARCHITECTURE],
                    ),
                    ModelSpec(
                        provider="xai",
                        model_id="grok-4.1",
                        focus=[ReviewFocus.OPERATIONS, ReviewFocus.EDGE_CASES],
                    ),
                    ModelSpec(
                        provider="openai",
                        model_id="codex",
                        focus=[ReviewFocus.CORRECTNESS, ReviewFocus.PERFORMANCE],
                    ),
                ],
                require_consensus=True,
                min_confidence_to_proceed=0.8,
            ),
        },

        # Always escalate these paths to CRITICAL tier
        always_escalate_patterns=[
            "**/auth/**",
            "**/security/**",
            "**/*payment*",
            "**/*billing*",
            "**/migrations/**",
            ".github/workflows/**",
            "**/secrets/**",
            "**/*credential*",
            "**/api/**",  # API changes are important
            "**/core/**",  # Core modules
        ],
    )


# ============================================================================
# Review Orchestrator
# ============================================================================

class ReviewOrchestrator:
    """
    Orchestrate multi-model code reviews.

    Philosophy: More reviews are better. We gold-plate the review process
    because catching issues early is much cheaper than fixing them later.
    """

    def __init__(self, config: Optional[ReviewConfig] = None):
        self.config = config or get_default_config()

    def determine_tier(self, context: ChangeContext) -> ReviewTier:
        """
        Determine the appropriate review tier.

        With bias="more_review", we escalate when uncertain.
        """
        # Check critical paths first (auto-escalate)
        if self._touches_critical_paths(context):
            logger.info("Change touches critical paths - using CRITICAL tier")
            return ReviewTier.CRITICAL

        # Check explicit escalation triggers
        if context.is_merge_conflict_resolution:
            logger.info("Merge conflict resolution - using CRITICAL tier")
            return ReviewTier.CRITICAL

        if context.is_security_related:
            logger.info("Security-related change - using CRITICAL tier")
            return ReviewTier.CRITICAL

        if context.touches_api_surface:
            logger.info("API surface change - using COMPREHENSIVE tier minimum")
            # Will be escalated further if other conditions met

        # Determine by file count and complexity
        total_files = context.total_files

        if total_files <= self.config.simple_change_max_files:
            base_tier = ReviewTier.MINIMAL
        elif total_files <= self.config.standard_change_max_files:
            base_tier = ReviewTier.STANDARD
        elif total_files <= self.config.comprehensive_change_max_files:
            base_tier = ReviewTier.COMPREHENSIVE
        else:
            base_tier = ReviewTier.CRITICAL

        # Apply bias toward more review
        if self.config.bias == "more_review":
            base_tier = self._escalate_tier(base_tier)
            logger.info(f"Applied 'more_review' bias - escalated to {base_tier.value}")

        # If API changes, ensure at least COMPREHENSIVE
        if context.touches_api_surface and base_tier in [ReviewTier.MINIMAL, ReviewTier.STANDARD]:
            base_tier = ReviewTier.COMPREHENSIVE
            logger.info("API changes detected - escalated to COMPREHENSIVE")

        return base_tier

    def _touches_critical_paths(self, context: ChangeContext) -> bool:
        """Check if any changed files match critical path patterns."""
        all_files = context.files_changed + context.files_added + context.files_deleted

        for pattern in self.config.always_escalate_patterns:
            for file_path in all_files:
                if fnmatch.fnmatch(file_path, pattern):
                    logger.debug(f"File {file_path} matches critical pattern {pattern}")
                    return True

        return False

    def _escalate_tier(self, tier: ReviewTier) -> ReviewTier:
        """Escalate to the next tier (used for more_review bias)."""
        tier_order = [
            ReviewTier.MINIMAL,
            ReviewTier.STANDARD,
            ReviewTier.COMPREHENSIVE,
            ReviewTier.CRITICAL,
        ]
        current_idx = tier_order.index(tier)
        if current_idx < len(tier_order) - 1:
            return tier_order[current_idx + 1]
        return tier

    async def review(self, context: ChangeContext) -> SynthesizedReview:
        """
        Execute the full review process.

        1. Determine tier
        2. Self-review (always)
        3. External reviews (based on tier)
        4. Synthesize results
        """
        start_time = datetime.now(timezone.utc)
        tier = self.determine_tier(context)
        tier_config = self.config.tiers.get(tier, self.config.tiers[ReviewTier.COMPREHENSIVE])

        logger.info(f"Starting {tier.value} review with {len(tier_config.reviewers)} external reviewers")

        reviews: list[ModelReview] = []

        # 1. Self-review (always first)
        if self.config.self_review_enabled:
            self_reviewer = SelfReviewer()
            self_review = await self_reviewer.review(context)
            reviews.append(self_review)
            logger.info("Self-review completed")

        # 2. External reviews (in parallel for speed)
        if tier_config.reviewers:
            external_reviews = await self._run_external_reviews(
                context,
                tier_config.reviewers
            )
            reviews.extend(external_reviews)

        # 3. Synthesize results
        synthesized = self._synthesize(reviews, tier)

        synthesized.started_at = start_time
        synthesized.completed_at = datetime.now(timezone.utc)

        # Log summary
        logger.info(
            f"Review completed: {len(synthesized.issues)} issues found, "
            f"{len(synthesized.consensus_issues)} with consensus, "
            f"confidence={synthesized.overall_confidence:.2f}"
        )

        return synthesized

    async def _run_external_reviews(
        self,
        context: ChangeContext,
        model_specs: list[ModelSpec]
    ) -> list[ModelReview]:
        """Run external reviews in parallel."""
        tasks = []

        for spec in model_specs:
            reviewer = ReviewerFactory.create(spec)
            task = asyncio.create_task(
                self._run_single_review(reviewer, context, spec.full_id)
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        reviews = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Review failed for {model_specs[i].full_id}: {result}")
                # Create error review
                reviews.append(ModelReview(
                    model_id=model_specs[i].model_id,
                    model_provider=model_specs[i].provider,
                    focus=model_specs[i].focus,
                    error=str(result),
                    completed_at=datetime.now(timezone.utc),
                ))
            else:
                reviews.append(result)

        return reviews

    async def _run_single_review(
        self,
        reviewer,
        context: ChangeContext,
        model_id: str
    ) -> ModelReview:
        """Run a single review with logging."""
        logger.info(f"Starting review with {model_id}")
        try:
            review = await reviewer.review(context)
            logger.info(
                f"Review from {model_id} completed: "
                f"{len(review.issues)} issues, {review.latency_ms}ms"
            )
            return review
        except Exception as e:
            logger.error(f"Review failed for {model_id}: {e}")
            raise

    def _synthesize(
        self,
        reviews: list[ModelReview],
        tier: ReviewTier
    ) -> SynthesizedReview:
        """
        Synthesize multiple reviews into a unified result.

        - Deduplicate issues
        - Identify consensus (multiple reviewers agree)
        - Calculate overall confidence
        - Determine blocking issues
        """
        result = SynthesizedReview(
            tier_used=tier,
            models_used=[r.model_id for r in reviews if r.is_successful],
            individual_reviews=reviews,
        )

        # Collect all issues and group by similarity
        issue_groups: dict[str, list[ReviewIssue]] = defaultdict(list)

        for review in reviews:
            if not review.is_successful:
                continue

            for issue in review.issues:
                # Create similarity key (category + rough title match)
                key = self._issue_similarity_key(issue)
                issue_groups[key].append(issue)

            # Collect validated choices
            result.validated_choices.extend(review.validated_choices)

            # Collect tokens
            result.total_tokens_used += review.tokens_used
            result.total_latency_ms += review.latency_ms

        # Deduplicate and mark consensus
        for key, issues in issue_groups.items():
            # Take the most detailed issue as representative
            representative = max(issues, key=lambda i: len(i.description))

            # Update consensus info
            representative.consensus_count = len(issues)
            representative.found_by = list(set(
                model_id
                for issue in issues
                for model_id in issue.found_by
            ))

            # Set confidence based on consensus
            if len(issues) >= 3:
                representative.confidence = ConfidenceLevel.HIGH
            elif len(issues) >= 2:
                representative.confidence = ConfidenceLevel.MEDIUM
            else:
                representative.confidence = ConfidenceLevel.LOW

            result.issues.append(representative)

            # Track consensus vs unique
            if len(issues) >= 2:
                result.consensus_issues.append(representative)
            else:
                result.unique_issues.append(representative)

        # Sort issues by severity
        severity_order = {
            IssueSeverity.CRITICAL: 0,
            IssueSeverity.HIGH: 1,
            IssueSeverity.MEDIUM: 2,
            IssueSeverity.LOW: 3,
            IssueSeverity.INFO: 4,
        }
        result.issues.sort(key=lambda i: severity_order[i.severity])

        # Identify blocking issues
        result.blocking_issues = [
            i for i in result.issues
            if i.severity == IssueSeverity.CRITICAL
            or (i.severity == IssueSeverity.HIGH and i.consensus_count >= 2)
        ]

        # Calculate overall confidence
        successful_reviews = [r for r in reviews if r.is_successful]
        if successful_reviews:
            # Higher confidence with more reviewers and fewer errors
            base_confidence = len(successful_reviews) / len(reviews) if reviews else 0
            consensus_boost = len(result.consensus_issues) * 0.05
            result.overall_confidence = min(base_confidence + consensus_boost, 1.0)
        else:
            result.overall_confidence = 0.0

        # Determine if we should proceed
        result.proceed_recommended = (
            len(result.blocking_issues) == 0
            and result.overall_confidence >= 0.6
        )

        # Generate summary
        result.summary = self._generate_summary(result)

        return result

    def _issue_similarity_key(self, issue: ReviewIssue) -> str:
        """Generate a key for grouping similar issues."""
        # Normalize title for comparison
        title_words = set(issue.title.lower().split())
        # Use category + first few significant words
        significant_words = sorted(title_words - {"the", "a", "an", "in", "on", "at", "to"})[:3]
        return f"{issue.category.value}:{':'.join(significant_words)}"

    def _generate_summary(self, result: SynthesizedReview) -> str:
        """Generate a human-readable summary."""
        parts = []

        parts.append(f"Review completed using {result.tier_used.value} tier.")
        parts.append(f"Models: {', '.join(result.models_used)}")

        if result.issues:
            critical = len([i for i in result.issues if i.severity == IssueSeverity.CRITICAL])
            high = len([i for i in result.issues if i.severity == IssueSeverity.HIGH])
            parts.append(f"Found {len(result.issues)} issues ({critical} critical, {high} high).")
        else:
            parts.append("No issues found.")

        if result.consensus_issues:
            parts.append(f"{len(result.consensus_issues)} issues had multi-model consensus.")

        if result.blocking_issues:
            parts.append(f"BLOCKING: {len(result.blocking_issues)} issues must be addressed.")

        parts.append(f"Overall confidence: {result.overall_confidence:.0%}")

        if result.proceed_recommended:
            parts.append("Recommendation: PROCEED")
        else:
            parts.append("Recommendation: ADDRESS ISSUES FIRST")

        return " ".join(parts)


# ============================================================================
# Convenience Functions
# ============================================================================

async def review_changes(
    context: ChangeContext,
    config: Optional[ReviewConfig] = None
) -> SynthesizedReview:
    """
    Convenience function to review changes.

    Usage:
        result = await review_changes(ChangeContext(
            files_changed=["src/auth.py", "src/api.py"],
            diff_content="...",
            description="Add OAuth support",
        ))
    """
    orchestrator = ReviewOrchestrator(config)
    return await orchestrator.review(context)


def get_review_tier(context: ChangeContext, config: Optional[ReviewConfig] = None) -> ReviewTier:
    """
    Convenience function to determine review tier without running review.

    Useful for estimating cost/time before committing to full review.
    """
    orchestrator = ReviewOrchestrator(config)
    return orchestrator.determine_tier(context)
