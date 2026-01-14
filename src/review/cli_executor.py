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
from .result import ReviewResult, ReviewErrorType, parse_review_output

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
    "vibe_coding": (
        "This is AI-generated code with ZERO human review. "
        "Check for AI-specific issues: hallucinated APIs that don't exist, "
        "plausible-but-wrong logic, tests that pass but don't test real behavior, "
        "comment/code drift, deprecated patterns from training data, cargo cult code. "
        "AI optimizes locally - find where it missed the big picture."
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
            review_type: One of security, consistency, quality, holistic, vibe_coding

        Returns:
            ReviewResult with findings
        """
        tool = get_tool(review_type)
        prompt = CLI_PROMPTS.get(review_type, CLI_PROMPTS["holistic"])

        start_time = time.time()

        try:
            if tool == "codex":
                output, model = self._run_codex(prompt)
            elif tool == "grok":
                output, model = self._run_grok(prompt)
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
                error_type=ReviewErrorType.TIMEOUT,  # CORE-026-E1
                duration_seconds=self.timeout,
            )

        except FileNotFoundError as e:
            return ReviewResult(
                review_type=review_type,
                success=False,
                model_used=tool,
                method_used="cli",
                error=f"CLI tool not found: {e}. Install with: npm install -g @openai/codex @google/gemini-cli",
                error_type=ReviewErrorType.KEY_MISSING,  # CORE-026-E1: CLI tool not installed
            )

        except Exception as e:
            logger.exception(f"Error executing {review_type} review")
            # CORE-026-E1: Classify the error type
            error_type = self._classify_error(str(e))
            return ReviewResult(
                review_type=review_type,
                success=False,
                model_used=tool,
                method_used="cli",
                error=str(e),
                error_type=error_type,
                duration_seconds=time.time() - start_time,
            )

    def _run_codex(self, prompt: str, base_branch: str = "main") -> tuple[str, str]:
        """
        Run Codex CLI review.

        Returns (output, model_name)
        """
        process = None
        try:
            # Codex CLI: --base and prompt can't be used together
            # Use --base alone - Codex has full repo access and will do a comprehensive review
            process = subprocess.Popen(
                [
                    "codex",
                    "review",
                    "--base", base_branch,
                ],
                cwd=self.working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = process.communicate(timeout=self.timeout)

            if process.returncode != 0 and stderr:
                logger.warning(f"Codex returned non-zero: {stderr}")

            output = stdout or stderr
            return output, "codex/gpt-5.1-codex-max"

        except subprocess.TimeoutExpired:
            if process:
                process.kill()
                process.wait()  # Ensure process is cleaned up
            raise

        finally:
            if process and process.poll() is None:
                process.kill()
                process.wait()

    def _run_gemini(self, prompt: str) -> tuple[str, str]:
        """
        Run Gemini CLI code review.

        Returns (output, model_name)
        """
        # Build full prompt for code review
        full_prompt = f"""Review the code changes in this repository.

{prompt}

Analyze the git diff and changed files to provide your review. Output your findings in a structured format."""

        process = None
        try:
            # Gemini CLI uses positional prompt (not -p which is deprecated)
            # Use --model to specify Gemini 3 Pro
            # Use --yolo to auto-approve any tool calls
            # Use --output-format text for clean output
            process = subprocess.Popen(
                [
                    "gemini",
                    "--model", "gemini-3-pro-preview",
                    "--yolo",
                    "--output-format", "text",
                    full_prompt,
                ],
                cwd=self.working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = process.communicate(timeout=self.timeout)

            if process.returncode != 0 and stderr:
                logger.warning(f"Gemini returned non-zero: {stderr}")

            output = stdout or stderr
            return output, "gemini/gemini-3-pro-preview"

        except subprocess.TimeoutExpired:
            if process:
                process.kill()
                process.wait()  # Ensure process is cleaned up
            raise

        finally:
            if process and process.poll() is None:
                process.kill()
                process.wait()

    def _run_grok(self, prompt: str) -> tuple[str, str]:
        """
        Run Grok review via OpenRouter API (more reliable than XAI direct).

        Uses the model registry to get the latest Grok model version.

        Returns (output, model_name)
        """
        import os
        import json
        import urllib.request
        import urllib.error
        from src.model_registry import get_model_registry

        # Get latest Grok model from registry
        registry = get_model_registry(self.working_dir)
        model_id = registry.get_latest_model("grok")
        logger.info(f"Using Grok model from registry: {model_id}")

        # Try OpenRouter first (more reliable), fall back to XAI direct
        # Check both uppercase and lowercase variants (Happy uses lowercase)
        api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("openrouter_api_key")
        use_openrouter = bool(api_key)

        if not api_key:
            api_key = (
                os.environ.get("XAI_API_KEY") or
                os.environ.get("xai_api_key") or
                os.environ.get("grok_api_key")
            )
            if not api_key:
                raise ValueError("No Grok API key found. Set XAI_API_KEY, xai_api_key, or grok_api_key")

        # Get git diff for context
        try:
            diff_result = subprocess.run(
                ["git", "diff", "HEAD~1"],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            git_diff = diff_result.stdout[:50000]  # Limit context size
        except Exception:
            git_diff = "(Could not get git diff)"

        full_prompt = f"""{prompt}

## Git Diff (recent changes)
```diff
{git_diff}
```

Analyze the code changes and provide your review."""

        if use_openrouter:
            # Use OpenRouter API with model from registry
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/workflow-orchestrator",
            }
            data = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": "You are a code reviewer specializing in catching issues in AI-generated code."},
                    {"role": "user", "content": full_prompt}
                ],
                "max_tokens": 4096,
            }
            model_name = f"grok/{model_id.split('/')[-1]}-via-openrouter"
        else:
            # Use XAI API directly - strip provider prefix
            xai_model = model_id.replace("x-ai/", "")
            url = "https://api.x.ai/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            data = {
                "model": xai_model,
                "messages": [
                    {"role": "system", "content": "You are a code reviewer specializing in catching issues in AI-generated code."},
                    {"role": "user", "content": full_prompt}
                ],
                "max_tokens": 4096,
            }
            model_name = f"grok/{xai_model}"

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
                output = result["choices"][0]["message"]["content"]
                return output, model_name

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else str(e)
            raise RuntimeError(f"Grok API error: {e.code} - {error_body}")

    def check_tools_available(self) -> dict[str, bool]:
        """Check if required CLI tools are available."""
        import shutil
        import os
        return {
            "codex": shutil.which("codex") is not None,
            "gemini": shutil.which("gemini") is not None,
            "grok": bool(
                os.environ.get("XAI_API_KEY") or
                os.environ.get("xai_api_key") or
                os.environ.get("grok_api_key") or
                os.environ.get("OPENROUTER_API_KEY") or
                os.environ.get("openrouter_api_key")
            ),
        }

    def _classify_error(self, error_msg: str) -> ReviewErrorType:
        """
        Classify an error message into a ReviewErrorType.

        CORE-026-E1: Wire error classification in executors.
        """
        error_lower = error_msg.lower()

        # Check for HTTP status codes
        if "401" in error_msg or "403" in error_msg:
            return ReviewErrorType.KEY_INVALID
        if "429" in error_msg:
            return ReviewErrorType.RATE_LIMITED

        # Check for common error patterns
        if "unauthorized" in error_lower:
            return ReviewErrorType.KEY_INVALID
        if "rate limit" in error_lower or "ratelimit" in error_lower:
            return ReviewErrorType.RATE_LIMITED
        if "timeout" in error_lower:
            return ReviewErrorType.TIMEOUT
        if "connection" in error_lower or "network" in error_lower:
            return ReviewErrorType.NETWORK_ERROR

        # Default to generic failure
        return ReviewErrorType.REVIEW_FAILED
