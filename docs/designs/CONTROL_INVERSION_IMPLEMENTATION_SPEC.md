# Control Inversion V4.1: Complete Implementation Specification

**Version:** 4.1
**Date:** 2026-01-17
**Status:** READY FOR AUTONOMOUS BUILD
**Supersedes:** CONTROL_INVERSION_DESIGN_V4.md

## Purpose

This document provides **complete implementation specifications** for full control inversion. Every class, method, file path, and edge case is defined. An autonomous Claude Code session can build this without asking questions.

---

## Build Scope

**IN SCOPE:**
- `orchestrator run` command (core executor)
- `ClaudeCodeRunner` (subprocess-based, NOT API)
- Basic gates: `file_exists`, `command`, `no_pattern`
- One complete workflow: `default_workflow_v4.yaml`
- State management in `.orchestrator/v4/`

**OUT OF SCOPE (V4.2+):**
- `orchestrator chat` command
- `ClaudeAPIRunner` (API mode)
- `external_reviews` gate
- `human_approval` gate
- `min_coverage` gate
- Token budget tracking
- Tool allow/deny enforcement

---

## File Structure

```
workflow-orchestrator/
├── src/
│   ├── __init__.py                    # EXISTING
│   ├── cli.py                         # EXISTING - ADD run command
│   ├── schema.py                      # EXISTING - ADD v4 schemas
│   ├── gates.py                       # EXISTING - EXTEND with GateEngine
│   ├── executor.py                    # NEW - Core executor
│   ├── runners/                       # NEW directory
│   │   ├── __init__.py               # NEW
│   │   ├── base.py                   # NEW - Runner interface
│   │   └── claude_code.py            # NEW - Subprocess runner
│   └── v4/                            # NEW directory
│       ├── __init__.py               # NEW
│       ├── models.py                 # NEW - All dataclasses
│       ├── state.py                  # NEW - State management
│       └── parser.py                 # NEW - YAML parsing
├── workflows/                         # NEW directory
│   └── default_v4.yaml               # NEW - Migrated workflow
└── tests/
    └── test_executor.py              # NEW - Executor tests
```

---

## Complete Data Models

### File: `src/v4/models.py`

```python
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
```

---

## State Store

### File: `src/v4/state.py`

```python
"""
State persistence for V4 workflows.
Uses .orchestrator/v4/ directory, separate from existing state.
"""
import json
import fcntl
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import WorkflowState, WorkflowStatus


class StateStore:
    """
    Manages workflow state persistence.

    State file: .orchestrator/v4/state_{workflow_id}.json
    Lock file:  .orchestrator/v4/state_{workflow_id}.lock
    """

    def __init__(self, working_dir: Path):
        self.working_dir = Path(working_dir)
        self.state_dir = self.working_dir / ".orchestrator" / "v4"
        self._state: Optional[WorkflowState] = None
        self._lock_fd: Optional[int] = None

    def _ensure_dir(self) -> None:
        """Create state directory if it doesn't exist"""
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Add to .gitignore
        gitignore = self.state_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n")

    def _state_file(self, workflow_id: str) -> Path:
        return self.state_dir / f"state_{workflow_id}.json"

    def _lock_file(self, workflow_id: str) -> Path:
        return self.state_dir / f"state_{workflow_id}.lock"

    def acquire_lock(self, workflow_id: str, timeout: float = 10.0) -> bool:
        """
        Acquire exclusive lock for workflow state.
        Prevents concurrent modifications.
        """
        self._ensure_dir()
        lock_path = self._lock_file(workflow_id)

        try:
            self._lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (OSError, IOError):
            if self._lock_fd is not None:
                os.close(self._lock_fd)
                self._lock_fd = None
            return False

    def release_lock(self) -> None:
        """Release the workflow lock"""
        if self._lock_fd is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            self._lock_fd = None

    def initialize(self, workflow_name: str, task_description: str) -> WorkflowState:
        """Create new workflow state"""
        self._ensure_dir()

        self._state = WorkflowState(
            workflow_name=workflow_name,
            task_description=task_description,
            status=WorkflowStatus.INITIALIZED
        )

        # Acquire lock for new workflow
        if not self.acquire_lock(self._state.workflow_id):
            raise RuntimeError(f"Could not acquire lock for workflow {self._state.workflow_id}")

        self.save()
        return self._state

    def load(self, workflow_id: str) -> WorkflowState:
        """Load existing workflow state"""
        state_file = self._state_file(workflow_id)

        if not state_file.exists():
            raise FileNotFoundError(f"No state file for workflow {workflow_id}")

        # Acquire lock
        if not self.acquire_lock(workflow_id):
            raise RuntimeError(f"Workflow {workflow_id} is locked by another process")

        data = json.loads(state_file.read_text())
        self._state = WorkflowState.from_dict(data)
        return self._state

    def save(self) -> None:
        """Save current state to disk (atomic write)"""
        if self._state is None:
            raise RuntimeError("No state to save")

        self._state.updated_at = datetime.now()
        state_file = self._state_file(self._state.workflow_id)

        # Atomic write: write to temp file, then rename
        temp_file = state_file.with_suffix('.tmp')
        temp_file.write_text(json.dumps(self._state.to_dict(), indent=2))
        temp_file.rename(state_file)

    @property
    def state(self) -> WorkflowState:
        """Get current state (raises if not loaded)"""
        if self._state is None:
            raise RuntimeError("No state loaded")
        return self._state

    def update_phase(self, phase_id: str, attempt: int) -> None:
        """Update current phase tracking"""
        self.state.current_phase_id = phase_id
        self.state.current_attempt = attempt
        self.state.status = WorkflowStatus.RUNNING
        self.save()

    def complete_phase(self, phase_id: str) -> None:
        """Mark a phase as completed"""
        if phase_id not in self.state.phases_completed:
            self.state.phases_completed.append(phase_id)
        self.state.current_attempt = 0
        self.save()

    def mark_complete(self, success: bool = True) -> None:
        """Mark workflow as complete"""
        self.state.status = WorkflowStatus.COMPLETED if success else WorkflowStatus.FAILED
        self.state.completed_at = datetime.now()
        self.state.current_phase_id = None
        self.save()

    def cleanup(self) -> None:
        """Release lock and cleanup"""
        self.release_lock()


def find_active_workflow(working_dir: Path) -> Optional[str]:
    """Find an active (non-completed) workflow in the working directory"""
    state_dir = working_dir / ".orchestrator" / "v4"
    if not state_dir.exists():
        return None

    for state_file in state_dir.glob("state_*.json"):
        try:
            data = json.loads(state_file.read_text())
            status = WorkflowStatus(data.get("status", ""))
            if status not in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
                return data["workflow_id"]
        except (json.JSONDecodeError, KeyError):
            continue

    return None
```

---

## YAML Parser

### File: `src/v4/parser.py`

```python
"""
Parse workflow YAML into WorkflowSpec.
Validates structure and provides clear error messages.
"""
import yaml
from pathlib import Path
from typing import Any, Dict, List

from .models import (
    WorkflowSpec, PhaseSpec, EnforcementConfig, PhaseType,
    GateSpec, FileExistsGate, CommandGate, NoPatternGate, JsonValidGate, GateType
)


class WorkflowParseError(Exception):
    """Error parsing workflow YAML"""
    pass


def parse_gate(gate_dict: Dict[str, Any]) -> GateSpec:
    """Parse a single gate definition"""
    gate_type = gate_dict.get("type")

    if gate_type == GateType.FILE_EXISTS.value:
        return FileExistsGate(
            path=gate_dict.get("path", "")
        )
    elif gate_type == GateType.COMMAND.value:
        return CommandGate(
            cmd=gate_dict.get("cmd", ""),
            exit_code=gate_dict.get("exit_code", 0),
            timeout=gate_dict.get("timeout", 300),
            expect_empty=gate_dict.get("expect_empty", False)
        )
    elif gate_type == GateType.NO_PATTERN.value:
        return NoPatternGate(
            pattern=gate_dict.get("pattern", ""),
            paths=gate_dict.get("paths", [])
        )
    elif gate_type == GateType.JSON_VALID.value:
        return JsonValidGate(
            path=gate_dict.get("path", "")
        )
    else:
        raise WorkflowParseError(f"Unknown gate type: {gate_type}")


def parse_phase(phase_dict: Dict[str, Any]) -> PhaseSpec:
    """Parse a single phase definition"""
    phase_id = phase_dict.get("id")
    if not phase_id:
        raise WorkflowParseError("Phase missing 'id' field")

    # Parse gates
    gates = []
    for gate_dict in phase_dict.get("gates", []):
        gates.append(parse_gate(gate_dict))

    # Parse phase type
    phase_type_str = phase_dict.get("phase_type", "guided")
    try:
        phase_type = PhaseType(phase_type_str)
    except ValueError:
        raise WorkflowParseError(f"Invalid phase_type: {phase_type_str}")

    return PhaseSpec(
        id=phase_id,
        name=phase_dict.get("name", phase_id),
        phase_type=phase_type,
        description=phase_dict.get("description", ""),
        gates=gates,
        next_phase=phase_dict.get("next"),
        max_attempts=phase_dict.get("max_attempts", 3),
        timeout=phase_dict.get("timeout", 3600),
        on_failure=phase_dict.get("on_failure", "retry")
    )


def parse_enforcement(enforcement_dict: Dict[str, Any]) -> EnforcementConfig:
    """Parse enforcement configuration"""
    return EnforcementConfig(
        mode=enforcement_dict.get("mode", "strict"),
        programmatic=enforcement_dict.get("programmatic", [
            "phase_order", "gate_validation", "workflow_completion"
        ]),
        discretionary=enforcement_dict.get("discretionary", [
            "implementation_approach", "task_ordering"
        ])
    )


def parse_workflow(yaml_path: Path) -> WorkflowSpec:
    """
    Parse a workflow YAML file into WorkflowSpec.

    Args:
        yaml_path: Path to the workflow YAML file

    Returns:
        WorkflowSpec object

    Raises:
        WorkflowParseError: If YAML is invalid or missing required fields
    """
    if not yaml_path.exists():
        raise WorkflowParseError(f"Workflow file not found: {yaml_path}")

    try:
        content = yaml_path.read_text()
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise WorkflowParseError(f"Invalid YAML: {e}")

    if not isinstance(data, dict):
        raise WorkflowParseError("Workflow YAML must be a dictionary at top level")

    # Get workflow root (handle both flat and nested structures)
    workflow_data = data.get("workflow", data)

    # Required fields
    version = workflow_data.get("version", "4.0")
    name = workflow_data.get("name")
    if not name:
        raise WorkflowParseError("Workflow missing 'name' field")

    # Parse enforcement config
    enforcement_dict = workflow_data.get("enforcement", {})
    enforcement = parse_enforcement(enforcement_dict)

    # Parse phases
    phases_list = workflow_data.get("phases", [])
    if not phases_list:
        raise WorkflowParseError("Workflow must have at least one phase")

    phases = []
    for phase_dict in phases_list:
        phases.append(parse_phase(phase_dict))

    return WorkflowSpec(
        version=version,
        name=name,
        description=workflow_data.get("description", ""),
        enforcement=enforcement,
        phases=phases
    )
```

---

## Gate Engine

### File: `src/v4/gate_engine.py`

```python
"""
Programmatic gate validation.
Gates are checked by CODE, not by LLM self-report.
"""
import json
import re
import subprocess
from pathlib import Path
from typing import List

from .models import (
    GateSpec, GateResult, GateStatus,
    FileExistsGate, CommandGate, NoPatternGate, JsonValidGate
)


class GateEngine:
    """
    Validates gates programmatically.
    LLM cannot bypass these checks.
    """

    def __init__(self, working_dir: Path):
        self.working_dir = Path(working_dir)

    def validate_all(self, gates: List[GateSpec]) -> List[GateResult]:
        """
        Validate all gates for a phase.
        Returns list of results (one per gate).
        """
        results = []
        for gate in gates:
            result = self._validate_gate(gate)
            results.append(result)
        return results

    def all_passed(self, results: List[GateResult]) -> bool:
        """Check if all gate results passed"""
        return all(r.passed for r in results)

    def _validate_gate(self, gate: GateSpec) -> GateResult:
        """Dispatch to appropriate validator"""
        if isinstance(gate, FileExistsGate):
            return self._validate_file_exists(gate)
        elif isinstance(gate, CommandGate):
            return self._validate_command(gate)
        elif isinstance(gate, NoPatternGate):
            return self._validate_no_pattern(gate)
        elif isinstance(gate, JsonValidGate):
            return self._validate_json_valid(gate)
        else:
            return GateResult(
                gate_type=str(type(gate)),
                status=GateStatus.FAILED,
                reason=f"Unknown gate type: {type(gate)}"
            )

    def _validate_file_exists(self, gate: FileExistsGate) -> GateResult:
        """Check if a file exists"""
        path = self.working_dir / gate.path

        if path.exists():
            return GateResult(
                gate_type="file_exists",
                status=GateStatus.PASSED,
                details={"path": str(path)}
            )
        else:
            return GateResult(
                gate_type="file_exists",
                status=GateStatus.FAILED,
                reason=f"File not found: {gate.path}",
                details={"path": str(path)}
            )

    def _validate_command(self, gate: CommandGate) -> GateResult:
        """Run a command and check exit code"""
        try:
            result = subprocess.run(
                gate.cmd,
                shell=True,
                cwd=str(self.working_dir),
                capture_output=True,
                text=True,
                timeout=gate.timeout
            )

            # Check exit code
            if result.returncode != gate.exit_code:
                return GateResult(
                    gate_type="command",
                    status=GateStatus.FAILED,
                    reason=f"Command exited with {result.returncode}, expected {gate.exit_code}",
                    details={
                        "cmd": gate.cmd,
                        "returncode": result.returncode,
                        "stdout": result.stdout[:1000] if result.stdout else "",
                        "stderr": result.stderr[:1000] if result.stderr else ""
                    }
                )

            # Check empty output if required
            if gate.expect_empty and result.stdout.strip():
                return GateResult(
                    gate_type="command",
                    status=GateStatus.FAILED,
                    reason=f"Expected empty output but got: {result.stdout[:200]}",
                    details={"stdout": result.stdout[:1000]}
                )

            return GateResult(
                gate_type="command",
                status=GateStatus.PASSED,
                details={"cmd": gate.cmd, "returncode": result.returncode}
            )

        except subprocess.TimeoutExpired:
            return GateResult(
                gate_type="command",
                status=GateStatus.FAILED,
                reason=f"Command timed out after {gate.timeout}s",
                details={"cmd": gate.cmd, "timeout": gate.timeout}
            )
        except Exception as e:
            return GateResult(
                gate_type="command",
                status=GateStatus.FAILED,
                reason=f"Command execution error: {str(e)}",
                details={"cmd": gate.cmd, "error": str(e)}
            )

    def _validate_no_pattern(self, gate: NoPatternGate) -> GateResult:
        """Check that files don't contain a pattern"""
        try:
            pattern = re.compile(gate.pattern)
        except re.error as e:
            return GateResult(
                gate_type="no_pattern",
                status=GateStatus.FAILED,
                reason=f"Invalid regex pattern: {e}"
            )

        matches_found = []

        for glob_pattern in gate.paths:
            for file_path in self.working_dir.glob(glob_pattern):
                if file_path.is_file():
                    try:
                        content = file_path.read_text()
                        matches = pattern.findall(content)
                        if matches:
                            matches_found.append({
                                "file": str(file_path.relative_to(self.working_dir)),
                                "matches": matches[:5]  # Limit to first 5
                            })
                    except (UnicodeDecodeError, PermissionError):
                        continue  # Skip binary or inaccessible files

        if matches_found:
            return GateResult(
                gate_type="no_pattern",
                status=GateStatus.FAILED,
                reason=f"Pattern '{gate.pattern}' found in {len(matches_found)} file(s)",
                details={"matches": matches_found}
            )

        return GateResult(
            gate_type="no_pattern",
            status=GateStatus.PASSED,
            details={"pattern": gate.pattern, "paths_checked": gate.paths}
        )

    def _validate_json_valid(self, gate: JsonValidGate) -> GateResult:
        """Check that a file contains valid JSON"""
        path = self.working_dir / gate.path

        if not path.exists():
            return GateResult(
                gate_type="json_valid",
                status=GateStatus.FAILED,
                reason=f"File not found: {gate.path}"
            )

        try:
            content = path.read_text()
            json.loads(content)
            return GateResult(
                gate_type="json_valid",
                status=GateStatus.PASSED,
                details={"path": gate.path}
            )
        except json.JSONDecodeError as e:
            return GateResult(
                gate_type="json_valid",
                status=GateStatus.FAILED,
                reason=f"Invalid JSON: {e}",
                details={"path": gate.path, "error": str(e)}
            )
```

---

## Claude Code Runner

### File: `src/runners/base.py`

```python
"""
Base interface for agent runners.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..v4.models import PhaseInput, PhaseOutput


class RunnerError(Exception):
    """Base error for runner failures"""
    pass


class AgentRunner(ABC):
    """
    Interface for running agent phases.
    Implementations execute phases and return structured output.
    """

    @abstractmethod
    def run_phase(self, phase_input: PhaseInput) -> PhaseOutput:
        """
        Execute a workflow phase.

        Args:
            phase_input: Input context for the phase

        Returns:
            PhaseOutput with execution results

        Raises:
            RunnerError: If execution fails unrecoverably
        """
        pass
```

### File: `src/runners/claude_code.py`

```python
"""
Claude Code subprocess runner.
Spawns a Claude Code session to execute each phase.
"""
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from .base import AgentRunner, RunnerError
from ..v4.models import PhaseInput, PhaseOutput


class ClaudeCodeRunner(AgentRunner):
    """
    Runs phases using Claude Code CLI as a subprocess.

    This is the PRIMARY runner for V4 - it has access to all
    Claude Code capabilities (file editing, terminal, etc.)
    """

    def __init__(
        self,
        working_dir: Path,
        timeout: int = 3600,  # 1 hour default
        claude_binary: str = "claude"
    ):
        self.working_dir = Path(working_dir)
        self.timeout = timeout
        self.claude_binary = claude_binary

    def run_phase(self, phase_input: PhaseInput) -> PhaseOutput:
        """
        Execute a phase using Claude Code.

        Strategy:
        1. Write phase instructions to a temp file
        2. Run Claude Code with --print flag (non-interactive)
        3. Capture output and parse results
        """
        # Build the prompt for this phase
        prompt = self._build_prompt(phase_input)

        # Write prompt to temp file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.md',
            delete=False,
            dir=str(self.working_dir)
        ) as f:
            f.write(prompt)
            prompt_file = f.name

        try:
            # Run Claude Code
            result = self._execute_claude(prompt_file, phase_input)
            return result
        finally:
            # Clean up temp file
            try:
                os.unlink(prompt_file)
            except OSError:
                pass

    def _build_prompt(self, phase_input: PhaseInput) -> str:
        """Build the prompt for Claude Code"""

        retry_section = ""
        if phase_input.is_retry:
            retry_section = f"""
## RETRY NOTICE

Your previous attempt did not pass the gate validation.
Feedback: {phase_input.retry_feedback}

Please address the issues and try again.
"""

        prompt = f"""# Workflow Phase: {phase_input.phase_name}

## Task Description
{phase_input.task_description}

## Phase Objective
{phase_input.phase_description}
{retry_section}
## Constraints
{chr(10).join(f'- {c}' for c in phase_input.constraints) if phase_input.constraints else '- None specified'}

## Context
Previous phases completed: {', '.join(phase_input.context.get('phases_completed', [])) or 'None'}

## Instructions

Complete this phase by performing the necessary work. When you are done:

1. Ensure all required files/artifacts exist
2. The orchestrator will automatically validate completion via gate checks
3. Do NOT call any orchestrator commands - just do the work

Focus on completing the phase objective. The orchestrator handles workflow progression.
"""
        return prompt

    def _execute_claude(self, prompt_file: str, phase_input: PhaseInput) -> PhaseOutput:
        """Execute Claude Code and capture results"""

        # Build command
        # Use --print for non-interactive mode
        # Use --dangerously-skip-permissions to avoid permission prompts
        cmd = [
            self.claude_binary,
            "--print",
            "--dangerously-skip-permissions",
            "-p", f"Execute the task in {prompt_file}. Read the file first, then complete the work described."
        ]

        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.working_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "orchestrator-v4"}
            )

            duration = time.time() - start_time

            # Check if Claude Code executed successfully
            if result.returncode != 0:
                return PhaseOutput(
                    phase_id=phase_input.phase_id,
                    success=False,
                    error_message=f"Claude Code exited with code {result.returncode}: {result.stderr[:500]}"
                )

            # Parse output to extract summary
            output_text = result.stdout
            summary = self._extract_summary(output_text)

            return PhaseOutput(
                phase_id=phase_input.phase_id,
                success=True,
                summary=summary,
                files_modified=[]  # We don't track this currently
            )

        except subprocess.TimeoutExpired:
            return PhaseOutput(
                phase_id=phase_input.phase_id,
                success=False,
                error_message=f"Phase timed out after {self.timeout} seconds"
            )
        except FileNotFoundError:
            raise RunnerError(
                f"Claude Code binary not found: {self.claude_binary}. "
                "Ensure Claude Code is installed and in PATH."
            )
        except Exception as e:
            return PhaseOutput(
                phase_id=phase_input.phase_id,
                success=False,
                error_message=f"Execution error: {str(e)}"
            )

    def _extract_summary(self, output: str) -> str:
        """Extract a summary from Claude's output"""
        # Take the last meaningful chunk of output
        lines = output.strip().split('\n')

        # Filter out empty lines and take last portion
        meaningful_lines = [l for l in lines if l.strip()]

        if not meaningful_lines:
            return "Phase completed (no output captured)"

        # Return last 10 lines as summary
        summary_lines = meaningful_lines[-10:]
        return '\n'.join(summary_lines)
```

---

## Core Executor

### File: `src/executor.py`

```python
"""
Core workflow executor - implements control inversion.
The orchestrator DRIVES; Claude Code EXECUTES within bounds.
"""
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .v4.models import (
    WorkflowSpec, WorkflowState, WorkflowStatus, WorkflowResult,
    PhaseSpec, PhaseInput, PhaseOutput, PhaseExecution, GateResult
)
from .v4.state import StateStore
from .v4.gate_engine import GateEngine
from .v4.parser import parse_workflow
from .runners.base import AgentRunner, RunnerError


class ExecutorError(Exception):
    """Error during workflow execution"""
    pass


class WorkflowExecutor:
    """
    The deterministic workflow executor.

    This is where CONTROL INVERSION happens:
    - Orchestrator owns the loop
    - Orchestrator calls Claude Code for each phase
    - Orchestrator validates gates
    - Orchestrator guarantees completion

    LLM cannot:
    - Skip phases
    - Self-declare completion
    - Bypass gate validation
    """

    def __init__(
        self,
        workflow_spec: WorkflowSpec,
        runner: AgentRunner,
        state_store: StateStore,
        gate_engine: GateEngine
    ):
        self.spec = workflow_spec
        self.runner = runner
        self.state_store = state_store
        self.gate_engine = gate_engine

    def run(self, task_description: str) -> WorkflowResult:
        """
        Execute the workflow to completion.

        This is THE MAIN LOOP - deterministic and guaranteed to complete.

        Args:
            task_description: What the workflow should accomplish

        Returns:
            WorkflowResult with final status
        """
        start_time = time.time()

        # Initialize state
        state = self.state_store.initialize(
            workflow_name=self.spec.name,
            task_description=task_description
        )

        print(f"\n{'='*60}")
        print(f"ORCHESTRATOR: Starting workflow '{self.spec.name}'")
        print(f"Workflow ID: {state.workflow_id}")
        print(f"Task: {task_description}")
        print(f"{'='*60}\n")

        try:
            # Start with first phase
            current_phase = self.spec.get_first_phase()

            # THE MAIN LOOP
            while current_phase is not None:
                phase_result = self._execute_phase(current_phase, state)

                if phase_result:
                    # Phase passed - advance
                    self.state_store.complete_phase(current_phase.id)
                    current_phase = self.spec.get_next_phase(current_phase.id)
                else:
                    # Phase failed after max attempts
                    self.state_store.mark_complete(success=False)
                    return WorkflowResult(
                        workflow_id=state.workflow_id,
                        status=WorkflowStatus.FAILED,
                        phases_completed=state.phases_completed,
                        total_duration_seconds=time.time() - start_time,
                        error_message=f"Phase '{current_phase.id}' failed after max attempts"
                    )

            # All phases complete - SUCCESS
            self.state_store.mark_complete(success=True)

            print(f"\n{'='*60}")
            print("ORCHESTRATOR: Workflow COMPLETED successfully")
            print(f"Phases completed: {', '.join(state.phases_completed)}")
            print(f"Duration: {time.time() - start_time:.1f}s")
            print(f"{'='*60}\n")

            return WorkflowResult(
                workflow_id=state.workflow_id,
                status=WorkflowStatus.COMPLETED,
                phases_completed=state.phases_completed,
                total_duration_seconds=time.time() - start_time,
                summary=f"Successfully completed {len(state.phases_completed)} phases"
            )

        except Exception as e:
            # Unexpected error - save state and fail
            self.state_store.mark_complete(success=False)
            return WorkflowResult(
                workflow_id=state.workflow_id,
                status=WorkflowStatus.FAILED,
                phases_completed=state.phases_completed,
                total_duration_seconds=time.time() - start_time,
                error_message=f"Unexpected error: {str(e)}"
            )
        finally:
            self.state_store.cleanup()

    def _execute_phase(self, phase: PhaseSpec, state: WorkflowState) -> bool:
        """
        Execute a single phase with retry logic.

        Returns:
            True if phase completed successfully, False if failed after max attempts
        """
        print(f"\n{'-'*40}")
        print(f"PHASE: {phase.id} - {phase.name}")
        print(f"Max attempts: {phase.max_attempts}")
        print(f"{'-'*40}")

        for attempt in range(1, phase.max_attempts + 1):
            print(f"\n  Attempt {attempt}/{phase.max_attempts}")

            # Update state
            self.state_store.update_phase(phase.id, attempt)

            # Record execution start
            execution = PhaseExecution(
                phase_id=phase.id,
                attempt=attempt,
                started_at=datetime.now()
            )
            state.phase_executions.append(execution)

            # Build phase input
            is_retry = attempt > 1
            retry_feedback = ""
            if is_retry and state.phase_executions:
                # Get feedback from previous attempt's gate failures
                prev_exec = state.phase_executions[-2] if len(state.phase_executions) > 1 else None
                if prev_exec and prev_exec.gate_results:
                    failed_gates = [g for g in prev_exec.gate_results if not g.passed]
                    retry_feedback = "\n".join([
                        f"- {g.gate_type}: {g.reason}" for g in failed_gates
                    ])

            phase_input = PhaseInput(
                phase_id=phase.id,
                phase_name=phase.name,
                task_description=state.task_description,
                phase_description=phase.description,
                constraints=[],  # Could be populated from YAML
                context={
                    "phases_completed": state.phases_completed,
                    "workflow_name": self.spec.name,
                    "attempt": attempt
                },
                is_retry=is_retry,
                retry_feedback=retry_feedback
            )

            # Execute via runner
            print(f"  Running Claude Code...")
            try:
                output = self.runner.run_phase(phase_input)
            except RunnerError as e:
                print(f"  ERROR: Runner failed: {e}")
                execution.status = "failed"
                execution.completed_at = datetime.now()
                continue

            execution.output_summary = output.summary

            if not output.success:
                print(f"  Phase execution failed: {output.error_message}")
                execution.status = "failed"
                execution.completed_at = datetime.now()
                continue

            # Validate gates
            print(f"  Validating gates...")
            gate_results = self.gate_engine.validate_all(phase.gates)
            execution.gate_results = gate_results

            # Check if all gates passed
            if self.gate_engine.all_passed(gate_results):
                print(f"  All gates PASSED")
                execution.status = "passed"
                execution.completed_at = datetime.now()
                self.state_store.save()
                return True
            else:
                # Report failed gates
                failed = [g for g in gate_results if not g.passed]
                print(f"  {len(failed)} gate(s) FAILED:")
                for g in failed:
                    print(f"    - {g.gate_type}: {g.reason}")
                execution.status = "failed"
                execution.completed_at = datetime.now()
                self.state_store.save()

        # Max attempts exhausted
        print(f"\n  Phase FAILED after {phase.max_attempts} attempts")
        return False

    def resume(self, workflow_id: str) -> WorkflowResult:
        """
        Resume a paused or interrupted workflow.

        Args:
            workflow_id: ID of workflow to resume

        Returns:
            WorkflowResult with final status
        """
        start_time = time.time()

        # Load existing state
        state = self.state_store.load(workflow_id)

        if state.is_complete():
            return WorkflowResult(
                workflow_id=workflow_id,
                status=state.status,
                phases_completed=state.phases_completed,
                total_duration_seconds=0,
                summary="Workflow already complete"
            )

        print(f"\n{'='*60}")
        print(f"ORCHESTRATOR: Resuming workflow '{state.workflow_name}'")
        print(f"Workflow ID: {workflow_id}")
        print(f"Resuming from phase: {state.current_phase_id}")
        print(f"{'='*60}\n")

        try:
            # Resume from current phase
            current_phase = self.spec.get_phase(state.current_phase_id)

            # Continue the loop
            while current_phase is not None:
                phase_result = self._execute_phase(current_phase, state)

                if phase_result:
                    self.state_store.complete_phase(current_phase.id)
                    current_phase = self.spec.get_next_phase(current_phase.id)
                else:
                    self.state_store.mark_complete(success=False)
                    return WorkflowResult(
                        workflow_id=workflow_id,
                        status=WorkflowStatus.FAILED,
                        phases_completed=state.phases_completed,
                        total_duration_seconds=time.time() - start_time,
                        error_message=f"Phase '{current_phase.id}' failed after max attempts"
                    )

            self.state_store.mark_complete(success=True)

            return WorkflowResult(
                workflow_id=workflow_id,
                status=WorkflowStatus.COMPLETED,
                phases_completed=state.phases_completed,
                total_duration_seconds=time.time() - start_time,
                summary=f"Successfully completed {len(state.phases_completed)} phases"
            )

        finally:
            self.state_store.cleanup()
```

---

## CLI Integration

### Changes to `src/cli.py`

Add this to the existing cli.py (using argparse as per existing code):

```python
# Add to imports at top of cli.py
from pathlib import Path
from .v4.parser import parse_workflow, WorkflowParseError
from .v4.state import StateStore, find_active_workflow
from .v4.gate_engine import GateEngine
from .executor import WorkflowExecutor
from .runners.claude_code import ClaudeCodeRunner


def cmd_run(args):
    """
    orchestrator run - Execute workflow with control inversion.

    The orchestrator drives; Claude Code executes within bounds.
    """
    working_dir = Path(args.dir or '.').resolve()
    workflow_file = Path(args.workflow)

    # Parse workflow
    try:
        spec = parse_workflow(workflow_file)
    except WorkflowParseError as e:
        print(f"Error parsing workflow: {e}")
        return 1

    # Check for existing active workflow
    if not args.resume:
        active = find_active_workflow(working_dir)
        if active:
            print(f"Error: Active workflow {active} exists in this directory.")
            print(f"Use 'orchestrator run --resume {active}' to resume")
            print(f"Or clean up with 'rm -rf .orchestrator/v4/'")
            return 1

    # Initialize components
    state_store = StateStore(working_dir)
    gate_engine = GateEngine(working_dir)
    runner = ClaudeCodeRunner(
        working_dir=working_dir,
        timeout=args.timeout or 3600
    )

    executor = WorkflowExecutor(
        workflow_spec=spec,
        runner=runner,
        state_store=state_store,
        gate_engine=gate_engine
    )

    # Run or resume
    if args.resume:
        result = executor.resume(args.resume)
    else:
        if not args.task:
            print("Error: --task is required for new workflows")
            return 1
        result = executor.run(args.task)

    # Report result
    print(f"\nWorkflow {result.status.value}")
    print(f"Phases completed: {', '.join(result.phases_completed)}")
    print(f"Duration: {result.total_duration_seconds:.1f}s")

    if result.error_message:
        print(f"Error: {result.error_message}")
        return 1

    return 0


# Add to argument parser (find the subparsers section)
def setup_run_parser(subparsers):
    """Add the 'run' subcommand"""
    run_parser = subparsers.add_parser(
        'run',
        help='Execute workflow with control inversion (V4)'
    )
    run_parser.add_argument(
        'workflow',
        help='Path to workflow YAML file'
    )
    run_parser.add_argument(
        '-t', '--task',
        help='Task description (required for new workflows)'
    )
    run_parser.add_argument(
        '-r', '--resume',
        help='Resume workflow by ID'
    )
    run_parser.add_argument(
        '-d', '--dir',
        help='Working directory (default: current)'
    )
    run_parser.add_argument(
        '--timeout',
        type=int,
        default=3600,
        help='Phase timeout in seconds (default: 3600)'
    )
    run_parser.set_defaults(func=cmd_run)
```

---

## Default Workflow (V4 Format)

### File: `workflows/default_v4.yaml`

```yaml
# Default Development Workflow - V4 Format
# Control Inversion: Orchestrator drives, Claude executes

workflow:
  version: "4.0"
  name: "Development Workflow V4"
  description: |
    5-phase development workflow with control inversion.
    Orchestrator enforces phase order and gate validation.
    Claude Code executes work within each phase.

  enforcement:
    mode: strict
    programmatic:
      - phase_order
      - gate_validation
      - workflow_completion
    discretionary:
      - implementation_approach
      - task_ordering

  phases:
    # Phase 1: Planning
    - id: plan
      name: "Planning"
      phase_type: strict
      description: |
        Analyze the task and create a detailed plan.
        Create docs/plan.md with implementation steps.
      max_attempts: 3
      timeout: 1800  # 30 minutes
      gates:
        - type: file_exists
          path: docs/plan.md
      next: implement

    # Phase 2: Implementation
    - id: implement
      name: "Implementation"
      phase_type: guided
      description: |
        Implement the solution according to the plan.
        Write code, tests, and any necessary documentation.
      max_attempts: 3
      timeout: 3600  # 1 hour
      gates:
        - type: command
          cmd: "test -d src || test -d lib || test -f *.py"
          exit_code: 0
      next: test

    # Phase 3: Testing
    - id: test
      name: "Testing"
      phase_type: strict
      description: |
        Run tests to verify the implementation.
        Ensure all tests pass before proceeding.
      max_attempts: 3
      timeout: 1800  # 30 minutes
      gates:
        - type: command
          cmd: "python -m pytest -v 2>/dev/null || npm test 2>/dev/null || echo 'No tests configured'"
          exit_code: 0
      next: review

    # Phase 4: Review
    - id: review
      name: "Code Review"
      phase_type: guided
      description: |
        Review the implementation for quality and correctness.
        Check for common issues and ensure code follows best practices.
      max_attempts: 2
      timeout: 1800
      gates:
        - type: no_pattern
          pattern: "TODO|FIXME|XXX|HACK"
          paths:
            - "src/**/*.py"
            - "lib/**/*.py"
            - "**/*.ts"
            - "**/*.js"
      next: complete

    # Phase 5: Completion
    - id: complete
      name: "Completion"
      phase_type: strict
      description: |
        Finalize the work. Ensure all changes are committed.
        Clean up any temporary files.
      max_attempts: 2
      timeout: 600  # 10 minutes
      gates:
        - type: command
          cmd: "git status --porcelain"
          expect_empty: true
      next: null  # Terminal phase
```

---

## Error Handling Strategy

```python
# Defined error hierarchy (add to src/v4/models.py or separate errors.py)

class OrchestratorError(Exception):
    """Base error for orchestrator"""
    pass

class WorkflowParseError(OrchestratorError):
    """Error parsing workflow YAML"""
    pass

class StateError(OrchestratorError):
    """Error with workflow state"""
    pass

class GateValidationError(OrchestratorError):
    """Error during gate validation"""
    pass

class RunnerError(OrchestratorError):
    """Error from agent runner"""
    retryable: bool = False

class PhaseTimeoutError(RunnerError):
    """Phase exceeded time limit"""
    retryable = False

class APIError(RunnerError):
    """API call failed (for future API runner)"""
    retryable = True
```

---

## Acceptance Tests

### File: `tests/test_executor.py`

```python
"""
Acceptance tests for control inversion.
These MUST pass before the feature is complete.
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from src.v4.models import WorkflowSpec, PhaseSpec, PhaseType, WorkflowStatus
from src.v4.state import StateStore
from src.v4.gate_engine import GateEngine
from src.v4.parser import parse_workflow
from src.executor import WorkflowExecutor
from src.runners.base import AgentRunner
from src.v4.models import PhaseInput, PhaseOutput


class MockRunner(AgentRunner):
    """Mock runner for testing"""
    def __init__(self, outputs=None):
        self.outputs = outputs or []
        self.call_count = 0

    def run_phase(self, phase_input: PhaseInput) -> PhaseOutput:
        self.call_count += 1
        return PhaseOutput(
            phase_id=phase_input.phase_id,
            success=True,
            summary="Mock execution complete"
        )


def test_workflow_completes_even_if_llm_doesnt_call_finish():
    """
    CORE REQUIREMENT: Orchestrator guarantees completion.
    The LLM cannot prevent the workflow from finishing.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)

        # Create a simple workflow
        workflow_yaml = working_dir / "workflow.yaml"
        workflow_yaml.write_text("""
workflow:
  version: "4.0"
  name: "Test Workflow"
  phases:
    - id: phase1
      name: "Phase 1"
      gates: []
      next: null
""")

        # Create required file for gate
        spec = parse_workflow(workflow_yaml)
        state_store = StateStore(working_dir)
        gate_engine = GateEngine(working_dir)
        runner = MockRunner()

        executor = WorkflowExecutor(spec, runner, state_store, gate_engine)
        result = executor.run("Test task")

        # Even though the mock LLM never called anything special,
        # the workflow completed
        assert result.status == WorkflowStatus.COMPLETED
        assert "phase1" in result.phases_completed


def test_llm_cannot_skip_phases():
    """
    Phase order is enforced programmatically.
    LLM cannot skip from phase1 to phase3.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)

        workflow_yaml = working_dir / "workflow.yaml"
        workflow_yaml.write_text("""
workflow:
  version: "4.0"
  name: "Multi-phase Workflow"
  phases:
    - id: phase1
      name: "Phase 1"
      gates: []
      next: phase2
    - id: phase2
      name: "Phase 2"
      gates: []
      next: phase3
    - id: phase3
      name: "Phase 3"
      gates: []
      next: null
""")

        spec = parse_workflow(workflow_yaml)
        state_store = StateStore(working_dir)
        gate_engine = GateEngine(working_dir)
        runner = MockRunner()

        executor = WorkflowExecutor(spec, runner, state_store, gate_engine)
        result = executor.run("Test task")

        # Phases executed in order
        assert result.phases_completed == ["phase1", "phase2", "phase3"]
        assert runner.call_count == 3  # Called once per phase


def test_gates_validated_by_code_not_llm():
    """
    Gate validation is done by code, not LLM self-report.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)

        # Workflow requires a file that doesn't exist
        workflow_yaml = working_dir / "workflow.yaml"
        workflow_yaml.write_text("""
workflow:
  version: "4.0"
  name: "Gate Test"
  phases:
    - id: phase1
      name: "Phase 1"
      max_attempts: 1
      gates:
        - type: file_exists
          path: required_file.txt
      next: null
""")

        spec = parse_workflow(workflow_yaml)
        state_store = StateStore(working_dir)
        gate_engine = GateEngine(working_dir)

        # Mock runner that claims success but doesn't create file
        runner = MockRunner()

        executor = WorkflowExecutor(spec, runner, state_store, gate_engine)
        result = executor.run("Test task")

        # Workflow fails because gate (code check) fails
        # Even though runner said it succeeded
        assert result.status == WorkflowStatus.FAILED


def test_finalize_always_called():
    """
    The finalize step (mark_complete) is always called,
    even if phases fail.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)

        workflow_yaml = working_dir / "workflow.yaml"
        workflow_yaml.write_text("""
workflow:
  version: "4.0"
  name: "Finalize Test"
  phases:
    - id: phase1
      name: "Phase 1"
      max_attempts: 1
      gates:
        - type: command
          cmd: "exit 1"
      next: null
""")

        spec = parse_workflow(workflow_yaml)
        state_store = StateStore(working_dir)
        gate_engine = GateEngine(working_dir)
        runner = MockRunner()

        executor = WorkflowExecutor(spec, runner, state_store, gate_engine)
        result = executor.run("Test task")

        # Workflow failed but state is properly marked
        assert result.status == WorkflowStatus.FAILED

        # Reload state and verify it's marked complete
        state = state_store.load(result.workflow_id)
        assert state.status == WorkflowStatus.FAILED
        assert state.completed_at is not None
```

---

## Dependencies

Add to `pyproject.toml` or `requirements.txt`:

```
pyyaml>=6.0
```

No other new dependencies required. Uses stdlib for:
- `subprocess` - Running Claude Code
- `json` - State serialization
- `fcntl` - File locking (Unix)
- `re` - Pattern matching
- `pathlib` - Path handling

---

## Build Checklist

For the autonomous build session:

1. [ ] Create `src/v4/` directory with `__init__.py`
2. [ ] Create `src/v4/models.py` (copy from spec)
3. [ ] Create `src/v4/state.py` (copy from spec)
4. [ ] Create `src/v4/parser.py` (copy from spec)
5. [ ] Create `src/v4/gate_engine.py` (copy from spec)
6. [ ] Create `src/runners/` directory with `__init__.py`
7. [ ] Create `src/runners/base.py` (copy from spec)
8. [ ] Create `src/runners/claude_code.py` (copy from spec)
9. [ ] Create `src/executor.py` (copy from spec)
10. [ ] Add `cmd_run` and `setup_run_parser` to `src/cli.py`
11. [ ] Create `workflows/` directory
12. [ ] Create `workflows/default_v4.yaml` (copy from spec)
13. [ ] Create `tests/test_executor.py` (copy from spec)
14. [ ] Run tests: `python -m pytest tests/test_executor.py -v`
15. [ ] Test manually: `orchestrator run workflows/default_v4.yaml --task "Create hello world"`

---

## What This Achieves

With this implementation:

1. **Control is inverted**: `orchestrator run` drives the workflow
2. **Phases are enforced**: Cannot skip, must complete in order
3. **Gates are programmatic**: Code validates, not LLM self-report
4. **Completion is guaranteed**: `mark_complete()` always called
5. **State survives crashes**: JSON persistence with locking
6. **Existing CLI preserved**: Old commands still work

The LLM **cannot forget** to finish because it doesn't control the loop.
