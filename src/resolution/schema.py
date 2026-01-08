"""
Resolution Schema Definitions

Data models for the conflict resolution pipeline:
- ConflictContext: All gathered context for resolution
- ExtractedIntent: Agent intent with constraints
- IntentComparison: Comparison between agent intents
- ResolutionCandidate: A candidate resolution
- HarmonizedResult: Result of interface harmonization
"""

from dataclasses import dataclass, field
from typing import Optional, Literal
from datetime import datetime, timezone

from ..conflict.pipeline import PipelineResult
from ..coordinator.schema import AgentManifest, DerivedManifest


# ============================================================================
# Context Assembly (Stage 1)
# ============================================================================

@dataclass
class FileVersion:
    """A specific version of a file."""
    path: str
    content: str
    source: str  # "base", "agent1", "agent2", etc.
    sha: Optional[str] = None


@dataclass
class RelatedFile:
    """A file related to the conflict (imports, callers, etc.)."""
    path: str
    content: str
    relationship: Literal["imports", "imported_by", "calls", "called_by", "same_module", "same_domain"]


@dataclass
class ProjectConvention:
    """A convention detected in the project."""
    name: str
    description: str
    examples: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)


@dataclass
class ConflictContext:
    """
    Complete context for resolving a conflict.

    Assembled by Stage 1 (ContextAssembler) from:
    - Agent manifests (from artifacts)
    - Git diffs (derived, not trusted)
    - File contents (base, agent versions)
    - Related files (imports, callers)
    - Project conventions
    """
    # Detection result
    detection_result: PipelineResult

    # Agent information
    agent_manifests: list[AgentManifest] = field(default_factory=list)
    derived_manifests: list[DerivedManifest] = field(default_factory=list)

    # Conflicting files
    base_files: list[FileVersion] = field(default_factory=list)
    agent_files: dict[str, list[FileVersion]] = field(default_factory=dict)  # agent_id -> files

    # Related context
    related_files: list[RelatedFile] = field(default_factory=list)
    conventions: list[ProjectConvention] = field(default_factory=list)

    # Git info
    base_branch: str = "main"
    base_sha: str = ""
    agent_branches: dict[str, str] = field(default_factory=dict)  # agent_id -> branch

    # Metadata
    assembled_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def conflicting_files(self) -> list[str]:
        """Get list of files in conflict."""
        if self.detection_result.textual_result:
            return [f.file_path for f in self.detection_result.textual_result.conflicting_files]
        return []

    @property
    def agent_ids(self) -> list[str]:
        """Get list of involved agent IDs."""
        return list(self.agent_files.keys())


# ============================================================================
# Intent Extraction (Stage 2)
# ============================================================================

@dataclass
class Constraint:
    """A constraint extracted from agent intent."""
    description: str
    constraint_type: Literal["hard", "soft"]
    evidence: str
    source: Literal["task", "code", "tests", "manifest", "inferred"]


@dataclass
class ExtractedIntent:
    """
    Intent extracted from an agent's work.

    Extracted by Stage 2 (IntentExtractor) from:
    - Agent manifest (task description)
    - Code changes (what was actually done)
    - Test additions (what behavior is expected)
    - Commit messages
    """
    agent_id: str

    # Core intent
    primary_intent: str  # One sentence summary
    secondary_effects: list[str] = field(default_factory=list)

    # Constraints
    hard_constraints: list[Constraint] = field(default_factory=list)
    soft_constraints: list[Constraint] = field(default_factory=list)

    # Supporting evidence
    assumptions: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)  # Citations to code/tests

    # Confidence
    confidence: Literal["high", "medium", "low"] = "medium"
    confidence_reasons: list[str] = field(default_factory=list)


@dataclass
class IntentComparison:
    """
    Comparison of intents from multiple agents.

    Determines if agent intents can coexist or conflict.
    """
    relationship: Literal["compatible", "conflicting", "orthogonal"]

    # Shared understanding
    shared_constraints: list[Constraint] = field(default_factory=list)

    # Conflicts
    conflicting_constraints: list[tuple] = field(default_factory=list)  # (constraint1, constraint2, reason)

    # Resolution hint
    suggested_resolution: str = ""
    requires_human_judgment: bool = False

    # Overall confidence
    confidence: Literal["high", "medium", "low"] = "medium"


@dataclass
class IntentAnalysis:
    """Complete intent analysis for all agents."""
    intents: list[ExtractedIntent] = field(default_factory=list)
    comparison: Optional[IntentComparison] = None
    overall_confidence: Literal["high", "medium", "low"] = "medium"

    @property
    def can_auto_resolve(self) -> bool:
        """Check if this can be auto-resolved."""
        if self.overall_confidence == "low":
            return False
        if self.comparison and self.comparison.requires_human_judgment:
            return False
        return True


# ============================================================================
# Interface Harmonization (Stage 3)
# ============================================================================

@dataclass
class InterfaceChange:
    """A change to an interface (function, class, API)."""
    file_path: str
    name: str
    interface_type: Literal["function", "class", "method", "api_endpoint", "type", "export"]
    change_type: Literal["added", "modified", "removed", "signature_changed"]
    agent_id: str
    old_signature: Optional[str] = None
    new_signature: Optional[str] = None


@dataclass
class AdapterCode:
    """Generated adapter code to bridge interface differences."""
    file_path: str
    code: str
    reason: str
    is_temporary: bool = True  # Mark for potential removal


@dataclass
class HarmonizedResult:
    """
    Result of interface harmonization.

    After harmonization:
    - All interfaces have a canonical form
    - Adapters bridge any incompatibilities
    - Code should build (tests may still fail)
    """
    # Interface decisions
    canonical_interfaces: list[InterfaceChange] = field(default_factory=list)
    adapters_generated: list[AdapterCode] = field(default_factory=list)

    # Call site updates
    call_sites_updated: list[tuple] = field(default_factory=list)  # (file, old_call, new_call)

    # Build status
    build_passes: bool = False
    build_errors: list[str] = field(default_factory=list)

    # Logging for escalation
    decisions_log: list[str] = field(default_factory=list)


# ============================================================================
# Candidate Generation (Stage 5 - basic for Phase 3)
# ============================================================================

@dataclass
class ResolutionCandidate:
    """
    A candidate resolution.

    Generated using one of several strategies:
    - agent1_primary: Keep agent 1's architecture, adapt agent 2's features
    - agent2_primary: Keep agent 2's architecture, adapt agent 1's features
    - convention_primary: Match existing repo patterns
    - fresh_synthesis: Re-implement from scratch (Phase 5)
    """
    candidate_id: str
    strategy: Literal["agent1_primary", "agent2_primary", "convention_primary", "fresh_synthesis"]

    # Git info
    branch_name: str
    diff_from_base: str = ""
    files_modified: list[str] = field(default_factory=list)

    # Validation results
    build_passed: bool = False
    lint_score: float = 0.0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0

    # Scoring (Phase 3: basic scoring)
    correctness_score: float = 0.0
    simplicity_score: float = 0.0
    convention_score: float = 0.0
    intent_satisfaction_score: float = 0.0
    total_score: float = 0.0

    # Explanation
    summary: str = ""
    technical_details: str = ""

    @property
    def is_viable(self) -> bool:
        """Check if this candidate passed basic validation."""
        return self.build_passed and self.tests_failed == 0


# ============================================================================
# Resolution Result
# ============================================================================

@dataclass
class Resolution:
    """
    Final resolution result.

    Either:
    - Successfully auto-resolved with winning candidate
    - Needs escalation with options
    """
    resolution_id: str

    # Outcome
    needs_escalation: bool = False
    escalation_reason: Optional[str] = None

    # Success case
    winning_candidate: Optional[ResolutionCandidate] = None
    ported_features: list[str] = field(default_factory=list)

    # PR info (if created)
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None

    # All candidates (for transparency)
    all_candidates: list[ResolutionCandidate] = field(default_factory=list)

    # Timing
    resolved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
