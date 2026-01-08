"""
Tiered Validator (Phase 5)

Validates resolution candidates through progressive tiers:
- Tier 1 (Smoke): Build only - eliminate non-compiling
- Tier 2 (Lint): Build + lint - score convention compliance
- Tier 3 (Targeted): Build + lint + related tests (5 min budget)
- Tier 4 (Comprehensive): Full test suite (high-risk only)

Early elimination: candidates failing earlier tiers are dropped
before more expensive validation.
"""

import logging
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Optional, Union

from .schema import (
    ResolutionCandidate,
    ConflictContext,
    ValidationTier,
    TieredValidationResult,
)

logger = logging.getLogger(__name__)

# Patterns that trigger comprehensive (Tier 4) validation
HIGH_RISK_PATTERNS = [
    r".*auth.*",
    r".*security.*",
    r".*payment.*",
    r".*billing.*",
    r".*migration.*",
    r".*api/.*",
    r".*credential.*",
    r".*secret.*",
    r".*\.github/workflows/.*",
]


class TieredValidator:
    """
    Validates candidates through progressive tiers.

    Implements fail-fast: expensive validation only runs
    if cheaper tiers pass.
    """

    def __init__(
        self,
        repo_path: Optional[Path] = None,
        build_command: Optional[str] = None,
        test_command: Optional[str] = None,
        lint_command: Optional[str] = None,
        targeted_test_timeout: int = 300,  # 5 minutes
        full_test_timeout: int = 600,  # 10 minutes
    ):
        self.repo_path = repo_path or Path.cwd()
        self.build_command = build_command
        self.test_command = test_command
        self.lint_command = lint_command
        self.targeted_test_timeout = targeted_test_timeout
        self.full_test_timeout = full_test_timeout

    def validate_all(
        self,
        candidates: list[ResolutionCandidate],
        context: ConflictContext,
        max_tier: Optional[ValidationTier] = None,
    ) -> list[TieredValidationResult]:
        """
        Validate all candidates through appropriate tiers.

        Args:
            candidates: Candidates to validate
            context: Conflict context
            max_tier: Maximum tier to run (for limiting validation)

        Returns:
            Validation results for each candidate
        """
        results = []

        for candidate in candidates:
            # Determine appropriate tier based on files
            tier = self.determine_tier(candidate.files_modified)
            if max_tier and tier.value > max_tier.value:
                tier = max_tier

            result = self.validate_candidate(candidate, context, tier)
            results.append(result)

            # Update candidate with results
            candidate.build_passed = result.build_passed
            candidate.lint_score = result.lint_score
            candidate.tests_passed = (
                result.targeted_tests_passed + result.full_tests_passed
            )
            candidate.tests_failed = (
                result.targeted_tests_failed + result.full_tests_failed
            )
            candidate.tests_skipped = (
                result.targeted_tests_skipped + result.full_tests_skipped
            )

        return results

    def validate_candidate(
        self,
        candidate: ResolutionCandidate,
        context: ConflictContext,
        target_tier: ValidationTier,
    ) -> TieredValidationResult:
        """
        Validate a single candidate through specified tier.

        Implements early elimination: stops if any tier fails.
        """
        result = TieredValidationResult(candidate_id=candidate.candidate_id)

        # Checkout candidate branch
        if not self._checkout_branch(candidate.branch_name):
            return result

        # Tier 1: Smoke (build)
        start = time.time()
        result.build_passed = self._run_build()
        result.build_time_ms = int((time.time() - start) * 1000)
        result.tier_reached = ValidationTier.SMOKE

        if not result.build_passed:
            logger.info(f"Candidate {candidate.candidate_id} failed build")
            return result

        if target_tier == ValidationTier.SMOKE:
            return result

        # Tier 2: Lint
        result.lint_score = self._run_lint()
        result.lint_issues = self._count_lint_issues_from_score(result.lint_score)
        result.tier_reached = ValidationTier.LINT

        if target_tier == ValidationTier.LINT:
            return result

        # Tier 3: Targeted tests
        start = time.time()
        targeted = self._run_targeted_tests(
            candidate.files_modified,
            context,
        )
        result.targeted_tests_passed = targeted.get("passed", 0)
        result.targeted_tests_failed = targeted.get("failed", 0)
        result.targeted_tests_skipped = targeted.get("skipped", 0)
        result.targeted_test_time_ms = int((time.time() - start) * 1000)
        result.tier_reached = ValidationTier.TARGETED

        if result.targeted_tests_failed > 0:
            logger.info(
                f"Candidate {candidate.candidate_id} failed "
                f"{result.targeted_tests_failed} targeted tests"
            )

        if target_tier == ValidationTier.TARGETED:
            return result

        # Tier 4: Comprehensive (full suite)
        start = time.time()
        full = self._run_full_test_suite()
        result.full_tests_passed = full.get("passed", 0)
        result.full_tests_failed = full.get("failed", 0)
        result.full_tests_skipped = full.get("skipped", 0)
        result.full_test_time_ms = int((time.time() - start) * 1000)
        result.tier_reached = ValidationTier.COMPREHENSIVE

        return result

    def validate_tier(
        self,
        candidate: ResolutionCandidate,
        tier: ValidationTier,
    ) -> TieredValidationResult:
        """
        Validate a candidate at a specific tier only.

        For testing and fine-grained control.
        """
        result = TieredValidationResult(candidate_id=candidate.candidate_id)

        if not self._checkout_branch(candidate.branch_name):
            return result

        if tier == ValidationTier.SMOKE:
            result.build_passed = self._run_build()
            result.tier_reached = ValidationTier.SMOKE

        elif tier == ValidationTier.LINT:
            result.build_passed = self._run_build()
            if result.build_passed:
                result.lint_score = self._run_lint()
                result.tier_reached = ValidationTier.LINT

        elif tier == ValidationTier.TARGETED:
            result.build_passed = self._run_build()
            if result.build_passed:
                result.lint_score = self._run_lint()
                targeted = self._run_targeted_tests(
                    getattr(candidate, 'files_modified', []),
                    None,
                )
                result.targeted_tests_passed = targeted.get("passed", 0)
                result.targeted_tests_failed = targeted.get("failed", 0)
                result.tier_reached = ValidationTier.TARGETED

        elif tier == ValidationTier.COMPREHENSIVE:
            result.build_passed = self._run_build()
            if result.build_passed:
                result.lint_score = self._run_lint()
                full = self._run_full_test_suite()
                result.full_tests_passed = full.get("passed", 0)
                result.full_tests_failed = full.get("failed", 0)
                result.tier_reached = ValidationTier.COMPREHENSIVE

        return result

    def determine_tier(self, modified_files: list[str]) -> ValidationTier:
        """
        Determine appropriate validation tier based on files.

        High-risk files (auth, security, API) require comprehensive testing.
        """
        for filepath in modified_files:
            for pattern in HIGH_RISK_PATTERNS:
                if re.match(pattern, filepath, re.IGNORECASE):
                    logger.info(
                        f"File {filepath} matches high-risk pattern, "
                        f"using comprehensive validation"
                    )
                    return ValidationTier.COMPREHENSIVE

        return ValidationTier.TARGETED

    def filter_viable(
        self,
        candidates: list[ResolutionCandidate],
        require_build: bool = True,
        require_tests: bool = False,
    ) -> list[ResolutionCandidate]:
        """
        Filter candidates to only viable ones.

        Args:
            candidates: All candidates
            require_build: Require build to pass
            require_tests: Require tests to pass

        Returns:
            Viable candidates only
        """
        viable = []
        for c in candidates:
            if require_build and not c.build_passed:
                continue
            if require_tests and c.tests_failed > 0:
                continue
            viable.append(c)
        return viable

    def _checkout_branch(self, branch: str) -> bool:
        """Checkout a git branch with validation."""
        if not branch or not isinstance(branch, str):
            return False
        if branch.startswith('-') or '..' in branch:
            return False

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
            cmd_args = self._validate_command(command)
            if not cmd_args:
                logger.error("Build command validation failed")
                return False

            result = subprocess.run(
                cmd_args,
                shell=False,
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

    def _validate_command(self, command: Union[str, list[str]]) -> Optional[list[str]]:
        """
        Validate and parse a command safely.

        SECURITY: Validates command against allowed patterns to prevent injection.
        Only allows predefined command prefixes.
        """
        ALLOWED_COMMANDS = {
            "python", "python3", "pip", "npm", "node", "npx",
            "cargo", "go", "make", "pytest", "ruff", "flake8",
            "pylint", "which", "git"
        }

        if isinstance(command, str):
            cmd_args = shlex.split(command)
        else:
            cmd_args = list(command)

        if not cmd_args:
            return None

        # Extract base command (may be a path like /usr/bin/python)
        base_cmd = Path(cmd_args[0]).name

        if base_cmd not in ALLOWED_COMMANDS:
            logger.warning(f"Command '{base_cmd}' not in allowed list")
            return None

        return cmd_args

    def _detect_build_command(self) -> Optional[Union[str, list[str]]]:
        """Detect appropriate build command."""
        if self.build_command:
            return self.build_command

        if (self.repo_path / "pyproject.toml").exists():
            return ["python", "-m", "py_compile", "--help"]
        elif (self.repo_path / "package.json").exists():
            return ["npm", "run", "build", "--if-present"]
        elif (self.repo_path / "Cargo.toml").exists():
            return ["cargo", "check"]
        elif (self.repo_path / "go.mod").exists():
            return ["go", "build", "./..."]
        elif (self.repo_path / "Makefile").exists():
            return ["make", "build"]

        return None

    def _run_lint(self) -> float:
        """Run linter and return score (0.0 to 1.0)."""
        command = self._detect_lint_command()
        if not command:
            return 1.0

        try:
            cmd_args = self._validate_command(command)
            if not cmd_args:
                logger.warning("Lint command validation failed")
                return 0.5

            result = subprocess.run(
                cmd_args,
                shell=False,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=120,
            )

            output = result.stdout + result.stderr
            issue_count = self._count_lint_issues(output)

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

    def _detect_lint_command(self) -> Optional[Union[str, list[str]]]:
        """Detect appropriate lint command."""
        if self.lint_command:
            return self.lint_command

        if (self.repo_path / "pyproject.toml").exists():
            if self._command_exists("ruff"):
                return ["ruff", "check", "."]
            elif self._command_exists("flake8"):
                return ["flake8", "."]

        elif (self.repo_path / "package.json").exists():
            return ["npm", "run", "lint", "--if-present"]

        return None

    def _command_exists(self, cmd: str) -> bool:
        """Check if a command exists."""
        try:
            result = subprocess.run(["which", cmd], capture_output=True)
            return result.returncode == 0
        except Exception:
            return False

    def _count_lint_issues(self, output: str) -> int:
        """Count lint issues from output."""
        patterns = [
            r"(\d+)\s+(?:error|warning|issue)",
            r"Found\s+(\d+)\s+",
            r"(\d+)\s+problems?",
        ]

        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return int(match.group(1))

        issue_lines = [
            l for l in output.split("\n")
            if re.match(r"^\s*[EW]\d+:|error:|warning:", l, re.IGNORECASE)
        ]
        return len(issue_lines)

    def _count_lint_issues_from_score(self, score: float) -> int:
        """Estimate issue count from lint score."""
        if score >= 1.0:
            return 0
        elif score >= 0.9:
            return 3
        elif score >= 0.8:
            return 7
        elif score >= 0.6:
            return 15
        else:
            return 25

    def _run_targeted_tests(
        self,
        modified_files: list[str],
        context: Optional[ConflictContext],
    ) -> dict:
        """Run tests related to modified files only."""
        results = {"passed": 0, "failed": 0, "skipped": 0}

        test_files = self._find_related_tests(modified_files)
        if not test_files:
            logger.info("No targeted tests found")
            return results

        command = self._detect_test_command(test_files)
        if not command:
            return results

        try:
            result = subprocess.run(
                command,
                shell=False,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=self.targeted_test_timeout,
            )

            output = result.stdout + result.stderr
            return self._parse_test_results(output, result.returncode)

        except subprocess.TimeoutExpired:
            logger.error("Targeted tests timed out")
            results["failed"] = 1
        except Exception as e:
            logger.error(f"Test error: {e}")
            results["failed"] = 1

        return results

    def _run_full_test_suite(self) -> dict:
        """Run the complete test suite."""
        results = {"passed": 0, "failed": 0, "skipped": 0}

        command = self._detect_full_test_command()
        if not command:
            logger.warning("No test command detected")
            return results

        try:
            result = subprocess.run(
                command,
                shell=False,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=self.full_test_timeout,
            )

            output = result.stdout + result.stderr
            return self._parse_test_results(output, result.returncode)

        except subprocess.TimeoutExpired:
            logger.error("Full test suite timed out")
            results["failed"] = 1
        except Exception as e:
            logger.error(f"Test error: {e}")
            results["failed"] = 1

        return results

    def _find_related_tests(self, modified_files: list[str]) -> list[str]:
        """Find test files related to modified source files."""
        test_files = []

        for filepath in modified_files:
            if "test" in filepath.lower():
                test_files.append(filepath)
                continue

            if filepath.endswith(".py"):
                base = Path(filepath)
                name = base.stem
                parent = base.parent

                possible_tests = [
                    parent / f"test_{name}.py",
                    parent / f"{name}_test.py",
                    parent / "tests" / f"test_{name}.py",
                    Path("tests") / f"test_{name}.py",
                ]

                for test_path in possible_tests:
                    if (self.repo_path / test_path).exists():
                        test_files.append(str(test_path))
                        break

        return list(set(test_files))

    def _detect_test_command(self, test_files: list[str]) -> Optional[list[str]]:
        """Detect test command for specific files."""
        if self.test_command:
            if isinstance(self.test_command, str):
                return shlex.split(self.test_command)
            return self.test_command

        safe_files = test_files[:10]

        if (self.repo_path / "pyproject.toml").exists():
            if self._command_exists("pytest"):
                return ["pytest"] + safe_files + ["-v", "--tb=short"]

        elif (self.repo_path / "package.json").exists():
            return ["npm", "test", "--"] + safe_files

        return None

    def _detect_full_test_command(self) -> Optional[list[str]]:
        """Detect command for full test suite."""
        if self.test_command:
            if isinstance(self.test_command, str):
                return shlex.split(self.test_command)
            return self.test_command

        if (self.repo_path / "pyproject.toml").exists():
            if self._command_exists("pytest"):
                return ["pytest", "-v", "--tb=short"]

        elif (self.repo_path / "package.json").exists():
            return ["npm", "test"]

        return None

    def _parse_test_results(self, output: str, return_code: int) -> dict:
        """Parse test results from output."""
        results = {"passed": 0, "failed": 0, "skipped": 0}

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

        passed_match = re.search(r"(\d+)\s+passed", output, re.IGNORECASE)
        if passed_match:
            results["passed"] = int(passed_match.group(1))

        failed_match = re.search(r"(\d+)\s+failed", output, re.IGNORECASE)
        if failed_match:
            results["failed"] = int(failed_match.group(1))

        if results["passed"] == 0 and results["failed"] == 0:
            if return_code == 0:
                results["passed"] = 1
            else:
                results["failed"] = 1

        return results
