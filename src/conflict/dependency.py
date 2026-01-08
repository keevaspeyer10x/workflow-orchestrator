"""
Dependency Analyzer

Detects dependency conflicts between branches by analyzing package files
like package.json, requirements.txt, Cargo.toml, etc.
"""

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DependencyConflict:
    """A conflict between dependency versions."""
    package: str
    version1: str
    version2: str
    package_manager: str
    conflict_type: str  # "incompatible", "major_diff", "minor_diff"
    severity: str  # "high", "medium", "low"

    @property
    def description(self) -> str:
        return f"{self.package}: {self.version1} vs {self.version2} ({self.conflict_type})"


class DependencyAnalyzer:
    """
    Analyzes dependency conflicts between branches.

    Supports:
    - npm (package.json)
    - pip (requirements.txt, pyproject.toml)
    - cargo (Cargo.toml)
    - go (go.mod)
    """

    DEPENDENCY_FILES = {
        "npm": ["package.json", "package-lock.json"],
        "pip": ["requirements.txt", "pyproject.toml", "setup.py"],
        "cargo": ["Cargo.toml", "Cargo.lock"],
        "go": ["go.mod", "go.sum"],
    }

    def analyze(
        self,
        branches: list[str],
        base_branch: str = "main",
    ) -> list[DependencyConflict]:
        """
        Analyze dependency conflicts between branches.

        Args:
            branches: List of branch names to analyze
            base_branch: Base branch for comparison

        Returns:
            List of DependencyConflict objects
        """
        conflicts = []

        # Get dependency files from each branch
        all_deps = {}
        for branch in [base_branch] + branches:
            all_deps[branch] = self._get_branch_dependencies(branch)

        # Compare each branch against base
        base_deps = all_deps.get(base_branch, {})
        for branch in branches:
            branch_deps = all_deps.get(branch, {})

            for pkg_manager in self.DEPENDENCY_FILES:
                base_pkgs = base_deps.get(pkg_manager, {})
                branch_pkgs = branch_deps.get(pkg_manager, {})

                branch_conflicts = self.compare_deps(
                    base_pkgs, branch_pkgs, pkg_manager
                )
                conflicts.extend(branch_conflicts)

        # Also compare branches against each other
        for i, branch1 in enumerate(branches):
            for branch2 in branches[i + 1:]:
                deps1 = all_deps.get(branch1, {})
                deps2 = all_deps.get(branch2, {})

                for pkg_manager in self.DEPENDENCY_FILES:
                    pkgs1 = deps1.get(pkg_manager, {})
                    pkgs2 = deps2.get(pkg_manager, {})

                    inter_conflicts = self.compare_deps(pkgs1, pkgs2, pkg_manager)
                    conflicts.extend(inter_conflicts)

        # Deduplicate
        seen = set()
        unique_conflicts = []
        for c in conflicts:
            key = (c.package, c.version1, c.version2)
            if key not in seen:
                seen.add(key)
                unique_conflicts.append(c)

        return unique_conflicts

    def compare_deps(
        self,
        deps1: dict[str, str],
        deps2: dict[str, str],
        package_manager: str,
    ) -> list[DependencyConflict]:
        """
        Compare two sets of dependencies for conflicts.

        Args:
            deps1: First set of dependencies {package: version}
            deps2: Second set of dependencies {package: version}
            package_manager: npm, pip, cargo, etc.

        Returns:
            List of conflicts found
        """
        conflicts = []

        # Find packages present in both with different versions
        common_packages = set(deps1.keys()) & set(deps2.keys())

        for package in common_packages:
            v1 = deps1[package]
            v2 = deps2[package]

            if v1 == v2:
                continue

            # Check if versions are compatible
            conflict_type, severity = self._check_version_conflict(
                v1, v2, package_manager
            )

            if conflict_type:
                conflicts.append(DependencyConflict(
                    package=package,
                    version1=v1,
                    version2=v2,
                    package_manager=package_manager,
                    conflict_type=conflict_type,
                    severity=severity,
                ))

        return conflicts

    def _get_branch_dependencies(self, branch: str) -> dict[str, dict[str, str]]:
        """Get all dependencies from a branch."""
        deps = {}

        for pkg_manager, files in self.DEPENDENCY_FILES.items():
            for file_path in files:
                content = self._get_file_from_branch(branch, file_path)
                if content:
                    parsed = self._parse_dependency_file(
                        content, file_path, pkg_manager
                    )
                    if parsed:
                        deps[pkg_manager] = {**deps.get(pkg_manager, {}), **parsed}

        return deps

    def _get_file_from_branch(self, branch: str, file_path: str) -> Optional[str]:
        """Get file contents from a specific branch."""
        result = subprocess.run(
            ["git", "show", f"{branch}:{file_path}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout
        return None

    def _parse_dependency_file(
        self,
        content: str,
        file_path: str,
        package_manager: str,
    ) -> dict[str, str]:
        """Parse a dependency file and extract packages."""
        if file_path == "package.json":
            return self._parse_package_json(content)
        elif file_path == "requirements.txt":
            return self._parse_requirements_txt(content)
        elif file_path == "pyproject.toml":
            return self._parse_pyproject_toml(content)
        elif file_path == "Cargo.toml":
            return self._parse_cargo_toml(content)
        elif file_path == "go.mod":
            return self._parse_go_mod(content)
        return {}

    def _parse_package_json(self, content: str) -> dict[str, str]:
        """Parse npm package.json."""
        try:
            data = json.loads(content)
            deps = {}
            for key in ["dependencies", "devDependencies", "peerDependencies"]:
                if key in data:
                    deps.update(data[key])
            return deps
        except json.JSONDecodeError:
            return {}

    def _parse_requirements_txt(self, content: str) -> dict[str, str]:
        """Parse pip requirements.txt."""
        deps = {}
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue

            # Parse: package==1.0.0, package>=1.0.0, package~=1.0.0
            match = re.match(r"([a-zA-Z0-9_-]+)\s*([<>=!~]+.+)?", line)
            if match:
                package = match.group(1)
                version = match.group(2) or "*"
                deps[package] = version.strip()

        return deps

    def _parse_pyproject_toml(self, content: str) -> dict[str, str]:
        """Parse pyproject.toml dependencies."""
        deps = {}

        # Simple regex-based parsing (proper TOML parsing would be better)
        in_deps_section = False
        for line in content.split("\n"):
            if "[project.dependencies]" in line or "[tool.poetry.dependencies]" in line:
                in_deps_section = True
                continue
            if line.strip().startswith("[") and in_deps_section:
                in_deps_section = False
                continue

            if in_deps_section:
                # Parse: package = "version" or package = {version = "..."}
                match = re.match(r'([a-zA-Z0-9_-]+)\s*=\s*["\']([^"\']+)["\']', line)
                if match:
                    deps[match.group(1)] = match.group(2)

        return deps

    def _parse_cargo_toml(self, content: str) -> dict[str, str]:
        """Parse Cargo.toml dependencies."""
        deps = {}

        in_deps_section = False
        for line in content.split("\n"):
            if "[dependencies]" in line or "[dev-dependencies]" in line:
                in_deps_section = True
                continue
            if line.strip().startswith("[") and in_deps_section:
                in_deps_section = False
                continue

            if in_deps_section:
                # Parse: package = "version" or package = { version = "..." }
                match = re.match(r'([a-zA-Z0-9_-]+)\s*=\s*["\']([^"\']+)["\']', line)
                if match:
                    deps[match.group(1)] = match.group(2)
                else:
                    # Try inline table format
                    match = re.match(r'([a-zA-Z0-9_-]+)\s*=\s*\{.*version\s*=\s*["\']([^"\']+)["\']', line)
                    if match:
                        deps[match.group(1)] = match.group(2)

        return deps

    def _parse_go_mod(self, content: str) -> dict[str, str]:
        """Parse go.mod dependencies."""
        deps = {}

        in_require = False
        for line in content.split("\n"):
            if line.strip() == "require (":
                in_require = True
                continue
            if line.strip() == ")" and in_require:
                in_require = False
                continue

            if in_require or line.strip().startswith("require "):
                # Parse: module/path v1.2.3
                match = re.match(r'\s*([^\s]+)\s+(v[\d.]+)', line)
                if match:
                    deps[match.group(1)] = match.group(2)

        return deps

    def _check_version_conflict(
        self,
        v1: str,
        v2: str,
        package_manager: str,
    ) -> tuple[Optional[str], str]:
        """
        Check if two version strings conflict.

        Returns:
            (conflict_type, severity) or (None, "") if compatible
        """
        # Clean up version strings
        v1_clean = re.sub(r"[^0-9.]", "", v1)
        v2_clean = re.sub(r"[^0-9.]", "", v2)

        if not v1_clean or not v2_clean:
            return None, ""

        # Parse major.minor.patch
        parts1 = v1_clean.split(".")
        parts2 = v2_clean.split(".")

        major1 = int(parts1[0]) if parts1 else 0
        major2 = int(parts2[0]) if parts2 else 0

        minor1 = int(parts1[1]) if len(parts1) > 1 else 0
        minor2 = int(parts2[1]) if len(parts2) > 1 else 0

        # Major version difference = incompatible
        if major1 != major2:
            return "incompatible", "high"

        # Different caret/tilde ranges may be compatible
        if "^" in v1 and "^" in v2:
            # Caret allows minor/patch changes, may be compatible
            if minor1 != minor2:
                return "minor_diff", "low"
            return None, ""

        # Direct version mismatch
        if minor1 != minor2:
            return "minor_diff", "medium"

        return None, ""
