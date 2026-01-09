"""
Tests for Git Conflict Resolver - CORE-023 Part 1

Tests conflict detection, resolution strategies, and escalation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import subprocess

from src.git_conflict_resolver import (
    GitConflictResolver,
    ConflictedFile,
    ResolutionResult,
    ResolveAllResult,
    ConflictType,
    ResolutionStrategy,
    get_resolver,
    check_conflicts,
    format_escalation_for_user,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_repo(tmp_path):
    """Create a mock git repo directory."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    return tmp_path


@pytest.fixture
def resolver(mock_repo):
    """Create a resolver for the mock repo."""
    with patch.object(GitConflictResolver, '_validate_git_repo'):
        return GitConflictResolver(repo_path=mock_repo)


# ============================================================================
# Conflict Detection Tests
# ============================================================================

class TestConflictDetection:
    """Tests for detecting git conflict state."""

    def test_has_conflicts_when_unmerged_files(self, resolver):
        """Should detect conflicts when git reports unmerged files."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                stdout="src/file1.py\nsrc/file2.py\n",
                stderr="",
                returncode=0
            )

            assert resolver.has_conflicts() is True

    def test_no_conflicts_when_clean(self, resolver):
        """Should report no conflicts when git is clean."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                stdout="",
                stderr="",
                returncode=0
            )

            assert resolver.has_conflicts() is False

    def test_get_conflicted_files_parses_output(self, resolver):
        """Should parse git diff output into file list."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                stdout="src/api/client.py\nsrc/utils.py\ntests/test_client.py\n",
                stderr="",
                returncode=0
            )

            files = resolver.get_conflicted_files()

            assert len(files) == 3
            assert "src/api/client.py" in files
            assert "src/utils.py" in files
            assert "tests/test_client.py" in files

    def test_get_conflicted_files_empty_when_clean(self, resolver):
        """Should return empty list when no conflicts."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(stdout="", stderr="", returncode=0)

            files = resolver.get_conflicted_files()

            assert files == []

    def test_is_rebase_conflict_detects_rebase_merge_dir(self, mock_repo):
        """Should detect rebase conflict from .git/rebase-merge directory."""
        (mock_repo / ".git" / "rebase-merge").mkdir()

        with patch.object(GitConflictResolver, '_validate_git_repo'):
            resolver = GitConflictResolver(repo_path=mock_repo)

            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(stdout="file.py\n", returncode=0)

                assert resolver.is_rebase_conflict() is True
                assert resolver.get_conflict_type() == ConflictType.REBASE

    def test_is_rebase_conflict_detects_rebase_apply_dir(self, mock_repo):
        """Should detect rebase conflict from .git/rebase-apply directory."""
        (mock_repo / ".git" / "rebase-apply").mkdir()

        with patch.object(GitConflictResolver, '_validate_git_repo'):
            resolver = GitConflictResolver(repo_path=mock_repo)

            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(stdout="file.py\n", returncode=0)

                assert resolver.is_rebase_conflict() is True

    def test_is_merge_conflict_when_no_rebase_dirs(self, mock_repo):
        """Should detect merge conflict when no rebase directories exist."""
        with patch.object(GitConflictResolver, '_validate_git_repo'):
            resolver = GitConflictResolver(repo_path=mock_repo)

            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(stdout="file.py\n", returncode=0)

                assert resolver.is_rebase_conflict() is False
                assert resolver.get_conflict_type() == ConflictType.MERGE


class TestGetConflictInfo:
    """Tests for getting base/ours/theirs from git index."""

    def test_gets_all_three_stages(self, resolver):
        """Should get base, ours, and theirs from git index."""
        def mock_git_show(cmd, **kwargs):
            ref = cmd[2]  # "git show :N:path"
            if ":1:" in ref:
                return Mock(stdout="base content\n", returncode=0)
            elif ":2:" in ref:
                return Mock(stdout="ours content\n", returncode=0)
            elif ":3:" in ref:
                return Mock(stdout="theirs content\n", returncode=0)
            return Mock(stdout="", returncode=1)

        with patch('subprocess.run', side_effect=mock_git_show):
            conflict = resolver.get_conflict_info("src/file.py")

            assert conflict.path == "src/file.py"
            assert conflict.base == "base content\n"
            assert conflict.ours == "ours content\n"
            assert conflict.theirs == "theirs content\n"

    def test_handles_missing_base(self, resolver):
        """Should handle case where base doesn't exist (new file added on both sides)."""
        def mock_git_show(cmd, **kwargs):
            ref = cmd[2]
            if ":1:" in ref:
                return Mock(stdout="", returncode=1)  # No base
            elif ":2:" in ref:
                return Mock(stdout="ours content", returncode=0)
            elif ":3:" in ref:
                return Mock(stdout="theirs content", returncode=0)
            return Mock(returncode=1)

        with patch('subprocess.run', side_effect=mock_git_show):
            conflict = resolver.get_conflict_info("src/new_file.py")

            assert conflict.base is None
            assert conflict.ours == "ours content"
            assert conflict.theirs == "theirs content"


# ============================================================================
# Resolution Strategy Tests
# ============================================================================

class TestResolutionStrategies:
    """Tests for different resolution strategies."""

    def test_strategy_ours_returns_ours_content(self, resolver):
        """Strategy 'ours' should return our version."""
        with patch.object(resolver, 'get_conflict_info') as mock_info:
            # Use valid Python content for validation
            our_content = "def hello():\n    pass\n"
            mock_info.return_value = ConflictedFile(
                path="file.py",
                base="def base(): pass",
                ours=our_content,
                theirs="def their(): pass",
            )

            result = resolver.resolve_file("file.py", strategy="ours")

            assert result.resolved_content == our_content
            assert result.strategy == "ours"
            assert result.confidence == 1.0
            assert result.success is True

    def test_strategy_theirs_returns_theirs_content(self, resolver):
        """Strategy 'theirs' should return their version."""
        with patch.object(resolver, 'get_conflict_info') as mock_info:
            mock_info.return_value = ConflictedFile(
                path="file.py",
                base="base",
                ours="our content",
                theirs="their content",
            )

            result = resolver.resolve_file("file.py", strategy="theirs")

            assert result.resolved_content == "their content"
            assert result.strategy == "theirs"
            assert result.confidence == 1.0

    def test_strategy_both_concatenates(self, resolver):
        """Strategy 'both' should concatenate ours and theirs."""
        with patch.object(resolver, 'get_conflict_info') as mock_info:
            mock_info.return_value = ConflictedFile(
                path="file.txt",
                base="base",
                ours="line from ours",
                theirs="line from theirs",
            )

            result = resolver.resolve_file("file.txt", strategy="both")

            assert "line from ours" in result.resolved_content
            assert "line from theirs" in result.resolved_content
            assert result.strategy == "both"
            assert result.confidence == 0.5  # Low confidence

    def test_rerere_used_when_available(self, resolver, mock_repo):
        """Should use rerere resolution when available."""
        # Create a file that would be resolved by rerere
        resolved_file = mock_repo / "file.py"
        resolved_file.write_text("def hello():\n    pass\n")

        with patch.object(resolver, 'get_conflict_info') as mock_info, \
             patch('subprocess.run') as mock_run:
            mock_info.return_value = ConflictedFile(
                path="file.py",
                base="base",
                ours="ours",
                theirs="theirs",
            )

            # Mock rerere status showing this file
            def mock_subprocess(cmd, **kwargs):
                if len(cmd) >= 3 and cmd[1] == "rerere" and cmd[2] == "status":
                    return Mock(stdout="file.py\n", returncode=0)
                elif len(cmd) >= 2 and cmd[1] == "rerere":
                    return Mock(stdout="", returncode=0)
                return Mock(returncode=0)

            mock_run.side_effect = mock_subprocess

            result = resolver.resolve_file("file.py", strategy="auto")

            assert result.strategy == "rerere"
            assert result.confidence == 0.95

    def test_3way_merge_works_for_clean_merge(self, resolver):
        """3-way merge should work for non-overlapping changes."""
        # Directly test the _try_3way_merge method
        conflict = ConflictedFile(
            path="file.txt",  # Use non-Python to avoid syntax validation
            base="line 1\nline 2\nline 3",
            ours="line 1 modified\nline 2\nline 3",
            theirs="line 1\nline 2\nline 3 modified",
        )

        with patch('subprocess.run') as mock_run:
            # Mock git merge-file returning clean merge
            mock_run.return_value = Mock(
                stdout="line 1 modified\nline 2\nline 3 modified",
                returncode=0
            )

            result = resolver._try_3way_merge(conflict)

            assert result.strategy == "3way"
            assert result.confidence == 0.8
            assert result.success is True
            assert "line 1 modified" in result.resolved_content
            assert "line 3 modified" in result.resolved_content

    def test_3way_merge_escalates_on_conflict(self, resolver):
        """3-way merge should escalate when it produces conflicts."""
        # Directly test the _try_3way_merge method
        conflict = ConflictedFile(
            path="file.txt",
            base="line",
            ours="line ours",
            theirs="line theirs",
        )

        with patch('subprocess.run') as mock_run:
            # Mock git merge-file returning conflict
            mock_run.return_value = Mock(
                stdout="<<<<<<< ours\nline ours\n=======\nline theirs\n>>>>>>> theirs\n",
                returncode=1  # Non-zero = conflicts
            )

            result = resolver._try_3way_merge(conflict)

            assert result.needs_escalation is True
            assert "3-way merge" in result.escalation_analysis

    def test_auto_escalates_when_all_strategies_fail(self, resolver):
        """Auto strategy should escalate when rerere and 3way both fail."""
        with patch.object(resolver, 'get_conflict_info') as mock_info, \
             patch.object(resolver, '_check_rerere', return_value=None), \
             patch.object(resolver, '_try_3way_merge') as mock_3way:

            mock_info.return_value = ConflictedFile(
                path="file.py",
                base="base",
                ours="ours",
                theirs="theirs",
                ours_line_range=(1, 5),
                theirs_line_range=(3, 8),
                overlap_range=(3, 5),
                ours_summary="5 lines changed",
                theirs_summary="6 lines changed",
            )

            mock_3way.return_value = ResolutionResult(
                file_path="file.py",
                needs_escalation=True,
                escalation_analysis="3-way merge failed",
            )

            result = resolver.resolve_file("file.py", strategy="auto")

            assert result.needs_escalation is True
            assert result.escalation_options is not None
            assert len(result.escalation_options) > 0


# ============================================================================
# Validation Tests
# ============================================================================

class TestValidation:
    """Tests for resolution validation."""

    def test_detects_leftover_conflict_markers(self, resolver):
        """Should detect leftover conflict markers."""
        content_with_markers = """
def hello():
<<<<<<< HEAD
    print("hello from ours")
=======
    print("hello from theirs")
>>>>>>> branch
"""
        valid, error = resolver._validate_resolution("file.py", content_with_markers)

        assert valid is False
        assert "conflict markers" in error.lower()

    def test_validates_python_syntax(self, resolver):
        """Should validate Python syntax for .py files."""
        bad_python = """
def broken(:
    print("syntax error")
"""
        valid, error = resolver._validate_resolution("file.py", bad_python)

        assert valid is False
        assert "syntax error" in error.lower()

    def test_accepts_valid_python(self, resolver):
        """Should accept valid Python code."""
        good_python = """
def hello():
    print("hello world")
"""
        valid, error = resolver._validate_resolution("file.py", good_python)

        assert valid is True
        assert error == ""

    def test_skips_syntax_check_for_non_python(self, resolver):
        """Should skip syntax check for non-Python files."""
        # Invalid Python but valid for other file types
        content = "{ broken: json syntax }"

        valid, error = resolver._validate_resolution("file.json", content)

        assert valid is True


# ============================================================================
# Escalation Tests
# ============================================================================

class TestEscalation:
    """Tests for building escalation info."""

    def test_builds_analysis_with_line_ranges(self, resolver):
        """Escalation should include line range analysis."""
        conflict = ConflictedFile(
            path="file.py",
            base="base",
            ours="ours",
            theirs="theirs",
            ours_line_range=(10, 25),
            theirs_line_range=(15, 30),
            overlap_range=(15, 25),
            ours_summary="15 lines changed",
            theirs_summary="16 lines changed",
        )

        result = resolver._build_escalation(conflict)

        assert result.needs_escalation is True
        assert "10-25" in result.escalation_analysis or "Lines" in result.escalation_analysis
        assert "15-30" in result.escalation_analysis

    def test_provides_options(self, resolver):
        """Escalation should provide user options."""
        conflict = ConflictedFile(
            path="file.py",
            base="base",
            ours="ours",
            theirs="theirs",
        )

        result = resolver._build_escalation(conflict)

        assert len(result.escalation_options) == 4
        assert any("OURS" in opt for opt in result.escalation_options)
        assert any("THEIRS" in opt for opt in result.escalation_options)
        assert any("BOTH" in opt for opt in result.escalation_options)
        assert any("editor" in opt.lower() for opt in result.escalation_options)

    def test_provides_recommendation(self, resolver):
        """Escalation should include rebase-first recommendation."""
        conflict = ConflictedFile(
            path="file.py",
            base="base",
            ours="ours",
            theirs="theirs",
        )

        result = resolver._build_escalation(conflict)

        assert "RECOMMENDATION" in result.escalation_recommendation
        assert "ours" in result.escalation_recommendation.lower() or "OURS" in result.escalation_recommendation


# ============================================================================
# Resolve All Tests
# ============================================================================

class TestResolveAll:
    """Tests for resolving all conflicts."""

    def test_resolves_multiple_files(self, resolver):
        """Should resolve multiple files and track results."""
        with patch.object(resolver, 'get_conflicted_files') as mock_files, \
             patch.object(resolver, 'resolve_file') as mock_resolve:

            mock_files.return_value = ["file1.py", "file2.py", "file3.py"]
            mock_resolve.side_effect = [
                ResolutionResult(file_path="file1.py", resolved_content="resolved1", strategy="3way", confidence=0.8),
                ResolutionResult(file_path="file2.py", needs_escalation=True),
                ResolutionResult(file_path="file3.py", resolved_content="resolved3", strategy="ours", confidence=1.0),
            ]

            result = resolver.resolve_all()

            assert result.total_files == 3
            assert result.resolved_count == 2
            assert result.escalated_count == 1
            assert result.all_resolved is False
            assert result.has_escalations is True

    def test_handles_resolution_errors(self, resolver):
        """Should handle errors during resolution."""
        with patch.object(resolver, 'get_conflicted_files') as mock_files, \
             patch.object(resolver, 'resolve_file') as mock_resolve:

            mock_files.return_value = ["file1.py"]
            mock_resolve.side_effect = Exception("Resolution failed")

            result = resolver.resolve_all()

            assert result.failed_count == 1
            assert result.results[0].needs_escalation is True


# ============================================================================
# Apply Resolution Tests
# ============================================================================

class TestApplyResolution:
    """Tests for applying resolutions to working tree."""

    def test_writes_resolved_content(self, resolver, mock_repo):
        """Should write resolved content to file."""
        result = ResolutionResult(
            file_path="src/file.py",
            resolved_content="resolved content",
            strategy="3way",
            confidence=0.8,
        )

        # Create parent directory
        (mock_repo / "src").mkdir(exist_ok=True)

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)

            success = resolver.apply_resolution(result)

            assert success is True
            assert (mock_repo / "src/file.py").read_text() == "resolved content"

    def test_stages_resolved_file(self, resolver, mock_repo):
        """Should git add the resolved file."""
        result = ResolutionResult(
            file_path="file.py",
            resolved_content="resolved",
            strategy="ours",
            confidence=1.0,
        )

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)

            resolver.apply_resolution(result)

            # Check that git add was called
            calls = [str(c) for c in mock_run.call_args_list]
            assert any("add" in c for c in calls)

    def test_does_not_apply_without_content(self, resolver):
        """Should not apply resolution without content."""
        result = ResolutionResult(
            file_path="file.py",
            needs_escalation=True,
        )

        success = resolver.apply_resolution(result)

        assert success is False


# ============================================================================
# Rollback and Abort Tests
# ============================================================================

class TestRollbackAndAbort:
    """Tests for rollback and abort functionality."""

    def test_rollback_restores_conflict_markers(self, resolver):
        """Rollback should restore file to conflicted state."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)

            success = resolver.rollback_file("file.py")

            assert success is True
            # Check git checkout --conflict=merge was called
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "checkout" in call_args
            assert "--conflict=merge" in call_args

    def test_abort_merge(self, resolver):
        """Should abort merge when in merge conflict."""
        with patch.object(resolver, 'is_rebase_conflict', return_value=False), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)

            success = resolver.abort()

            assert success is True
            call_args = mock_run.call_args[0][0]
            assert "merge" in call_args
            assert "--abort" in call_args

    def test_abort_rebase(self, mock_repo):
        """Should abort rebase when in rebase conflict."""
        (mock_repo / ".git" / "rebase-merge").mkdir()

        with patch.object(GitConflictResolver, '_validate_git_repo'):
            resolver = GitConflictResolver(repo_path=mock_repo)

            with patch('subprocess.run') as mock_run:
                # First call for has_conflicts, second for abort
                mock_run.return_value = Mock(returncode=0, stdout="file.py\n")

                success = resolver.abort()

                assert success is True
                # Find the abort call
                abort_calls = [c for c in mock_run.call_args_list
                              if "--abort" in str(c)]
                assert len(abort_calls) > 0


# ============================================================================
# Convenience Function Tests
# ============================================================================

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_check_conflicts_returns_tuple(self, mock_repo):
        """check_conflicts should return (has_conflicts, files) tuple."""
        with patch.object(GitConflictResolver, '_validate_git_repo'), \
             patch.object(GitConflictResolver, 'get_conflicted_files') as mock_files:
            mock_files.return_value = ["file1.py", "file2.py"]

            has_conflicts, files = check_conflicts(mock_repo)

            assert has_conflicts is True
            assert len(files) == 2

    def test_check_conflicts_handles_non_repo(self, tmp_path):
        """check_conflicts should handle non-git directories."""
        has_conflicts, files = check_conflicts(tmp_path)

        assert has_conflicts is False
        assert files == []

    def test_format_escalation_for_user(self):
        """format_escalation_for_user should format for terminal display."""
        result = ResolutionResult(
            file_path="src/file.py",
            needs_escalation=True,
            escalation_analysis="Conflict at lines 10-20",
            escalation_options=["[A] Keep OURS", "[B] Keep THEIRS"],
            escalation_recommendation="Choose OURS",
        )

        formatted = format_escalation_for_user(result)

        assert "MANUAL DECISION REQUIRED" in formatted
        assert "src/file.py" in formatted
        assert "Conflict at lines 10-20" in formatted
        assert "[A] Keep OURS" in formatted
        assert "Choose OURS" in formatted

    def test_format_escalation_empty_for_non_escalation(self):
        """format_escalation_for_user should return empty for non-escalation."""
        result = ResolutionResult(
            file_path="file.py",
            resolved_content="content",
            strategy="3way",
            confidence=0.8,
        )

        formatted = format_escalation_for_user(result)

        assert formatted == ""


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_validates_git_repo_on_init(self, tmp_path):
        """Should raise error if not a git repository."""
        with pytest.raises(ValueError, match="Not a git repository"):
            GitConflictResolver(repo_path=tmp_path)

    def test_handles_empty_file_content(self, resolver):
        """Should handle files with empty content."""
        with patch.object(resolver, 'get_conflict_info') as mock_info:
            mock_info.return_value = ConflictedFile(
                path="empty.py",
                base="",
                ours="",
                theirs="content",
            )

            result = resolver.resolve_file("empty.py", strategy="theirs")

            assert result.resolved_content == "content"

    def test_handles_binary_file_detection(self, resolver):
        """Should handle files that git can't show (binary, etc)."""
        with patch.object(resolver, '_git_show', return_value=None):
            conflict = resolver.get_conflict_info("binary.png")

            assert conflict.base is None
            assert conflict.ours is None
            assert conflict.theirs is None
