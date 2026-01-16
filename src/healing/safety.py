"""Safety categorization for fix analysis.

This module categorizes fixes by safety level based on diff analysis.
"""

import re
from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatch
from typing import List, Optional

from .config import get_config


class SafetyCategory(Enum):
    """Safety level for a proposed fix."""

    SAFE = "safe"  # Formatting, imports, type hints
    MODERATE = "moderate"  # Error handling, conditionals
    RISKY = "risky"  # Protected paths, signatures, returns


@dataclass
class SafetyAnalysis:
    """Result of safety categorization."""

    category: SafetyCategory
    reasons: List[str]
    protected_paths_matched: List[str]

    @property
    def is_auto_applicable(self) -> bool:
        """Check if this fix can be auto-applied."""
        config = get_config()
        if self.category == SafetyCategory.SAFE:
            return config.auto_apply_safe
        elif self.category == SafetyCategory.MODERATE:
            return config.auto_apply_moderate
        return False


class SafetyCategorizer:
    """Categorize fix safety based on diff analysis.

    This class analyzes diffs to determine how risky a fix is:
    - SAFE: Formatting, imports, type hints only
    - MODERATE: Error handling, conditionals
    - RISKY: Protected paths, function signatures, return types
    """

    def __init__(self, config=None):
        """Initialize with optional config override."""
        self._config = config

    @property
    def config(self):
        """Get configuration (lazy load)."""
        if self._config is None:
            self._config = get_config()
        return self._config

    def categorize(
        self,
        diff: str,
        affected_files: List[str],
    ) -> SafetyAnalysis:
        """Analyze diff and return safety category.

        Args:
            diff: The unified diff content
            affected_files: List of file paths affected by the change

        Returns:
            SafetyAnalysis with category and reasoning
        """
        reasons = []
        protected_matches = []

        # Check protected paths first (highest priority)
        for path in affected_files:
            if self._is_protected(path):
                protected_matches.append(path)

        if protected_matches:
            reasons.append(f"Protected paths: {', '.join(protected_matches)}")
            return SafetyAnalysis(
                category=SafetyCategory.RISKY,
                reasons=reasons,
                protected_paths_matched=protected_matches,
            )

        # Analyze diff content
        if not diff.strip():
            reasons.append("Empty diff")
            return SafetyAnalysis(
                category=SafetyCategory.SAFE,
                reasons=reasons,
                protected_paths_matched=[],
            )

        # Check for risky changes
        risky_reasons = self._check_risky_changes(diff)
        if risky_reasons:
            reasons.extend(risky_reasons)
            return SafetyAnalysis(
                category=SafetyCategory.RISKY,
                reasons=reasons,
                protected_paths_matched=[],
            )

        # Check if only safe changes
        if self._only_formatting(diff):
            reasons.append("Formatting changes only")
            return SafetyAnalysis(
                category=SafetyCategory.SAFE,
                reasons=reasons,
                protected_paths_matched=[],
            )

        if self._only_imports(diff):
            reasons.append("Import changes only")
            return SafetyAnalysis(
                category=SafetyCategory.SAFE,
                reasons=reasons,
                protected_paths_matched=[],
            )

        if self._only_type_hints(diff):
            reasons.append("Type hint changes only")
            return SafetyAnalysis(
                category=SafetyCategory.SAFE,
                reasons=reasons,
                protected_paths_matched=[],
            )

        if self._only_comments(diff):
            reasons.append("Comment changes only")
            return SafetyAnalysis(
                category=SafetyCategory.SAFE,
                reasons=reasons,
                protected_paths_matched=[],
            )

        # Check for moderate changes
        moderate_reasons = self._check_moderate_changes(diff)
        if moderate_reasons:
            reasons.extend(moderate_reasons)
            return SafetyAnalysis(
                category=SafetyCategory.MODERATE,
                reasons=reasons,
                protected_paths_matched=[],
            )

        # Default to moderate if we can't determine
        reasons.append("Unclassified code changes")
        return SafetyAnalysis(
            category=SafetyCategory.MODERATE,
            reasons=reasons,
            protected_paths_matched=[],
        )

    def _is_protected(self, path: str) -> bool:
        """Check if path matches any protected pattern."""
        for pattern in self.config.protected_paths:
            if fnmatch(path, pattern):
                return True
        return False

    def _get_added_lines(self, diff: str) -> List[str]:
        """Extract added lines from diff (excluding header)."""
        lines = []
        for line in diff.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                lines.append(line[1:])  # Remove the + prefix
        return lines

    def _get_removed_lines(self, diff: str) -> List[str]:
        """Extract removed lines from diff (excluding header)."""
        lines = []
        for line in diff.split("\n"):
            if line.startswith("-") and not line.startswith("---"):
                lines.append(line[1:])  # Remove the - prefix
        return lines

    def _only_formatting(self, diff: str) -> bool:
        """Check if diff only contains whitespace/formatting changes."""
        added = self._get_added_lines(diff)
        removed = self._get_removed_lines(diff)

        if not added and not removed:
            return True

        # Compare stripped versions
        added_stripped = [line.strip() for line in added if line.strip()]
        removed_stripped = [line.strip() for line in removed if line.strip()]

        return added_stripped == removed_stripped

    def _only_imports(self, diff: str) -> bool:
        """Check if diff only contains import statements."""
        added = self._get_added_lines(diff)

        for line in added:
            content = line.strip()
            if not content:
                continue
            # Python imports
            if content.startswith("import ") or content.startswith("from "):
                continue
            # JavaScript/TypeScript imports
            if content.startswith("import ") or content.startswith("export "):
                continue
            # Go imports
            if content.startswith('"') and content.endswith('"'):
                continue
            # Rust imports
            if content.startswith("use "):
                continue
            # Not an import
            return False

        return True

    def _only_type_hints(self, diff: str) -> bool:
        """Check if diff only contains type hint changes."""
        added = self._get_added_lines(diff)
        removed = self._get_removed_lines(diff)

        # Type hint patterns for Python
        type_hint_patterns = [
            r":\s*\w+",  # : Type
            r"->\s*\w+",  # -> ReturnType
            r"Optional\[",  # Optional[T]
            r"List\[",  # List[T]
            r"Dict\[",  # Dict[K, V]
            r"Tuple\[",  # Tuple[...]
            r"Union\[",  # Union[...]
        ]

        for add, rem in zip(added, removed):
            add_stripped = add.strip()
            rem_stripped = rem.strip()

            # Check if the only difference is type hints
            add_no_hints = add_stripped
            rem_no_hints = rem_stripped

            for pattern in type_hint_patterns:
                add_no_hints = re.sub(pattern, "", add_no_hints)
                rem_no_hints = re.sub(pattern, "", rem_no_hints)

            if add_no_hints != rem_no_hints:
                return False

        return len(added) == len(removed)

    def _only_comments(self, diff: str) -> bool:
        """Check if diff only contains comment changes."""
        added = self._get_added_lines(diff)
        removed = self._get_removed_lines(diff)

        for line in added:
            content = line.strip()
            if not content:
                continue
            # Python/Shell comments
            if content.startswith("#"):
                continue
            # JavaScript/Go/Rust comments
            if content.startswith("//"):
                continue
            # Multi-line comments
            if content.startswith("/*") or content.startswith("*") or content.endswith("*/"):
                continue
            # Docstrings
            if content.startswith('"""') or content.startswith("'''"):
                continue
            # Not a comment
            return False

        for line in removed:
            content = line.strip()
            if not content:
                continue
            if content.startswith("#"):
                continue
            if content.startswith("//"):
                continue
            if content.startswith("/*") or content.startswith("*") or content.endswith("*/"):
                continue
            if content.startswith('"""') or content.startswith("'''"):
                continue
            return False

        return True

    def _check_risky_changes(self, diff: str) -> List[str]:
        """Check for risky change patterns."""
        reasons = []
        added = self._get_added_lines(diff)
        removed = self._get_removed_lines(diff)
        all_lines = added + removed

        # Function signature changes
        for line in all_lines:
            content = line.strip()
            # Python def with different parameters
            if re.match(r"def\s+\w+\s*\([^)]*\)", content):
                reasons.append("Function signature modified")
                break
            # JavaScript function
            if re.match(r"function\s+\w+\s*\([^)]*\)", content):
                reasons.append("Function signature modified")
                break
            # Arrow function
            if re.match(r"const\s+\w+\s*=\s*\([^)]*\)\s*=>", content):
                reasons.append("Function signature modified")
                break

        # Return type changes
        for line in all_lines:
            if re.search(r"->\s*\w+", line) and "def " in line:
                reasons.append("Return type modified")
                break

        # Database/SQL operations
        for line in added:
            content = line.lower()
            if any(
                kw in content
                for kw in ["delete from", "drop table", "alter table", "truncate"]
            ):
                reasons.append("Database schema modification")
                break

        # Security-sensitive patterns
        for line in added:
            content = line.lower()
            if any(
                kw in content
                for kw in ["password", "secret", "token", "credential", "auth"]
            ):
                reasons.append("Security-sensitive code")
                break

        return reasons

    def _check_moderate_changes(self, diff: str) -> List[str]:
        """Check for moderate change patterns."""
        reasons = []
        added = self._get_added_lines(diff)

        for line in added:
            content = line.strip()

            # Error handling
            if re.search(r"(try|except|catch|throw|raise)", content):
                reasons.append("Error handling modified")
                break

            # Conditionals
            if re.search(r"(if\s|elif\s|else\s|switch\s|case\s)", content):
                reasons.append("Conditional logic modified")
                break

            # Loops
            if re.search(r"(for\s|while\s|forEach)", content):
                reasons.append("Loop logic modified")
                break

        return reasons
