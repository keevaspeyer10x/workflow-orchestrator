"""
Skip decision validation.

Ensures that when steps are skipped, the reasoning is substantive
and demonstrates conscious consideration.
"""

import re
from typing import Optional, Literal
from pydantic import BaseModel, Field, model_validator


# Minimum length for skip reasoning
MIN_SKIP_REASON_LENGTH = 50

# Patterns that indicate shallow reasoning
SHALLOW_PATTERNS = [
    r"^not needed$",
    r"^not applicable$",
    r"^n/?a$",
    r"^none$",
    r"^obvious$",
    r"^already done$",
    r"^skip$",
    r"^skipped$",
    r"^no need$",
    r"^unnecessary$",
    r"^not required$",
    r"^done$",
    r"^ok$",
    r"^fine$",
]


class SkipDecision(BaseModel):
    """
    Model for a step completion/skip decision.

    Forces structured reasoning when skipping steps.
    """
    action: Literal["completed", "skipped"]

    # Required if completed (optional schema validation happens elsewhere)
    evidence: Optional[dict] = None

    # Required if skipped
    skip_reasoning: Optional[str] = Field(
        default=None,
        description="Substantive explanation of why step was skipped"
    )
    context_considered: Optional[list[str]] = Field(
        default=None,
        description="What context/factors were considered in the decision"
    )

    @model_validator(mode='after')
    def validate_skip_decision(self):
        """Validate that skipped decisions have substantive reasoning."""
        if self.action == "skipped":
            if not self.skip_reasoning:
                raise ValueError("Must explain why step was skipped")

            # Check length
            if len(self.skip_reasoning.strip()) < MIN_SKIP_REASON_LENGTH:
                raise ValueError(
                    f"Skip reasoning too shallow - must be at least "
                    f"{MIN_SKIP_REASON_LENGTH} characters to demonstrate thought"
                )

            # Check for shallow patterns
            reasoning_lower = self.skip_reasoning.lower().strip()
            for pattern in SHALLOW_PATTERNS:
                if re.match(pattern, reasoning_lower, re.IGNORECASE):
                    raise ValueError(
                        f"Skip reasoning too shallow: '{self.skip_reasoning}'. "
                        "Explain what you considered and why this step doesn't apply."
                    )

        return self


def validate_skip_reasoning(reasoning: str) -> tuple[bool, Optional[str]]:
    """
    Validate skip reasoning without using the full SkipDecision model.

    Useful for validating reasoning in isolation.

    Args:
        reasoning: The skip reason to validate

    Returns:
        (is_valid, error_message) tuple
    """
    if not reasoning:
        return False, "Skip reasoning is required"

    reasoning = reasoning.strip()

    if len(reasoning) < MIN_SKIP_REASON_LENGTH:
        return False, (
            f"Skip reasoning too short ({len(reasoning)} chars). "
            f"Must be at least {MIN_SKIP_REASON_LENGTH} characters."
        )

    # Check for shallow patterns
    reasoning_lower = reasoning.lower()
    for pattern in SHALLOW_PATTERNS:
        if re.match(pattern, reasoning_lower, re.IGNORECASE):
            return False, (
                f"Skip reasoning too shallow: '{reasoning}'. "
                "Provide substantive explanation of why this step doesn't apply."
            )

    return True, None
