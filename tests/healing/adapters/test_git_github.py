"""Tests for GitHub git adapter."""

import pytest
from unittest.mock import AsyncMock, patch


class TestGitHubAPIAdapter:
    """Test GitHubAPIAdapter functionality."""

    @pytest.fixture
    def adapter(self):
        """Create a GitHubAPIAdapter instance."""
        from src.healing.adapters.git_github import GitHubAPIAdapter

        return GitHubAPIAdapter(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
        )

    @pytest.mark.asyncio
    async def test_create_branch_new(self, adapter):
        """GTG-001: create_branch() should create ref via API."""
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"object": {"sha": "base-sha-123"}}

            with patch.object(adapter, "_post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = {"ref": "refs/heads/new-branch"}
                await adapter.create_branch("new-branch", base="main")

                mock_post.assert_called_once()
                call_data = mock_post.call_args[0][1]
                assert "ref" in call_data
                assert "sha" in call_data

    @pytest.mark.asyncio
    async def test_create_branch_existing(self, adapter):
        """GTG-002: create_branch() should raise error for existing branch."""
        from src.healing.adapters.git_github import GitHubBranchExistsError

        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"object": {"sha": "base-sha"}}

            with patch.object(adapter, "_post", new_callable=AsyncMock) as mock_post:
                mock_post.side_effect = GitHubBranchExistsError("Branch already exists")

                with pytest.raises(GitHubBranchExistsError):
                    await adapter.create_branch("existing-branch")

    @pytest.mark.asyncio
    async def test_apply_diff(self, adapter):
        """GTG-003: apply_diff() should create commit via Trees API."""
        with patch.object(adapter, "_create_commit", new_callable=AsyncMock) as mock_commit:
            mock_commit.return_value = "new-commit-sha"

            sha = await adapter.apply_diff("diff content", message="Test commit")

            assert sha == "new-commit-sha"
            mock_commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_pr_valid(self, adapter):
        """GTG-004: create_pr() should create PR and return URL."""
        with patch.object(adapter, "_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {
                "html_url": "https://github.com/test-owner/test-repo/pull/1",
                "number": 1,
            }

            url = await adapter.create_pr(
                title="Test PR",
                body="Description",
                head="feature",
                base="main",
            )

            assert url == "https://github.com/test-owner/test-repo/pull/1"
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_pr_invalid_branch(self, adapter):
        """GTG-005: create_pr() should raise error for invalid branch."""
        from src.healing.adapters.git_github import GitHubAPIError

        with patch.object(adapter, "_post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = GitHubAPIError("Branch not found")

            with pytest.raises(GitHubAPIError):
                await adapter.create_pr(
                    title="Test",
                    body="Body",
                    head="nonexistent",
                    base="main",
                )

    @pytest.mark.asyncio
    async def test_merge_branch(self, adapter):
        """GTG-006: merge_branch() should merge via API."""
        with patch.object(adapter, "_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"sha": "merge-commit-sha"}

            await adapter.merge_branch("feature", into="main")

            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_branch(self, adapter):
        """GTG-007: delete_branch() should delete ref via API."""
        with patch.object(adapter, "_delete", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = None

            await adapter.delete_branch("feature")

            mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_authentication_failure(self, adapter):
        """GTG-008: Should raise AuthenticationError for invalid token."""
        from src.healing.adapters.git_github import GitHubAuthenticationError

        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = GitHubAuthenticationError("Bad credentials")

            with pytest.raises(GitHubAuthenticationError):
                await adapter.get_recent_commits()
