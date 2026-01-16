"""
Design Validation - Automated plan vs implementation comparison.

Issue #91: Automate design validation by comparing plan.md against git diff
using LLM analysis.

This module provides:
1. DesignValidationResult dataclass for structured results
2. validate_design() function for plan comparison
3. get_git_diff() helper for retrieving implementation changes
4. Integration with fallback chains from Issue #89
"""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)


@dataclass
class DesignValidationResult:
    """
    Result of design validation comparing plan vs implementation.

    Attributes:
        status: Overall validation result (PASS, PASS_WITH_NOTES, NEEDS_REVISION, SKIP)
        planned_items_implemented: Items from plan found in implementation
        unplanned_additions: Significant unplanned additions (scope creep)
        deviations: Major deviations from plan (in lenient mode, only major ones)
        notes: Summary of validation findings
        confidence: Confidence level of the analysis (0.0-1.0)
    """
    status: Literal["PASS", "PASS_WITH_NOTES", "NEEDS_REVISION", "SKIP"]
    planned_items_implemented: list[str] = field(default_factory=list)
    unplanned_additions: list[str] = field(default_factory=list)
    deviations: list[str] = field(default_factory=list)
    notes: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "status": self.status,
            "planned_items_implemented": self.planned_items_implemented,
            "unplanned_additions": self.unplanned_additions,
            "deviations": self.deviations,
            "notes": self.notes,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DesignValidationResult":
        """Create from dictionary."""
        return cls(
            status=data.get("status", "SKIP"),
            planned_items_implemented=data.get("planned_items_implemented", []),
            unplanned_additions=data.get("unplanned_additions", []),
            deviations=data.get("deviations", []),
            notes=data.get("notes", ""),
            confidence=data.get("confidence", 0.0),
        )


def get_git_diff(base_branch: str = "main", staged_only: bool = False) -> str:
    """
    Get git diff of implementation changes.

    Args:
        base_branch: Branch to diff against (default: main)
        staged_only: If True, only get staged changes

    Returns:
        Git diff output as string, or empty string on failure
    """
    try:
        if staged_only:
            cmd = ["git", "diff", "--cached"]
        else:
            # Diff from base branch to HEAD
            cmd = ["git", "diff", f"{base_branch}...HEAD"]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            # Try alternative: diff against base branch directly
            cmd = ["git", "diff", base_branch]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

        return result.stdout

    except subprocess.TimeoutExpired:
        logger.warning("Git diff timed out")
        return ""
    except Exception as e:
        logger.warning(f"Failed to get git diff: {e}")
        return ""


def call_with_fallback(model: str, prompt: str) -> Optional[object]:
    """
    Call model with fallback chain support (Issue #89 integration).

    This is a wrapper that uses the review system's fallback infrastructure.

    Args:
        model: Primary model to use (e.g., "gemini")
        prompt: The prompt to send

    Returns:
        Response object with content attribute, or None on failure
    """
    try:
        # Try to use the existing API executor with fallback support
        from .api_executor import APIExecutor
        from .config import get_fallback_chain

        # Create a minimal executor for this call
        import os
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            logger.warning("No OPENROUTER_API_KEY found for design validation")
            return None

        executor = APIExecutor(
            working_dir=str(Path.cwd()),
            api_key=api_key,
        )

        # Use execute_with_fallback to leverage Issue #89 infrastructure
        response = executor._call_openrouter(prompt, model)
        return type('Response', (), {'content': response})()

    except Exception as e:
        logger.warning(f"Failed to call model: {e}")
        return None


def validate_design(
    plan_path: Path = Path("docs/plan.md"),
    diff: Optional[str] = None,
    base_branch: str = "main",
    lenient: bool = True,
) -> Optional[DesignValidationResult]:
    """
    Compare implementation plan against actual code changes.

    This is the main entry point for design validation. It:
    1. Reads the plan file
    2. Gets the git diff (or uses provided diff)
    3. Sends both to LLM for comparison
    4. Returns structured validation result

    Args:
        plan_path: Path to plan file (default: docs/plan.md)
        diff: Optional pre-fetched diff (if None, will fetch via git)
        base_branch: Branch to diff against (default: main)
        lenient: If True, only flag major deviations (default: True per user preference)

    Returns:
        DesignValidationResult or None on failure
    """
    # Check if plan file exists
    if not plan_path.exists():
        logger.info(f"Plan file not found: {plan_path}")
        return DesignValidationResult(
            status="SKIP",
            notes=f"Plan file not found: {plan_path}",
        )

    # Read plan content
    try:
        plan_content = plan_path.read_text()
    except Exception as e:
        logger.error(f"Failed to read plan file: {e}")
        return DesignValidationResult(
            status="SKIP",
            notes=f"Failed to read plan file: {e}",
        )

    # Get diff if not provided
    if diff is None:
        diff = get_git_diff(base_branch)

    if not diff:
        logger.info("No diff found - nothing to validate")
        return DesignValidationResult(
            status="SKIP",
            notes="No changes found to validate",
        )

    # Truncate diff if too large (LLMs have context limits)
    max_diff_chars = 50000
    if len(diff) > max_diff_chars:
        diff = diff[:max_diff_chars] + f"\n... [truncated, {len(diff) - max_diff_chars} more chars]"
        logger.info(f"Diff truncated to {max_diff_chars} chars")

    # Build validation prompt
    mode_guidance = (
        "LENIENT MODE - Only flag MAJOR deviations. "
        "Minor additions (logging, error handling, tests, refactoring to support the change, "
        "different variable names) are OK and should NOT be flagged."
        if lenient else
        "STRICT MODE - Flag ALL deviations including minor differences in approach."
    )

    prompt = f"""Compare this implementation plan against the actual code changes.

{mode_guidance}

## Implementation Plan
{plan_content}

## Code Changes (git diff)
{diff}

Analyze the implementation and determine:
1. Are all planned items implemented? List each one found.
2. Are there significant unplanned additions? Only flag if lenient mode is off OR if they represent major scope creep.
3. Do implementations match the planned approach?
4. Are there deviations that need discussion?

Return a JSON object with this exact structure (no markdown code blocks):
{{
    "status": "PASS" | "PASS_WITH_NOTES" | "NEEDS_REVISION",
    "planned_items_implemented": ["item1", "item2"],
    "unplanned_additions": ["significant unplanned item"],
    "deviations": ["major deviation description"],
    "notes": "Brief summary of validation findings",
    "confidence": 0.9
}}

Guidelines for status:
- PASS: All planned items implemented, no major deviations
- PASS_WITH_NOTES: All planned items implemented with minor notes/clarifications
- NEEDS_REVISION: Missing planned items OR major unplanned additions OR significant deviations

Remember: In lenient mode, be generous. Only flag things that truly deviate from the plan's intent."""

    # Call LLM with fallback support
    response = call_with_fallback("gemini", prompt)

    if response is None:
        return DesignValidationResult(
            status="SKIP",
            notes="Failed to get LLM response for validation",
        )

    # Parse response
    try:
        content = response.content if hasattr(response, 'content') else str(response)

        # Clean up response - remove markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        data = json.loads(content.strip())
        return DesignValidationResult.from_dict(data)

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response as JSON: {e}")
        return DesignValidationResult(
            status="SKIP",
            notes=f"Failed to parse validation response: {e}. Raw response: {content[:500] if 'content' in dir() else 'N/A'}",
        )
    except Exception as e:
        logger.warning(f"Unexpected error parsing response: {e}")
        return DesignValidationResult(
            status="SKIP",
            notes=f"Error during validation: {e}",
        )
