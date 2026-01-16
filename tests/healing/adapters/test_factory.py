"""Tests for adapter factory."""

import pytest
from unittest.mock import patch
import os


class TestAdapterFactory:
    """Test AdapterFactory functionality."""

    @pytest.fixture
    def factory(self):
        """Create an AdapterFactory instance."""
        from src.healing.adapters.factory import AdapterFactory

        return AdapterFactory(
            github_token="test-token",
            github_owner="test-owner",
            github_repo="test-repo",
        )

    def test_create_storage_local(self, factory):
        """FAC-001: create_storage() should return LocalStorageAdapter for LOCAL env."""
        from src.healing.adapters.storage_local import LocalStorageAdapter
        from src.healing.environment import Environment

        with patch("src.healing.adapters.factory.ENVIRONMENT", Environment.LOCAL):
            adapter = factory.create_storage()
            assert isinstance(adapter, LocalStorageAdapter)

    def test_create_storage_cloud(self, factory):
        """FAC-002: create_storage() should return GitHubStorageAdapter for CLOUD env."""
        from src.healing.adapters.storage_github import GitHubStorageAdapter
        from src.healing.environment import Environment

        with patch("src.healing.adapters.factory.ENVIRONMENT", Environment.CLOUD):
            adapter = factory.create_storage()
            assert isinstance(adapter, GitHubStorageAdapter)

    def test_create_git_local(self, factory):
        """FAC-003: create_git() should return LocalGitAdapter for LOCAL env."""
        from src.healing.adapters.git_local import LocalGitAdapter
        from src.healing.environment import Environment

        with patch("src.healing.adapters.factory.ENVIRONMENT", Environment.LOCAL):
            adapter = factory.create_git()
            assert isinstance(adapter, LocalGitAdapter)

    def test_create_git_cloud(self, factory):
        """FAC-004: create_git() should return GitHubAPIAdapter for CLOUD env."""
        from src.healing.adapters.git_github import GitHubAPIAdapter
        from src.healing.environment import Environment

        with patch("src.healing.adapters.factory.ENVIRONMENT", Environment.CLOUD):
            adapter = factory.create_git()
            assert isinstance(adapter, GitHubAPIAdapter)

    def test_create_cache_local(self, factory):
        """FAC-005: create_cache() should return LocalSQLiteCache for LOCAL env."""
        from src.healing.adapters.cache_local import LocalSQLiteCache
        from src.healing.environment import Environment

        with patch("src.healing.adapters.factory.ENVIRONMENT", Environment.LOCAL):
            adapter = factory.create_cache()
            assert isinstance(adapter, LocalSQLiteCache)

    def test_create_cache_cloud(self, factory):
        """FAC-006: create_cache() should return InMemoryCache for CLOUD env."""
        from src.healing.adapters.cache_memory import InMemoryCache
        from src.healing.environment import Environment

        with patch("src.healing.adapters.factory.ENVIRONMENT", Environment.CLOUD):
            adapter = factory.create_cache()
            assert isinstance(adapter, InMemoryCache)

    def test_create_execution_local(self, factory):
        """FAC-007: create_execution() should return LocalExecutionAdapter for LOCAL env."""
        from src.healing.adapters.execution_local import LocalExecutionAdapter
        from src.healing.environment import Environment

        with patch("src.healing.adapters.factory.ENVIRONMENT", Environment.LOCAL):
            adapter = factory.create_execution()
            assert isinstance(adapter, LocalExecutionAdapter)

    def test_create_execution_cloud(self, factory):
        """FAC-008: create_execution() should return GitHubActionsAdapter for CLOUD env."""
        from src.healing.adapters.execution_github import GitHubActionsAdapter
        from src.healing.environment import Environment

        with patch("src.healing.adapters.factory.ENVIRONMENT", Environment.CLOUD):
            adapter = factory.create_execution()
            assert isinstance(adapter, GitHubActionsAdapter)

    def test_factory_missing_credentials(self):
        """FAC-009: Factory should raise ConfigurationError for missing credentials."""
        from src.healing.adapters.factory import AdapterFactory, ConfigurationError
        from src.healing.environment import Environment

        factory = AdapterFactory()  # No credentials

        with patch("src.healing.adapters.factory.ENVIRONMENT", Environment.CLOUD):
            with pytest.raises(ConfigurationError):
                factory.create_storage()

    def test_create_all_adapters(self, factory):
        """Test creating all adapters in a single call."""
        from src.healing.environment import Environment

        with patch("src.healing.adapters.factory.ENVIRONMENT", Environment.LOCAL):
            storage = factory.create_storage()
            git = factory.create_git()
            cache = factory.create_cache()
            execution = factory.create_execution()

            assert storage is not None
            assert git is not None
            assert cache is not None
            assert execution is not None
