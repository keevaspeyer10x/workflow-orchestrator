"""Adapters for environment-aware operations.

This package provides abstract interfaces and concrete implementations
for storage, git, cache, and execution operations across different environments.
"""

from .base import StorageAdapter, GitAdapter, CacheAdapter, ExecutionAdapter
from .factory import AdapterFactory, ConfigurationError

__all__ = [
    "StorageAdapter",
    "GitAdapter",
    "CacheAdapter",
    "ExecutionAdapter",
    "AdapterFactory",
    "ConfigurationError",
]
