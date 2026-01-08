"""
Review Schema Definitions using Pydantic

Defines the structure for multi-model code review configuration and results.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal, Any
from datetime import datetime, timezone
from enum import Enum


class ReviewTier(str, Enum):
    """Review intensity tiers based on change complexity/risk."""
    MINIMAL = "minimal"      # Self-review only
    STANDARD = "standard"    # Self + 1 external
    COMPREHENSIVE = "comprehensive"  # Self + 2 externals
    CRITICAL = "critical"    # Self + 3+ externals (gold-plated)


class ReviewFocus(str, Enum):
    """Focus areas for reviewers."""
    SECURITY = "security"
    ARCHITECTURE = "architecture"
    DESIGN = "design"
    CORRECTNESS = "correctness"
    EDGE_CASES = "edge_cases"
    OPERATIONS = "operations"
    PERFORMANCE = "performance"
    UX = "ux"
    COMPLETENESS = "completeness"


class IssueSeverity(str, Enum):
    """Severity of identified issues."""
    CRITICAL = "critical"    # Must fix before merge
    HIGH = "high"            # Should fix before merge
    MEDIUM = "medium"        # Consider fixing
    LOW = "low"              # Nice to have
    INFO = "info"            # Informational only


class IssueCategory(str, Enum):
    """Categories of issues."""
    SECURITY = "security"
    BUG = "bug"
    DESIGN = "design"
    PERFORMANCE = "performance"
    MAINTAINABILITY = "maintainability"
    EDGE_CASE = "edge_case"
    MISSING = "missing"
    SUGGESTION = "suggestion"


class ConfidenceLevel(str, Enum):
    """Confidence in findings."""
    HIGH = "high"        # Multiple reviewers agreed or strong evidence
    MEDIUM = "medium"    # Single reviewer or moderate evidence
    LOW = "low"          # Speculative or uncertain


# ============================================================================
# Model Configuration
# ============================================================================

class ModelSpec(BaseModel):
    """Specification for a review model."""
    provider: str  # openai, google, xai, anthropic
    model_id: str  # gpt-5.2-max, gemini-2.5-pro, grok-4.1, etc.
    focus: list[ReviewFocus] = Field(default_factory=list)
    temperature: float = 0.3  # Lower for more consistent reviews
    max_tokens: int = 4000

    @property
    def full_id(self) -> str:
        """Return provider/model_id format."""
        return f"{self.provider}/{self.model_id}"


class TierConfig(BaseModel):
    """Configuration for a review tier."""
    conditions: list[str] = Field(default_factory=list)
    reviewers: list[ModelSpec] = Field(default_factory=list)
    require_consensus: bool = False  # Require agreement on critical issues
    min_confidence_to_proceed: float = 0.7


class CriticalPathConfig(BaseModel):
    """Paths that auto-escalate to higher tiers."""
    patterns: list[str] = Field(default_factory=list)
    escalate_to: ReviewTier = ReviewTier.CRITICAL


class ReviewConfig(BaseModel):
    """Complete review orchestration configuration."""

    # Self-review settings
    self_review_enabled: bool = True
    self_review_focus: list[ReviewFocus] = Field(
        default_factory=lambda: [
            ReviewFocus.EDGE_CASES,
            ReviewFocus.UX,
            ReviewFocus.COMPLETENESS
        ]
    )

    # Tier configurations
    tiers: dict[ReviewTier, TierConfig] = Field(default_factory=dict)

    # Critical paths that auto-escalate
    critical_paths: list[CriticalPathConfig] = Field(default_factory=list)

    # Bias setting
    bias: Literal["more_review", "balanced", "less_review"] = "more_review"

    # Thresholds
    simple_change_max_files: int = 3
    standard_change_max_files: int = 15
    comprehensive_change_max_files: int = 30

    # Always escalate these
    always_escalate_patterns: list[str] = Field(
        default_factory=lambda: [
            "**/auth/**",
            "**/security/**",
            "**/*payment*",
            "**/*billing*",
            "**/migrations/**",
            ".github/workflows/**",
        ]
    )


# ============================================================================
# Review Input/Output
# ============================================================================

class ChangeContext(BaseModel):
    """Context about the change being reviewed."""
    # Files changed
    files_changed: list[str] = Field(default_factory=list)
    files_added: list[str] = Field(default_factory=list)
    files_deleted: list[str] = Field(default_factory=list)

    # Diff content
    diff_content: str = ""
    diff_stats: dict[str, int] = Field(default_factory=dict)  # insertions, deletions

    # Context
    description: Optional[str] = None
    commit_messages: list[str] = Field(default_factory=list)
    branch_name: Optional[str] = None
    base_branch: str = "main"

    # Metadata
    is_merge_conflict_resolution: bool = False
    is_auto_generated: bool = False
    touches_api_surface: bool = False

    # Calculated
    @property
    def total_files(self) -> int:
        return len(set(self.files_changed + self.files_added + self.files_deleted))

    @property
    def is_security_related(self) -> bool:
        security_patterns = ["auth", "security", "password", "token", "secret", "crypt"]
        all_files = " ".join(self.files_changed + self.files_added).lower()
        return any(p in all_files for p in security_patterns)


class ReviewIssue(BaseModel):
    """A single issue identified during review."""
    id: str = Field(default_factory=lambda: f"issue-{datetime.now().timestamp()}")
    severity: IssueSeverity
    category: IssueCategory
    title: str
    description: str

    # Location
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None

    # Recommendation
    recommendation: Optional[str] = None
    code_suggestion: Optional[str] = None

    # Confidence
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    consensus_count: int = 1  # How many reviewers flagged this

    # Source
    found_by: list[str] = Field(default_factory=list)  # Model IDs that found this

    def __hash__(self):
        """Hash for deduplication."""
        return hash((self.category, self.title, self.file_path))


class ModelReview(BaseModel):
    """Review output from a single model."""
    model_id: str
    model_provider: str
    focus: list[ReviewFocus]

    # Results
    issues: list[ReviewIssue] = Field(default_factory=list)
    summary: str = ""

    # Validation
    validated_choices: list[str] = Field(default_factory=list)  # Things the model approved

    # Metadata
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    tokens_used: int = 0
    latency_ms: int = 0
    error: Optional[str] = None

    @property
    def is_successful(self) -> bool:
        return self.error is None and self.completed_at is not None


class SynthesizedReview(BaseModel):
    """Combined review from all models."""
    tier_used: ReviewTier
    models_used: list[str] = Field(default_factory=list)

    # Synthesized issues (deduplicated, with consensus info)
    issues: list[ReviewIssue] = Field(default_factory=list)

    # Summary
    summary: str = ""
    overall_confidence: float = 0.0

    # Consensus analysis
    consensus_issues: list[ReviewIssue] = Field(default_factory=list)  # 2+ models agreed
    unique_issues: list[ReviewIssue] = Field(default_factory=list)    # Only 1 model found

    # Validation
    validated_choices: list[str] = Field(default_factory=list)

    # Recommendation
    proceed_recommended: bool = True
    blocking_issues: list[ReviewIssue] = Field(default_factory=list)

    # Individual reviews (for audit)
    individual_reviews: list[ModelReview] = Field(default_factory=list)

    # Metadata
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    total_tokens_used: int = 0
    total_latency_ms: int = 0

    @property
    def critical_issues(self) -> list[ReviewIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.CRITICAL]

    @property
    def high_issues(self) -> list[ReviewIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.HIGH]
