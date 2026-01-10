"""
Input Validation Module

Provides validation functions for user input to prevent DoS
via extremely long strings and ensure data quality.
"""

from typing import Optional

# Maximum length constants
MAX_CONSTRAINT_LENGTH = 1000
MAX_NOTE_LENGTH = 2000  # Increased from 500 to allow detailed clarifying questions


def validate_constraint(constraint: str) -> str:
    """
    Validate a constraint string.

    Args:
        constraint: The constraint text to validate

    Returns:
        The validated constraint string

    Raises:
        ValueError: If constraint exceeds MAX_CONSTRAINT_LENGTH characters
    """
    if len(constraint) > MAX_CONSTRAINT_LENGTH:
        raise ValueError(
            f"Constraint exceeds maximum length of {MAX_CONSTRAINT_LENGTH} characters "
            f"(got {len(constraint)} characters)"
        )
    return constraint


def validate_note(note: Optional[str]) -> Optional[str]:
    """
    Validate a note string.

    Args:
        note: The note text to validate (can be None or empty)

    Returns:
        The validated note string

    Raises:
        ValueError: If note exceeds MAX_NOTE_LENGTH characters
    """
    if note and len(note) > MAX_NOTE_LENGTH:
        raise ValueError(
            f"Note exceeds maximum length of {MAX_NOTE_LENGTH} characters "
            f"(got {len(note)} characters)"
        )
    return note


def validate_constraints(constraints: list[str]) -> list[str]:
    """
    Validate a list of constraint strings.

    Args:
        constraints: List of constraint texts to validate

    Returns:
        The validated list of constraints

    Raises:
        ValueError: If any constraint exceeds MAX_CONSTRAINT_LENGTH
    """
    return [validate_constraint(c) for c in constraints]
