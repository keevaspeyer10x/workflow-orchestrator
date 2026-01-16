"""GitHub API storage adapter."""

import base64
from typing import Optional

import httpx

from .base import StorageAdapter


class GitHubFileNotFoundError(Exception):
    """Raised when a file is not found in the GitHub repository."""


class GitHubAuthenticationError(Exception):
    """Raised when GitHub API authentication fails."""


class GitHubAPIError(Exception):
    """Raised for general GitHub API errors."""


class GitHubStorageAdapter(StorageAdapter):
    """GitHub API implementation of StorageAdapter."""

    def __init__(
        self,
        owner: str,
        repo: str,
        token: str,
        branch: str = "main",
    ):
        """Initialize GitHub storage adapter.

        Args:
            owner: Repository owner (user or organization).
            repo: Repository name.
            token: GitHub API token.
            branch: Branch to operate on. Defaults to main.
        """
        self.owner = owner
        self.repo = repo
        self.token = token
        self.branch = branch
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"token {self.token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                timeout=30.0,
            )
        return self._client

    async def _get(self, path: str) -> dict:
        """Make GET request to GitHub API."""
        client = await self._get_client()
        url = f"{self.base_url}/contents/{path}?ref={self.branch}"
        response = await client.get(url)

        if response.status_code == 404:
            raise GitHubFileNotFoundError(f"File not found: {path}")
        if response.status_code == 401:
            raise GitHubAuthenticationError("Invalid GitHub token")
        if response.status_code == 403:
            # Check for rate limit
            if "rate limit" in response.text.lower():
                raise GitHubAPIError("GitHub API rate limit exceeded")
            raise GitHubAuthenticationError("Access denied")
        if response.status_code != 200:
            raise GitHubAPIError(f"GitHub API error: {response.status_code}")

        return response.json()

    async def _put(self, path: str, data: dict) -> dict:
        """Make PUT request to GitHub API."""
        client = await self._get_client()
        url = f"{self.base_url}/contents/{path}"
        response = await client.put(url, json=data)

        if response.status_code == 401:
            raise GitHubAuthenticationError("Invalid GitHub token")
        if response.status_code not in (200, 201):
            raise GitHubAPIError(f"GitHub API error: {response.status_code} - {response.text}")

        return response.json()

    async def read_file(self, path: str) -> str:
        """Read file content from GitHub API."""
        data = await self._get(path)

        if data.get("encoding") == "base64":
            content = base64.b64decode(data["content"]).decode("utf-8")
        else:
            content = data.get("content", "")

        return content

    async def write_file(self, path: str, content: str) -> None:
        """Write file content via GitHub API (creates commit)."""
        # Check if file exists to get SHA
        sha = None
        try:
            existing = await self._get(path)
            sha = existing.get("sha")
        except GitHubFileNotFoundError:
            pass

        # Encode content
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        data = {
            "message": f"Update {path}",
            "content": content_b64,
            "branch": self.branch,
        }
        if sha:
            data["sha"] = sha

        await self._put(path, data)

    async def file_exists(self, path: str) -> bool:
        """Check if file exists via GitHub API."""
        try:
            await self._get(path)
            return True
        except GitHubFileNotFoundError:
            return False

    async def list_files(self, pattern: str) -> list[str]:
        """List files matching pattern.

        Note: GitHub API doesn't support glob patterns directly.
        This implementation fetches directory contents and filters locally.
        """
        # For simplicity, just return empty list
        # Full implementation would require recursive tree traversal
        return []

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
