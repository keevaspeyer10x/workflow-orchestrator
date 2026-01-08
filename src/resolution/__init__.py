"""
Resolution Package

Phase 3: Basic conflict resolution system.

Stages:
1. Context Assembly - Gather all context for resolution
2. Intent Extraction - Extract agent intents and compare
3. Interface Harmonization - Make code buildable
4. Candidate Generation - Generate resolution candidates
5. Validation - Validate candidates (build + tests)
6. Selection - Select winning candidate

Target: Auto-resolve ~60% of conflicts.
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
)

from .context import ContextAssembler
from .intent import IntentExtractor
from .harmonizer import InterfaceHarmonizer
from .candidate import CandidateGenerator
from .validator import ResolutionValidator
from .pipeline import ResolutionPipeline, resolve_conflicts

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
    # Components
    "ContextAssembler",
    "IntentExtractor",
    "InterfaceHarmonizer",
    "CandidateGenerator",
    "ResolutionValidator",
    "ResolutionPipeline",
    "resolve_conflicts",
]
