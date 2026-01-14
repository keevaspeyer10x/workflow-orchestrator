"""
API executor for reviews.

Executes reviews using OpenRouter API with context injection.
Used when CLI tools are not available (e.g., Claude Code Web).
"""

import os
import time
import logging
from pathlib import Path
from typing import Optional

from .context import ReviewContext, ReviewContextCollector
from .prompts import get_prompt, get_tool
from .result import ReviewResult, ReviewErrorType, classify_http_error, parse_review_output
from ..secrets import get_secret

logger = logging.getLogger(__name__)


# Model mapping for OpenRouter
# Use latest available models for best review quality
OPENROUTER_MODELS = {
    "codex": "openai/gpt-5.1",  # Latest OpenAI model via OpenRouter
    "gemini": "google/gemini-3-pro-preview",  # Latest Gemini model via OpenRouter (1M context)
}


class APIExecutor:
    """
    Executes reviews using OpenRouter API.

    This injects repository context into the prompt since
    the API doesn't have direct repository access.
    """

    def __init__(
        self,
        working_dir: Path,
        context_limit: Optional[int] = None,
        base_branch: str = "main",
        api_key: Optional[str] = None
    ):
        self.working_dir = Path(working_dir).resolve()
        self.context_collector = ReviewContextCollector(
            working_dir=self.working_dir,
            context_limit=context_limit,
            base_branch=base_branch
        )
        # Try to get API key from multiple sources:
        # 1. Passed directly
        # 2. Environment variable
        # 3. SecretsManager (SOPS, GitHub repo, etc.)
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY") or get_secret("OPENROUTER_API_KEY")

        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY not found. Checked:\n"
                "  1. Environment variable\n"
                "  2. SOPS-encrypted secrets (secrets.enc.yaml)\n"
                "  3. GitHub private repo (if configured)\n"
                "Run: eval \"$(sops -d secrets.enc.yaml | sed 's/: /=/' | sed 's/^/export /')\" to load keys"
            )

    def execute(self, review_type: str, context_override: Optional[str] = None) -> ReviewResult:
        """
        Execute a review using OpenRouter API.

        Args:
            review_type: One of security, consistency, quality, holistic
            context_override: Optional custom prompt to use instead of auto-collected context

        Returns:
            ReviewResult with findings
        """
        start_time = time.time()

        try:
            # Use context_override if provided, otherwise collect normally
            if context_override:
                prompt = context_override
                context = None
            else:
                # Collect context
                context = self.context_collector.collect(review_type)
                # Build prompt
                prompt = self._build_prompt(review_type, context)

            # Get model
            tool = get_tool(review_type)
            model = OPENROUTER_MODELS.get(tool, OPENROUTER_MODELS["gemini"])

            # Call OpenRouter
            output = self._call_openrouter(prompt, model)

            duration = time.time() - start_time

            # Parse output
            findings, metadata = parse_review_output(review_type, output)

            result = ReviewResult(
                review_type=review_type,
                success=True,
                model_used=model,
                method_used="api",
                findings=findings,
                raw_output=output,
                summary=metadata.get("summary"),
                score=metadata.get("score"),
                assessment=metadata.get("assessment"),
                duration_seconds=duration,
            )

            # Add truncation warning if applicable
            if context and context.truncated:
                result.summary = (result.summary or "") + f"\n\n⚠️ {context.truncation_warning}"

            return result

        except Exception as e:
            logger.exception(f"Error executing {review_type} review via API")
            # Sanitize error message to avoid leaking sensitive info
            error_msg = self._sanitize_error(str(e))

            # CORE-026-E1: Classify the error type
            error_type = self._classify_exception(e)

            return ReviewResult(
                review_type=review_type,
                success=False,
                model_used="unknown",
                method_used="api",
                error=error_msg,
                error_type=error_type,
                duration_seconds=time.time() - start_time,
            )

    def _sanitize_error(self, error: str) -> str:
        """Sanitize error message to avoid leaking sensitive information."""
        import re
        # Remove potential API keys (sk-..., AIza..., etc.)
        sanitized = re.sub(r'sk-[a-zA-Z0-9_-]+', '[REDACTED_KEY]', error)
        sanitized = re.sub(r'AIza[a-zA-Z0-9_-]+', '[REDACTED_KEY]', sanitized)
        # Remove Bearer tokens
        sanitized = re.sub(r'Bearer\s+[a-zA-Z0-9_-]+', 'Bearer [REDACTED]', sanitized)
        # Truncate long error messages
        if len(sanitized) > 500:
            sanitized = sanitized[:500] + "... (truncated)"
        return sanitized

    def _classify_exception(self, exc: Exception) -> ReviewErrorType:
        """
        Classify an exception into a ReviewErrorType.

        CORE-026-E1: Wire error classification in executors.
        """
        import requests

        # Check for specific exception types first
        if isinstance(exc, requests.exceptions.Timeout):
            return ReviewErrorType.TIMEOUT
        if isinstance(exc, requests.exceptions.ConnectionError):
            return ReviewErrorType.NETWORK_ERROR

        # Check for HTTP status codes in the error message
        error_str = str(exc).lower()
        error_full = str(exc)

        # Try to extract HTTP status code from RuntimeError message
        # Format: "OpenRouter API error: 401 - ..."
        if "401" in error_full or "403" in error_full:
            return ReviewErrorType.KEY_INVALID
        if "429" in error_full:
            return ReviewErrorType.RATE_LIMITED
        if "500" in error_full or "502" in error_full or "503" in error_full:
            return ReviewErrorType.NETWORK_ERROR

        # Check for keywords
        if "timeout" in error_str:
            return ReviewErrorType.TIMEOUT
        if "connection" in error_str or "network" in error_str:
            return ReviewErrorType.NETWORK_ERROR
        if "unauthorized" in error_str or "invalid" in error_str and "key" in error_str:
            return ReviewErrorType.KEY_INVALID
        if "rate" in error_str and "limit" in error_str:
            return ReviewErrorType.RATE_LIMITED

        # Default to generic failure
        return ReviewErrorType.REVIEW_FAILED

    def _build_prompt(self, review_type: str, context: ReviewContext) -> str:
        """Build the full prompt with context."""
        template = get_prompt(review_type)

        # Substitute context into template
        prompt = template.format(
            git_diff=context.git_diff or "(no diff available)",
            changed_files=context.format_changed_files(),
            related_files=context.format_related_files(),
            architecture_docs=context.architecture_docs or "(no architecture docs)",
            context=context.context_summary or "(no additional context)",
            project_context=context.project_context or "(project type not detected)",
        )

        return prompt

    def _call_openrouter(self, prompt: str, model: str) -> str:
        """
        Call OpenRouter API.

        Returns the model's response text.
        """
        import requests

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/workflow-orchestrator",
                "X-Title": "Workflow Orchestrator Reviews",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are an expert code reviewer. "
                            "Review the provided code thoroughly and provide detailed, actionable feedback. "
                            "This is AI-generated code with zero human review - be thorough."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                "max_tokens": 4000,
                "temperature": 0.3,  # Lower temperature for more consistent reviews
            },
            timeout=300,  # 5 minute timeout
            verify=True,  # Explicitly enforce SSL certificate verification
        )

        if response.status_code != 200:
            error_msg = f"OpenRouter API error: {response.status_code}"
            try:
                error_data = response.json()
                if "error" in error_data:
                    error_msg = f"{error_msg} - {error_data['error']}"
            except Exception:
                error_msg = f"{error_msg} - {response.text[:500]}"
            raise RuntimeError(error_msg)

        data = response.json()

        if "choices" not in data or not data["choices"]:
            raise RuntimeError("No response from OpenRouter API")

        return data["choices"][0]["message"]["content"]
