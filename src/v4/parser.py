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
