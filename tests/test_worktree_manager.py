"""Tests for WorktreeManager - CORE-025 Phase 4

TDD RED phase: These tests should fail until WorktreeManager is implemented.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestWorktreeManager:
    """Test WorktreeManager class"""

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a temporary git repository for testing"""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path, check=True, capture_output=True
        )

        # Create initial commit
        (repo_path / "README.md").write_text("# Test Repo")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path, check=True, capture_output=True
        )

        return repo_path

    @pytest.fixture
    def manager(self, git_repo):
        """Create WorktreeManager instance"""
        from src.worktree_manager import WorktreeManager
        return WorktreeManager(git_repo)

    def test_create_worktree_success(self, manager, git_repo):
        """Test creating a worktree successfully"""
        session_id = "abc12345"

        result = manager.create(session_id)

        # Worktree should exist with human-readable name containing session_id
        assert result.exists()
        assert result.is_dir()
        assert result.parent == git_repo / ".orchestrator" / "worktrees"
        # Name should end with session_id (format: YYYYMMDD-adjective-noun-sessionid)
        assert result.name.endswith(f"-{session_id}")

        # Branch should exist
        branch_result = subprocess.run(
            ["git", "branch", "--list", f"wf-{session_id}"],
            cwd=git_repo, capture_output=True, text=True
        )
        assert f"wf-{session_id}" in branch_result.stdout

    def test_create_worktree_copies_env_files(self, manager, git_repo):
        """Test that .env files are copied to worktree"""
        # Create .env files in repo root and add to gitignore
        (git_repo / ".gitignore").write_text(".env*\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=git_repo, check=True)
        subprocess.run(["git", "commit", "-m", "Add gitignore"], cwd=git_repo, check=True)

        # Now create .env files (ignored, so repo stays clean)
        (git_repo / ".env").write_text("SECRET=value")
        (git_repo / ".env.local").write_text("LOCAL_SECRET=value")
        (git_repo / ".envrc").write_text("# Should not be copied")

        session_id = "abc12345"
        worktree_path = manager.create(session_id)

        # .env and .env.local should be copied
        assert (worktree_path / ".env").exists()
        assert (worktree_path / ".env").read_text() == "SECRET=value"
        assert (worktree_path / ".env.local").exists()
        assert (worktree_path / ".env.local").read_text() == "LOCAL_SECRET=value"

        # .envrc should NOT be copied (not .env*)
        assert not (worktree_path / ".envrc").exists()

    def test_create_worktree_fails_on_dirty_repo(self, manager, git_repo):
        """Test that worktree creation fails with uncommitted changes"""
        from src.worktree_manager import DirtyWorkingDirectoryError

        # Create uncommitted changes
        (git_repo / "new_file.txt").write_text("uncommitted content")

        with pytest.raises(DirtyWorkingDirectoryError):
            manager.create("abc12345")

        # No worktree should be created
        worktree_path = git_repo / ".orchestrator" / "worktrees" / "abc12345"
        assert not worktree_path.exists()

    def test_list_worktrees_empty(self, manager):
        """Test listing worktrees when none exist"""
        result = manager.list()
        assert result == []

    def test_list_worktrees_with_entries(self, git_repo):
        """Test listing worktrees after creating some"""
        from src.worktree_manager import WorktreeManager

        # Add .orchestrator to gitignore so worktrees don't make repo dirty
        (git_repo / ".gitignore").write_text(".orchestrator/\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=git_repo, check=True)
        subprocess.run(["git", "commit", "-m", "Add gitignore"], cwd=git_repo, check=True)

        # Create first worktree
        manager1 = WorktreeManager(git_repo)
        manager1.create("session1")

        # Create second worktree
        manager2 = WorktreeManager(git_repo)
        manager2.create("session2")

        result = manager2.list()

        assert len(result) == 2
        session_ids = [w.session_id for w in result]
        assert "session1" in session_ids
        assert "session2" in session_ids

    def test_cleanup_worktree_success(self, manager, git_repo):
        """Test cleaning up a worktree"""
        session_id = "abc12345"
        worktree_path = manager.create(session_id)

        assert worktree_path.exists()

        result = manager.cleanup(session_id)

        assert result is True
        assert not worktree_path.exists()

    def test_cleanup_worktree_not_found(self, manager):
        """Test cleanup returns False for non-existent worktree"""
        result = manager.cleanup("nonexistent")
        assert result is False

    def test_get_worktree_path(self, manager, git_repo):
        """Test getting worktree path for a session"""
        session_id = "abc12345"
        created_path = manager.create(session_id)

        result = manager.get_worktree_path(session_id)
        assert result == created_path

    def test_get_worktree_path_not_found(self, manager):
        """Test get_worktree_path returns None for non-existent session"""
        result = manager.get_worktree_path("nonexistent")
        assert result is None

    def test_merge_and_cleanup_success(self, manager, git_repo):
        """Test merging worktree changes back to original branch"""
        # Get the current branch name (could be 'main' or 'master')
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=git_repo, capture_output=True, text=True
        )
        original_branch = result.stdout.strip()

        session_id = "abc12345"
        worktree_path = manager.create(session_id)

        # Make changes in worktree
        new_file = worktree_path / "new_feature.py"
        new_file.write_text("# New feature code")
        subprocess.run(["git", "add", "."], cwd=worktree_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add new feature"],
            cwd=worktree_path, check=True
        )

        # Merge back to original branch
        result = manager.merge_and_cleanup(session_id, original_branch)

        assert result.success is True
        assert not worktree_path.exists()

        # Changes should be in original branch
        assert (git_repo / "new_feature.py").exists()

    def test_merge_and_cleanup_with_conflict(self, git_repo):
        """Test merge conflict handling"""
        from src.worktree_manager import WorktreeManager, MergeConflictError

        # Get the current branch name
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=git_repo, capture_output=True, text=True
        )
        original_branch = result.stdout.strip()

        manager = WorktreeManager(git_repo)
        session_id = "abc12345"
        worktree_path = manager.create(session_id)

        # Make changes in worktree first (so it's not dirty when we go back to main)
        (worktree_path / "README.md").write_text("# Worktree changes")
        subprocess.run(["git", "add", "."], cwd=worktree_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Worktree change"],
            cwd=worktree_path, check=True, capture_output=True
        )

        # Now make conflicting changes in main repo (checkout main first)
        subprocess.run(["git", "checkout", original_branch], cwd=git_repo, check=True, capture_output=True)
        (git_repo / "README.md").write_text("# Main changes")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Main branch change"],
            cwd=git_repo, check=True, capture_output=True
        )

        # Merge should raise conflict error
        with pytest.raises(MergeConflictError):
            manager.merge_and_cleanup(session_id, original_branch)

        # Worktree should still exist for manual resolution
        assert worktree_path.exists()

    def test_is_in_worktree(self, manager, git_repo):
        """Test detecting if we're in a worktree"""
        # From main repo, should be False
        assert manager.is_in_worktree() is False

        # Create worktree and check from there
        session_id = "abc12345"
        worktree_path = manager.create(session_id)

        # Create manager for worktree
        from src.worktree_manager import WorktreeManager
        worktree_manager = WorktreeManager(worktree_path)
        assert worktree_manager.is_in_worktree() is True

    def test_get_original_branch(self, manager, git_repo):
        """Test getting the original branch when in worktree"""
        # Should return None when not in worktree
        assert manager.get_original_branch() is None

        # Create worktree from main branch
        session_id = "abc12345"
        worktree_path = manager.create(session_id)

        # Manager for worktree should report original branch
        from src.worktree_manager import WorktreeManager
        worktree_manager = WorktreeManager(worktree_path)
        # Note: This requires storing original branch in metadata

    def test_branch_name_collision(self, manager, git_repo):
        """Test handling when branch name already exists"""
        session_id = "abc12345"

        # Create branch manually first
        subprocess.run(
            ["git", "branch", f"wf-{session_id}"],
            cwd=git_repo, check=True
        )

        # Should still create worktree (use unique suffix or error)
        from src.worktree_manager import BranchExistsError

        with pytest.raises(BranchExistsError):
            manager.create(session_id)


class TestWorktreeInfo:
    """Test WorktreeInfo dataclass"""

    def test_worktree_info_creation(self):
        """Test creating WorktreeInfo"""
        from src.worktree_manager import WorktreeInfo

        info = WorktreeInfo(
            session_id="abc12345",
            path=Path("/tmp/worktree"),
            branch="wf-abc12345"
        )

        assert info.session_id == "abc12345"
        assert info.path == Path("/tmp/worktree")
        assert info.branch == "wf-abc12345"


class TestMergeResult:
    """Test MergeResult dataclass"""

    def test_merge_result_success(self):
        """Test MergeResult for successful merge"""
        from src.worktree_manager import MergeResult

        result = MergeResult(
            success=True,
            merged_commits=3,
            message="Merged 3 commits from wf-abc12345"
        )

        assert result.success is True
        assert result.merged_commits == 3


class TestHumanReadableNaming:
    """Test human-readable worktree naming"""

    def test_generate_worktree_name_format(self):
        """Test that generated names have correct format"""
        from src.worktree_manager import generate_worktree_name
        from datetime import datetime

        session_id = "abc12345"
        name = generate_worktree_name(session_id)

        # Format should be YYYYMMDD-adjective-noun-sessionid
        parts = name.split("-")
        assert len(parts) == 4

        # First part should be today's date
        today = datetime.now().strftime("%Y%m%d")
        assert parts[0] == today

        # Last part should be session_id
        assert parts[3] == session_id

    def test_parse_worktree_name_new_format(self):
        """Test parsing new format worktree names"""
        from src.worktree_manager import WorktreeManager
        from datetime import datetime

        manager = WorktreeManager(Path("/tmp"))

        # Test new format
        session_id, created_at = manager._parse_worktree_name("20260113-brave-falcon-abc12345")
        assert session_id == "abc12345"
        assert created_at == datetime(2026, 1, 13)

    def test_parse_worktree_name_legacy_format(self):
        """Test parsing legacy format worktree names"""
        from src.worktree_manager import WorktreeManager

        manager = WorktreeManager(Path("/tmp"))

        # Test legacy format (just session_id)
        session_id, created_at = manager._parse_worktree_name("abc12345")
        assert session_id == "abc12345"
        assert created_at is None

    def test_worktree_info_has_name_and_date(self, tmp_path):
        """Test that list() returns WorktreeInfo with name and created_at"""
        from src.worktree_manager import WorktreeManager
        import subprocess

        # Create a git repo
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        (tmp_path / ".gitignore").write_text(".orchestrator/\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True, capture_output=True)

        manager = WorktreeManager(tmp_path)
        manager.create("testsession")

        worktrees = manager.list()
        assert len(worktrees) == 1

        wt = worktrees[0]
        assert wt.session_id == "testsession"
        assert wt.name != ""  # Should have human-readable name
        assert wt.name.endswith("-testsession")
        assert wt.created_at is not None  # Should have creation date
