"""
Workflow Schema Definitions using Pydantic

This module defines the structure for workflow YAML files and runtime state.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime, timezone
from enum import Enum


class VerificationType(str, Enum):
    """Types of verification that can be performed on checklist items."""
    FILE_EXISTS = "file_exists"
    COMMAND = "command"
    MANUAL_GATE = "manual_gate"
    NONE = "none"


class ItemStatus(str, Enum):
    """Status of a checklist item."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    FAILED = "failed"


class PhaseStatus(str, Enum):
    """Status of a workflow phase."""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class WorkflowStatus(str, Enum):
    """Status of a workflow instance."""
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    PAUSED = "paused"


# ============================================================================
# YAML Schema (Workflow Definition)
# ============================================================================

class VerificationConfig(BaseModel):
    """Configuration for how to verify a checklist item is complete."""
    type: VerificationType = VerificationType.NONE
    path: Optional[str] = None  # For file_exists
    command: Optional[str] = None  # For command
    expect_exit_code: int = 0  # For command
    description: Optional[str] = None  # For manual_gate
    
    @field_validator('path')
    @classmethod
    def path_required_for_file_exists(cls, v, info):
        if info.data.get('type') == VerificationType.FILE_EXISTS and not v:
            raise ValueError('path is required for file_exists verification')
        return v
    
    @field_validator('command')
    @classmethod
    def command_required_for_command_type(cls, v, info):
        if info.data.get('type') == VerificationType.COMMAND and not v:
            raise ValueError('command is required for command verification')
        return v


class ChecklistItemDef(BaseModel):
    """Definition of a checklist item in the workflow YAML."""
    id: str
    name: str
    description: Optional[str] = None
    required: bool = True
    skippable: bool = True
    skip_conditions: list[str] = Field(default_factory=list)
    verification: VerificationConfig = Field(default_factory=VerificationConfig)
    agent: Optional[str] = None  # Which agent should handle this (e.g., "manus", "claude_code")
    notes: list[str] = Field(default_factory=list)  # Operating notes for this item
    
    @field_validator('id')
    @classmethod
    def id_must_be_valid(cls, v):
        if not v.replace('_', '').isalnum():
            raise ValueError('id must be alphanumeric with underscores only')
        return v


class PhaseDef(BaseModel):
    """Definition of a workflow phase in the YAML."""
    id: str
    name: str
    description: Optional[str] = None
    agent: Optional[str] = None  # Default agent for this phase
    executor: Optional[str] = None  # Which executor to use (e.g., "manus", "claude_code")
    items: list[ChecklistItemDef] = Field(default_factory=list)
    exit_gate: Optional[str] = None  # e.g., "human_approval", "all_tests_pass"
    notes: list[str] = Field(default_factory=list)  # Operating notes for this phase
    
    @field_validator('id')
    @classmethod
    def id_must_be_uppercase(cls, v):
        if not v.isupper():
            raise ValueError('phase id must be uppercase')
        return v.upper()


class WorkflowDef(BaseModel):
    """Complete workflow definition loaded from YAML."""
    name: str
    version: str = "1.0"
    description: Optional[str] = None
    phases: list[PhaseDef]
    settings: dict = Field(default_factory=dict)
    
    def get_phase(self, phase_id: str) -> Optional[PhaseDef]:
        """Get a phase by ID."""
        for phase in self.phases:
            if phase.id == phase_id:
                return phase
        return None
    
    def get_phase_index(self, phase_id: str) -> int:
        """Get the index of a phase."""
        for i, phase in enumerate(self.phases):
            if phase.id == phase_id:
                return i
        return -1
    
    def get_next_phase(self, current_phase_id: str) -> Optional[PhaseDef]:
        """Get the next phase after the current one."""
        idx = self.get_phase_index(current_phase_id)
        if idx >= 0 and idx < len(self.phases) - 1:
            return self.phases[idx + 1]
        return None


# ============================================================================
# Runtime State Schema
# ============================================================================

def _utc_now():
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class ItemState(BaseModel):
    """Runtime state of a checklist item."""
    id: str
    status: ItemStatus = ItemStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    skipped_at: Optional[datetime] = None
    skip_reason: Optional[str] = None
    notes: Optional[str] = None
    verification_result: Optional[dict] = None
    retry_count: int = 0
    files_modified: Optional[list[str]] = None  # WF-006: Track files modified during item completion


class PhaseState(BaseModel):
    """Runtime state of a workflow phase."""
    id: str
    status: PhaseStatus = PhaseStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    items: dict[str, ItemState] = Field(default_factory=dict)


class WorkflowState(BaseModel):
    """Complete runtime state of a workflow instance."""
    workflow_id: str
    workflow_type: str
    workflow_version: str
    task_description: str
    project: Optional[str] = None
    status: WorkflowStatus = WorkflowStatus.ACTIVE
    current_phase_id: str
    phases: dict[str, PhaseState] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    completed_at: Optional[datetime] = None
    metadata: dict = Field(default_factory=dict)
    # Version-locked workflow definition - stored at workflow start to prevent schema drift
    workflow_definition: Optional[dict] = None
    # Task-specific constraints (Feature 4)
    constraints: list[str] = Field(default_factory=list)
    
    def get_current_phase(self) -> Optional[PhaseState]:
        """Get the current phase state."""
        return self.phases.get(self.current_phase_id)
    
    def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc)


# ============================================================================
# Event Log Schema
# ============================================================================

class EventType(str, Enum):
    """Types of events that can be logged."""
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_ABANDONED = "workflow_abandoned"
    PHASE_STARTED = "phase_started"
    PHASE_COMPLETED = "phase_completed"
    ITEM_STARTED = "item_started"
    ITEM_COMPLETED = "item_completed"
    ITEM_SKIPPED = "item_skipped"
    ITEM_FAILED = "item_failed"
    VERIFICATION_PASSED = "verification_passed"
    VERIFICATION_FAILED = "verification_failed"
    HUMAN_OVERRIDE = "human_override"
    NOTE_ADDED = "note_added"
    ERROR = "error"


class WorkflowEvent(BaseModel):
    """A single event in the workflow log."""
    timestamp: datetime = Field(default_factory=_utc_now)
    event_type: EventType
    workflow_id: str
    phase_id: Optional[str] = None
    item_id: Optional[str] = None
    message: str
    details: dict = Field(default_factory=dict)
    actor: str = "system"  # "manus", "claude_code", "human", "system"
