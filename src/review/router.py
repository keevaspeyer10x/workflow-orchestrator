"""
Review router - detects method and dispatches reviews.

Supports three execution methods:
- CLI: Codex CLI + Gemini CLI (full repo access)
- API: OpenRouter (context injection)
- GitHub Actions: Triggered on PR (handled separately)
"""

import os
import shutil
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from .context import ReviewContext, ReviewContextCollector
from .result import ReviewResult
from .prompts import get_prompt, get_tool, REVIEW_PROMPTS
from .setup import ReviewSetup, check_review_setup as _check_setup
from .registry import get_all_review_types
from .constants import MODEL_TO_API_KEY
from ..secrets import get_secret

logger = logging.getLogger(__name__)


# =============================================================================
# WF-035 Phase 4: Review Threshold Error
# =============================================================================

class ReviewThresholdError(Exception):
    """
    Raised when insufficient reviews complete successfully.

    Used when on_insufficient_reviews is set to "block" and the number of
    successful reviews is below the minimum_required threshold.
    """

    def __init__(
        self,
        message: str,
        successful: int = 0,
        required: int = 3
    ):
        super().__init__(message)
        self.successful = successful
        self.required = required


# API keys to auto-load from secrets if not in environment
API_KEYS_TO_LOAD = [
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "XAI_API_KEY",
]

# Lowercase variants (e.g., Happy uses lowercase env vars)
API_KEY_ALIASES = {
    "XAI_API_KEY": ["xai_api_key", "grok_api_key"],
    "OPENROUTER_API_KEY": ["openrouter_api_key"],
    "OPENAI_API_KEY": ["openai_api_key"],
    "GEMINI_API_KEY": ["gemini_api_key"],
}


def ensure_api_keys_loaded() -> dict[str, bool]:
    """
    Load API keys from SecretsManager into environment if not already set.

    Also normalizes lowercase variants (e.g., grok_api_key -> XAI_API_KEY)
    to ensure compatibility with tools like Happy that use lowercase env vars.

    This allows SOPS-encrypted secrets to be used by CLI tools and litellm
    without requiring manual 'eval $(sops -d ...)' commands.

    Returns:
        Dict of key_name -> was_loaded (True if loaded from secrets or alias)
    """
    loaded = {}
    for key_name in API_KEYS_TO_LOAD:
        if os.environ.get(key_name):
            # Already in environment (uppercase)
            loaded[key_name] = False
            continue

        # Check for lowercase aliases (e.g., grok_api_key -> XAI_API_KEY)
        aliases = API_KEY_ALIASES.get(key_name, [])
        alias_value = None
        for alias in aliases:
            alias_value = os.environ.get(alias)
            if alias_value:
                os.environ[key_name] = alias_value
                loaded[key_name] = True
                logger.debug(f"Normalized {alias} -> {key_name}")
                break

        if loaded.get(key_name):
            continue

        # Try to get from secrets (SOPS, GitHub repo, etc.)
        value = get_secret(key_name)
        if value:
            os.environ[key_name] = value
            loaded[key_name] = True
            logger.debug(f"Loaded {key_name} from secrets")
        else:
            loaded[key_name] = False

    return loaded


def validate_api_keys(
    models: list[str],
    ping: bool = False
) -> tuple[bool, dict[str, str]]:
    """
    Validate that API keys are available for the specified models.

    CORE-026: Proactive key validation before running reviews.
    CORE-026-E2: Added ping validation to test keys with real API calls.

    Args:
        models: List of model names to validate (e.g., ["gemini", "openai"])
        ping: If True, also ping the API to verify key is valid

    Returns:
        Tuple of (all_valid, errors_dict) where errors_dict maps model -> error message
    """
    # First ensure keys are loaded from secrets
    ensure_api_keys_loaded()

    errors = {}
    for model in models:
        model_lower = model.lower()
        key_name = MODEL_TO_API_KEY.get(model_lower)

        if not key_name:
            # Unknown model, skip validation
            logger.warning(f"Unknown model for validation: {model}")
            continue

        key_value = os.environ.get(key_name)
        if not key_value:
            errors[model_lower] = f"{key_name} not set in environment"
            continue

        # Basic format validation (keys should be non-empty strings)
        if len(key_value.strip()) < 10:
            errors[model_lower] = f"{key_name} appears invalid (too short)"
            continue

        # CORE-026-E2: If ping=True, make a lightweight API call to verify the key
        if ping and model_lower not in errors:
            ping_error = _ping_api(model_lower, key_value)
            if ping_error:
                errors[model_lower] = ping_error

    return len(errors) == 0, errors


def _ping_api(model: str, api_key: str) -> Optional[str]:
    """
    Test an API key by making a lightweight request.

    CORE-026-E2: Ping validation for API keys.

    Uses model list endpoints which are cheap and fast.

    Args:
        model: Model name (gemini, openai, openrouter, grok)
        api_key: The API key to test

    Returns:
        None if successful, error message string if failed
    """
    import urllib.request
    import urllib.error
    import json

    try:
        if model in ("openrouter",):
            # OpenRouter: GET /api/v1/models
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                method="GET",
            )
        elif model in ("openai", "codex"):
            # OpenAI: GET /v1/models
            req = urllib.request.Request(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                method="GET",
            )
        elif model in ("gemini",):
            # Google AI: GET models with key parameter
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
                method="GET",
            )
        elif model in ("grok",):
            # XAI: GET /v1/models (or use OpenRouter if available)
            # Check if this looks like an OpenRouter key
            if api_key.startswith("sk-or-"):
                req = urllib.request.Request(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    method="GET",
                )
            else:
                req = urllib.request.Request(
                    "https://api.x.ai/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    method="GET",
                )
        else:
            # Unknown model, skip ping
            logger.debug(f"No ping endpoint configured for model: {model}")
            return None

        with urllib.request.urlopen(req, timeout=10) as response:
            # Success - key is valid
            return None

    except urllib.error.HTTPError as e:
        return f"API returned HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return f"Network error: {e.reason}"
    except Exception as e:
        return f"Ping failed: {str(e)}"


class ReviewMethod(Enum):
    """Available review execution methods."""
    CLI = "cli"
    AIDER = "aider"
    API = "api"
    GITHUB_ACTIONS = "github-actions"
    UNAVAILABLE = "unavailable"


def check_review_setup(working_dir: Optional[Path] = None) -> ReviewSetup:
    """
    Check what review infrastructure is available.

    Args:
        working_dir: Working directory to check for GitHub Actions

    Returns:
        ReviewSetup with availability flags
    """
    return _check_setup(working_dir or Path("."))


class ReviewRouter:
    """
    Routes review requests to the appropriate executor.
    """

    def __init__(
        self,
        working_dir: Path,
        method: Optional[str] = None,
        context_limit: Optional[int] = None,
        base_branch: str = "main",
        no_fallback: bool = False
    ):
        self.working_dir = Path(working_dir).resolve()
        self.context_limit = context_limit
        self.base_branch = base_branch
        self.no_fallback = no_fallback  # CORE-028b: Disable fallback

        # Auto-load API keys from SOPS/secrets before checking setup
        self._loaded_keys = ensure_api_keys_loaded()
        if any(self._loaded_keys.values()):
            loaded_names = [k for k, v in self._loaded_keys.items() if v]
            logger.info(f"Loaded API keys from secrets: {', '.join(loaded_names)}")

        self.setup = check_review_setup(self.working_dir)

        # Determine method
        if method and method != "auto":
            self._method = ReviewMethod(method)
        else:
            best = self.setup.best_method()
            self._method = ReviewMethod(best) if best != "unavailable" else ReviewMethod.UNAVAILABLE

        # Initialize executors lazily
        self._cli_executor = None
        self._aider_executor = None
        self._api_executor = None

    @property
    def method(self) -> ReviewMethod:
        """Current execution method."""
        return self._method

    def get_status_message(self) -> str:
        """Get human-readable status message."""
        lines = ["Review Infrastructure Status:"]

        # CLI tools
        codex_status = "✓" if self.setup.codex_cli else "✗"
        gemini_status = "✓" if self.setup.gemini_cli else "✗"
        lines.append(f"  CLI Tools:      {codex_status} codex, {gemini_status} gemini")

        # Aider (Gemini via OpenRouter with repo context)
        aider_status = "✓" if self.setup.aider_cli else "✗"
        aider_note = " (gemini via openrouter)" if self.setup.aider_available else ""
        lines.append(f"  Aider:          {aider_status} aider{aider_note}")

        # API key
        api_status = "✓" if self.setup.openrouter_key else "✗"
        lines.append(f"  API Key:        {api_status} OPENROUTER_API_KEY")

        # GitHub Actions
        actions_status = "✓" if self.setup.github_actions else "✗"
        lines.append(f"  GitHub Actions: {actions_status} .github/workflows/ai-reviews.yml")

        # Current method
        lines.append(f"")
        lines.append(f"  Using method:   {self._method.value}")

        if self._method == ReviewMethod.UNAVAILABLE:
            lines.append("")
            lines.append("  ⚠️  No review method available!")
            lines.append("  Run: pip install aider-chat")
            lines.append("  Or: npm install -g @openai/codex @google/gemini-cli")
            lines.append("  And set: OPENROUTER_API_KEY")

        return "\n".join(lines)

    def execute_review(
        self,
        review_type: str,
        context_override: Optional[str] = None,
    ) -> ReviewResult:
        """
        Execute a review using the appropriate method.

        Args:
            review_type: One of security, consistency, quality, holistic, critique
            context_override: Optional custom prompt/context to use instead of auto-collected context

        Returns:
            ReviewResult with findings
        """
        # Normalize review type
        review_type = review_type.replace("_review", "")

        logger.info(f"Executing {review_type} review using {self._method.value} method")

        if self._method == ReviewMethod.CLI:
            return self._execute_cli(review_type, context_override)
        elif self._method == ReviewMethod.AIDER:
            return self._execute_aider(review_type, context_override)
        elif self._method == ReviewMethod.API:
            return self._execute_api(review_type, context_override)
        else:
            return ReviewResult(
                review_type=review_type,
                success=False,
                model_used="none",
                method_used="unavailable",
                error="No review method available. Install aider-chat, CLIs, or set OPENROUTER_API_KEY."
            )

    def _execute_cli(self, review_type: str, context_override: Optional[str] = None) -> ReviewResult:
        """Execute review using CLI tools."""
        from .cli_executor import CLIExecutor

        if self._cli_executor is None:
            self._cli_executor = CLIExecutor(self.working_dir)

        # CLI tools don't support context_override - they use full repo access
        return self._cli_executor.execute(review_type)

    def _execute_aider(self, review_type: str, context_override: Optional[str] = None) -> ReviewResult:
        """Execute review using Aider with OpenRouter."""
        from .aider_executor import AiderExecutor

        if self._aider_executor is None:
            self._aider_executor = AiderExecutor(self.working_dir)

        # Aider uses full repo access, context_override not applicable
        return self._aider_executor.execute(review_type)

    def _execute_api(self, review_type: str, context_override: Optional[str] = None) -> ReviewResult:
        """Execute review using OpenRouter API."""
        from .api_executor import APIExecutor

        if self._api_executor is None:
            self._api_executor = APIExecutor(
                working_dir=self.working_dir,
                context_limit=self.context_limit,
                base_branch=self.base_branch
            )

        # CORE-028b: Use execute_with_fallback for automatic fallback on transient errors
        return self._api_executor.execute_with_fallback(
            review_type,
            context_override=context_override,
            no_fallback=self.no_fallback
        )

    def execute_all_reviews(self) -> dict[str, ReviewResult]:
        """
        Execute all reviews defined in the registry.

        ARCH-003: Review types are now defined in registry.py (single source of truth).
        See registry.REVIEW_TYPES for the canonical list.

        Returns:
            Dict mapping review_type to ReviewResult
        """
        results = {}
        for review_type in get_all_review_types():
            results[review_type] = self.execute_review(review_type)
        return results
