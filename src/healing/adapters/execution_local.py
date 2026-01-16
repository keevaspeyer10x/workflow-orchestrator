"""Local subprocess execution adapter."""

import asyncio
from typing import Optional

from .base import ExecutionAdapter, TestResult, BuildResult, LintResult


class ExecutionTimeoutError(Exception):
    """Raised when a command times out."""

    def __init__(self, command: str, timeout: int):
        self.command = command
        self.timeout = timeout
        super().__init__(f"Command '{command}' timed out after {timeout} seconds")


class LocalExecutionAdapter(ExecutionAdapter):
    """Subprocess-based execution for local environments."""

    async def run_command(
        self, command: str, timeout_seconds: int = 300
    ) -> tuple[int, str, str]:
        """Run command using asyncio subprocess."""
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds
            )
            return proc.returncode, stdout.decode(), stderr.decode()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()  # Clean up
            raise ExecutionTimeoutError(command, timeout_seconds)

    async def run_tests(
        self,
        test_pattern: Optional[str] = None,
        test_path: Optional[str] = None,
        timeout_seconds: int = 600,
    ) -> TestResult:
        """Run tests using pytest."""
        # Build pytest command
        cmd_parts = ["python", "-m", "pytest", "-v"]
        if test_path:
            cmd_parts.append(test_path)
        if test_pattern:
            cmd_parts.extend(["-k", test_pattern])

        command = " ".join(cmd_parts)

        try:
            exit_code, stdout, stderr = await self.run_command(
                command, timeout_seconds
            )

            passed = exit_code == 0
            output = stdout + stderr

            # Extract failed test names if any
            failed_tests = []
            if not passed:
                for line in output.split("\n"):
                    if "FAILED" in line and "::" in line:
                        # Extract test name from lines like "FAILED tests/test_foo.py::test_bar"
                        parts = line.split()
                        for part in parts:
                            if "::" in part:
                                failed_tests.append(part)
                                break

            return TestResult(
                passed=passed,
                message="All tests passed" if passed else f"{len(failed_tests)} tests failed",
                output=output,
                failed_tests=failed_tests,
            )
        except ExecutionTimeoutError:
            return TestResult(
                passed=False,
                message=f"Tests timed out after {timeout_seconds} seconds",
                output="",
            )

    async def run_build(
        self,
        build_command: Optional[str] = None,
        cwd: Optional[str] = None,
        timeout_seconds: int = 300,
    ) -> BuildResult:
        """Run build command."""
        if build_command is None:
            # Try to detect build command
            build_command = "echo 'No build command specified'"

        # Prepend cd if cwd specified
        if cwd:
            build_command = f"cd {cwd} && {build_command}"

        try:
            exit_code, stdout, stderr = await self.run_command(
                build_command, timeout_seconds
            )
            passed = exit_code == 0
            output = stdout + stderr

            return BuildResult(
                passed=passed,
                message="Build succeeded" if passed else "Build failed",
                output=output,
            )
        except ExecutionTimeoutError:
            return BuildResult(
                passed=False,
                message=f"Build timed out after {timeout_seconds} seconds",
                output="",
            )

    async def run_lint(
        self,
        lint_command: Optional[str] = None,
        timeout_seconds: int = 60,
    ) -> LintResult:
        """Run linter command."""
        if lint_command is None:
            # Default to ruff for Python
            lint_command = "python -m ruff check ."

        try:
            exit_code, stdout, stderr = await self.run_command(
                lint_command, timeout_seconds
            )
            passed = exit_code == 0
            output = stdout + stderr

            # Extract issues from output
            issues = []
            for line in output.split("\n"):
                line = line.strip()
                if line and (":" in line) and not line.startswith("Found"):
                    issues.append(line)

            return LintResult(
                passed=passed,
                message="Linting passed" if passed else f"{len(issues)} issues found",
                output=output,
                issues=issues[:50],  # Limit to 50 issues
            )
        except ExecutionTimeoutError:
            return LintResult(
                passed=False,
                message=f"Lint timed out after {timeout_seconds} seconds",
                output="",
            )
