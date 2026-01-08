"""
Review configuration module - Single Source of Truth for review types.

This module reads review type configuration from workflow.yaml settings
and provides functions to access review configuration.

The workflow.yaml settings.reviews.types section is the authoritative
source for which tool handles each review type.

Example configuration in workflow.yaml:
    settings:
      reviews:
        enabled: true
        types:
          security_review: codex
          quality_review: codex
          consistency_review: gemini
          holistic_review: gemini
          vibe_coding_review: grok
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ReviewConfigError(Exception):
    """Error in review configuration."""

    pass


# Valid tools that can be assigned to review types
VALID_TOOLS = {"codex", "gemini", "grok"}

# Default review type -> tool mappings (used when workflow.yaml doesn't specify)
DEFAULT_REVIEW_TYPES = {
    "security_review": "codex",
    "quality_review": "codex",
    "consistency_review": "gemini",
    "holistic_review": "gemini",
    "vibe_coding_review": "grok",
}

# Short name aliases (e.g., "security" -> "security_review")
SHORT_NAME_ALIASES = {
    "security": "security_review",
    "quality": "quality_review",
    "consistency": "consistency_review",
    "holistic": "holistic_review",
    "vibe_coding": "vibe_coding_review",
    "vibe": "vibe_coding_review",
}


class ReviewTypeConfig:
    """
    Configuration for review type -> tool mappings.

    Reads review type configuration from workflow settings and provides
    methods to query which tool handles each review type.

    Note: This is separate from ReviewConfig in schema.py which handles
    review orchestration settings (tiers, critical paths, etc.)
    """

    def __init__(self, settings: dict):
        """
        Initialize review configuration from workflow settings.

        Args:
            settings: The 'settings' dict from WorkflowDef

        Raises:
            ReviewConfigError: If configuration is invalid
        """
        self._settings = settings
        self._reviews_config = settings.get("reviews", {})
        self._types = self._load_types()
        self._validation_warnings: list[str] = []
        self._validate()

    def _load_types(self) -> dict[str, str]:
        """Load review types from settings or use defaults."""
        types = self._reviews_config.get("types", {})

        if not types:
            # Use defaults if not specified
            return DEFAULT_REVIEW_TYPES.copy()

        return types

    def _validate(self) -> None:
        """Validate the configuration."""
        # Check that all tools are valid
        for review_type, tool in self._types.items():
            if tool not in VALID_TOOLS:
                raise ReviewConfigError(
                    f"Invalid tool '{tool}' for review type '{review_type}'. "
                    f"Valid tools are: {', '.join(sorted(VALID_TOOLS))}"
                )

        # Check that review types have corresponding prompts (warning only)
        try:
            from .prompts import REVIEW_PROMPTS

            for review_type in self._types:
                # Check both full name and short name
                short_name = review_type.replace("_review", "")
                if review_type not in REVIEW_PROMPTS and short_name not in REVIEW_PROMPTS:
                    self._validation_warnings.append(
                        f"Review type '{review_type}' has no corresponding prompt template"
                    )
                    logger.warning(
                        f"Review type '{review_type}' configured but no prompt template found"
                    )
        except ImportError:
            # Prompts module not available during early initialization
            pass

    def is_enabled(self) -> bool:
        """Check if reviews are enabled."""
        return self._reviews_config.get("enabled", True)

    def get_tool(self, review_type: str) -> str:
        """
        Get the tool for a review type.

        Args:
            review_type: The review type (e.g., "security_review" or "security")

        Returns:
            Tool name (codex, gemini, or grok)
        """
        # Normalize the review type (handle short names)
        normalized = self._normalize_type(review_type)

        # Look up in configured types
        if normalized in self._types:
            return self._types[normalized]

        # Fall back to defaults if type not configured
        if normalized in DEFAULT_REVIEW_TYPES:
            return DEFAULT_REVIEW_TYPES[normalized]

        # Unknown type - use gemini as default
        logger.debug(f"Unknown review type '{review_type}', using gemini as default")
        return "gemini"

    def _normalize_type(self, review_type: str) -> str:
        """Normalize review type to full name."""
        # Check if it's a short alias
        if review_type in SHORT_NAME_ALIASES:
            return SHORT_NAME_ALIASES[review_type]

        # Already a full name or unknown
        return review_type

    def get_available_types(self) -> list[str]:
        """Get list of available review types."""
        return list(self._types.keys())

    def get_validation_warnings(self) -> list[str]:
        """Get any validation warnings."""
        return self._validation_warnings.copy()


# Module-level cache for the config
_cached_config: Optional[ReviewTypeConfig] = None
_cached_settings: Optional[dict] = None


def clear_config_cache() -> None:
    """Clear the cached configuration (for testing)."""
    global _cached_config, _cached_settings
    _cached_config = None
    _cached_settings = None


def get_review_config(settings: Optional[dict] = None) -> ReviewTypeConfig:
    """
    Get the review configuration.

    If settings are not provided, attempts to load from the current
    workflow. Uses cached config if available and settings haven't changed.

    Args:
        settings: Optional settings dict to use

    Returns:
        ReviewConfig instance
    """
    global _cached_config, _cached_settings

    # Use provided settings or try to load from workflow
    if settings is None:
        settings = _load_workflow_settings()

    # Check cache
    if _cached_config is not None and _cached_settings == settings:
        return _cached_config

    # Create new config
    _cached_config = ReviewTypeConfig(settings)
    _cached_settings = settings
    return _cached_config


def _load_workflow_settings() -> dict:
    """
    Load settings from the workflow.yaml file.

    Searches for workflow.yaml in:
    1. Current working directory
    2. Parent directories up to 5 levels

    Returns:
        Settings dict from workflow.yaml, or empty dict if not found
    """
    import yaml

    # Search for workflow.yaml
    cwd = Path.cwd()
    search_paths = [cwd] + list(cwd.parents)[:5]

    for search_dir in search_paths:
        workflow_path = search_dir / "workflow.yaml"
        if workflow_path.exists():
            try:
                with open(workflow_path) as f:
                    workflow = yaml.safe_load(f)
                    return workflow.get("settings", {})
            except Exception as e:
                logger.warning(f"Failed to load {workflow_path}: {e}")
                break

    # Try default workflow
    default_path = Path(__file__).parent.parent / "default_workflow.yaml"
    if default_path.exists():
        try:
            with open(default_path) as f:
                workflow = yaml.safe_load(f)
                return workflow.get("settings", {})
        except Exception as e:
            logger.warning(f"Failed to load default workflow: {e}")

    # No workflow found, use empty settings (will use defaults)
    return {}


def get_tool_for_review(review_type: str) -> str:
    """
    Get the tool for a review type.

    This is the main entry point for other modules to get
    tool assignments for review types.

    Args:
        review_type: The review type (e.g., "security_review" or "security")

    Returns:
        Tool name (codex, gemini, or grok)
    """
    config = get_review_config()
    return config.get_tool(review_type)


def get_available_review_types() -> list[str]:
    """
    Get list of available review types.

    Returns:
        List of review type names
    """
    config = get_review_config()
    return config.get_available_types()
