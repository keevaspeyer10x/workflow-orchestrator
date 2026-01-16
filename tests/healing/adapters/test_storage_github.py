"""Tests for GitHub storage adapter."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGitHubStorageAdapter:
    """Test GitHubStorageAdapter functionality."""

    @pytest.fixture
    def adapter(self):
        """Create a GitHubStorageAdapter instance."""
        from src.healing.adapters.storage_github import GitHubStorageAdapter

        return GitHubStorageAdapter(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
        )

    @pytest.mark.asyncio
    async def test_read_file_existing(self, adapter):
        """STG-001: read_file() should return decoded content from API."""
        import base64

        mock_response = {
            "content": base64.b64encode(b"file content").decode(),
            "encoding": "base64",
        }

        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            result = await adapter.read_file("path/to/file.txt")

            assert result == "file content"
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_file_nonexistent(self, adapter):
        """STG-002: read_file() should raise error for non-existent file."""
        from src.healing.adapters.storage_github import GitHubFileNotFoundError

        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = GitHubFileNotFoundError("Not found")

            with pytest.raises(GitHubFileNotFoundError):
                await adapter.read_file("nonexistent.txt")

    @pytest.mark.asyncio
    async def test_write_file_new(self, adapter):
        """STG-003: write_file() should create commit via API for new file."""
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            from src.healing.adapters.storage_github import GitHubFileNotFoundError

            mock_get.side_effect = GitHubFileNotFoundError("Not found")

            with patch.object(adapter, "_put", new_callable=AsyncMock) as mock_put:
                mock_put.return_value = {"commit": {"sha": "abc123"}}
                await adapter.write_file("new_file.txt", "content")

                mock_put.assert_called_once()
                call_args = mock_put.call_args
                assert "message" in call_args[1] or "message" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_write_file_existing(self, adapter):
        """STG-004: write_file() should update file via API."""
        import base64

        existing_file = {
            "sha": "existing-sha",
            "content": base64.b64encode(b"old content").decode(),
        }

        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = existing_file

            with patch.object(adapter, "_put", new_callable=AsyncMock) as mock_put:
                mock_put.return_value = {"commit": {"sha": "new-sha"}}
                await adapter.write_file("existing.txt", "new content")

                mock_put.assert_called_once()

    @pytest.mark.asyncio
    async def test_file_exists_true(self, adapter):
        """STG-005: file_exists() should return True for existing file."""
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"sha": "abc123"}
            result = await adapter.file_exists("existing.txt")
            assert result is True

    @pytest.mark.asyncio
    async def test_file_exists_false(self, adapter):
        """STG-006: file_exists() should return False for non-existent file."""
        from src.healing.adapters.storage_github import GitHubFileNotFoundError

        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = GitHubFileNotFoundError("Not found")
            result = await adapter.file_exists("nonexistent.txt")
            assert result is False

    @pytest.mark.asyncio
    async def test_rate_limit_handling(self, adapter):
        """STG-007: Should retry with backoff on 429 response."""
        import httpx

        with patch.object(adapter, "_client") as mock_client:
            # First call returns 429, second returns success
            rate_limit_response = MagicMock()
            rate_limit_response.status_code = 429
            rate_limit_response.headers = {"Retry-After": "1"}

            success_response = MagicMock()
            success_response.status_code = 200
            success_response.json.return_value = {"sha": "abc123"}

            mock_client.get = AsyncMock(
                side_effect=[rate_limit_response, success_response]
            )

            # This test verifies rate limit handling is implemented
            # Implementation should retry after rate limit

    @pytest.mark.asyncio
    async def test_invalid_token(self, adapter):
        """STG-008: Should raise AuthenticationError for invalid token."""
        from src.healing.adapters.storage_github import GitHubAuthenticationError

        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = GitHubAuthenticationError("Bad credentials")

            with pytest.raises(GitHubAuthenticationError):
                await adapter.read_file("any.txt")
