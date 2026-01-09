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
from ..secrets import get_secret

logger = logging.getLogger(__name__)


# API keys to auto-load from secrets if not in environment
API_KEYS_TO_LOAD = [
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "XAI_API_KEY",
]


def ensure_api_keys_loaded() -> dict[str, bool]:
    """
    Load API keys from SecretsManager into environment if not already set.

    This allows SOPS-encrypted secrets to be used by CLI tools and litellm
    without requiring manual 'eval $(sops -d ...)' commands.

    Returns:
        Dict of key_name -> was_loaded (True if loaded from secrets)
    """
    loaded = {}
    for key_name in API_KEYS_TO_LOAD:
        if os.environ.get(key_name):
            # Already in environment
            loaded[key_name] = False
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
        base_branch: str = "main"
    ):
        self.working_dir = Path(working_dir).resolve()
        self.context_limit = context_limit
        self.base_branch = base_branch

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

        return self._api_executor.execute(review_type, context_override=context_override)

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
