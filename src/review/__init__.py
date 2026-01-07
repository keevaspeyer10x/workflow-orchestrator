"""
Multi-model review system for AI-generated code.

This module provides automated code reviews using multiple AI models
(Codex, Gemini) to catch issues that coding agents often miss.

Reviews:
- security_review: OWASP vulnerabilities, auth issues, secrets
- consistency_review: Pattern compliance, existing utilities, codebase fit
- quality_review: Edge cases, error handling, test coverage
- holistic_review: Open-ended "what did the AI miss?"

Execution modes:
- CLI: Codex CLI + Gemini CLI (full repo access)
- API: OpenRouter (context injection, for Claude Code Web)
- GitHub Actions: PR gate with full repo access
"""

from .context import ReviewContext, ReviewContextCollector
from .router import ReviewRouter, ReviewMethod
from .result import ReviewResult, ReviewFinding, Severity
from .prompts import REVIEW_PROMPTS
from .setup import setup_reviews, check_review_setup, ReviewSetup
from .aider_executor import AiderExecutor

__all__ = [
    # Context
    "ReviewContext",
    "ReviewContextCollector",
    # Router
    "ReviewRouter",
    "ReviewMethod",
    # Results
    "ReviewResult",
    "ReviewFinding",
    "Severity",
    # Prompts
    "REVIEW_PROMPTS",
    # Setup
    "setup_reviews",
    "check_review_setup",
    "ReviewSetup",
    # Executors
    "AiderExecutor",
]
