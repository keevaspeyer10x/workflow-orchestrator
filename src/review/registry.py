"""
Review Type Registry - Single Source of Truth

This module defines all review types in one place. All other modules
(cli.py, router.py, workflow.yaml) should reference these definitions
to prevent silent misconfigurations where reviews don't run.

ARCH-003: If you add a new review type, add it HERE and it will be
available everywhere. Validation at startup ensures sync.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ReviewTypeDefinition:
    """Definition of a review type."""
    name: str  # Short name: "security", "quality", etc.
    workflow_item_id: str  # Workflow item ID: "security_review", etc.
    model: str  # Model category: "codex", "gemini", "grok"
    description: str  # Human-readable description
    prompt_key: Optional[str] = None  # Key in REVIEW_PROMPTS (defaults to name)

    def __post_init__(self):
        # Default prompt_key to name if not specified
        if self.prompt_key is None:
            object.__setattr__(self, 'prompt_key', self.name)


# =============================================================================
# CANONICAL REVIEW TYPE DEFINITIONS
# =============================================================================
# Add new review types here. They will automatically be available in:
# - REVIEW_ITEM_MAPPING (cli.py)
# - execute_all_reviews() (router.py)
# - Validation checks
# =============================================================================

REVIEW_TYPES = {
    "security": ReviewTypeDefinition(
        name="security",
        workflow_item_id="security_review",
        model="codex",
        description="OWASP Top 10, injection attacks, auth issues, SSRF, hardcoded secrets",
    ),
    "quality": ReviewTypeDefinition(
        name="quality",
        workflow_item_id="quality_review",
        model="codex",
        description="Code smells, edge cases, error handling, test coverage gaps",
    ),
    "consistency": ReviewTypeDefinition(
        name="consistency",
        workflow_item_id="consistency_review",
        model="gemini",
        description="Codebase patterns, existing utilities, conventions",
    ),
    "holistic": ReviewTypeDefinition(
        name="holistic",
        workflow_item_id="holistic_review",
        model="gemini",
        description="Senior engineer perspective, PR approval, concerns",
    ),
    "vibe_coding": ReviewTypeDefinition(
        name="vibe_coding",
        workflow_item_id="vibe_coding_review",
        model="grok",
        description="AI-specific issues: hallucinated APIs, cargo cult code, tests that don't test",
    ),
}

# Legacy mapping for backwards compatibility
LEGACY_ITEM_MAPPINGS = {
    "architecture_review": "holistic",  # Old name -> new review type
}


# =============================================================================
# DERIVED DATA STRUCTURES
# =============================================================================
# These are computed from REVIEW_TYPES to ensure consistency

def get_review_item_mapping() -> dict[str, str]:
    """
    Get mapping from workflow item IDs to review type names.

    Used by cli.py to trigger auto-reviews when items are completed.

    Returns:
        Dict mapping item_id -> review_type_name
        e.g., {"security_review": "security", ...}
    """
    mapping = {}

    # Add canonical mappings
    for review_type in REVIEW_TYPES.values():
        mapping[review_type.workflow_item_id] = review_type.name

    # Add legacy mappings for backwards compatibility
    mapping.update(LEGACY_ITEM_MAPPINGS)

    return mapping


def get_all_review_types() -> list[str]:
    """
    Get list of all review type names.

    Used by router.py for execute_all_reviews().

    Returns:
        List of review type names: ["security", "quality", ...]
    """
    return list(REVIEW_TYPES.keys())


def get_review_type(name: str) -> Optional[ReviewTypeDefinition]:
    """
    Get a review type definition by name.

    Args:
        name: Review type name (e.g., "security", "quality")

    Returns:
        ReviewTypeDefinition or None if not found
    """
    return REVIEW_TYPES.get(name)


def get_model_for_review(review_type: str) -> str:
    """
    Get the model category for a review type.

    Args:
        review_type: Review type name

    Returns:
        Model category ("codex", "gemini", "grok") or "gemini" as default
    """
    defn = REVIEW_TYPES.get(review_type)
    if defn:
        return defn.model
    return "gemini"  # Safe default


def get_workflow_item_ids() -> list[str]:
    """
    Get list of all workflow item IDs for reviews.

    Returns:
        List of workflow item IDs: ["security_review", "quality_review", ...]
    """
    return [rt.workflow_item_id for rt in REVIEW_TYPES.values()]


# =============================================================================
# VALIDATION
# =============================================================================

class ReviewConfigurationError(Exception):
    """Raised when review configuration is inconsistent."""
    pass


def validate_review_configuration(
    workflow_review_items: Optional[list[str]] = None,
    raise_on_error: bool = True
) -> list[str]:
    """
    Validate that review configuration is consistent across all locations.

    This function should be called at orchestrator startup to catch
    misconfigurations early.

    Args:
        workflow_review_items: List of review item IDs from workflow.yaml's
                              REVIEW phase. If None, skips workflow validation.
        raise_on_error: If True, raises ReviewConfigurationError on mismatch.
                       If False, returns list of error messages.

    Returns:
        List of error messages (empty if valid)

    Raises:
        ReviewConfigurationError: If configuration is invalid and raise_on_error=True
    """
    errors = []

    # Get canonical data
    canonical_types = set(REVIEW_TYPES.keys())
    canonical_items = set(get_workflow_item_ids())

    # Validate workflow items if provided
    if workflow_review_items is not None:
        workflow_items_set = set(workflow_review_items)

        # Check for missing items in workflow
        missing_from_workflow = canonical_items - workflow_items_set
        if missing_from_workflow:
            # Filter out items that might be optional or have different names
            # Only report if significantly out of sync
            errors.append(
                f"Review items missing from workflow.yaml REVIEW phase: {missing_from_workflow}. "
                f"These reviews will not run automatically."
            )

        # Check for unknown items in workflow
        # (excluding legacy mappings and collect_review_results)
        known_items = canonical_items | set(LEGACY_ITEM_MAPPINGS.keys()) | {"collect_review_results"}
        unknown_in_workflow = workflow_items_set - known_items
        if unknown_in_workflow:
            errors.append(
                f"Unknown review items in workflow.yaml: {unknown_in_workflow}. "
                f"These will not trigger auto-reviews."
            )

    # Validate that REVIEW_PROMPTS has all types (import check)
    try:
        from .prompts import REVIEW_PROMPTS
        prompt_types = set()
        for key in REVIEW_PROMPTS.keys():
            # Normalize: remove _review suffix if present
            normalized = key.replace("_review", "")
            prompt_types.add(normalized)

        missing_prompts = canonical_types - prompt_types
        if missing_prompts:
            errors.append(
                f"Review types missing from REVIEW_PROMPTS: {missing_prompts}. "
                f"These reviews will use fallback prompts."
            )
    except ImportError:
        pass  # Prompts module not available, skip this check

    if errors and raise_on_error:
        raise ReviewConfigurationError("\n".join(errors))

    return errors


def get_configuration_status() -> dict:
    """
    Get a status report of review configuration.

    Returns:
        Dict with configuration status for debugging/display
    """
    return {
        "review_types": list(REVIEW_TYPES.keys()),
        "workflow_item_ids": get_workflow_item_ids(),
        "item_mapping": get_review_item_mapping(),
        "legacy_mappings": LEGACY_ITEM_MAPPINGS,
        "models": {name: defn.model for name, defn in REVIEW_TYPES.items()},
    }
