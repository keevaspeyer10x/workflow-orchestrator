"""
Conflict Detection Module

Detects and classifies conflicts between agent branches.

Phase 1 (MVP): Basic textual conflict detection using git merge-tree
Phase 2+: Semantic analysis, dependency conflicts, build testing
"""

from .detector import (
    ConflictType,
    ConflictSeverity,
    ConflictInfo,
    ConflictDetector,
    detect_conflicts,
)

__all__ = [
    "ConflictType",
    "ConflictSeverity",
    "ConflictInfo",
    "ConflictDetector",
    "detect_conflicts",
]
