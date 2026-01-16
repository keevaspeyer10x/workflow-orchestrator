"""Self-healing infrastructure for the workflow orchestrator.

This module provides automatic error detection, pattern matching, and fix application
to reduce manual intervention in workflow execution.
"""

from .environment import Environment, detect_environment, ENVIRONMENT

__all__ = [
    "Environment",
    "detect_environment",
    "ENVIRONMENT",
]
