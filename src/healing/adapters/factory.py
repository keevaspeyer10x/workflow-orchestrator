"""Adapter factory for creating environment-appropriate adapters."""

from pathlib import Path
from typing import Optional

from ..environment import ENVIRONMENT, Environment
from .base import StorageAdapter, GitAdapter, CacheAdapter, ExecutionAdapter
from .storage_local import LocalStorageAdapter
from .storage_github import GitHubStorageAdapter
from .git_local import LocalGitAdapter
from .git_github import GitHubAPIAdapter
from .cache_local import LocalSQLiteCache
from .cache_memory import InMemoryCache
from .execution_local import LocalExecutionAdapter
from .execution_github import GitHubActionsAdapter


class ConfigurationError(Exception):
    """Raised when required configuration is missing."""


class AdapterFactory:
    """Create appropriate adapters based on environment."""

    def __init__(
        self,
        github_token: Optional[str] = None,
        github_owner: Optional[str] = None,
        github_repo: Optional[str] = None,
        base_path: Optional[Path] = None,
    ):
        """Initialize adapter factory.

        Args:
            github_token: GitHub API token (required for cloud).
            github_owner: GitHub repository owner (required for cloud).
            github_repo: GitHub repository name (required for cloud).
            base_path: Base path for local operations. Defaults to cwd.
        """
        self.github_token = github_token
        self.github_owner = github_owner
        self.github_repo = github_repo
        self.base_path = base_path or Path.cwd()

    def _check_github_config(self) -> None:
        """Check that GitHub configuration is available."""
        if not self.github_token:
            raise ConfigurationError(
                "GitHub token is required for cloud environment. "
                "Set github_token parameter."
            )
        if not self.github_owner or not self.github_repo:
            raise ConfigurationError(
                "GitHub owner and repo are required for cloud environment. "
                "Set github_owner and github_repo parameters."
            )

    def create_storage(self) -> StorageAdapter:
        """Create storage adapter based on environment."""
        if ENVIRONMENT == Environment.LOCAL:
            return LocalStorageAdapter(base_path=self.base_path)
        else:  # CLOUD or CI
            self._check_github_config()
            return GitHubStorageAdapter(
                owner=self.github_owner,
                repo=self.github_repo,
                token=self.github_token,
            )

    def create_git(self) -> GitAdapter:
        """Create git adapter based on environment."""
        if ENVIRONMENT == Environment.LOCAL:
            return LocalGitAdapter(repo_path=self.base_path)
        else:  # CLOUD or CI
            self._check_github_config()
            return GitHubAPIAdapter(
                owner=self.github_owner,
                repo=self.github_repo,
                token=self.github_token,
            )

    def create_cache(self) -> CacheAdapter:
        """Create cache adapter based on environment."""
        if ENVIRONMENT == Environment.LOCAL:
            return LocalSQLiteCache(
                path=self.base_path / ".claude" / "healing_cache.sqlite"
            )
        else:  # CLOUD or CI
            return InMemoryCache()

    def create_execution(self) -> ExecutionAdapter:
        """Create execution adapter based on environment."""
        if ENVIRONMENT == Environment.LOCAL:
            return LocalExecutionAdapter()
        else:  # CLOUD or CI
            self._check_github_config()
            return GitHubActionsAdapter(
                owner=self.github_owner,
                repo=self.github_repo,
                token=self.github_token,
            )

    def create_all(self) -> tuple[StorageAdapter, GitAdapter, CacheAdapter, ExecutionAdapter]:
        """Create all adapters.

        Returns:
            Tuple of (storage, git, cache, execution) adapters.
        """
        return (
            self.create_storage(),
            self.create_git(),
            self.create_cache(),
            self.create_execution(),
        )
