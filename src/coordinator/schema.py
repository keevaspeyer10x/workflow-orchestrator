"""
Coordinator Schema Definitions

Defines the structure for multi-agent coordination:
- Agent manifests (what each agent is working on)
- Agent registry (tracking all active agents)
- Completion detection (knowing when agents are done)

CRITICAL: Manifests are stored as GitHub Action artifacts, NOT committed to repo.
This avoids merge conflicts, commit noise, and security issues.
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime, timezone
from enum import Enum


# ============================================================================
# Enums
# ============================================================================

class AgentType(str, Enum):
    """Type of agent interface."""
    CLAUDE_WEB = "claude-web"
    CLAUDE_CLI = "claude-cli"
    CLAUDE_CODE = "claude-code"
    AIDER = "aider"
    CURSOR = "cursor"
    OTHER = "other"


class AgentStatus(str, Enum):
    """Current status of an agent's work."""
    INITIALIZING = "initializing"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"
    ABANDONED = "abandoned"


class RiskFlag(str, Enum):
    """Risk indicators for agent work."""
    SECURITY_SENSITIVE = "security_sensitive"
    API_CHANGES = "api_changes"
    DATABASE_CHANGES = "database_changes"
    DEPENDENCY_CHANGES = "dependency_changes"
    INFRASTRUCTURE = "infrastructure"
    BREAKING_CHANGE = "breaking_change"
    LARGE_REFACTOR = "large_refactor"
    NEW_EXTERNAL_SERVICE = "new_external_service"


# ============================================================================
# Agent Manifest Components
# ============================================================================

class AgentInfo(BaseModel):
    """Information about the agent itself."""
    id: str = Field(..., description="Unique agent identifier (e.g., claude-web-abc123)")
    type: AgentType = AgentType.CLAUDE_CODE
    session_id: str = Field(..., description="Session/conversation ID")
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_provider: str = "anthropic"
    model_name: str = "claude-sonnet-4"


class GitInfo(BaseModel):
    """Git branch information for the agent's work."""
    branch: str = Field(..., description="Branch name (e.g., claude/add-auth-abc123)")
    base_sha: str = Field(..., description="SHA of base commit (usually main)")
    head_sha: Optional[str] = Field(None, description="SHA of latest commit on branch")
    base_branch: str = "main"


class TaskInfo(BaseModel):
    """Information about the task the agent is working on."""
    description: str = Field(..., description="What the agent is implementing")
    user_prompt: Optional[str] = Field(None, description="Original user request")
    prd_reference: Optional[str] = Field(None, description="Reference to PRD if part of larger project")
    parent_task_id: Optional[str] = Field(None, description="Parent task for subtasks")


class WorkProgress(BaseModel):
    """Current progress of the agent's work."""
    status: AgentStatus = AgentStatus.INITIALIZING
    files_read: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    files_added: list[str] = Field(default_factory=list)
    files_deleted: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list, description="Key decisions made")
    tests_added: list[str] = Field(default_factory=list)
    dependencies_added: list[str] = Field(default_factory=list)


class InterfaceChange(BaseModel):
    """A change to an interface (API, function signature, etc.)."""
    file_path: str
    interface_type: Literal["function", "class", "api_endpoint", "type", "config"]
    name: str
    change_type: Literal["added", "modified", "removed", "signature_changed"]
    details: Optional[str] = None


class CompletionInfo(BaseModel):
    """Information about how/when agent completed."""
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    final_commit_sha: str
    completion_signal: Literal["explicit_marker", "commit_message", "inactivity", "user_confirmed"]
    summary: Optional[str] = None
    tests_status: Literal["passed", "failed", "skipped", "unknown"] = "unknown"


# ============================================================================
# Agent Manifest (Full)
# ============================================================================

class AgentManifest(BaseModel):
    """
    Complete manifest for an agent's work session.

    CRITICAL: This is stored as a GitHub Action artifact, NOT committed to repo.
    The coordinator derives actual file changes from git diff (don't trust blindly).
    """
    schema_version: str = "2.0"

    # Core info
    agent: AgentInfo
    git: GitInfo
    task: TaskInfo

    # Progress tracking
    work: WorkProgress = Field(default_factory=WorkProgress)

    # Risk assessment
    risk_flags: list[RiskFlag] = Field(default_factory=list)

    # Interface changes (for semantic conflict detection)
    interfaces_changed: list[InterfaceChange] = Field(default_factory=list)

    # Completion (None until agent is done)
    completion: Optional[CompletionInfo] = None

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_complete(self) -> bool:
        """Check if agent has completed its work."""
        return self.completion is not None

    @property
    def all_files_touched(self) -> list[str]:
        """Get all files the agent has modified, added, or deleted."""
        return list(set(
            self.work.files_modified +
            self.work.files_added +
            self.work.files_deleted
        ))

    def model_post_init(self, __context):
        """Update timestamp on any change."""
        self.updated_at = datetime.now(timezone.utc)


# ============================================================================
# Derived Manifest (From Git, Not Agent-Provided)
# ============================================================================

class DerivedManifest(BaseModel):
    """
    Manifest derived from actual git diff.

    CRITICAL: Don't trust agent-provided manifest blindly.
    Always derive actual changes from git diff.
    """
    agent_id: str
    branch: str
    base_sha: str
    head_sha: str

    # Derived from git diff
    files_modified: list[str] = Field(default_factory=list)
    files_added: list[str] = Field(default_factory=list)
    files_deleted: list[str] = Field(default_factory=list)

    # LLM-summarized changes
    summary: Optional[str] = None

    # Derived at
    derived_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def all_files_touched(self) -> list[str]:
        """Get all files touched according to git."""
        return list(set(
            self.files_modified +
            self.files_added +
            self.files_deleted
        ))


# ============================================================================
# Completion Detection
# ============================================================================

class CompletionStatus(BaseModel):
    """Result of completion detection."""
    is_complete: bool
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0.0 to 1.0")
    signals: list[str] = Field(default_factory=list, description="Signals that contributed")
    score: int = Field(description="Raw score before threshold comparison")
    threshold: int = 5


# ============================================================================
# Agent Registry Entry
# ============================================================================

class AgentRegistryEntry(BaseModel):
    """Entry in the agent registry."""
    agent_id: str
    branch: str
    status: AgentStatus
    task_description: str

    # Quick reference
    files_touched: list[str] = Field(default_factory=list)
    risk_flags: list[RiskFlag] = Field(default_factory=list)

    # Timing
    started_at: datetime
    last_activity: datetime
    completed_at: Optional[datetime] = None

    # Completion
    completion_status: Optional[CompletionStatus] = None

    # Reference to full manifest
    manifest_artifact_name: Optional[str] = None


# ============================================================================
# Conflict Cluster (for grouping related agents)
# ============================================================================

class ConflictCluster(BaseModel):
    """
    A group of agents that may have conflicts.

    Agents are clustered by:
    - Modified files overlap
    - Domain (auth, db, api, etc.)
    - Dependencies touched
    """
    cluster_id: str
    agent_ids: list[str] = Field(default_factory=list)
    reason: str = Field(description="Why these agents are clustered")
    files_in_common: list[str] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
