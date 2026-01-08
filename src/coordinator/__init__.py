"""
Multi-Agent Coordinator Module

Orchestrates work from multiple AI agents working on parallel branches,
detecting conflicts, and managing merges to main.

Key Components:
- AgentManifest: Schema for what each agent is working on
- AgentRegistry: Tracks all active agent sessions
- AgentDiscovery: Finds agent branches (claude/*)
- ManifestStore: Stores/retrieves manifests via GitHub artifacts
- CompletionDetector: Detects when agents finish their work

Philosophy: Treat agent branches as untrusted. Always verify actual
changes from git diff, don't trust agent-provided manifests blindly.
"""

from .schema import (
    # Enums
    AgentType,
    AgentStatus,
    RiskFlag,

    # Manifest components
    AgentInfo,
    GitInfo,
    TaskInfo,
    WorkProgress,
    InterfaceChange,
    CompletionInfo,

    # Main schemas
    AgentManifest,
    DerivedManifest,
    CompletionStatus,
    AgentRegistryEntry,
    ConflictCluster,
)

from .discovery import (
    DiscoveredBranch,
    AgentDiscovery,
    discover_agent_branches,
)

from .manifest_store import (
    ManifestStore,
    get_manifest_store,
)

from .fast_path import (
    PRInfo,
    MergeResult,
    FastPathMerger,
    create_fast_path_pr,
)

__all__ = [
    # Enums
    "AgentType",
    "AgentStatus",
    "RiskFlag",

    # Manifest components
    "AgentInfo",
    "GitInfo",
    "TaskInfo",
    "WorkProgress",
    "InterfaceChange",
    "CompletionInfo",

    # Main schemas
    "AgentManifest",
    "DerivedManifest",
    "CompletionStatus",
    "AgentRegistryEntry",
    "ConflictCluster",

    # Discovery
    "DiscoveredBranch",
    "AgentDiscovery",
    "discover_agent_branches",

    # Manifest Storage
    "ManifestStore",
    "get_manifest_store",

    # Fast-Path Merge
    "PRInfo",
    "MergeResult",
    "FastPathMerger",
    "create_fast_path_pr",
]
