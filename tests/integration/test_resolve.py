"""
Integration tests for Git Conflict Resolution - CORE-023

These tests create real git conflicts and verify the resolver works correctly.
"""

import os
import pytest
import subprocess
import tempfile
from pathlib import Path

from src.git_conflict_resolver import (
    GitConflictResolver,
    check_conflicts,
    ConflictType,
)


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run a git command."""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True
    )


@pytest.fixture
def git_repo(tmp_path):
    """Create a fresh git repository with an initial commit."""
    # Initialize repo
    run_git(["init"], tmp_path)
    run_git(["config", "user.email", "test@test.com"], tmp_path)
    run_git(["config", "user.name", "Test User"], tmp_path)

    # Create initial file
    (tmp_path / "file.txt").write_text("line 1\nline 2\nline 3\n")
    run_git(["add", "file.txt"], tmp_path)
    run_git(["commit", "-m", "Initial commit"], tmp_path)

    return tmp_path


@pytest.fixture
def conflicted_repo(git_repo):
    """Create a repository in merge conflict state."""
    # Create branch and make changes
    run_git(["checkout", "-b", "feature"], git_repo)
    (git_repo / "file.txt").write_text("line 1\nline 2 - feature change\nline 3\n")
    run_git(["commit", "-am", "Feature change"], git_repo)

    # Go back to main and make conflicting changes
    run_git(["checkout", "master"], git_repo)
    (git_repo / "file.txt").write_text("line 1\nline 2 - main change\nline 3\n")
    run_git(["commit", "-am", "Main change"], git_repo)

    # Try to merge - this will create a conflict
    result = run_git(["merge", "feature"], git_repo)
    assert result.returncode != 0, "Expected merge conflict"

    return git_repo


class TestRealConflictDetection:
    """Tests for detecting real git conflicts."""

    def test_detects_no_conflict_in_clean_repo(self, git_repo):
        """Should report no conflicts in a clean repository."""
        resolver = GitConflictResolver(repo_path=git_repo)

        assert resolver.has_conflicts() is False
        assert resolver.get_conflicted_files() == []
        assert resolver.get_conflict_type() == ConflictType.NONE

    def test_detects_merge_conflict(self, conflicted_repo):
        """Should detect merge conflict state."""
        resolver = GitConflictResolver(repo_path=conflicted_repo)

        assert resolver.has_conflicts() is True
        assert resolver.get_conflict_type() == ConflictType.MERGE
        assert "file.txt" in resolver.get_conflicted_files()

    def test_gets_base_ours_theirs(self, conflicted_repo):
        """Should get base, ours, and theirs content from git index."""
        resolver = GitConflictResolver(repo_path=conflicted_repo)

        conflict = resolver.get_conflict_info("file.txt")

        assert conflict.path == "file.txt"
        assert conflict.base is not None
        assert "line 2\n" in conflict.base  # Original line
        assert conflict.ours is not None
        assert "main change" in conflict.ours
        assert conflict.theirs is not None
        assert "feature change" in conflict.theirs


class TestRealConflictResolution:
    """Tests for resolving real git conflicts."""

    def test_resolve_with_ours_strategy(self, conflicted_repo):
        """Should resolve conflict by keeping our changes."""
        resolver = GitConflictResolver(repo_path=conflicted_repo)

        result = resolver.resolve_file("file.txt", strategy="ours")

        assert result.success is True
        assert result.strategy == "ours"
        assert "main change" in result.resolved_content

    def test_resolve_with_theirs_strategy(self, conflicted_repo):
        """Should resolve conflict by keeping their changes."""
        resolver = GitConflictResolver(repo_path=conflicted_repo)

        result = resolver.resolve_file("file.txt", strategy="theirs")

        assert result.success is True
        assert result.strategy == "theirs"
        assert "feature change" in result.resolved_content

    def test_apply_resolution(self, conflicted_repo):
        """Should apply resolution to working tree."""
        resolver = GitConflictResolver(repo_path=conflicted_repo)

        result = resolver.resolve_file("file.txt", strategy="ours")
        assert result.success is True

        applied = resolver.apply_resolution(result)
        assert applied is True

        # Check file is resolved
        content = (conflicted_repo / "file.txt").read_text()
        assert "main change" in content
        assert "<<<<<<" not in content

    def test_abort_merge(self, conflicted_repo):
        """Should abort the merge and restore clean state."""
        resolver = GitConflictResolver(repo_path=conflicted_repo)
        assert resolver.has_conflicts() is True

        success = resolver.abort()
        assert success is True

        # Should be clean now
        assert resolver.has_conflicts() is False


class TestRebaseConflict:
    """Tests for rebase conflicts."""

    @pytest.fixture
    def rebase_conflict_repo(self, git_repo):
        """Create a repository in rebase conflict state."""
        # Create branch with changes
        run_git(["checkout", "-b", "feature"], git_repo)
        (git_repo / "file.txt").write_text("line 1\nline 2 - feature\nline 3\n")
        run_git(["commit", "-am", "Feature change"], git_repo)

        # Make changes on master
        run_git(["checkout", "master"], git_repo)
        (git_repo / "file.txt").write_text("line 1\nline 2 - master\nline 3\n")
        run_git(["commit", "-am", "Master change"], git_repo)

        # Go back to feature and rebase
        run_git(["checkout", "feature"], git_repo)
        result = run_git(["rebase", "master"], git_repo)

        # Should have conflict
        assert result.returncode != 0

        return git_repo

    def test_detects_rebase_conflict(self, rebase_conflict_repo):
        """Should detect rebase conflict state."""
        resolver = GitConflictResolver(repo_path=rebase_conflict_repo)

        assert resolver.has_conflicts() is True
        assert resolver.get_conflict_type() == ConflictType.REBASE
        assert resolver.is_rebase_conflict() is True

    def test_abort_rebase(self, rebase_conflict_repo):
        """Should abort the rebase."""
        resolver = GitConflictResolver(repo_path=rebase_conflict_repo)
        assert resolver.is_rebase_conflict() is True

        success = resolver.abort()
        assert success is True

        # Should be clean now
        assert resolver.has_conflicts() is False


class TestResolveAll:
    """Tests for resolving all conflicts at once."""

    @pytest.fixture
    def multi_file_conflict(self, git_repo):
        """Create conflicts in multiple files."""
        # Create initial files
        (git_repo / "file1.txt").write_text("file 1 content\n")
        (git_repo / "file2.txt").write_text("file 2 content\n")
        run_git(["add", "."], git_repo)
        run_git(["commit", "-m", "Add files"], git_repo)

        # Create branch and modify
        run_git(["checkout", "-b", "feature"], git_repo)
        (git_repo / "file1.txt").write_text("file 1 - feature\n")
        (git_repo / "file2.txt").write_text("file 2 - feature\n")
        run_git(["commit", "-am", "Feature changes"], git_repo)

        # Modify on master
        run_git(["checkout", "master"], git_repo)
        (git_repo / "file1.txt").write_text("file 1 - master\n")
        (git_repo / "file2.txt").write_text("file 2 - master\n")
        run_git(["commit", "-am", "Master changes"], git_repo)

        # Merge
        run_git(["merge", "feature"], git_repo)

        return git_repo

    def test_resolve_all_with_strategy(self, multi_file_conflict):
        """Should resolve all conflicts with the given strategy."""
        resolver = GitConflictResolver(repo_path=multi_file_conflict)

        files = resolver.get_conflicted_files()
        assert len(files) == 2

        results = resolver.resolve_all(strategy="ours")

        assert results.total_files == 2
        assert results.resolved_count == 2
        assert results.escalated_count == 0


class TestCheckConflictsConvenience:
    """Tests for the check_conflicts convenience function."""

    def test_check_conflicts_in_clean_repo(self, git_repo):
        """Should return False for clean repo."""
        has_conflicts, files = check_conflicts(git_repo)

        assert has_conflicts is False
        assert files == []

    def test_check_conflicts_with_conflicts(self, conflicted_repo):
        """Should return True with file list for conflicted repo."""
        has_conflicts, files = check_conflicts(conflicted_repo)

        assert has_conflicts is True
        assert len(files) > 0
        assert "file.txt" in files

    def test_check_conflicts_in_non_git_dir(self, tmp_path):
        """Should return False for non-git directory."""
        has_conflicts, files = check_conflicts(tmp_path)

        assert has_conflicts is False
        assert files == []


class TestValidation:
    """Tests for resolution validation."""

    @pytest.fixture
    def python_conflict_repo(self, git_repo):
        """Create a conflict in a Python file."""
        # Create initial Python file
        (git_repo / "app.py").write_text("def hello():\n    return 'hello'\n")
        run_git(["add", "app.py"], git_repo)
        run_git(["commit", "-m", "Add app.py"], git_repo)

        # Create branch and modify
        run_git(["checkout", "-b", "feature"], git_repo)
        (git_repo / "app.py").write_text("def hello():\n    return 'hello from feature'\n")
        run_git(["commit", "-am", "Feature: modify hello"], git_repo)

        # Modify on master
        run_git(["checkout", "master"], git_repo)
        (git_repo / "app.py").write_text("def hello():\n    return 'hello from master'\n")
        run_git(["commit", "-am", "Master: modify hello"], git_repo)

        # Merge
        run_git(["merge", "feature"], git_repo)

        return git_repo

    def test_validates_python_syntax_on_resolution(self, python_conflict_repo):
        """Should validate Python syntax after resolution."""
        resolver = GitConflictResolver(repo_path=python_conflict_repo)

        result = resolver.resolve_file("app.py", strategy="ours")

        # Ours is valid Python
        assert result.is_valid is True
        assert result.validation_error == ""

    def test_detects_conflict_markers_in_resolution(self, conflicted_repo):
        """Should detect if resolution still has conflict markers."""
        resolver = GitConflictResolver(repo_path=conflicted_repo)

        # Read the current (conflicted) content
        content = (conflicted_repo / "file.txt").read_text()
        assert "<<<<<<" in content

        # Validation should catch this
        valid, error = resolver._validate_resolution("file.txt", content)
        assert valid is False
        assert "conflict markers" in error.lower()
