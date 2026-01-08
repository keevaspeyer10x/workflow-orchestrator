"""
Feature Porter

Ports features from losing options to the winning architecture.

When a user selects an option, the other options' valuable features
should be preserved and adapted to the winning approach.
"""

import logging
import subprocess
import re
from pathlib import Path
from typing import Optional

from .schema import (
    EscalationOption,
    FeaturePort,
)
from ..resolution.schema import ResolutionCandidate

logger = logging.getLogger(__name__)


class FeaturePorter:
    """
    Ports features from losing candidates to the winning one.

    Steps:
    1. Identify unique features in losing candidates
    2. Determine if features can be adapted
    3. Apply features to winning branch
    4. Verify build still passes
    """

    def __init__(
        self,
        repo_path: Optional[Path] = None,
        base_branch: str = "main",
    ):
        self.repo_path = repo_path or Path.cwd()
        self.base_branch = base_branch

    def port_features(
        self,
        winner: EscalationOption,
        losers: list[EscalationOption],
    ) -> list[FeaturePort]:
        """
        Port features from losing options to the winner.

        Args:
            winner: The selected winning option
            losers: The losing options to port from

        Returns:
            List of FeaturePort results
        """
        logger.info(f"Porting features to winner {winner.option_id}")

        ports = []

        for loser in losers:
            port = self._port_single_feature(winner, loser)
            ports.append(port)

        # Summary
        successful = sum(1 for p in ports if p.success)
        logger.info(f"Ported {successful}/{len(ports)} features successfully")

        return ports

    def _port_single_feature(
        self,
        winner: EscalationOption,
        loser: EscalationOption,
    ) -> FeaturePort:
        """Port a single feature from loser to winner."""
        port = FeaturePort(
            from_option=loser.option_id,
            to_option=winner.option_id,
            feature_description=loser.title,
        )

        if not winner.candidate or not loser.candidate:
            port.error = "Missing candidate information"
            return port

        try:
            # Identify unique files in loser
            unique_files = self._identify_unique_features(
                winner.candidate,
                loser.candidate,
            )

            if not unique_files:
                logger.info(f"No unique features to port from {loser.option_id}")
                port.success = True
                return port

            port.files_modified = unique_files

            # Apply features
            success = self._apply_features(
                winner.candidate.branch_name,
                loser.candidate.branch_name,
                unique_files,
            )

            if success:
                # Verify build
                if self._verify_build(winner.candidate.branch_name):
                    port.success = True
                else:
                    port.error = "Build failed after porting"
                    # Revert
                    self._revert_changes(winner.candidate.branch_name)
            else:
                port.error = "Failed to apply features"

        except Exception as e:
            logger.error(f"Error porting feature: {e}")
            port.error = str(e)

        return port

    def _identify_unique_features(
        self,
        winner: ResolutionCandidate,
        loser: ResolutionCandidate,
    ) -> list[str]:
        """Identify files unique to the loser that should be ported."""
        winner_files = set(winner.files_modified)
        loser_files = set(loser.files_modified)

        # Files only in loser (purely additive features)
        unique = loser_files - winner_files

        # Filter to likely feature files (not tests, configs, etc.)
        feature_files = [
            f for f in unique
            if not self._is_test_or_config(f)
        ]

        return feature_files

    def _is_test_or_config(self, filepath: str) -> bool:
        """Check if file is a test or config file."""
        path = filepath.lower()

        # Test files
        if "test" in path or "spec" in path:
            return True

        # Config files
        config_patterns = [
            ".config.",
            "config/",
            ".env",
            ".yaml",
            ".yml",
            ".json",
            ".toml",
            "setup.",
            "pyproject.",
        ]

        return any(p in path for p in config_patterns)

    def _apply_features(
        self,
        winner_branch: str,
        loser_branch: str,
        files: list[str],
    ) -> bool:
        """Apply feature files from loser to winner branch."""
        if not files:
            return True

        try:
            # Checkout winner branch
            subprocess.run(
                ["git", "checkout", winner_branch],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )

            # Cherry-pick or copy files from loser
            for filepath in files:
                # Get file content from loser branch
                result = subprocess.run(
                    ["git", "show", f"{loser_branch}:{filepath}"],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0:
                    logger.warning(f"Could not get {filepath} from {loser_branch}")
                    continue

                # Write to winner branch
                target_path = self.repo_path / filepath
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(result.stdout)

            # Commit the changes
            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.repo_path,
                capture_output=True,
            )

            subprocess.run(
                ["git", "commit", "-m", f"Port features from {loser_branch}"],
                cwd=self.repo_path,
                capture_output=True,
            )

            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Git operation failed: {e}")
            return False

    def _verify_build(self, branch: str) -> bool:
        """Verify that build passes after porting."""
        try:
            subprocess.run(
                ["git", "checkout", branch],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )

            # Auto-detect and run build
            if (self.repo_path / "pyproject.toml").exists():
                result = subprocess.run(
                    ["python", "-m", "py_compile"] +
                    [str(f) for f in self.repo_path.glob("**/*.py") if ".venv" not in str(f)][:50],
                    cwd=self.repo_path,
                    capture_output=True,
                )
                return result.returncode == 0

            elif (self.repo_path / "package.json").exists():
                result = subprocess.run(
                    ["npm", "run", "build", "--if-present"],
                    cwd=self.repo_path,
                    capture_output=True,
                )
                return result.returncode == 0

            # No build system detected, assume success
            return True

        except Exception as e:
            logger.error(f"Build verification failed: {e}")
            return False

    def _revert_changes(self, branch: str) -> bool:
        """Revert the last commit on a branch."""
        try:
            subprocess.run(
                ["git", "checkout", branch],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )

            subprocess.run(
                ["git", "reset", "--hard", "HEAD~1"],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )

            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Revert failed: {e}")
            return False


class FeatureIdentifier:
    """
    Identifies what features exist in each candidate.

    Used to understand what would be lost when selecting an option.
    """

    def __init__(self, repo_path: Optional[Path] = None):
        self.repo_path = repo_path or Path.cwd()

    def identify_features(
        self,
        candidate: ResolutionCandidate,
        base_branch: str = "main",
    ) -> list[dict]:
        """
        Identify features added by this candidate.

        Returns list of dicts with:
        - name: Feature name
        - files: Files involved
        - description: Auto-generated description
        """
        features = []

        # Group files by apparent feature
        file_groups = self._group_files_by_feature(candidate.files_modified)

        for feature_name, files in file_groups.items():
            description = self._describe_feature(files, candidate.branch_name, base_branch)
            features.append({
                "name": feature_name,
                "files": files,
                "description": description,
            })

        return features

    def _group_files_by_feature(self, files: list[str]) -> dict[str, list[str]]:
        """Group files by apparent feature based on directory/naming."""
        groups = {}

        for filepath in files:
            # Extract feature name from path
            parts = Path(filepath).parts

            # Use second-level directory as feature name if it exists
            if len(parts) >= 2:
                feature = parts[1]  # e.g., "auth" from "src/auth/login.py"
            else:
                feature = "core"

            if feature not in groups:
                groups[feature] = []
            groups[feature].append(filepath)

        return groups

    def _describe_feature(
        self,
        files: list[str],
        branch: str,
        base_branch: str,
    ) -> str:
        """Generate a description of a feature from its files."""
        # Count file types
        py_count = sum(1 for f in files if f.endswith(".py"))
        js_count = sum(1 for f in files if f.endswith((".js", ".ts")))
        test_count = sum(1 for f in files if "test" in f.lower())

        parts = []

        if py_count > 0:
            parts.append(f"{py_count} Python files")
        if js_count > 0:
            parts.append(f"{js_count} JS/TS files")
        if test_count > 0:
            parts.append(f"{test_count} tests")

        return f"Adds {', '.join(parts)}" if parts else "Various changes"
