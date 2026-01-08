"""
Learning module for conflict pattern memory and strategy optimization.

This module provides components for learning from past conflict resolutions
to improve future resolution suggestions.

Components:
- pattern_schema: Data models for conflict patterns (ConflictPattern, PatternMatch, ResolutionOutcome)
"""

from .pattern_schema import (
    PatternState,
    ValidationResult,
    ConflictPattern,
    PatternMatch,
    ResolutionOutcome,
    ACTIVE_THRESHOLD,
    SUGGESTING_THRESHOLD,
    DEPRECATION_FAILURE_COUNT,
)
from .pattern_database import PatternDatabase
from .pattern_hasher import PatternHasher

__all__ = [
    # Enums
    "PatternState",
    "ValidationResult",
    # Data models
    "ConflictPattern",
    "PatternMatch",
    "ResolutionOutcome",
    # Database
    "PatternDatabase",
    # Hasher
    "PatternHasher",
    # Constants
    "ACTIVE_THRESHOLD",
    "SUGGESTING_THRESHOLD",
    "DEPRECATION_FAILURE_COUNT",
]
