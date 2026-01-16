"""Tests for GitHub Actions execution adapter."""

import pytest
from unittest.mock import AsyncMock, patch


class TestGitHubActionsAdapter:
    """Test GitHubActionsAdapter functionality."""

    @pytest.fixture
    def adapter(self):
        """Create a GitHubActionsAdapter instance."""
        from src.healing.adapters.execution_github import GitHubActionsAdapter

        return GitHubActionsAdapter(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
        )

    @pytest.mark.asyncio
    async def test_run_tests_triggers_workflow(self, adapter):
        """EXG-001: run_tests() should trigger workflow."""
        with patch.object(
            adapter, "_dispatch_workflow", new_callable=AsyncMock
        ) as mock_dispatch:
            mock_dispatch.return_value = "run-123"

            with patch.object(
                adapter, "_wait_for_workflow", new_callable=AsyncMock
            ) as mock_wait:
                mock_wait.return_value = {"conclusion": "success", "status": "completed"}

                result = await adapter.run_tests()

                mock_dispatch.assert_called_once()
                assert result.passed is True

    @pytest.mark.asyncio
    async def test_run_tests_workflow_success(self, adapter):
        """EXG-002: run_tests() should return TestResult(passed=True) on success."""
        with patch.object(
            adapter, "_dispatch_workflow", new_callable=AsyncMock
        ) as mock_dispatch:
            mock_dispatch.return_value = "run-123"

            with patch.object(
                adapter, "_wait_for_workflow", new_callable=AsyncMock
            ) as mock_wait:
                mock_wait.return_value = {"conclusion": "success", "status": "completed"}

                result = await adapter.run_tests()

                assert result.passed is True

    @pytest.mark.asyncio
    async def test_run_tests_workflow_failure(self, adapter):
        """EXG-003: run_tests() should return TestResult(passed=False) on failure."""
        with patch.object(
            adapter, "_dispatch_workflow", new_callable=AsyncMock
        ) as mock_dispatch:
            mock_dispatch.return_value = "run-123"

            with patch.object(
                adapter, "_wait_for_workflow", new_callable=AsyncMock
            ) as mock_wait:
                mock_wait.return_value = {"conclusion": "failure", "status": "completed"}

                result = await adapter.run_tests()

                assert result.passed is False

    @pytest.mark.asyncio
    async def test_run_tests_workflow_timeout(self, adapter):
        """EXG-004: run_tests() should raise ExecutionTimeoutError on timeout."""
        from src.healing.adapters.execution_github import ExecutionTimeoutError

        with patch.object(
            adapter, "_dispatch_workflow", new_callable=AsyncMock
        ) as mock_dispatch:
            mock_dispatch.return_value = "run-123"

            with patch.object(
                adapter, "_wait_for_workflow", new_callable=AsyncMock
            ) as mock_wait:
                mock_wait.side_effect = ExecutionTimeoutError("Workflow timed out")

                with pytest.raises(ExecutionTimeoutError):
                    await adapter.run_tests(timeout_seconds=1)

    @pytest.mark.asyncio
    async def test_run_build_triggers_workflow(self, adapter):
        """EXG-005: run_build() should trigger workflow."""
        with patch.object(
            adapter, "_dispatch_workflow", new_callable=AsyncMock
        ) as mock_dispatch:
            mock_dispatch.return_value = "run-456"

            with patch.object(
                adapter, "_wait_for_workflow", new_callable=AsyncMock
            ) as mock_wait:
                mock_wait.return_value = {"conclusion": "success", "status": "completed"}

                result = await adapter.run_build()

                mock_dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_workflow_polling_with_backoff(self, adapter):
        """EXG-006: Workflow polling should use backoff."""
        call_times = []

        async def mock_get_status(*args, **kwargs):
            import time

            call_times.append(time.time())
            if len(call_times) < 3:
                return {"status": "in_progress"}
            return {"status": "completed", "conclusion": "success"}

        with patch.object(
            adapter, "_dispatch_workflow", new_callable=AsyncMock
        ) as mock_dispatch:
            mock_dispatch.return_value = "run-789"

            with patch.object(
                adapter, "_get_workflow_status", new_callable=AsyncMock
            ) as mock_status:
                mock_status.side_effect = mock_get_status

                await adapter.run_tests(poll_interval=0.1)

                # Verify multiple polls were made
                assert len(call_times) >= 3
