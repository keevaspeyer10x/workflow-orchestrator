"""
Task Provider - Backend-agnostic task/issue tracking.

This module provides a unified interface for managing tasks across
different backends (local JSON, GitHub Issues, etc.).

Usage:
    from src.task_provider import get_task_provider, TaskTemplate

    provider = get_task_provider()  # Auto-detect backend
    task = provider.create_task(TaskTemplate(
        title="My Task",
        description="Task description",
        problem_solved="What this fixes"
    ))
"""

from typing import Optional, Type, Dict

from .interface import (
    TaskProvider,
    Task,
    TaskTemplate,
    TaskStatus,
    TaskPriority,
)

# Registry of available providers
_PROVIDERS: Dict[str, Type[TaskProvider]] = {}


def register_provider(name: str, provider_class: Type[TaskProvider]) -> None:
    """
    Register a task provider class.

    Args:
        name: Provider name for registry
        provider_class: Provider class (must inherit from TaskProvider)
    """
    if not issubclass(provider_class, TaskProvider):
        raise TypeError(f"Provider class must inherit from TaskProvider")
    _PROVIDERS[name] = provider_class


def list_providers() -> list:
    """List all registered provider names."""
    return list(_PROVIDERS.keys())


def get_task_provider(
    name: Optional[str] = None,
    **kwargs
) -> TaskProvider:
    """
    Get a task provider instance.

    Args:
        name: Provider name (default: auto-detect)
        **kwargs: Additional arguments for provider constructor

    Returns:
        TaskProvider: An initialized provider instance

    Raises:
        ValueError: If provider not found
    """
    # Lazy import to avoid circular dependencies
    from .backends.local import LocalTaskProvider
    from .backends.github import GitHubTaskProvider

    # Register providers on first call
    if not _PROVIDERS:
        register_provider("local", LocalTaskProvider)
        register_provider("github", GitHubTaskProvider)

    # If no name specified, auto-detect
    if name is None:
        # Try GitHub first if in a git repo
        try:
            github_provider = GitHubTaskProvider(**kwargs)
            if github_provider.is_available():
                return github_provider
        except Exception:
            pass

        # Fallback to local
        return LocalTaskProvider(**kwargs)

    # Explicit name specified
    if name not in _PROVIDERS:
        available = ", ".join(list_providers())
        raise ValueError(f"Unknown provider '{name}'. Available: {available}")

    return _PROVIDERS[name](**kwargs)


__all__ = [
    # Interface
    "TaskProvider",
    "Task",
    "TaskTemplate",
    "TaskStatus",
    "TaskPriority",
    # Factory
    "get_task_provider",
    "register_provider",
    "list_providers",
]
