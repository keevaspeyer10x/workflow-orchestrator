"""
V4 Security Module - Phase 0: Security Hardening.

This module provides:
- Secure command execution (shell=False, allowlists, sandbox)
- Path traversal prevention (canonicalization, symlink checks)
- Approval authentication (HMAC signatures, OAuth, replay protection)
- Secure SQLite storage (AUTOINCREMENT, busy_timeout, WAL mode)
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
from .storage import EventStore

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
    # Storage
    "EventStore",
]
