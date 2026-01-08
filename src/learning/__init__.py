"""
Learning module for conflict pattern memory and strategy optimization.

This module provides components for learning from past conflict resolutions
to improve future resolution suggestions.

Components:
- pattern_schema: Data models for conflict patterns (ConflictPattern, PatternMatch, ResolutionOutcome)
- strategy_schema: Data models for strategy tracking (StrategyStats, StrategyContext, StrategyRecommendation)
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
from .pattern_memory import ConflictPatternMemory, ResolutionSuggestion
from .strategy_schema import (
    ResolutionStrategy,
    ContextType,
    StrategyStats,
    StrategyContext,
    StrategyRecommendation,
    DEFAULT_STRATEGY_ORDER,
)
from .strategy_tracker import StrategyTracker

__all__ = [
    # Pattern Enums
    "PatternState",
    "ValidationResult",
    # Pattern Data models
    "ConflictPattern",
    "PatternMatch",
    "ResolutionOutcome",
    # Database
    "PatternDatabase",
    # Hasher
    "PatternHasher",
    # Memory
    "ConflictPatternMemory",
    "ResolutionSuggestion",
    # Pattern Constants
    "ACTIVE_THRESHOLD",
    "SUGGESTING_THRESHOLD",
    "DEPRECATION_FAILURE_COUNT",
    # Strategy Enums
    "ResolutionStrategy",
    "ContextType",
    # Strategy Data models
    "StrategyStats",
    "StrategyContext",
    "StrategyRecommendation",
    # Strategy Constants
    "DEFAULT_STRATEGY_ORDER",
    # Tracker
    "StrategyTracker",
]
