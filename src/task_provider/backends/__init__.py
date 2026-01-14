"""
Task Provider Backends.

This module exports all available task provider backends.
"""

from .local import LocalTaskProvider
from .github import GitHubTaskProvider

__all__ = [
    "LocalTaskProvider",
    "GitHubTaskProvider",
]
