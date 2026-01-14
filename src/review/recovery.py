"""
Recovery instructions for API key and review failures.

CORE-026: Provides user-friendly guidance for recovering from review failures.
"""

from typing import Optional
from .result import ReviewResult, ReviewErrorType
from .constants import MODEL_TO_API_KEY
from ..secrets import get_secrets_manager


def get_sops_file_path() -> str:
    """Get the configured SOPS file path."""
    try:
        sources = get_secrets_manager().list_sources()
        return sources.get("sops", {}).get("file_path", "secrets.enc.yaml")
    except Exception:
        return "secrets.enc.yaml"


def get_recovery_instructions(model: str) -> str:
    """
    Get recovery instructions for a specific model.

    Args:
        model: Model name (gemini, openai, grok, etc.)

    Returns:
        Recovery instructions string
    """
    model_lower = model.lower()
    key_name = MODEL_TO_API_KEY.get(model_lower, "OPENROUTER_API_KEY")
    sops_file = get_sops_file_path()
    
    return f"""
To reload {model} API key:
  1. Using SOPS: eval "$(sops -d {sops_file} | sed 's/: /=/' | sed 's/^/export /')"
  2. Or set directly: export {key_name}="your-key-here"
  3. Then retry: orchestrator review retry
"""


def get_key_name_for_model(model: str) -> str:
    """
    Get the API key environment variable name for a model.

    Args:
        model: Model name

    Returns:
        Environment variable name (e.g., "GEMINI_API_KEY")
    """
    return MODEL_TO_API_KEY.get(model.lower(), "OPENROUTER_API_KEY")


def format_review_error(result: ReviewResult, model: Optional[str] = None) -> str:
    """
    Format a review error with recovery guidance.

    Args:
        result: ReviewResult with error information
        model: Optional model override (uses result.model_used if not provided)

    Returns:
        Formatted error message with recovery instructions
    """
    model_name = model or result.model_used
    key_name = get_key_name_for_model(model_name)

    # Build error message
    lines = [
        f"Review failed: {result.review_type}",
        f"  Model: {model_name}",
        f"  Error: {result.error or 'Unknown error'}",
    ]

    # Add error type specific guidance
    if result.error_type == ReviewErrorType.KEY_MISSING:
        lines.append(f"\n  Cause: {key_name} not found in environment")
        lines.append(get_recovery_instructions(model_name))
    elif result.error_type == ReviewErrorType.KEY_INVALID:
        lines.append(f"\n  Cause: {key_name} was rejected (invalid or expired)")
        lines.append(get_recovery_instructions(model_name))
    elif result.error_type == ReviewErrorType.RATE_LIMITED:
        lines.append("\n  Cause: API rate limit exceeded")
        lines.append("  Try again in a few minutes, or use a different model.")
        lines.append("  Retry command: orchestrator review retry")
    elif result.error_type == ReviewErrorType.NETWORK_ERROR:
        lines.append("\n  Cause: Network error or API unavailable")
        lines.append("  Check your internet connection and try again.")
        lines.append("  Retry command: orchestrator review retry")
    elif result.error_type == ReviewErrorType.TIMEOUT:
        lines.append("\n  Cause: Review timed out")
        lines.append("  The review took too long to complete.")
        lines.append("  Retry command: orchestrator review retry")
    else:
        # Generic recovery hint
        lines.append("\n  Retry command: orchestrator review retry")

    return "\n".join(lines)
