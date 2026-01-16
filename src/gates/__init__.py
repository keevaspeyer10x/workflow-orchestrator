"""
Gates module - Gate validation and approval systems.

This module provides:
- Artifact-based gates: ArtifactGate, CommandGate, CompositeGate, HumanApprovalGate
- MindsGateProxy: Multi-model consensus for autonomous gate decisions (Issue #39)
- GateContext: Context information for gate evaluation
- Configuration loading for minds proxy settings
"""

# Re-export original artifact gate classes for backward compatibility
from src.artifact_gates import (
    ArtifactGate,
    CommandGate,
    HumanApprovalGate,
    CompositeGate,
    GateProtocol,
    DEFAULT_VALIDATOR,
)

# Minds proxy classes for Issue #39
from .minds_proxy import (
    MindsGateProxy,
    MindsDecision,
    GateContext,
    weighted_vote,
    should_escalate,
    re_deliberate,
    generate_rollback_command,
    write_decision,
)
from .minds_config import load_minds_config, MindsConfig

__all__ = [
    # Artifact gates
    "ArtifactGate",
    "CommandGate",
    "HumanApprovalGate",
    "CompositeGate",
    "GateProtocol",
    "DEFAULT_VALIDATOR",
    # Minds proxy
    "MindsGateProxy",
    "MindsDecision",
    "GateContext",
    "weighted_vote",
    "should_escalate",
    "re_deliberate",
    "generate_rollback_command",
    "write_decision",
    "load_minds_config",
    "MindsConfig",
]
