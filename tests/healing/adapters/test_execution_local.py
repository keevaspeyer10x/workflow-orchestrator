"""Tests for local execution adapter."""

import pytest
import tempfile
from pathlib import Path


class TestLocalExecutionAdapter:
    """Test LocalExecutionAdapter functionality."""

    @pytest.fixture
    def adapter(self):
        """Create a LocalExecutionAdapter instance."""
        from src.healing.adapters.execution_local import LocalExecutionAdapter

        return LocalExecutionAdapter()

    @pytest.mark.asyncio
    async def test_run_command_success(self, adapter):
        """EXL-001: run_command() should return (0, stdout, '') for success."""
        exit_code, stdout, stderr = await adapter.run_command("echo hello")

        assert exit_code == 0
        assert "hello" in stdout
        assert stderr == "" or stderr is None or stderr.strip() == ""

    @pytest.mark.asyncio
    async def test_run_command_failure(self, adapter):
        """EXL-002: run_command() should return (non-zero, stdout, stderr) for failure."""
        exit_code, stdout, stderr = await adapter.run_command("ls /nonexistent_path_xyz")

        assert exit_code != 0
        assert stderr is not None

    @pytest.mark.asyncio
    async def test_run_command_timeout(self, adapter):
        """EXL-003: run_command() should raise ExecutionTimeoutError on timeout."""
        from src.healing.adapters.execution_local import ExecutionTimeoutError

        with pytest.raises(ExecutionTimeoutError):
            await adapter.run_command("sleep 10", timeout_seconds=1)

    @pytest.mark.asyncio
    async def test_run_tests_pass(self, adapter):
        """EXL-004: run_tests() should return TestResult(passed=True) when all pass."""
        # Create a simple passing test
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_simple.py"
            test_file.write_text(
                """
def test_pass():
    assert True
"""
            )

            result = await adapter.run_tests(test_path=str(tmpdir))

            assert result.passed is True

    @pytest.mark.asyncio
    async def test_run_tests_fail(self, adapter):
        """EXL-005: run_tests() should return TestResult(passed=False) when some fail."""
        # Create a simple failing test
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_simple.py"
            test_file.write_text(
                """
def test_fail():
    assert False, "This test should fail"
"""
            )

            result = await adapter.run_tests(test_path=str(tmpdir))

            assert result.passed is False

    @pytest.mark.asyncio
    async def test_run_build_success(self, adapter):
        """EXL-006: run_build() should return BuildResult(passed=True) on success."""
        # Most projects don't have a build step, so we test with a simple command
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple "build" that just echoes
            result = await adapter.run_build(
                build_command="echo 'Build complete'", cwd=tmpdir
            )

            assert result.passed is True

    @pytest.mark.asyncio
    async def test_run_build_failure(self, adapter):
        """EXL-007: run_build() should return BuildResult(passed=False) on failure."""
        result = await adapter.run_build(build_command="exit 1")

        assert result.passed is False

    @pytest.mark.asyncio
    async def test_run_lint_clean(self, adapter):
        """EXL-008: run_lint() should return LintResult(passed=True) for clean code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a clean Python file
            clean_file = Path(tmpdir) / "clean.py"
            clean_file.write_text('"""Clean module."""\n\n\ndef hello():\n    """Say hello."""\n    return "hello"\n')

            result = await adapter.run_lint(lint_command=f"python -m py_compile {clean_file}")

            assert result.passed is True
