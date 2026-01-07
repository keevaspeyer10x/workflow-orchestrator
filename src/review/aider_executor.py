"""
Aider executor for reviews.

Executes reviews using Aider CLI with OpenRouter,
providing full repository context via Aider's repo map.
"""

import os
import subprocess
import time
import logging
from pathlib import Path
from typing import Optional

from .prompts import get_prompt
from .result import ReviewResult, parse_review_output

logger = logging.getLogger(__name__)


# Review prompts for Aider
AIDER_PROMPTS = {
    "security": (
        "Review this codebase for security vulnerabilities. "
        "Focus on: injection attacks (SQL, command, XSS), authentication bypasses, "
        "hardcoded secrets, SSRF, path traversal, insecure deserialization. "
        "This code may have had limited human review - be thorough. "
        "Provide a structured report with findings, severity levels, and recommendations."
    ),
    "consistency": (
        "Review this codebase for consistency with existing patterns. "
        "Look for: 1) Existing utilities that should be reused, "
        "2) Pattern violations vs established conventions, "
        "3) Naming/structure inconsistencies. "
        "Provide specific file locations and recommendations."
    ),
    "quality": (
        "Review this codebase for production readiness. "
        "Check for: edge cases, error handling, resource cleanup, input validation, "
        "unnecessary complexity, test coverage gaps. "
        "Provide a quality assessment with specific findings."
    ),
    "holistic": (
        "Perform a comprehensive code review of this codebase. "
        "Would you approve this code? What concerns you? "
        "What questions would you ask? What would you do differently? "
        "Provide honest, constructive feedback."
    ),
}

# Default model for Aider via OpenRouter
DEFAULT_MODEL = "openrouter/google/gemini-2.0-flash-001"


class AiderExecutor:
    """
    Executes reviews using Aider CLI with OpenRouter.

    Aider provides full repository context via its repo map feature,
    making it ideal for comprehensive code reviews with models like Gemini.
    """

    DEFAULT_TIMEOUT = 300  # 5 minutes per review

    def __init__(
        self,
        working_dir: Path,
        timeout: int = DEFAULT_TIMEOUT,
        model: str = DEFAULT_MODEL
    ):
        self.working_dir = Path(working_dir).resolve()
        self.timeout = timeout
        self.model = model

    def execute(self, review_type: str) -> ReviewResult:
        """
        Execute a review using Aider.

        Args:
            review_type: One of security, consistency, quality, holistic

        Returns:
            ReviewResult with findings
        """
        prompt = AIDER_PROMPTS.get(review_type, AIDER_PROMPTS["holistic"])

        start_time = time.time()

        try:
            output = self._run_aider(prompt)
            duration = time.time() - start_time

            # Parse the output
            findings, metadata = parse_review_output(review_type, output)

            return ReviewResult(
                review_type=review_type,
                success=True,
                model_used=self.model.replace("openrouter/", ""),
                method_used="aider",
                findings=findings,
                raw_output=output,
                summary=metadata.get("summary"),
                score=metadata.get("score"),
                assessment=metadata.get("assessment"),
                duration_seconds=duration,
            )

        except subprocess.TimeoutExpired:
            return ReviewResult(
                review_type=review_type,
                success=False,
                model_used=self.model,
                method_used="aider",
                error=f"Review timed out after {self.timeout} seconds",
                duration_seconds=self.timeout,
            )

        except FileNotFoundError as e:
            return ReviewResult(
                review_type=review_type,
                success=False,
                model_used=self.model,
                method_used="aider",
                error=f"Aider not found. Install with: pip install aider-chat",
            )

        except Exception as e:
            logger.exception(f"Error executing {review_type} review with Aider")
            return ReviewResult(
                review_type=review_type,
                success=False,
                model_used=self.model,
                method_used="aider",
                error=str(e),
                duration_seconds=time.time() - start_time,
            )

    def _run_aider(self, prompt: str) -> str:
        """
        Run Aider with the given prompt.

        Returns the output from Aider.
        """
        # Build aider command
        # --no-auto-commits: Don't create commits (review only)
        # --no-git: Don't interact with git
        # --yes: Auto-confirm prompts
        # --message: Non-interactive mode with prompt
        cmd = [
            "aider",
            "--model", self.model,
            "--no-auto-commits",
            "--no-git",
            "--yes",
            "--message", prompt,
        ]

        # Ensure OPENROUTER_API_KEY is available
        env = os.environ.copy()
        if "OPENROUTER_API_KEY" not in env:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")

        process = None
        try:
            process = subprocess.Popen(
                cmd,
                cwd=self.working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            stdout, stderr = process.communicate(timeout=self.timeout)

            if process.returncode != 0 and stderr:
                logger.warning(f"Aider returned non-zero: {stderr}")

            # Combine stdout and stderr, prefer stdout
            output = stdout if stdout else stderr
            return output

        except subprocess.TimeoutExpired:
            if process:
                process.kill()
                process.wait()
            raise

        finally:
            if process and process.poll() is None:
                process.kill()
                process.wait()

    def check_available(self) -> bool:
        """Check if Aider is available."""
        import shutil
        return shutil.which("aider") is not None
