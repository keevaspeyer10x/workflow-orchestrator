"""
Git Conflict Resolver - CORE-023 Part 1

Resolves git merge/rebase conflicts when git is in conflict state.

Philosophy: Rebase-first - target branch is truth, adapt our changes.

Resolution strategies (in order):
1. rerere - reuse recorded resolution
2. 3-way merge (git merge-file) - for non-overlapping changes
3. ours/theirs - forced strategy
4. interactive - escalate to user with analysis and recommendation

This module is designed for:
- CLI usage: `orchestrator resolve`
- PRD integration: WaveResolver can use the same core
"""

import ast
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class ResolutionStrategy(Enum):
    """Resolution strategy used."""
    AUTO = "auto"        # Try automatic strategies
    RERERE = "rerere"    # Reused recorded resolution
    THREE_WAY = "3way"   # Git 3-way merge
    OURS = "ours"        # Keep our changes
    THEIRS = "theirs"    # Keep their changes
    BOTH = "both"        # Keep both (concatenated)
    INTERACTIVE = "interactive"  # User chose


class ConflictType(Enum):
    """Type of git conflict state."""
    NONE = "none"        # No conflict
    MERGE = "merge"      # During git merge
    REBASE = "rebase"    # During git rebase


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ConflictedFile:
    """A file with conflicts, including base/ours/theirs versions."""
    path: str
    base: Optional[str] = None     # Common ancestor (stage 1)
    ours: Optional[str] = None     # Our version (stage 2 / HEAD)
    theirs: Optional[str] = None   # Their version (stage 3 / MERGE_HEAD)

    # Analysis info (populated during escalation)
    ours_line_range: tuple[int, int] = (0, 0)
    theirs_line_range: tuple[int, int] = (0, 0)
    overlap_range: tuple[int, int] = (0, 0)
    ours_summary: str = ""
    theirs_summary: str = ""


@dataclass
class ResolutionResult:
    """Result of resolving a single file."""
    file_path: str
    resolved_content: Optional[str] = None
    strategy: str = "auto"
    confidence: float = 0.0

    # Escalation info
    needs_escalation: bool = False
    escalation_analysis: Optional[str] = None
    escalation_options: list[str] = field(default_factory=list)
    escalation_recommendation: str = ""

    # Validation
    is_valid: bool = True
    validation_error: str = ""

    @property
    def success(self) -> bool:
        """True if resolution succeeded without escalation."""
        return self.resolved_content is not None and not self.needs_escalation and self.is_valid


@dataclass
class ResolveAllResult:
    """Result of resolving all conflicts."""
    total_files: int
    resolved_count: int
    escalated_count: int
    failed_count: int
    results: list[ResolutionResult] = field(default_factory=list)

    @property
    def all_resolved(self) -> bool:
        """True if all files resolved without escalation."""
        return self.resolved_count == self.total_files

    @property
    def has_escalations(self) -> bool:
        """True if any files need user input."""
        return self.escalated_count > 0


# ============================================================================
# Git Conflict Resolver
# ============================================================================

class GitConflictResolver:
    """
    Resolves git merge/rebase conflicts when git is in conflict state.

    Usage:
        resolver = GitConflictResolver()
        if resolver.has_conflicts():
            result = resolver.resolve_all()
            if result.has_escalations:
                # Handle interactive resolution
                for r in result.results:
                    if r.needs_escalation:
                        print(r.escalation_analysis)
    """

    def __init__(self, repo_path: Optional[Path] = None):
        """
        Initialize the resolver.

        Args:
            repo_path: Path to git repository (default: current directory)
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self._validate_git_repo()

    def _validate_git_repo(self) -> None:
        """Validate that we're in a git repository."""
        git_dir = self.repo_path / ".git"
        if not git_dir.exists():
            raise ValueError(f"Not a git repository: {self.repo_path}")

    # ========================================================================
    # Detection Methods
    # ========================================================================

    def has_conflicts(self) -> bool:
        """
        Check if git is currently in a conflict state.

        Returns:
            True if there are unresolved conflicts
        """
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            capture_output=True, text=True,
            cwd=self.repo_path
        )
        return bool(result.stdout.strip())

    def get_conflict_type(self) -> ConflictType:
        """
        Determine if we're in a merge or rebase conflict.

        Returns:
            ConflictType.MERGE, ConflictType.REBASE, or ConflictType.NONE
        """
        if not self.has_conflicts():
            return ConflictType.NONE

        if (self.repo_path / ".git/rebase-merge").exists():
            return ConflictType.REBASE
        if (self.repo_path / ".git/rebase-apply").exists():
            return ConflictType.REBASE

        return ConflictType.MERGE

    def is_rebase_conflict(self) -> bool:
        """Check if conflict is from rebase (vs merge)."""
        return self.get_conflict_type() == ConflictType.REBASE

    def get_conflicted_files(self) -> list[str]:
        """
        Get list of files with unresolved conflicts.

        Returns:
            List of file paths relative to repo root
        """
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            capture_output=True, text=True,
            cwd=self.repo_path
        )
        if not result.stdout.strip():
            return []
        return [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]

    def get_conflict_info(self, file_path: str) -> ConflictedFile:
        """
        Get base/ours/theirs versions of a conflicted file.

        Uses git index stages:
        - Stage 1 (:1:) = common ancestor (base)
        - Stage 2 (:2:) = ours (HEAD)
        - Stage 3 (:3:) = theirs (MERGE_HEAD)

        Args:
            file_path: Path to conflicted file

        Returns:
            ConflictedFile with all three versions
        """
        base = self._git_show(f":1:{file_path}")
        ours = self._git_show(f":2:{file_path}")
        theirs = self._git_show(f":3:{file_path}")

        conflict = ConflictedFile(
            path=file_path,
            base=base,
            ours=ours,
            theirs=theirs,
        )

        # Calculate line change ranges for escalation analysis
        if base and ours and theirs:
            self._analyze_changes(conflict)

        return conflict

    def _git_show(self, ref: str) -> Optional[str]:
        """Get content from a git ref (e.g., ':1:path')."""
        result = subprocess.run(
            ["git", "show", ref],
            capture_output=True, text=True,
            cwd=self.repo_path
        )
        if result.returncode != 0:
            return None
        return result.stdout

    def _analyze_changes(self, conflict: ConflictedFile) -> None:
        """Analyze what changed in ours vs theirs compared to base."""
        if not conflict.base or not conflict.ours or not conflict.theirs:
            return

        base_lines = conflict.base.splitlines()
        ours_lines = conflict.ours.splitlines()
        theirs_lines = conflict.theirs.splitlines()

        # Simple line-by-line diff to find changed ranges
        # (This is a simplified version - production would use difflib)
        ours_diff_start = 0
        ours_diff_end = 0
        theirs_diff_start = 0
        theirs_diff_end = 0

        # Find first difference in ours
        for i, (b, o) in enumerate(zip(base_lines, ours_lines)):
            if b != o:
                ours_diff_start = i + 1
                break

        # Find last difference in ours
        for i, (b, o) in enumerate(zip(reversed(base_lines), reversed(ours_lines))):
            if b != o:
                ours_diff_end = len(ours_lines) - i
                break

        # Same for theirs
        for i, (b, t) in enumerate(zip(base_lines, theirs_lines)):
            if b != t:
                theirs_diff_start = i + 1
                break

        for i, (b, t) in enumerate(zip(reversed(base_lines), reversed(theirs_lines))):
            if b != t:
                theirs_diff_end = len(theirs_lines) - i
                break

        conflict.ours_line_range = (ours_diff_start, ours_diff_end)
        conflict.theirs_line_range = (theirs_diff_start, theirs_diff_end)

        # Calculate overlap
        overlap_start = max(ours_diff_start, theirs_diff_start)
        overlap_end = min(ours_diff_end, theirs_diff_end)
        if overlap_start <= overlap_end:
            conflict.overlap_range = (overlap_start, overlap_end)

        # Generate summaries (simple version for Part 1)
        ours_changed = ours_diff_end - ours_diff_start + 1 if ours_diff_start else 0
        theirs_changed = theirs_diff_end - theirs_diff_start + 1 if theirs_diff_start else 0

        conflict.ours_summary = f"{ours_changed} lines changed"
        conflict.theirs_summary = f"{theirs_changed} lines changed"

    # ========================================================================
    # Resolution Methods
    # ========================================================================

    def resolve_file(self, file_path: str, strategy: str = "auto") -> ResolutionResult:
        """
        Resolve a single conflicted file.

        Strategy escalation for "auto":
        1. Check rerere for recorded resolution
        2. Try fast 3-way merge (git merge-file)
        3. If fails → build escalation for interactive resolution

        Args:
            file_path: Path to conflicted file
            strategy: "auto", "ours", "theirs", "3way", or "both"

        Returns:
            ResolutionResult with resolved content or escalation info
        """
        conflict = self.get_conflict_info(file_path)

        # Strategy 1: Check rerere
        if strategy == "auto":
            rerere_result = self._check_rerere(file_path)
            if rerere_result:
                result = ResolutionResult(
                    file_path=file_path,
                    resolved_content=rerere_result,
                    strategy="rerere",
                    confidence=0.95,
                )
                # Validate
                valid, error = self._validate_resolution(file_path, rerere_result)
                result.is_valid = valid
                result.validation_error = error
                return result

        # Strategy 2: Fast 3-way merge
        if strategy in ("auto", "3way"):
            merge_result = self._try_3way_merge(conflict)
            if merge_result.success:
                return merge_result

        # Strategy 3: Forced strategy - ours
        if strategy == "ours":
            if not conflict.ours:
                return ResolutionResult(
                    file_path=file_path,
                    needs_escalation=True,
                    escalation_analysis="Cannot get 'ours' version from git index",
                )
            result = ResolutionResult(
                file_path=file_path,
                resolved_content=conflict.ours,
                strategy="ours",
                confidence=1.0,
            )
            valid, error = self._validate_resolution(file_path, conflict.ours)
            result.is_valid = valid
            result.validation_error = error
            return result

        # Strategy 4: Forced strategy - theirs
        if strategy == "theirs":
            if not conflict.theirs:
                return ResolutionResult(
                    file_path=file_path,
                    needs_escalation=True,
                    escalation_analysis="Cannot get 'theirs' version from git index",
                )
            result = ResolutionResult(
                file_path=file_path,
                resolved_content=conflict.theirs,
                strategy="theirs",
                confidence=1.0,
            )
            valid, error = self._validate_resolution(file_path, conflict.theirs)
            result.is_valid = valid
            result.validation_error = error
            return result

        # Strategy 5: Keep both (concatenate)
        if strategy == "both":
            if not conflict.ours or not conflict.theirs:
                return ResolutionResult(
                    file_path=file_path,
                    needs_escalation=True,
                    escalation_analysis="Cannot get both versions from git index",
                )
            both_content = conflict.ours + "\n" + conflict.theirs
            result = ResolutionResult(
                file_path=file_path,
                resolved_content=both_content,
                strategy="both",
                confidence=0.5,  # Low confidence - may need cleanup
            )
            valid, error = self._validate_resolution(file_path, both_content)
            result.is_valid = valid
            result.validation_error = error
            return result

        # Escalate to interactive
        return self._build_escalation(conflict)

    def resolve_all(self, strategy: str = "auto") -> ResolveAllResult:
        """
        Resolve all conflicted files.

        Args:
            strategy: Strategy to use for all files

        Returns:
            ResolveAllResult with per-file results
        """
        files = self.get_conflicted_files()
        results = []
        resolved = 0
        escalated = 0
        failed = 0

        for file_path in files:
            try:
                result = self.resolve_file(file_path, strategy)
                results.append(result)

                if result.success:
                    resolved += 1
                elif result.needs_escalation:
                    escalated += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Failed to resolve {file_path}: {e}")
                results.append(ResolutionResult(
                    file_path=file_path,
                    needs_escalation=True,
                    escalation_analysis=f"Resolution failed: {e}",
                ))
                failed += 1

        return ResolveAllResult(
            total_files=len(files),
            resolved_count=resolved,
            escalated_count=escalated,
            failed_count=failed,
            results=results,
        )

    def apply_resolution(self, result: ResolutionResult) -> bool:
        """
        Apply a resolution to the working tree.

        Args:
            result: Resolution result to apply

        Returns:
            True if applied successfully
        """
        if not result.resolved_content:
            return False

        file_path = self.repo_path / result.file_path

        # Write resolved content
        try:
            file_path.write_text(result.resolved_content)
        except Exception as e:
            logger.error(f"Failed to write {result.file_path}: {e}")
            return False

        # Stage the resolved file
        subprocess.run(
            ["git", "add", result.file_path],
            cwd=self.repo_path,
            capture_output=True
        )

        return True

    def apply_all_resolutions(self, results: list[ResolutionResult]) -> tuple[int, int]:
        """
        Apply all successful resolutions.

        Args:
            results: List of resolution results

        Returns:
            Tuple of (applied_count, failed_count)
        """
        applied = 0
        failed = 0

        for result in results:
            if result.success:
                if self.apply_resolution(result):
                    applied += 1
                else:
                    failed += 1

        return applied, failed

    # ========================================================================
    # Resolution Strategies
    # ========================================================================

    def _check_rerere(self, file_path: str) -> Optional[str]:
        """
        Check if rerere has a recorded resolution for this conflict.

        Returns:
            Resolved content if rerere has a resolution, None otherwise
        """
        # Run git rerere to check for recorded resolution
        result = subprocess.run(
            ["git", "rerere", "status"],
            capture_output=True, text=True,
            cwd=self.repo_path
        )

        if file_path not in result.stdout:
            return None

        # Try to apply rerere resolution
        subprocess.run(
            ["git", "rerere"],
            capture_output=True, text=True,
            cwd=self.repo_path
        )

        # Check if file is now clean
        full_path = self.repo_path / file_path
        if full_path.exists():
            content = full_path.read_text()
            # Check if conflict markers are gone
            if "<<<<<<" not in content and "======" not in content:
                return content

        return None

    def _try_3way_merge(self, conflict: ConflictedFile) -> ResolutionResult:
        """
        Try to resolve using git merge-file (3-way merge).

        This works for non-overlapping changes.
        """
        if not conflict.base or not conflict.ours or not conflict.theirs:
            return ResolutionResult(
                file_path=conflict.path,
                needs_escalation=True,
                escalation_analysis="Cannot perform 3-way merge: missing base, ours, or theirs",
            )

        # Create temp files
        with tempfile.TemporaryDirectory() as tmpdir:
            base_file = Path(tmpdir) / "base"
            ours_file = Path(tmpdir) / "ours"
            theirs_file = Path(tmpdir) / "theirs"

            base_file.write_text(conflict.base)
            ours_file.write_text(conflict.ours)
            theirs_file.write_text(conflict.theirs)

            # Run git merge-file (modifies ours_file in place)
            result = subprocess.run(
                ["git", "merge-file", "-p", str(ours_file), str(base_file), str(theirs_file)],
                capture_output=True, text=True,
                cwd=self.repo_path
            )

            # returncode 0 = clean merge, >0 = conflicts
            if result.returncode == 0:
                merged_content = result.stdout
                res = ResolutionResult(
                    file_path=conflict.path,
                    resolved_content=merged_content,
                    strategy="3way",
                    confidence=0.8,
                )
                valid, error = self._validate_resolution(conflict.path, merged_content)
                res.is_valid = valid
                res.validation_error = error
                return res
            else:
                # 3-way merge had conflicts
                return ResolutionResult(
                    file_path=conflict.path,
                    needs_escalation=True,
                    escalation_analysis="3-way merge produced conflicts",
                )

    def _build_escalation(self, conflict: ConflictedFile) -> ResolutionResult:
        """
        Build escalation info for interactive resolution.

        Provides:
        - Analysis of what changed
        - Options to choose from
        - Recommendation (rebase-first: prefer ours)
        """
        # Build analysis
        analysis_lines = [
            f"CONFLICT ANALYSIS: {conflict.path}",
            "",
            "Changes detected:",
        ]

        if conflict.ours_line_range[0]:
            analysis_lines.append(
                f"  OURS (our changes): Lines {conflict.ours_line_range[0]}-{conflict.ours_line_range[1]} "
                f"({conflict.ours_summary})"
            )

        if conflict.theirs_line_range[0]:
            analysis_lines.append(
                f"  THEIRS (target branch): Lines {conflict.theirs_line_range[0]}-{conflict.theirs_line_range[1]} "
                f"({conflict.theirs_summary})"
            )

        if conflict.overlap_range[0]:
            analysis_lines.append(
                f"  OVERLAP: Lines {conflict.overlap_range[0]}-{conflict.overlap_range[1]}"
            )

        # Build options
        options = [
            "[A] Keep OURS - Preserves our work (RECOMMENDED: rebase-first philosophy)",
            "[B] Keep THEIRS - Accepts target branch changes, discards ours",
            "[C] Keep BOTH - Concatenates both (may need manual cleanup)",
            "[D] Open in editor - Manual resolution with conflict markers",
        ]

        # Recommendation: rebase-first = prefer ours
        recommendation = (
            "RECOMMENDATION: Choose [A] Keep OURS\n"
            "Rebase-first philosophy: Target is truth, but preserve our work and "
            "refactor it to be consistent with target."
        )

        return ResolutionResult(
            file_path=conflict.path,
            needs_escalation=True,
            escalation_analysis="\n".join(analysis_lines),
            escalation_options=options,
            escalation_recommendation=recommendation,
        )

    # ========================================================================
    # Validation
    # ========================================================================

    def _validate_resolution(self, file_path: str, content: str) -> tuple[bool, str]:
        """
        Validate a resolution.

        Checks:
        1. No leftover conflict markers
        2. Python syntax valid (for .py files)

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check for leftover conflict markers
        if "<<<<<<" in content or "======" in content or ">>>>>>" in content:
            return False, "Leftover conflict markers detected"

        # Syntax check for Python files
        if file_path.endswith(".py"):
            try:
                ast.parse(content)
            except SyntaxError as e:
                return False, f"Python syntax error: {e}"

        return True, ""

    # ========================================================================
    # Rollback and Abort
    # ========================================================================

    def rollback_file(self, file_path: str) -> bool:
        """
        Restore a file to its conflicted state.

        Args:
            file_path: Path to file to rollback

        Returns:
            True if successful
        """
        result = subprocess.run(
            ["git", "checkout", "--conflict=merge", file_path],
            cwd=self.repo_path,
            capture_output=True
        )
        return result.returncode == 0

    def abort(self) -> bool:
        """
        Abort the current merge or rebase.

        Returns:
            True if successful
        """
        if self.is_rebase_conflict():
            result = subprocess.run(
                ["git", "rebase", "--abort"],
                cwd=self.repo_path,
                capture_output=True
            )
        else:
            result = subprocess.run(
                ["git", "merge", "--abort"],
                cwd=self.repo_path,
                capture_output=True
            )

        return result.returncode == 0

    def continue_operation(self) -> bool:
        """
        Continue the merge/rebase after conflicts are resolved.

        Returns:
            True if successful
        """
        if self.is_rebase_conflict():
            result = subprocess.run(
                ["git", "rebase", "--continue"],
                cwd=self.repo_path,
                capture_output=True
            )
        else:
            # For merge, just need to commit
            result = subprocess.run(
                ["git", "commit", "--no-edit"],
                cwd=self.repo_path,
                capture_output=True
            )

        return result.returncode == 0


# ============================================================================
# Convenience Functions
# ============================================================================

def get_resolver(repo_path: Optional[Path] = None) -> GitConflictResolver:
    """
    Get a conflict resolver for the given repository.

    Args:
        repo_path: Path to git repository (default: current directory)

    Returns:
        GitConflictResolver instance
    """
    return GitConflictResolver(repo_path=repo_path)


def check_conflicts(repo_path: Optional[Path] = None) -> tuple[bool, list[str]]:
    """
    Check if there are any git conflicts.

    Args:
        repo_path: Path to git repository

    Returns:
        Tuple of (has_conflicts, list_of_files)
    """
    try:
        resolver = get_resolver(repo_path)
        files = resolver.get_conflicted_files()
        return len(files) > 0, files
    except ValueError:
        return False, []


def format_escalation_for_user(result: ResolutionResult) -> str:
    """
    Format an escalation result for interactive display.

    Args:
        result: ResolutionResult that needs escalation

    Returns:
        Formatted string for terminal display
    """
    if not result.needs_escalation:
        return ""

    lines = [
        "=" * 60,
        f"MANUAL DECISION REQUIRED: {result.file_path}",
        "=" * 60,
        "",
    ]

    if result.escalation_analysis:
        lines.append(result.escalation_analysis)
        lines.append("")

    if result.escalation_options:
        lines.append("OPTIONS:")
        for option in result.escalation_options:
            lines.append(f"  {option}")
        lines.append("")

    if result.escalation_recommendation:
        lines.append(result.escalation_recommendation)

    lines.append("=" * 60)

    return "\n".join(lines)
