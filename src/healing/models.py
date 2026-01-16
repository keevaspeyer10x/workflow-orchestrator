"""Data models for self-healing infrastructure.

This module defines the core data structures used across the healing system.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Literal, Optional


@dataclass
class PatternContext:
    """Context captured with each pattern for intelligent filtering.

    Dimensions are ordered by matching weight (highest first).
    Used to determine pattern relevance across different contexts.
    """

    # Tier 1: Must match (weight 1.0)
    language: Optional[str] = None  # python, javascript, go, rust, java, unknown

    # Tier 2: Should match (weight 0.8)
    error_category: Optional[str] = None  # dependency, syntax, runtime, network, permission, config, test

    # Tier 3: Nice to match (weight 0.5)
    workflow_phase: Optional[str] = None  # plan, execute, review, verify, learn
    framework: Optional[str] = None  # react, django, express, etc.

    # Tier 4: Optional refinement (weight 0.3)
    os: Optional[str] = None  # linux, darwin, windows
    runtime_version: Optional[str] = None  # Semver string
    package_manager: Optional[str] = None  # pip, npm, cargo, go

    # Metadata
    extraction_confidence: float = 0.5  # How confident we are in this context

    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "PatternContext":
        """Create from dictionary."""
        return cls(
            language=data.get("language"),
            error_category=data.get("error_category"),
            workflow_phase=data.get("workflow_phase"),
            framework=data.get("framework"),
            os=data.get("os"),
            runtime_version=data.get("runtime_version"),
            package_manager=data.get("package_manager"),
            extraction_confidence=data.get("extraction_confidence", 0.5),
        )

    def derive_tags(self) -> list[str]:
        """Derive searchable tags from context."""
        tags = []

        if self.language:
            tags.append(self.language)

        if self.error_category:
            tags.append(f"cat:{self.error_category}")

        if self.workflow_phase:
            tags.append(f"phase:{self.workflow_phase}")

        if self.framework:
            tags.append(f"fw:{self.framework}")

        if self.package_manager:
            tags.append(f"pkg:{self.package_manager}")

        return tags


@dataclass
class ErrorEvent:
    """Unified error event from any source.

    Represents an error detected from workflow logs, transcripts,
    subprocess output, or hooks.
    """

    # Required fields
    error_id: str
    timestamp: datetime
    source: Literal["workflow_log", "transcript", "subprocess", "hook"]
    description: str

    # Optional content fields
    error_type: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    stack_trace: Optional[str] = None
    command: Optional[str] = None
    exit_code: Optional[int] = None

    # Computed by Fingerprinter
    fingerprint: Optional[str] = None
    fingerprint_coarse: Optional[str] = None

    # Context
    workflow_id: Optional[str] = None
    phase_id: Optional[str] = None
    project_id: Optional[str] = None

    # Pattern context for intelligent filtering
    context: Optional[PatternContext] = None


@dataclass
class FixAction:
    """Schema for fix actions stored in learnings.

    Phase 2 will use this for fix application.
    """

    action_type: Literal["diff", "command", "file_edit", "multi_step"]

    # For action_type="diff"
    diff: Optional[str] = None

    # For action_type="command"
    command: Optional[str] = None

    # For action_type="file_edit"
    file_path: Optional[str] = None
    find: Optional[str] = None
    replace: Optional[str] = None

    # For action_type="multi_step"
    steps: Optional[list] = None

    # Metadata
    requires_context: bool = False
    context_files: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "action_type": self.action_type,
            "diff": self.diff,
            "command": self.command,
            "file_path": self.file_path,
            "find": self.find,
            "replace": self.replace,
            "steps": self.steps,
            "requires_context": self.requires_context,
            "context_files": self.context_files,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FixAction":
        """Create from dictionary."""
        return cls(
            action_type=data.get("action_type", "diff"),
            diff=data.get("diff"),
            command=data.get("command"),
            file_path=data.get("file_path"),
            find=data.get("find"),
            replace=data.get("replace"),
            steps=data.get("steps"),
            requires_context=data.get("requires_context", False),
            context_files=data.get("context_files", []),
        )
