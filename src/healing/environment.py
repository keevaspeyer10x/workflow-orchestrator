"""Environment detection for self-healing infrastructure.

This module detects whether the code is running in:
- LOCAL: Full filesystem access, git CLI available
- CLOUD: API-only (Claude Code Web, no local filesystem)
- CI: GitHub Actions or other CI environment
"""

import os
from enum import Enum


class Environment(Enum):
    """Detected execution environment for healing operations."""

    LOCAL = "local"  # Full filesystem + git CLI
    CLOUD = "cloud"  # API-only (Claude Code Web)
    CI = "ci"  # GitHub Actions context


def detect_environment() -> Environment:
    """Auto-detect execution environment.

    Detection priority:
    1. CLAUDE_CODE_WEB env var -> CLOUD
    2. CI or GITHUB_ACTIONS env var -> CI
    3. Default -> LOCAL

    Returns:
        Environment: The detected environment.
    """
    # Cloud environment (Claude Code Web)
    if os.environ.get("CLAUDE_CODE_WEB"):
        return Environment.CLOUD

    # CI environment (GitHub Actions or generic CI)
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        return Environment.CI

    # Default to local
    return Environment.LOCAL


# Global singleton - initialized on module import
ENVIRONMENT = detect_environment()


def get_environment() -> Environment:
    """Get the detected environment.

    This function provides a consistent way to access the environment
    detection result, which can be overridden for testing.

    Returns:
        Environment: The current environment.
    """
    return ENVIRONMENT
