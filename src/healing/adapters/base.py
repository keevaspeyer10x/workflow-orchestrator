"""Abstract base classes for healing adapters.

These interfaces define the contract for storage, git, cache, and execution
operations. Concrete implementations provide environment-specific behavior.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class TestResult:
    """Result of running tests."""

    passed: bool
    message: str = ""
    output: str = ""
    failed_tests: list[str] = None

    def __post_init__(self):
        if self.failed_tests is None:
            self.failed_tests = []


@dataclass
class BuildResult:
    """Result of running a build."""

    passed: bool
    message: str = ""
    output: str = ""


@dataclass
class LintResult:
    """Result of running a linter."""

    passed: bool
    message: str = ""
    output: str = ""
    issues: list[str] = None

    def __post_init__(self):
        if self.issues is None:
            self.issues = []


class StorageAdapter(ABC):
    """Abstract file operations for local/cloud compatibility."""

    @abstractmethod
    async def read_file(self, path: str) -> str:
        """Read file content.

        Args:
            path: Relative path to the file.

        Returns:
            File content as string.

        Raises:
            FileNotFoundError: If file doesn't exist.
        """

    @abstractmethod
    async def write_file(self, path: str, content: str) -> None:
        """Write file content.

        Args:
            path: Relative path to the file.
            content: Content to write.
        """

    @abstractmethod
    async def file_exists(self, path: str) -> bool:
        """Check if file exists.

        Args:
            path: Relative path to the file.

        Returns:
            True if file exists, False otherwise.
        """

    @abstractmethod
    async def list_files(self, pattern: str) -> list[str]:
        """List files matching pattern.

        Args:
            pattern: Glob pattern to match files.

        Returns:
            List of matching file paths.
        """


class GitAdapter(ABC):
    """Abstract git operations for local CLI vs GitHub API."""

    @abstractmethod
    async def create_branch(self, name: str, base: str = "main") -> None:
        """Create a new branch.

        Args:
            name: Name of the new branch.
            base: Base branch or commit to create from.

        Raises:
            GitBranchExistsError: If branch already exists.
        """

    @abstractmethod
    async def apply_diff(self, diff: str, message: str) -> str:
        """Apply diff and commit.

        Args:
            diff: Diff content to apply (can be empty for staged changes).
            message: Commit message.

        Returns:
            Commit SHA.
        """

    @abstractmethod
    async def create_pr(
        self, title: str, body: str, head: str, base: str
    ) -> str:
        """Create pull request.

        Args:
            title: PR title.
            body: PR description.
            head: Source branch.
            base: Target branch.

        Returns:
            PR URL.
        """

    @abstractmethod
    async def merge_branch(self, branch: str, into: str) -> None:
        """Merge branch.

        Args:
            branch: Branch to merge.
            into: Target branch to merge into.
        """

    @abstractmethod
    async def delete_branch(self, name: str) -> None:
        """Delete branch.

        Args:
            name: Name of branch to delete.
        """

    @abstractmethod
    async def get_recent_commits(self, count: int = 10) -> list[dict]:
        """Get recent commits for causality analysis.

        Args:
            count: Number of commits to retrieve.

        Returns:
            List of commit dicts with sha, message, author, date.
        """


class CacheAdapter(ABC):
    """Abstract cache for local SQLite vs in-memory."""

    @abstractmethod
    async def get(self, key: str) -> Optional[dict]:
        """Get cached value.

        Args:
            key: Cache key.

        Returns:
            Cached value or None if not found/expired.
        """

    @abstractmethod
    async def set(self, key: str, value: dict, ttl_seconds: int = 3600) -> None:
        """Set cached value with TTL.

        Args:
            key: Cache key.
            value: Value to cache (must be JSON-serializable).
            ttl_seconds: Time-to-live in seconds.
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete cached value.

        Args:
            key: Cache key to delete.
        """


class ExecutionAdapter(ABC):
    """Abstract command execution for local subprocess vs CI triggers."""

    @abstractmethod
    async def run_command(
        self, command: str, timeout_seconds: int = 300
    ) -> tuple[int, str, str]:
        """Run command.

        Args:
            command: Command to run.
            timeout_seconds: Maximum execution time.

        Returns:
            Tuple of (exit_code, stdout, stderr).

        Raises:
            ExecutionTimeoutError: If command times out.
        """

    @abstractmethod
    async def run_tests(
        self,
        test_pattern: Optional[str] = None,
        test_path: Optional[str] = None,
        timeout_seconds: int = 600,
    ) -> TestResult:
        """Run tests and return structured result.

        Args:
            test_pattern: Pattern to match test files.
            test_path: Path to test directory.
            timeout_seconds: Maximum execution time.

        Returns:
            TestResult with passed status and details.
        """

    @abstractmethod
    async def run_build(
        self,
        build_command: Optional[str] = None,
        cwd: Optional[str] = None,
        timeout_seconds: int = 300,
    ) -> BuildResult:
        """Run build and return structured result.

        Args:
            build_command: Command to run (default: auto-detect).
            cwd: Working directory.
            timeout_seconds: Maximum execution time.

        Returns:
            BuildResult with passed status and details.
        """

    @abstractmethod
    async def run_lint(
        self,
        lint_command: Optional[str] = None,
        timeout_seconds: int = 60,
    ) -> LintResult:
        """Run linter and return structured result.

        Args:
            lint_command: Lint command to run.
            timeout_seconds: Maximum execution time.

        Returns:
            LintResult with passed status and details.
        """
