"""
V4 Security Module - Phase 0 & Phase 1.

Phase 0 (Security Hardening):
- Secure command execution (shell=False, allowlists, sandbox)
- Path traversal prevention (canonicalization, symlink checks)
- Approval authentication (HMAC signatures, OAuth, replay protection)
- Secure SQLite storage (AUTOINCREMENT, busy_timeout, WAL mode)

Phase 1 (Persistence Layer - V4.2):
- Async event sourcing with optimistic concurrency control
- Checkpoint store for fast recovery (90%+ replay reduction)
- Database adapter pattern for SQLite/PostgreSQL compatibility
- Event sourced repository with automatic checkpointing
"""

from .execution import (
    SecureCommand,
    SandboxConfig,
    ToolSecurityConfig,
    ArgumentRules,
    CommandResult,
    execute_secure,
    SecurityError,
    TimeoutError,
)
from .paths import (
    safe_path,
    validate_glob_pattern,
    PathTraversalError,
)
from .approval import (
    ApprovalRequest,
    Approval,
    ApprovalAuthenticator,
    InvalidSignatureError,
    UnauthorizedApproverError,
    ReplayAttackError,
)
from .storage import EventStore, Event, ConcurrencyError, DatabaseError
from .async_storage import (
    DatabaseAdapter,
    SQLiteAdapter,
    AsyncEventStore,
    SQLiteAsyncEventStore,
    CheckpointStore,
    Checkpoint,
    EventSourcedRepository,
)

__all__ = [
    # Execution
    "SecureCommand",
    "SandboxConfig",
    "ToolSecurityConfig",
    "ArgumentRules",
    "CommandResult",
    "execute_secure",
    "SecurityError",
    "TimeoutError",
    # Paths
    "safe_path",
    "validate_glob_pattern",
    "PathTraversalError",
    # Approval
    "ApprovalRequest",
    "Approval",
    "ApprovalAuthenticator",
    "InvalidSignatureError",
    "UnauthorizedApproverError",
    "ReplayAttackError",
    # Storage (Sync)
    "EventStore",
    "Event",
    "ConcurrencyError",
    "DatabaseError",
    # Storage (Async)
    "DatabaseAdapter",
    "SQLiteAdapter",
    "AsyncEventStore",
    "SQLiteAsyncEventStore",
    "CheckpointStore",
    "Checkpoint",
    "EventSourcedRepository",
]
