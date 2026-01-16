"""GitHub API git adapter."""

from typing import Optional

import httpx

from .base import GitAdapter


class GitHubBranchExistsError(Exception):
    """Raised when trying to create a branch that already exists."""


class GitHubAuthenticationError(Exception):
    """Raised when GitHub API authentication fails."""


class GitHubAPIError(Exception):
    """Raised for general GitHub API errors."""


class GitHubAPIAdapter(GitAdapter):
    """GitHub API implementation of GitAdapter."""

    def __init__(
        self,
        owner: str,
        repo: str,
        token: str,
    ):
        """Initialize GitHub API adapter.

        Args:
            owner: Repository owner (user or organization).
            repo: Repository name.
            token: GitHub API token.
        """
        self.owner = owner
        self.repo = repo
        self.token = token
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

    async def _get(self, endpoint: str) -> dict:
        """Make GET request to GitHub API."""
        client = await self._get_client()
        url = f"{self.base_url}{endpoint}"
        response = await client.get(url)

        if response.status_code == 401:
            raise GitHubAuthenticationError("Invalid GitHub token")
        if response.status_code == 404:
            raise GitHubAPIError(f"Not found: {endpoint}")
        if response.status_code != 200:
            raise GitHubAPIError(f"GitHub API error: {response.status_code}")

        return response.json()

    async def _post(self, endpoint: str, data: dict) -> dict:
        """Make POST request to GitHub API."""
        client = await self._get_client()
        url = f"{self.base_url}{endpoint}"
        response = await client.post(url, json=data)

        if response.status_code == 401:
            raise GitHubAuthenticationError("Invalid GitHub token")
        if response.status_code == 422:
            error_msg = response.json().get("message", "Validation failed")
            if "Reference already exists" in error_msg:
                raise GitHubBranchExistsError("Branch already exists")
            raise GitHubAPIError(error_msg)
        if response.status_code not in (200, 201):
            raise GitHubAPIError(f"GitHub API error: {response.status_code}")

        return response.json()

    async def _delete(self, endpoint: str) -> None:
        """Make DELETE request to GitHub API."""
        client = await self._get_client()
        url = f"{self.base_url}{endpoint}"
        response = await client.delete(url)

        if response.status_code == 401:
            raise GitHubAuthenticationError("Invalid GitHub token")
        if response.status_code not in (200, 204):
            raise GitHubAPIError(f"GitHub API error: {response.status_code}")

    async def create_branch(self, name: str, base: str = "main") -> None:
        """Create branch via GitHub Refs API."""
        # Get base SHA
        ref = await self._get(f"/git/refs/heads/{base}")
        base_sha = ref["object"]["sha"]

        # Create new ref
        await self._post(
            "/git/refs",
            {
                "ref": f"refs/heads/{name}",
                "sha": base_sha,
            },
        )

    async def _create_commit(self, message: str, tree_sha: str, parent_sha: str) -> str:
        """Create a commit via GitHub API."""
        result = await self._post(
            "/git/commits",
            {
                "message": message,
                "tree": tree_sha,
                "parents": [parent_sha],
            },
        )
        return result["sha"]

    async def apply_diff(self, diff: str, message: str) -> str:
        """Apply diff and commit via GitHub API.

        Note: This is a simplified implementation that creates an empty commit.
        Full implementation would parse the diff and create proper tree objects.
        """
        # For now, just create a commit with the message
        # In practice, you'd need to:
        # 1. Parse the diff
        # 2. Create blob objects for changed files
        # 3. Create tree object
        # 4. Create commit
        return await self._create_commit(message, "placeholder", "placeholder")

    async def create_pr(
        self, title: str, body: str, head: str, base: str
    ) -> str:
        """Create PR via GitHub API."""
        result = await self._post(
            "/pulls",
            {
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            },
        )
        return result["html_url"]

    async def merge_branch(self, branch: str, into: str) -> None:
        """Merge branch via GitHub API."""
        await self._post(
            "/merges",
            {
                "base": into,
                "head": branch,
                "commit_message": f"Merge {branch} into {into}",
            },
        )

    async def delete_branch(self, name: str) -> None:
        """Delete branch via GitHub Refs API."""
        await self._delete(f"/git/refs/heads/{name}")

    async def get_recent_commits(self, count: int = 10) -> list[dict]:
        """Get recent commits via GitHub API."""
        result = await self._get(f"/commits?per_page={count}")
        return [
            {
                "sha": commit["sha"],
                "message": commit["commit"]["message"],
                "author": commit["commit"]["author"]["name"],
                "date": commit["commit"]["author"]["date"],
            }
            for commit in result
        ]

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
