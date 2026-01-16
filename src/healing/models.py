"""Data models for self-healing infrastructure.

This module defines the core data structures used across the healing system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


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
