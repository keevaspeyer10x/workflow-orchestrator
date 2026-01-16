"""GitHub Actions execution adapter."""

import asyncio
from typing import Optional

import httpx

from .base import ExecutionAdapter, TestResult, BuildResult, LintResult


class ExecutionTimeoutError(Exception):
    """Raised when a workflow execution times out."""

    def __init__(self, message: str):
        super().__init__(message)


class GitHubActionsAdapter(ExecutionAdapter):
    """Trigger GitHub Actions workflows for verification."""

    def __init__(
        self,
        owner: str,
        repo: str,
        token: str,
        test_workflow: str = "test.yml",
        build_workflow: str = "build.yml",
        lint_workflow: str = "lint.yml",
    ):
        """Initialize GitHub Actions adapter.

        Args:
            owner: Repository owner.
            repo: Repository name.
            token: GitHub API token.
            test_workflow: Name of test workflow file.
            build_workflow: Name of build workflow file.
            lint_workflow: Name of lint workflow file.
        """
        self.owner = owner
        self.repo = repo
        self.token = token
        self.test_workflow = test_workflow
        self.build_workflow = build_workflow
        self.lint_workflow = lint_workflow
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

    async def _dispatch_workflow(
        self, workflow_file: str, inputs: Optional[dict] = None
    ) -> str:
        """Dispatch a workflow and return the run ID."""
        client = await self._get_client()

        # Dispatch workflow
        url = f"{self.base_url}/actions/workflows/{workflow_file}/dispatches"
        data = {
            "ref": "main",
            "inputs": inputs or {},
        }
        response = await client.post(url, json=data)
        if response.status_code not in (200, 204):
            raise RuntimeError(f"Failed to dispatch workflow: {response.text}")

        # Wait a bit for the run to appear
        await asyncio.sleep(2)

        # Get the most recent run
        runs_url = f"{self.base_url}/actions/workflows/{workflow_file}/runs?per_page=1"
        response = await client.get(runs_url)
        runs = response.json()
        if runs.get("workflow_runs"):
            return str(runs["workflow_runs"][0]["id"])

        return "unknown"

    async def _get_workflow_status(self, run_id: str) -> dict:
        """Get workflow run status."""
        client = await self._get_client()
        url = f"{self.base_url}/actions/runs/{run_id}"
        response = await client.get(url)
        return response.json()

    async def _wait_for_workflow(
        self,
        run_id: str,
        timeout_seconds: int = 600,
        poll_interval: float = 10.0,
    ) -> dict:
        """Wait for workflow to complete."""
        elapsed = 0
        while elapsed < timeout_seconds:
            status = await self._get_workflow_status(run_id)
            if status.get("status") == "completed":
                return status
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise ExecutionTimeoutError(f"Workflow timed out after {timeout_seconds} seconds")

    async def run_command(
        self, command: str, timeout_seconds: int = 300
    ) -> tuple[int, str, str]:
        """Run command - not directly supported in GitHub Actions.

        This would require a custom workflow that accepts a command input.
        """
        raise NotImplementedError(
            "run_command is not directly supported in GitHub Actions adapter. "
            "Use run_tests, run_build, or run_lint instead."
        )

    async def run_tests(
        self,
        test_pattern: Optional[str] = None,
        test_path: Optional[str] = None,
        timeout_seconds: int = 600,
        poll_interval: float = 10.0,
    ) -> TestResult:
        """Trigger test workflow and poll for result."""
        inputs = {}
        if test_pattern:
            inputs["pattern"] = test_pattern
        if test_path:
            inputs["path"] = test_path

        run_id = await self._dispatch_workflow(self.test_workflow, inputs)
        result = await self._wait_for_workflow(run_id, timeout_seconds, poll_interval)

        passed = result.get("conclusion") == "success"
        return TestResult(
            passed=passed,
            message=f"Workflow {result.get('conclusion', 'unknown')}",
            output=f"Run ID: {run_id}",
        )

    async def run_build(
        self,
        build_command: Optional[str] = None,
        cwd: Optional[str] = None,
        timeout_seconds: int = 300,
    ) -> BuildResult:
        """Trigger build workflow and poll for result."""
        run_id = await self._dispatch_workflow(self.build_workflow)
        result = await self._wait_for_workflow(run_id, timeout_seconds)

        passed = result.get("conclusion") == "success"
        return BuildResult(
            passed=passed,
            message=f"Workflow {result.get('conclusion', 'unknown')}",
            output=f"Run ID: {run_id}",
        )

    async def run_lint(
        self,
        lint_command: Optional[str] = None,
        timeout_seconds: int = 60,
    ) -> LintResult:
        """Trigger lint workflow and poll for result."""
        run_id = await self._dispatch_workflow(self.lint_workflow)
        result = await self._wait_for_workflow(run_id, timeout_seconds)

        passed = result.get("conclusion") == "success"
        return LintResult(
            passed=passed,
            message=f"Workflow {result.get('conclusion', 'unknown')}",
            output=f"Run ID: {run_id}",
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
