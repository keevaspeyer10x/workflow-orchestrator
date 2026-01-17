"""
Control Inversion V4 - Orchestrator-driven workflow execution.

This module contains the core components for V4:
- models: Data models for workflows, phases, gates, and state
- state: State persistence with file locking
- parser: YAML workflow parsing
- gate_engine: Programmatic gate validation
"""

from .models import (
    PhaseType,
    GateType,
    WorkflowStatus,
    GateStatus,
    FileExistsGate,
    CommandGate,
    NoPatternGate,
    JsonValidGate,
    GateSpec,
    GateResult,
    PhaseSpec,
    EnforcementConfig,
    WorkflowSpec,
    PhaseExecution,
    WorkflowState,
    PhaseInput,
    PhaseOutput,
    WorkflowResult,
)
from .state import StateStore, find_active_workflow
from .parser import parse_workflow, WorkflowParseError
from .gate_engine import GateEngine

__all__ = [
    # Enums
    "PhaseType",
    "GateType",
    "WorkflowStatus",
    "GateStatus",
    # Gate specifications
    "FileExistsGate",
    "CommandGate",
    "NoPatternGate",
    "JsonValidGate",
    "GateSpec",
    "GateResult",
    # Workflow specifications
    "PhaseSpec",
    "EnforcementConfig",
    "WorkflowSpec",
    # Runtime state
    "PhaseExecution",
    "WorkflowState",
    # Input/Output contracts
    "PhaseInput",
    "PhaseOutput",
    "WorkflowResult",
    # State management
    "StateStore",
    "find_active_workflow",
    # Parser
    "parse_workflow",
    "WorkflowParseError",
    # Gate engine
    "GateEngine",
]
