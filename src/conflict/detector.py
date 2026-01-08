"""
Conflict Detector

Detects conflicts between agent branches using git merge-tree.

Phase 1 (MVP): Basic textual conflict detection
Phase 2+: Build testing, semantic analysis, dependency conflicts

CRITICAL: Test the MERGED result, not just individual branches.
A merge can be "git clean" but still broken (semantic conflicts).
"""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class ConflictType(Enum):
    """Type of conflict detected."""
    NONE = "none"                    # No conflicts, fast-path merge
    TEXTUAL = "textual"              # Git-level conflicts only
    SEMANTIC = "semantic"            # Same area, different approaches
    ARCHITECTURAL = "architectural"  # Fundamental design disagreement
    DEPENDENCY = "dependency"        # Package/library conflicts


class ConflictSeverity(Enum):
    """Severity of the conflict."""
    LOW = "low"           # Auto-resolve with high confidence
    MEDIUM = "medium"     # Auto-resolve with caution
    HIGH = "high"         # May need human input
    CRITICAL = "critical"  # Definitely needs human input


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ConflictFile:
    """A file with conflicts."""
    file_path: str
    conflict_markers: int = 0
    our_changes: list[str] = field(default_factory=list)
    their_changes: list[str] = field(default_factory=list)


@dataclass
class ConflictInfo:
    """Information about conflicts between branches."""
    has_conflicts: bool
    conflict_type: ConflictType
    severity: ConflictSeverity

    # Branches involved
    base_branch: str
    branches: list[str]

    # Conflict details
    conflicting_files: list[ConflictFile] = field(default_factory=list)
    merge_tree_output: str = ""

    # For fast-path: if no conflicts, this is the merged tree SHA
    merged_tree_sha: Optional[str] = None

    @property
    def is_fast_path(self) -> bool:
        """Can this be fast-path merged without resolution?"""
        return self.conflict_type == ConflictType.NONE

    @property
    def file_count(self) -> int:
        """Number of files with conflicts."""
        return len(self.conflicting_files)


# ============================================================================
# Conflict Detector
# ============================================================================

class ConflictDetector:
    """
    Detects conflicts between agent branches.

    Phase 1: Uses git merge-tree for basic textual conflict detection.
    Phase 2+: Will add build testing, semantic analysis.
    """

    def __init__(self, base_branch: str = "main"):
        self.base_branch = base_branch

    def detect(self, branches: list[str]) -> ConflictInfo:
        """
        Detect conflicts between branches.

        Args:
            branches: List of branch names to check for conflicts

        Returns:
            ConflictInfo with details about any conflicts found
        """
        if not branches:
            return self._no_conflict_result([])

        if len(branches) == 1:
            # Single branch - check against base
            return self._detect_single_branch(branches[0])

        # Multiple branches - check pairwise and combined
        return self._detect_multiple_branches(branches)

    def _detect_single_branch(self, branch: str) -> ConflictInfo:
        """Detect conflicts between a single branch and base."""
        # Get merge base
        merge_base = self._get_merge_base(self.base_branch, branch)
        if not merge_base:
            logger.error(f"Could not find merge base for {branch}")
            return self._error_result([branch], "Could not find merge base")

        # Use git merge-tree to check for conflicts
        result = self._run_merge_tree(merge_base, self.base_branch, branch)

        return self._parse_merge_tree_result(result, [branch])

    def _detect_multiple_branches(self, branches: list[str]) -> ConflictInfo:
        """
        Detect conflicts between multiple branches.

        Strategy:
        1. Find common merge base
        2. Try to merge all branches together
        3. Parse results for conflicts
        """
        # First, check if branches can merge with base individually
        individual_conflicts = []
        for branch in branches:
            result = self._detect_single_branch(branch)
            if result.has_conflicts:
                individual_conflicts.append((branch, result))

        if individual_conflicts:
            # Return the first conflict found
            # (Full multi-branch conflict detection is Phase 2+)
            branch, result = individual_conflicts[0]
            logger.warning(f"Branch {branch} has conflicts with {self.base_branch}")
            return result

        # All branches merge cleanly with base individually
        # Now check if they conflict with each other
        if len(branches) == 2:
            return self._detect_pairwise(branches[0], branches[1])

        # For 3+ branches, use sequential merge approach (MVP)
        # Full N-way conflict detection is Phase 2+
        return self._detect_sequential(branches)

    def _detect_pairwise(self, branch1: str, branch2: str) -> ConflictInfo:
        """Detect conflicts between two branches."""
        # Get merge base between the two branches
        merge_base = self._get_merge_base(branch1, branch2)
        if not merge_base:
            # Try using main as base
            merge_base = self._get_merge_base(self.base_branch, branch1)

        if not merge_base:
            return self._error_result([branch1, branch2], "Could not find merge base")

        result = self._run_merge_tree(merge_base, branch1, branch2)
        return self._parse_merge_tree_result(result, [branch1, branch2])

    def _detect_sequential(self, branches: list[str]) -> ConflictInfo:
        """
        Detect conflicts by sequentially merging branches.

        This is a simplified approach for MVP. Full graph-based
        conflict detection is Phase 2+.
        """
        # Check each pair of branches
        for i, branch1 in enumerate(branches):
            for branch2 in branches[i + 1:]:
                result = self._detect_pairwise(branch1, branch2)
                if result.has_conflicts:
                    logger.warning(f"Conflict detected between {branch1} and {branch2}")
                    return result

        # No conflicts found between any pairs
        return self._no_conflict_result(branches)

    def _run_merge_tree(
        self,
        base: str,
        branch1: str,
        branch2: str
    ) -> subprocess.CompletedProcess:
        """
        Run git merge-tree to detect conflicts.

        git merge-tree outputs:
        - Clean merge: just the tree SHA
        - Conflicts: conflict markers and file info
        """
        # Modern git merge-tree (2.38+) with --write-tree
        result = subprocess.run(
            ["git", "merge-tree", "--write-tree", base, branch1, branch2],
            capture_output=True,
            text=True
        )

        # If modern merge-tree fails, try legacy format
        if result.returncode != 0 and "unrecognized option" in result.stderr.lower():
            result = subprocess.run(
                ["git", "merge-tree", base, branch1, branch2],
                capture_output=True,
                text=True
            )

        return result

    def _parse_merge_tree_result(
        self,
        result: subprocess.CompletedProcess,
        branches: list[str]
    ) -> ConflictInfo:
        """Parse the output of git merge-tree."""
        output = result.stdout + result.stderr

        # Check for conflict markers
        has_conflict_markers = bool(re.search(r'<{7}|>{7}|={7}', output))
        has_conflict_header = "CONFLICT" in output.upper()

        if result.returncode == 0 and not has_conflict_markers and not has_conflict_header:
            # Clean merge
            tree_sha = output.strip().split('\n')[0] if output.strip() else None
            return ConflictInfo(
                has_conflicts=False,
                conflict_type=ConflictType.NONE,
                severity=ConflictSeverity.LOW,
                base_branch=self.base_branch,
                branches=branches,
                merged_tree_sha=tree_sha,
                merge_tree_output=output,
            )

        # Parse conflicting files
        conflicting_files = self._extract_conflicting_files(output)

        # Determine severity based on file types
        severity = self._assess_severity(conflicting_files)

        return ConflictInfo(
            has_conflicts=True,
            conflict_type=ConflictType.TEXTUAL,
            severity=severity,
            base_branch=self.base_branch,
            branches=branches,
            conflicting_files=conflicting_files,
            merge_tree_output=output,
        )

    def _extract_conflicting_files(self, output: str) -> list[ConflictFile]:
        """Extract list of files with conflicts from merge-tree output."""
        files = []

        # Look for file paths in conflict output
        # Format varies but typically includes file paths
        file_pattern = re.compile(r'(?:CONFLICT|conflict).*?(\S+\.\w+)')
        for match in file_pattern.finditer(output):
            file_path = match.group(1)
            if file_path not in [f.file_path for f in files]:
                files.append(ConflictFile(file_path=file_path))

        # Also look for paths in the content section
        path_pattern = re.compile(r'^[+\-]{3} [ab]/(.+)$', re.MULTILINE)
        for match in path_pattern.finditer(output):
            file_path = match.group(1)
            if file_path not in [f.file_path for f in files]:
                files.append(ConflictFile(file_path=file_path))

        return files

    def _assess_severity(self, conflicting_files: list[ConflictFile]) -> ConflictSeverity:
        """Assess conflict severity based on files involved."""
        critical_patterns = [
            r"auth", r"security", r"password", r"token", r"secret",
            r"payment", r"billing", r"migrations?/",
        ]

        high_patterns = [
            r"api/", r"core/", r"config", r"\.env",
        ]

        for file_info in conflicting_files:
            path = file_info.file_path.lower()

            for pattern in critical_patterns:
                if re.search(pattern, path):
                    return ConflictSeverity.CRITICAL

            for pattern in high_patterns:
                if re.search(pattern, path):
                    return ConflictSeverity.HIGH

        if len(conflicting_files) > 5:
            return ConflictSeverity.HIGH

        if len(conflicting_files) > 2:
            return ConflictSeverity.MEDIUM

        return ConflictSeverity.LOW

    def _get_merge_base(self, ref1: str, ref2: str) -> Optional[str]:
        """Get the merge base between two refs."""
        result = subprocess.run(
            ["git", "merge-base", ref1, ref2],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def _no_conflict_result(self, branches: list[str]) -> ConflictInfo:
        """Return a result indicating no conflicts."""
        return ConflictInfo(
            has_conflicts=False,
            conflict_type=ConflictType.NONE,
            severity=ConflictSeverity.LOW,
            base_branch=self.base_branch,
            branches=branches,
        )

    def _error_result(self, branches: list[str], message: str) -> ConflictInfo:
        """Return an error result."""
        logger.error(message)
        return ConflictInfo(
            has_conflicts=True,
            conflict_type=ConflictType.TEXTUAL,
            severity=ConflictSeverity.HIGH,
            base_branch=self.base_branch,
            branches=branches,
            merge_tree_output=f"Error: {message}",
        )


# ============================================================================
# Convenience Functions
# ============================================================================

def detect_conflicts(
    branches: list[str],
    base_branch: str = "main"
) -> ConflictInfo:
    """
    Convenience function to detect conflicts between branches.

    Args:
        branches: List of branch names to check
        base_branch: The base branch (default: main)

    Returns:
        ConflictInfo with details about any conflicts
    """
    detector = ConflictDetector(base_branch=base_branch)
    return detector.detect(branches)
