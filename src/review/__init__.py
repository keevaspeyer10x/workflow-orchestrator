"""
Multi-Model Code Review Module

Orchestrates code reviews across multiple AI models (GPT-5.2 Max, Gemini, Grok, Codex)
with dynamic tier selection based on change complexity and risk.

Philosophy: More reviews are better. We gold-plate the review process because
catching issues early is much cheaper than fixing them later.

Usage:
    from src.review import review_changes, ChangeContext, ReviewTier

    # Quick review
    result = await review_changes(ChangeContext(
        files_changed=["src/auth.py"],
        diff_content="...",
        description="Add OAuth support",
    ))

    # Check tier without running review
    tier = get_review_tier(context)

    # Custom configuration
    config = ReviewConfig(
        bias="more_review",
        simple_change_max_files=3,
    )
    result = await review_changes(context, config)

Model Strengths (from empirical testing):
- GPT-5.2 Max: Best for security, correctness, actionability (primary)
- Gemini: Best for architecture, unique insights, concise (architectural)
- Grok 4.1: Best for breadth, operations, edge cases (comprehensive)
- Codex: Best for code correctness, performance (code-focused)
- Claude (self): Best for edge cases, UX, context (always included)

Tiers:
- MINIMAL: Self-review only (very small, low-risk changes)
- STANDARD: Self + GPT-5.2 Max (most changes)
- COMPREHENSIVE: Self + GPT-5.2 Max + Gemini + Codex (complex changes)
- CRITICAL: All models (security, API, migrations, conflict resolution)
"""

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

__all__ = [
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
]
