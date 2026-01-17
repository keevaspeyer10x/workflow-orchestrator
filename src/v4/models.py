"""
Complete data model definitions for Control Inversion V4.
All types are fully specified - no ambiguity.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union
import json
import uuid


class PhaseType(str, Enum):
    """How strictly the phase is enforced"""
    STRICT = "strict"      # Cannot skip, must pass all gates
    GUIDED = "guided"      # Guidance provided, some flexibility


class GateType(str, Enum):
    """Types of gates that can be validated"""
    FILE_EXISTS = "file_exists"
    COMMAND = "command"
    NO_PATTERN = "no_pattern"
    JSON_VALID = "json_valid"


class WorkflowStatus(str, Enum):
    """Workflow execution status"""
    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class GateStatus(str, Enum):
    """Result of gate validation"""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ============================================================
# Gate Specifications
# ============================================================

@dataclass
class FileExistsGate:
    """Gate that checks if a file exists"""
    type: Literal["file_exists"] = "file_exists"
    path: str = ""  # Relative to working directory

    def to_dict(self) -> dict:
        return {"type": self.type, "path": self.path}


@dataclass
class CommandGate:
    """Gate that runs a command and checks exit code"""
    type: Literal["command"] = "command"
    cmd: str = ""
    exit_code: int = 0  # Expected exit code
    timeout: int = 300  # Seconds
    expect_empty: bool = False  # If True, stdout must be empty

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "cmd": self.cmd,
            "exit_code": self.exit_code,
            "timeout": self.timeout,
            "expect_empty": self.expect_empty
        }


@dataclass
class NoPatternGate:
    """Gate that checks files don't contain a pattern"""
    type: Literal["no_pattern"] = "no_pattern"
    pattern: str = ""  # Regex pattern
    paths: List[str] = field(default_factory=list)  # Glob patterns

    def to_dict(self) -> dict:
        return {"type": self.type, "pattern": self.pattern, "paths": self.paths}


@dataclass
class JsonValidGate:
    """Gate that checks a file is valid JSON"""
    type: Literal["json_valid"] = "json_valid"
    path: str = ""

    def to_dict(self) -> dict:
        return {"type": self.type, "path": self.path}


# Union of all gate types
GateSpec = Union[FileExistsGate, CommandGate, NoPatternGate, JsonValidGate]


@dataclass
class GateResult:
    """Result of validating a single gate"""
    gate_type: str
    status: GateStatus
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == GateStatus.PASSED


# ============================================================
# Phase and Workflow Specifications
# ============================================================

@dataclass
class PhaseSpec:
    """Specification for a single workflow phase"""
    id: str
    name: str
    phase_type: PhaseType = PhaseType.GUIDED
    description: str = ""
    gates: List[GateSpec] = field(default_factory=list)
    next_phase: Optional[str] = None  # None = terminal phase
    max_attempts: int = 3
    timeout: int = 3600  # Seconds (1 hour default)
    on_failure: Literal["retry", "fail"] = "retry"


@dataclass
class EnforcementConfig:
    """Configuration for what is enforced vs discretionary"""
    mode: Literal["strict", "permissive"] = "strict"
    programmatic: List[str] = field(default_factory=lambda: [
        "phase_order",
        "gate_validation",
        "workflow_completion"
    ])
    discretionary: List[str] = field(default_factory=lambda: [
        "implementation_approach",
        "task_ordering"
    ])


@dataclass
class WorkflowSpec:
    """Complete workflow specification parsed from YAML"""
    version: str
    name: str
    description: str = ""
    enforcement: EnforcementConfig = field(default_factory=EnforcementConfig)
    phases: List[PhaseSpec] = field(default_factory=list)

    def get_phase(self, phase_id: str) -> PhaseSpec:
        """Get a phase by ID"""
        for phase in self.phases:
            if phase.id == phase_id:
                return phase
        raise ValueError(f"Unknown phase: {phase_id}")

    def get_first_phase(self) -> PhaseSpec:
        """Get the first phase in the workflow"""
        if not self.phases:
            raise ValueError("Workflow has no phases")
        return self.phases[0]

    def get_next_phase(self, current_phase_id: str) -> Optional[PhaseSpec]:
        """Get the next phase after the current one"""
        current = self.get_phase(current_phase_id)
        if current.next_phase is None:
            return None
        return self.get_phase(current.next_phase)


# ============================================================
# Workflow State (Runtime)
# ============================================================

@dataclass
class PhaseExecution:
    """Record of a single phase execution"""
    phase_id: str
    attempt: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: Literal["running", "passed", "failed"] = "running"
    gate_results: List[GateResult] = field(default_factory=list)
    output_summary: str = ""


@dataclass
class WorkflowState:
    """Complete runtime state of a workflow execution"""
    # Identity
    workflow_id: str = field(default_factory=lambda: f"wf_{uuid.uuid4().hex[:8]}")
    workflow_name: str = ""
    task_description: str = ""

    # Progress
    status: WorkflowStatus = WorkflowStatus.INITIALIZED
    current_phase_id: Optional[str] = None
    current_attempt: int = 0

    # History
    phases_completed: List[str] = field(default_factory=list)
    phase_executions: List[PhaseExecution] = field(default_factory=list)

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    # Checkpointing
    checkpoint_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage"""
        return {
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "task_description": self.task_description,
            "status": self.status.value,
            "current_phase_id": self.current_phase_id,
            "current_attempt": self.current_attempt,
            "phases_completed": self.phases_completed,
            "phase_executions": [
                {
                    "phase_id": pe.phase_id,
                    "attempt": pe.attempt,
                    "started_at": pe.started_at.isoformat(),
                    "completed_at": pe.completed_at.isoformat() if pe.completed_at else None,
                    "status": pe.status,
                    "gate_results": [
                        {
                            "gate_type": gr.gate_type,
                            "status": gr.status.value,
                            "reason": gr.reason,
                            "details": gr.details
                        }
                        for gr in pe.gate_results
                    ],
                    "output_summary": pe.output_summary
                }
                for pe in self.phase_executions
            ],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "checkpoint_id": self.checkpoint_id
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'WorkflowState':
        """Deserialize from dictionary"""
        state = cls(
            workflow_id=data["workflow_id"],
            workflow_name=data["workflow_name"],
            task_description=data["task_description"],
            status=WorkflowStatus(data["status"]),
            current_phase_id=data["current_phase_id"],
            current_attempt=data["current_attempt"],
            phases_completed=data["phases_completed"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data["completed_at"] else None,
            checkpoint_id=data.get("checkpoint_id")
        )

        # Reconstruct phase executions
        for pe_data in data.get("phase_executions", []):
            pe = PhaseExecution(
                phase_id=pe_data["phase_id"],
                attempt=pe_data["attempt"],
                started_at=datetime.fromisoformat(pe_data["started_at"]),
                completed_at=datetime.fromisoformat(pe_data["completed_at"]) if pe_data["completed_at"] else None,
                status=pe_data["status"],
                output_summary=pe_data.get("output_summary", "")
            )
            for gr_data in pe_data.get("gate_results", []):
                pe.gate_results.append(GateResult(
                    gate_type=gr_data["gate_type"],
                    status=GateStatus(gr_data["status"]),
                    reason=gr_data.get("reason", ""),
                    details=gr_data.get("details", {})
                ))
            state.phase_executions.append(pe)

        return state

    def is_complete(self) -> bool:
        """Check if workflow has finished (success or failure)"""
        return self.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED)


# ============================================================
# Executor Input/Output Contracts
# ============================================================

@dataclass
class PhaseInput:
    """Input provided to agent for a phase"""
    phase_id: str
    phase_name: str
    task_description: str
    phase_description: str
    constraints: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    is_retry: bool = False
    retry_feedback: str = ""


@dataclass
class PhaseOutput:
    """Output captured from agent after phase execution"""
    phase_id: str
    success: bool
    summary: str = ""
    files_modified: List[str] = field(default_factory=list)
    error_message: str = ""


@dataclass
class WorkflowResult:
    """Final result of workflow execution"""
    workflow_id: str
    status: WorkflowStatus
    phases_completed: List[str]
    total_duration_seconds: float
    summary: str = ""
    error_message: str = ""
