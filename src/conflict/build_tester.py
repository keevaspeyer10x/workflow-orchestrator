"""
Build Tester

Runs build and tests on merged code to catch "clean but broken" merges.

This is critical for Phase 2 - git may say a merge is clean, but the
merged code may not compile or pass tests.
"""

import logging
import subprocess
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import uuid

logger = logging.getLogger(__name__)


@dataclass
class BuildTestResult:
    """Result of running build and tests on merged code."""
    build_passed: bool
    tests_passed: bool
    build_output: str = ""
    test_output: str = ""
    error: Optional[str] = None

    @property
    def all_passed(self) -> bool:
        """True if both build and tests passed."""
        return self.build_passed and self.tests_passed


class BuildTester:
    """
    Runs build and tests on merged code.

    Process:
    1. Create temporary branch with merged code
    2. Run build command
    3. Run test command (targeted tests for modified files)
    4. Clean up temporary branch
    """

    # Build system detection priority
    BUILD_SYSTEMS = [
        # (indicator_file, build_command, test_command)
        ("package.json", "npm run build", "npm test"),
        ("Cargo.toml", "cargo build", "cargo test"),
        ("go.mod", "go build ./...", "go test ./..."),
        ("pyproject.toml", "pip install -e . -q", "pytest"),
        ("setup.py", "pip install -e . -q", "pytest"),
        ("requirements.txt", None, "pytest"),
        ("Makefile", "make", "make test"),
        ("CMakeLists.txt", "cmake --build .", "ctest"),
    ]

    def __init__(
        self,
        base_branch: str = "main",
        build_command: Optional[str] = None,
        test_command: Optional[str] = None,
        timeout: int = 300,
    ):
        self.base_branch = base_branch
        self.build_command = build_command
        self.test_command = test_command
        self.timeout = timeout

    def test(
        self,
        branches: list[str],
        modified_files: Optional[list[str]] = None,
    ) -> BuildTestResult:
        """
        Test merged result of branches.

        Args:
            branches: List of branch names to merge and test
            modified_files: Optional list of modified files for targeted testing

        Returns:
            BuildTestResult with build and test outcomes
        """
        if not branches:
            return BuildTestResult(build_passed=True, tests_passed=True)

        # Generate unique temp branch name
        temp_branch = f"temp-merge-test-{uuid.uuid4().hex[:8]}"
        original_branch = self._get_current_branch()

        try:
            # Create temp branch from base
            self._create_temp_branch(temp_branch)

            # Merge all branches
            merge_success = self._merge_branches(branches)
            if not merge_success:
                return BuildTestResult(
                    build_passed=False,
                    tests_passed=False,
                    error="Merge failed - textual conflicts exist"
                )

            # Run build
            build_result = self._run_build()
            if not build_result.build_passed:
                return build_result

            # Run tests
            test_result = self._run_tests(modified_files)
            return BuildTestResult(
                build_passed=build_result.build_passed,
                tests_passed=test_result.tests_passed,
                build_output=build_result.build_output,
                test_output=test_result.test_output,
            )

        except Exception as e:
            logger.error(f"Build test error: {e}")
            return BuildTestResult(
                build_passed=False,
                tests_passed=False,
                error=str(e)
            )

        finally:
            # Always clean up
            self._cleanup(temp_branch, original_branch)

    def _create_temp_branch(self, branch_name: str) -> None:
        """Create temporary branch from base."""
        subprocess.run(
            ["git", "checkout", "-b", branch_name, self.base_branch],
            capture_output=True,
            check=True,
        )

    def _merge_branches(self, branches: list[str]) -> bool:
        """Merge branches into temp branch."""
        for branch in branches:
            result = subprocess.run(
                ["git", "merge", "--no-commit", "--no-ff", branch],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                # Abort merge and return failure
                subprocess.run(["git", "merge", "--abort"], capture_output=True)
                return False

        # Commit the merge
        subprocess.run(
            ["git", "commit", "-m", "Temp merge for testing"],
            capture_output=True,
        )
        return True

    def _run_build(self) -> BuildTestResult:
        """Run the build command."""
        build_cmd = self.build_command or self._detect_build_command()

        if not build_cmd:
            # No build needed
            return BuildTestResult(build_passed=True, tests_passed=True)

        logger.info(f"Running build: {build_cmd}")
        result = subprocess.run(
            build_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )

        return BuildTestResult(
            build_passed=result.returncode == 0,
            tests_passed=True,  # Not tested yet
            build_output=result.stdout + result.stderr,
        )

    def _run_tests(
        self,
        modified_files: Optional[list[str]] = None,
    ) -> BuildTestResult:
        """Run tests, optionally targeting modified files."""
        test_cmd = self.test_command or self._detect_test_command()

        if not test_cmd:
            # No tests configured
            return BuildTestResult(build_passed=True, tests_passed=True)

        # If we have modified files, try to run targeted tests
        if modified_files:
            targeted_cmd = self._get_targeted_test_command(test_cmd, modified_files)
            if targeted_cmd:
                test_cmd = targeted_cmd

        logger.info(f"Running tests: {test_cmd}")
        result = subprocess.run(
            test_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )

        return BuildTestResult(
            build_passed=True,
            tests_passed=result.returncode == 0,
            test_output=result.stdout + result.stderr,
        )

    def _detect_build_command(self) -> Optional[str]:
        """Auto-detect the appropriate build command."""
        for indicator, build_cmd, _ in self.BUILD_SYSTEMS:
            if Path(indicator).exists():
                return build_cmd
        return None

    def _detect_test_command(self) -> Optional[str]:
        """Auto-detect the appropriate test command."""
        for indicator, _, test_cmd in self.BUILD_SYSTEMS:
            if Path(indicator).exists():
                return test_cmd
        return None

    def _get_targeted_test_command(
        self,
        base_cmd: str,
        modified_files: list[str],
    ) -> Optional[str]:
        """Get a test command targeting specific files."""
        # Filter to test files
        test_files = [
            f for f in modified_files
            if "test" in f.lower() or f.endswith("_test.py") or f.endswith("_test.go")
        ]

        if not test_files:
            return None

        # Build targeted command based on test framework
        if "pytest" in base_cmd:
            return f"pytest {' '.join(test_files)}"
        elif "npm test" in base_cmd or "jest" in base_cmd:
            patterns = [f.replace("/", "\\/") for f in test_files]
            return f"npm test -- --testPathPattern=\"({'|'.join(patterns)})\""
        elif "go test" in base_cmd:
            packages = set()
            for f in test_files:
                pkg = str(Path(f).parent)
                packages.add(f"./{pkg}/...")
            return f"go test {' '.join(packages)}"

        return None

    def _get_current_branch(self) -> str:
        """Get the current branch name."""
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def _cleanup(self, temp_branch: str, original_branch: str) -> None:
        """Clean up temporary branch."""
        try:
            # Return to original branch
            subprocess.run(
                ["git", "checkout", original_branch],
                capture_output=True,
            )
            # Delete temp branch
            subprocess.run(
                ["git", "branch", "-D", temp_branch],
                capture_output=True,
            )
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
