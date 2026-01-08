"""
Resolution Package

Phase 3: Basic conflict resolution system.
Phase 5: Advanced resolution with multiple candidates.

Stages:
1. Context Assembly - Gather all context for resolution
2. Intent Extraction - Extract agent intents and compare
3. Interface Harmonization - Make code buildable
4. Candidate Generation - Generate resolution candidates
5. Validation - Validate candidates (build + tests)
6. Selection - Select winning candidate

Phase 3 Target: Auto-resolve ~60% of conflicts.
Phase 5 Target: Auto-resolve ~80% of conflicts.
"""

from .schema import (
    # Context
    FileVersion,
    RelatedFile,
    ProjectConvention,
    ConflictContext,
    # Intent
    Constraint,
    ExtractedIntent,
    IntentComparison,
    IntentAnalysis,
    # Harmonization
    InterfaceChange,
    AdapterCode,
    HarmonizedResult,
    # Candidate
    ResolutionCandidate,
    Resolution,
    # Phase 5
    ValidationTier,
    FlakyTestRecord,
    CritiqueResult,
    DiversityResult,
    TieredValidationResult,
)

from .context import ContextAssembler
from .intent import IntentExtractor
from .harmonizer import InterfaceHarmonizer
from .candidate import CandidateGenerator
from .validator import ResolutionValidator
from .pipeline import ResolutionPipeline, resolve_conflicts

# Phase 5 components
from .multi_candidate import MultiCandidateGenerator
from .diversity import DiversityChecker
from .validation_tiers import TieredValidator
from .flaky_handler import FlakyTestHandler
from .self_critic import SelfCritic

__all__ = [
    # Schema
    "FileVersion",
    "RelatedFile",
    "ProjectConvention",
    "ConflictContext",
    "Constraint",
    "ExtractedIntent",
    "IntentComparison",
    "IntentAnalysis",
    "InterfaceChange",
    "AdapterCode",
    "HarmonizedResult",
    "ResolutionCandidate",
    "Resolution",
    # Phase 5 Schema
    "ValidationTier",
    "FlakyTestRecord",
    "CritiqueResult",
    "DiversityResult",
    "TieredValidationResult",
    # Components
    "ContextAssembler",
    "IntentExtractor",
    "InterfaceHarmonizer",
    "CandidateGenerator",
    "ResolutionValidator",
    "ResolutionPipeline",
    "resolve_conflicts",
    # Phase 5 Components
    "MultiCandidateGenerator",
    "DiversityChecker",
    "TieredValidator",
    "FlakyTestHandler",
    "SelfCritic",
]
