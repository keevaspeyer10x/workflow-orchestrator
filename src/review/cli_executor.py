"""
CLI executor for reviews.

Executes reviews using Codex CLI and Gemini CLI,
which have full repository access.
"""

import subprocess
import time
import logging
from pathlib import Path
from typing import Optional

from .prompts import get_tool
from .result import ReviewResult, parse_review_output

logger = logging.getLogger(__name__)


# Custom prompts for CLI tools
CLI_PROMPTS = {
    "security": (
        "Focus on security vulnerabilities in AI-generated code. "
        "Check for: injection (SQL, command, XSS), auth bypasses, hardcoded secrets, "
        "SSRF, path traversal, insecure deserialization. "
        "This code has had ZERO human review - be thorough."
    ),
    "consistency": (
        "Check if this code fits the existing codebase. Look for: "
        "1) Existing utilities that should be used instead of new code, "
        "2) Pattern violations vs established conventions, "
        "3) Naming/structure inconsistencies. "
        "AI agents solve problems in isolation - find what they missed."
    ),
    "quality": (
        "Review for production readiness. Check for: "
        "edge cases, error handling, resource cleanup, input validation, "
        "complexity (simpler solution?), test coverage gaps. "
        "AI agents focus on happy paths - find the unhappy paths."
    ),
    "holistic": (
        "Review this AI-generated code with fresh eyes. "
        "Would you approve this PR? What concerns you? "
        "What questions would you ask? What would you do differently? "
        "Be the skeptical senior engineer this code hasn't had."
    ),
}


class CLIExecutor:
    """
    Executes reviews using Codex CLI and Gemini CLI.

    These tools have full repository access and work locally.
    """

    DEFAULT_TIMEOUT = 300  # 5 minutes per review

    def __init__(self, working_dir: Path, timeout: int = DEFAULT_TIMEOUT):
        self.working_dir = Path(working_dir).resolve()
        self.timeout = timeout

    def execute(self, review_type: str) -> ReviewResult:
        """
        Execute a review using the appropriate CLI tool.

        Args:
            review_type: One of security, consistency, quality, holistic

        Returns:
            ReviewResult with findings
        """
        tool = get_tool(review_type)
        prompt = CLI_PROMPTS.get(review_type, CLI_PROMPTS["holistic"])

        start_time = time.time()

        try:
            if tool == "codex":
                output, model = self._run_codex(prompt)
            else:
                output, model = self._run_gemini(prompt)

            duration = time.time() - start_time

            # Parse the output
            findings, metadata = parse_review_output(review_type, output)

            return ReviewResult(
                review_type=review_type,
                success=True,
                model_used=model,
                method_used="cli",
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
                model_used=tool,
                method_used="cli",
                error=f"Review timed out after {self.timeout} seconds",
                duration_seconds=self.timeout,
            )

        except FileNotFoundError as e:
            return ReviewResult(
                review_type=review_type,
                success=False,
                model_used=tool,
                method_used="cli",
                error=f"CLI tool not found: {e}. Install with: npm install -g @openai/codex @google/gemini-cli",
            )

        except Exception as e:
            logger.exception(f"Error executing {review_type} review")
            return ReviewResult(
                review_type=review_type,
                success=False,
                model_used=tool,
                method_used="cli",
                error=str(e),
                duration_seconds=time.time() - start_time,
            )

    def _run_codex(self, prompt: str) -> tuple[str, str]:
        """
        Run Codex CLI review.

        Returns (output, model_name)
        """
        # Codex CLI review command with custom instructions
        result = subprocess.run(
            [
                "codex",
                "review",
                "--custom", prompt,
                "--format", "markdown",
            ],
            cwd=self.working_dir,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )

        if result.returncode != 0 and result.stderr:
            logger.warning(f"Codex returned non-zero: {result.stderr}")

        output = result.stdout or result.stderr
        return output, "codex/gpt-5-codex"

    def _run_gemini(self, prompt: str) -> tuple[str, str]:
        """
        Run Gemini CLI code review.

        Returns (output, model_name)
        """
        # First check if code-review extension is installed
        # If not, fall back to regular prompt

        # Try the code-review extension first
        try:
            result = subprocess.run(
                [
                    "gemini",
                    "/code-review",
                    prompt,
                ],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            if result.returncode == 0:
                return result.stdout, "gemini/gemini-2.5-pro"

        except Exception:
            pass

        # Fall back to regular prompt
        full_prompt = f"""
Review the code changes in this repository.

{prompt}

Analyze the git diff and changed files to provide your review.
"""

        result = subprocess.run(
            [
                "gemini",
                "-p", full_prompt,
            ],
            cwd=self.working_dir,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )

        if result.returncode != 0 and result.stderr:
            logger.warning(f"Gemini returned non-zero: {result.stderr}")

        output = result.stdout or result.stderr
        return output, "gemini/gemini-2.5-pro"

    def check_tools_available(self) -> dict[str, bool]:
        """Check if required CLI tools are available."""
        import shutil
        return {
            "codex": shutil.which("codex") is not None,
            "gemini": shutil.which("gemini") is not None,
        }
