"""
Resolution Validation (Basic - Phase 3)

Validates resolution candidates:
1. Build check (must pass)
2. Lint check (score, not blocking)
3. Targeted tests (tests related to changed files)

Phase 3: Basic validation (build + targeted tests).
Phase 5: Full validation tiers with flaky test handling.
"""

import logging
import subprocess
import re
from pathlib import Path
from typing import Optional

from .schema import (
    ResolutionCandidate,
    ConflictContext,
)

logger = logging.getLogger(__name__)


class ResolutionValidator:
    """
    Validates resolution candidates.

    Phase 3: Basic validation - build and targeted tests.
    Phase 5: Full validation tiers.
    """

    def __init__(
        self,
        repo_path: Optional[Path] = None,
        build_command: Optional[str] = None,
        test_command: Optional[str] = None,
        lint_command: Optional[str] = None,
    ):
        self.repo_path = repo_path or Path.cwd()
        self.build_command = build_command
        self.test_command = test_command
        self.lint_command = lint_command

    def validate(
        self,
        candidates: list[ResolutionCandidate],
        context: ConflictContext,
    ) -> list[ResolutionCandidate]:
        """
        Validate candidates and update their scores.

        Args:
            candidates: List of candidates to validate
            context: ConflictContext for determining targeted tests

        Returns:
            List of validated candidates with updated scores
        """
        logger.info(f"Validating {len(candidates)} candidates")

        for candidate in candidates:
            # Checkout candidate branch
            self._checkout_branch(candidate.branch_name)

            # Run validations
            candidate.build_passed = self._run_build()
            candidate.lint_score = self._run_lint()

            test_results = self._run_targeted_tests(
                candidate.files_modified,
                context,
            )
            candidate.tests_passed = test_results["passed"]
            candidate.tests_failed = test_results["failed"]
            candidate.tests_skipped = test_results["skipped"]

            # Calculate scores
            self._calculate_scores(candidate, context)

            logger.info(
                f"Candidate {candidate.candidate_id}: "
                f"build={'PASS' if candidate.build_passed else 'FAIL'}, "
                f"tests={candidate.tests_passed}P/{candidate.tests_failed}F, "
                f"score={candidate.total_score:.2f}"
            )

        # Return to base branch
        self._checkout_branch(context.base_branch)

        return candidates

    def _checkout_branch(self, branch: str) -> bool:
        """Checkout a git branch."""
        try:
            subprocess.run(
                ["git", "checkout", branch],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to checkout {branch}: {e}")
            return False

    def _run_build(self) -> bool:
        """Run build and return success status."""
        command = self._detect_build_command()
        if not command:
            logger.warning("No build command detected, assuming success")
            return True

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.error("Build timed out")
            return False
        except Exception as e:
            logger.error(f"Build error: {e}")
            return False

    def _detect_build_command(self) -> Optional[str]:
        """Detect appropriate build command."""
        if self.build_command:
            return self.build_command

        # Auto-detect
        if (self.repo_path / "pyproject.toml").exists():
            return "python -m py_compile $(find . -name '*.py' -not -path './.*')"
        elif (self.repo_path / "package.json").exists():
            return "npm run build --if-present"
        elif (self.repo_path / "Cargo.toml").exists():
            return "cargo check"
        elif (self.repo_path / "go.mod").exists():
            return "go build ./..."
        elif (self.repo_path / "Makefile").exists():
            return "make build || make"

        return None

    def _run_lint(self) -> float:
        """Run linter and return score (0.0 to 1.0)."""
        command = self._detect_lint_command()
        if not command:
            return 1.0  # No linter = assume clean

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=120,
            )

            # Count issues
            output = result.stdout + result.stderr
            issue_count = self._count_lint_issues(output)

            # Score: 1.0 for 0 issues, decreasing
            if issue_count == 0:
                return 1.0
            elif issue_count < 5:
                return 0.9
            elif issue_count < 10:
                return 0.8
            elif issue_count < 20:
                return 0.6
            else:
                return 0.4

        except Exception as e:
            logger.warning(f"Lint check failed: {e}")
            return 0.5

    def _detect_lint_command(self) -> Optional[str]:
        """Detect appropriate lint command."""
        if self.lint_command:
            return self.lint_command

        # Auto-detect
        if (self.repo_path / "pyproject.toml").exists() or (self.repo_path / "setup.py").exists():
            # Try ruff first, then flake8, then pylint
            if self._command_exists("ruff"):
                return "ruff check . || true"
            elif self._command_exists("flake8"):
                return "flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics || true"
            elif self._command_exists("pylint"):
                return "pylint . --exit-zero --score=y"

        elif (self.repo_path / "package.json").exists():
            return "npm run lint --if-present || true"

        return None

    def _command_exists(self, cmd: str) -> bool:
        """Check if a command exists."""
        try:
            result = subprocess.run(
                ["which", cmd],
                capture_output=True,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _count_lint_issues(self, output: str) -> int:
        """Count lint issues from output."""
        # Common patterns for lint issue counts
        patterns = [
            r"(\d+)\s+(?:error|warning|issue)",
            r"Found\s+(\d+)\s+",
            r"(\d+)\s+problems?",
        ]

        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return int(match.group(1))

        # Fallback: count lines that look like issues
        issue_lines = [l for l in output.split("\n") if re.match(r"^\s*[EW]\d+:|error:|warning:", l, re.IGNORECASE)]
        return len(issue_lines)

    def _run_targeted_tests(
        self,
        modified_files: list[str],
        context: ConflictContext,
    ) -> dict:
        """Run tests related to modified files."""
        results = {"passed": 0, "failed": 0, "skipped": 0}

        # Find test files related to modified files
        test_files = self._find_related_tests(modified_files)

        if not test_files:
            logger.info("No targeted tests found")
            return results

        command = self._detect_test_command(test_files)
        if not command:
            logger.warning("No test command detected")
            return results

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes for tests
            )

            # Parse test results
            output = result.stdout + result.stderr
            results = self._parse_test_results(output, result.returncode)

        except subprocess.TimeoutExpired:
            logger.error("Tests timed out")
            results["failed"] = 1
        except Exception as e:
            logger.error(f"Test error: {e}")
            results["failed"] = 1

        return results

    def _find_related_tests(self, modified_files: list[str]) -> list[str]:
        """Find test files related to modified source files."""
        test_files = []

        for filepath in modified_files:
            # Skip if already a test file
            if "test" in filepath.lower():
                test_files.append(filepath)
                continue

            # Python: foo.py -> test_foo.py or foo_test.py
            if filepath.endswith(".py"):
                base = Path(filepath)
                name = base.stem
                parent = base.parent

                possible_tests = [
                    parent / f"test_{name}.py",
                    parent / f"{name}_test.py",
                    parent / "tests" / f"test_{name}.py",
                    Path("tests") / f"test_{name}.py",
                    Path("tests") / parent / f"test_{name}.py",
                ]

                for test_path in possible_tests:
                    if (self.repo_path / test_path).exists():
                        test_files.append(str(test_path))
                        break

            # JavaScript: foo.js -> foo.test.js or foo.spec.js
            elif filepath.endswith((".js", ".ts", ".jsx", ".tsx")):
                base = Path(filepath)
                name = base.stem
                ext = base.suffix
                parent = base.parent

                possible_tests = [
                    parent / f"{name}.test{ext}",
                    parent / f"{name}.spec{ext}",
                    parent / "__tests__" / f"{name}.test{ext}",
                ]

                for test_path in possible_tests:
                    if (self.repo_path / test_path).exists():
                        test_files.append(str(test_path))
                        break

        return list(set(test_files))

    def _detect_test_command(self, test_files: list[str]) -> Optional[str]:
        """Detect appropriate test command."""
        if self.test_command:
            return self.test_command

        # Build file list for targeted tests
        file_list = " ".join(test_files[:10])  # Limit to 10 files

        # Auto-detect
        if (self.repo_path / "pyproject.toml").exists() or (self.repo_path / "setup.py").exists():
            if self._command_exists("pytest"):
                return f"pytest {file_list} -v --tb=short"
            else:
                return f"python -m unittest {file_list.replace('/', '.').replace('.py', '')}"

        elif (self.repo_path / "package.json").exists():
            return f"npm test -- {file_list}"

        elif (self.repo_path / "Cargo.toml").exists():
            return "cargo test"

        elif (self.repo_path / "go.mod").exists():
            return "go test ./..."

        return None

    def _parse_test_results(self, output: str, return_code: int) -> dict:
        """Parse test results from output."""
        results = {"passed": 0, "failed": 0, "skipped": 0}

        # pytest output
        pytest_match = re.search(
            r"(\d+)\s+passed.*?(\d+)?\s*failed.*?(\d+)?\s*skipped",
            output,
            re.IGNORECASE
        )
        if pytest_match:
            results["passed"] = int(pytest_match.group(1) or 0)
            results["failed"] = int(pytest_match.group(2) or 0)
            results["skipped"] = int(pytest_match.group(3) or 0)
            return results

        # Just passed count
        passed_match = re.search(r"(\d+)\s+passed", output, re.IGNORECASE)
        if passed_match:
            results["passed"] = int(passed_match.group(1))

        # Just failed count
        failed_match = re.search(r"(\d+)\s+failed", output, re.IGNORECASE)
        if failed_match:
            results["failed"] = int(failed_match.group(1))

        # If we couldn't parse, use return code
        if results["passed"] == 0 and results["failed"] == 0:
            if return_code == 0:
                results["passed"] = 1  # At least something passed
            else:
                results["failed"] = 1

        return results

    def _calculate_scores(
        self,
        candidate: ResolutionCandidate,
        context: ConflictContext,
    ):
        """Calculate all scores for a candidate."""

        # Correctness: based on build and tests
        if not candidate.build_passed:
            candidate.correctness_score = 0.0
        elif candidate.tests_failed > 0:
            total_tests = candidate.tests_passed + candidate.tests_failed
            if total_tests > 0:
                candidate.correctness_score = candidate.tests_passed / total_tests
            else:
                candidate.correctness_score = 0.5
        else:
            candidate.correctness_score = 1.0

        # Simplicity: fewer files modified is simpler
        file_count = len(candidate.files_modified)
        if file_count <= 5:
            candidate.simplicity_score = 1.0
        elif file_count <= 10:
            candidate.simplicity_score = 0.8
        elif file_count <= 20:
            candidate.simplicity_score = 0.6
        else:
            candidate.simplicity_score = 0.4

        # Convention: lint score
        candidate.convention_score = candidate.lint_score

        # Intent satisfaction: assume satisfied if tests pass
        if candidate.tests_failed == 0:
            candidate.intent_satisfaction_score = 1.0
        else:
            candidate.intent_satisfaction_score = 0.5

        # Total score (weighted average)
        candidate.total_score = (
            candidate.correctness_score * 0.4 +
            candidate.simplicity_score * 0.2 +
            candidate.convention_score * 0.2 +
            candidate.intent_satisfaction_score * 0.2
        )
