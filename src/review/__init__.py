"""
Multi-model Code Review System

This module provides automated code reviews using multiple AI models.
It supports two execution modes:"""

import logging

logger = logging.getLogger(__name__)

__doc__ += """

1. CLI Mode (PRIMARY - recommended):
   - Uses Codex CLI + Gemini CLI directly
   - Full repository access, best context understanding
   - Reviews: security, consistency, quality, holistic

2. API Mode (FALLBACK):
   - Uses LiteLLM to call GPT, Gemini, Grok, Codex APIs
   - Sends diff content in request (limited context)
   - Used when CLIs unavailable or for merge conflict resolution

Usage:
    # CLI-based reviews (general workflow)
    from src.review import ReviewRouter, ReviewMethod
    router = ReviewRouter()
    result = await router.run_review("security_review", context)

    # API-based reviews (merge conflicts, fallback)
    from src.review import ReviewOrchestrator, ChangeContext
    orchestrator = ReviewOrchestrator()
    result = await orchestrator.review(change_context)

    # Auto-select best method
    from src.review import run_review
    result = await run_review(context, prefer_cli=True)

Model Strengths (from empirical testing):
- Codex CLI: Best for security, code correctness, performance (CLI primary)
- Gemini CLI: Best for architecture, 1M context window (CLI primary)
- GPT-5.2 Max: Best for security, correctness, actionability (API fallback)
- Grok 4.1: Best for breadth, operations, edge cases (API fallback)

Model configuration: See .claude/review-config.yaml for canonical model settings.
"""

# =============================================================================
# CLI-Based Review System (PRIMARY)
# Full repo access, best context understanding
# =============================================================================
from .context import ReviewContext, ReviewContextCollector
from .router import ReviewRouter, ReviewMethod
from .result import ReviewResult, ReviewFinding, Severity
from .prompts import REVIEW_PROMPTS
from .setup import setup_reviews, check_review_setup, ReviewSetup
from .aider_executor import AiderExecutor
from .cli_executor import CLIExecutor
from .api_executor import APIExecutor

# =============================================================================
# Review Type Registry (ARCH-003)
# Single source of truth for review types
# =============================================================================
from .registry import (
    REVIEW_TYPES,
    ReviewTypeDefinition,
    get_review_item_mapping,
    get_all_review_types,
    get_review_type,
    get_model_for_review,
    get_workflow_item_ids,
    validate_review_configuration,
    get_configuration_status,
    ReviewConfigurationError,
)

# =============================================================================
# API-Based Orchestrator System (FALLBACK)
# Used when CLIs unavailable or for merge conflict resolution
# =============================================================================
from .schema import (
    # Enums
    ReviewTier,
    ReviewFocus,
    IssueSeverity,
    IssueCategory,
    ConfidenceLevel,
    # Configuration
    ModelSpec,
    TierConfig,
    CriticalPathConfig,
    ReviewConfig,
    # Input/Output
    ChangeContext,
    ReviewIssue,
    ModelReview,
    SynthesizedReview,
)

from .orchestrator import (
    ReviewOrchestrator,
    get_default_config,
    review_changes,
    get_review_tier,
)

from .models import (
    BaseReviewer,
    LiteLLMReviewer,
    SelfReviewer,
    ReviewerFactory,
)


# =============================================================================
# Unified Interface
# =============================================================================

async def run_review(
    context,
    review_type: str = "security_review",
    prefer_cli: bool = True,
    fallback_to_api: bool = True,
):
    """
    Run a review using the best available method.

    Args:
        context: Either ReviewContext (CLI) or ChangeContext (API)
        review_type: Type of review (security_review, quality_review, etc.)
        prefer_cli: Try CLI first if available
        fallback_to_api: Fall back to API if CLI unavailable

    Returns:
        ReviewResult (CLI) or SynthesizedReview (API)
    """
    if prefer_cli:
        # Try CLI-based review first
        try:
            router = ReviewRouter()
            if router.get_method() in [ReviewMethod.CLI, ReviewMethod.HYBRID]:
                return await router.run_review(review_type, context)
        except Exception as e:
            logger.warning(f"CLI review failed, attempting API fallback: {e}")
            if not fallback_to_api:
                raise

    # Fall back to API-based orchestrator
    if isinstance(context, ChangeContext):
        orchestrator = ReviewOrchestrator()
        return await orchestrator.review(context)
    else:
        # Convert ReviewContext to ChangeContext for API
        change_context = ChangeContext(
            files_changed=list(context.changed_files.keys()),
            diff_content=context.git_diff,
        )
        orchestrator = ReviewOrchestrator()
        return await orchestrator.review(change_context)


__all__ = [
    # ===================
    # CLI System (Primary)
    # ===================
    # Context
    "ReviewContext",
    "ReviewContextCollector",
    # Router
    "ReviewRouter",
    "ReviewMethod",
    # Results
    "ReviewResult",
    "ReviewFinding",
    "Severity",
    # Prompts
    "REVIEW_PROMPTS",
    # Setup
    "setup_reviews",
    "check_review_setup",
    "ReviewSetup",
    # Executors
    "AiderExecutor",
    "CLIExecutor",
    "APIExecutor",

    # =======================
    # API Orchestrator (Fallback)
    # =======================
    # Enums
    "ReviewTier",
    "ReviewFocus",
    "IssueSeverity",
    "IssueCategory",
    "ConfidenceLevel",
    # Configuration
    "ModelSpec",
    "TierConfig",
    "CriticalPathConfig",
    "ReviewConfig",
    "get_default_config",
    # Input/Output
    "ChangeContext",
    "ReviewIssue",
    "ModelReview",
    "SynthesizedReview",
    # Orchestrator
    "ReviewOrchestrator",
    "review_changes",
    "get_review_tier",
    # Models
    "BaseReviewer",
    "LiteLLMReviewer",
    "SelfReviewer",
    "ReviewerFactory",

    # =======================
    # Unified Interface
    # =======================
    "run_review",
]
