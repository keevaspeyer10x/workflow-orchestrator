"""
Tests for SyncManager - CORE-031

TDD approach: Write tests first, then implement.
"""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestSyncManager:
    """Tests for the SyncManager class."""

    @pytest.fixture
    def mock_git_repo(self, tmp_path):
        """Create a mock git repository with a remote."""
        repo = tmp_path / "repo"
        repo.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo, capture_output=True
        )

        # Create initial commit
        (repo / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo, capture_output=True
        )

        return repo

    @pytest.fixture
    def mock_git_repo_with_remote(self, mock_git_repo, tmp_path):
        """Create a git repo with a bare remote."""
        repo = mock_git_repo
        remote = tmp_path / "remote.git"

        # Create bare remote
        subprocess.run(["git", "init", "--bare", str(remote)], capture_output=True)

        # Add remote and push
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote)],
            cwd=repo, capture_output=True
        )
        subprocess.run(
            ["git", "push", "-u", "origin", "master"],
            cwd=repo, capture_output=True
        )

        return repo, remote

    def test_sync_manager_import(self):
        """Test that SyncManager can be imported."""
        from src.sync_manager import SyncManager
        assert SyncManager is not None

    def test_get_remote_tracking_branch_with_upstream(self, mock_git_repo_with_remote):
        """Test getting remote tracking branch when configured."""
        from src.sync_manager import SyncManager

        repo, _ = mock_git_repo_with_remote
        sync_mgr = SyncManager(repo)

        result = sync_mgr.get_remote_tracking_branch()
        assert result is not None
        assert "origin" in result

    def test_get_remote_tracking_branch_no_upstream(self, mock_git_repo):
        """Test getting remote tracking branch when not configured."""
        from src.sync_manager import SyncManager

        sync_mgr = SyncManager(mock_git_repo)

        result = sync_mgr.get_remote_tracking_branch()
        assert result is None

    def test_has_uncommitted_changes_clean(self, mock_git_repo):
        """Test has_uncommitted_changes returns False when working directory is clean."""
        from src.sync_manager import SyncManager

        sync_mgr = SyncManager(mock_git_repo)

        result = sync_mgr.has_uncommitted_changes()
        assert result is False

    def test_has_uncommitted_changes_staged(self, mock_git_repo):
        """Test has_uncommitted_changes returns True when there are staged changes."""
        from src.sync_manager import SyncManager

        # Create and stage a new file
        (mock_git_repo / "new_file.txt").write_text("New content")
        subprocess.run(["git", "add", "new_file.txt"], cwd=mock_git_repo, capture_output=True)

        sync_mgr = SyncManager(mock_git_repo)

        result = sync_mgr.has_uncommitted_changes()
        assert result is True

    def test_has_uncommitted_changes_unstaged(self, mock_git_repo):
        """Test has_uncommitted_changes returns True when there are unstaged changes."""
        from src.sync_manager import SyncManager

        # Modify an existing file without staging
        (mock_git_repo / "README.md").write_text("# Modified")

        sync_mgr = SyncManager(mock_git_repo)

        result = sync_mgr.has_uncommitted_changes()
        assert result is True

    def test_has_uncommitted_changes_untracked(self, mock_git_repo):
        """Test has_uncommitted_changes returns True when there are untracked files."""
        from src.sync_manager import SyncManager

        # Create an untracked file
        (mock_git_repo / "untracked.txt").write_text("Untracked")

        sync_mgr = SyncManager(mock_git_repo)

        result = sync_mgr.has_uncommitted_changes()
        assert result is True

    def test_commit_all_success(self, mock_git_repo):
        """Test commit_all stages and commits all changes."""
        from src.sync_manager import SyncManager

        # Create some uncommitted changes
        (mock_git_repo / "new_file.txt").write_text("New content")
        (mock_git_repo / "README.md").write_text("# Modified")

        sync_mgr = SyncManager(mock_git_repo)
        assert sync_mgr.has_uncommitted_changes() is True

        # Commit all
        result = sync_mgr.commit_all("Test commit message")
        assert result is True

        # Verify changes are committed
        assert sync_mgr.has_uncommitted_changes() is False

        # Verify commit message
        log_result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=mock_git_repo,
            capture_output=True,
            text=True
        )
        assert log_result.stdout.strip() == "Test commit message"

    def test_commit_all_nothing_to_commit(self, mock_git_repo):
        """Test commit_all returns False when nothing to commit."""
        from src.sync_manager import SyncManager

        sync_mgr = SyncManager(mock_git_repo)
        assert sync_mgr.has_uncommitted_changes() is False

        # Commit with no changes - git commit returns non-zero
        result = sync_mgr.commit_all("Empty commit")
        assert result is False

    def test_fetch_success(self, mock_git_repo_with_remote):
        """Test successful fetch from remote."""
        from src.sync_manager import SyncManager

        repo, _ = mock_git_repo_with_remote
        sync_mgr = SyncManager(repo)

        result = sync_mgr.fetch()
        assert result is True

    def test_fetch_no_remote(self, mock_git_repo):
        """Test fetch when no remote configured."""
        from src.sync_manager import SyncManager

        sync_mgr = SyncManager(mock_git_repo)

        # Should not raise, just return False
        result = sync_mgr.fetch()
        assert result is False

    def test_check_divergence_in_sync(self, mock_git_repo_with_remote):
        """Test divergence check when in sync."""
        from src.sync_manager import SyncManager

        repo, _ = mock_git_repo_with_remote
        sync_mgr = SyncManager(repo)
        sync_mgr.fetch()

        info = sync_mgr.check_divergence()
        assert info.diverged is False
        assert info.local_ahead == 0
        assert info.remote_ahead == 0

    def test_check_divergence_local_ahead(self, mock_git_repo_with_remote):
        """Test divergence check when local is ahead."""
        from src.sync_manager import SyncManager

        repo, _ = mock_git_repo_with_remote

        # Create local commits
        (repo / "new_file.txt").write_text("New content")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Local commit"],
            cwd=repo, capture_output=True
        )

        sync_mgr = SyncManager(repo)
        sync_mgr.fetch()

        info = sync_mgr.check_divergence()
        assert info.diverged is False
        assert info.local_ahead == 1
        assert info.remote_ahead == 0

    def test_check_divergence_remote_ahead(self, mock_git_repo_with_remote, tmp_path):
        """Test divergence check when remote is ahead."""
        from src.sync_manager import SyncManager

        repo, remote = mock_git_repo_with_remote

        # Create another clone and push from there
        other_clone = tmp_path / "other"
        subprocess.run(
            ["git", "clone", str(remote), str(other_clone)],
            capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "other@test.com"],
            cwd=other_clone, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Other"],
            cwd=other_clone, capture_output=True
        )
        (other_clone / "other_file.txt").write_text("Other content")
        subprocess.run(["git", "add", "."], cwd=other_clone, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Other commit"],
            cwd=other_clone, capture_output=True
        )
        subprocess.run(["git", "push"], cwd=other_clone, capture_output=True)

        # Now check divergence from original repo
        sync_mgr = SyncManager(repo)
        sync_mgr.fetch()

        info = sync_mgr.check_divergence()
        assert info.diverged is True
        assert info.local_ahead == 0
        assert info.remote_ahead == 1

    def test_check_divergence_both_diverged(self, mock_git_repo_with_remote, tmp_path):
        """Test divergence check when both have diverged."""
        from src.sync_manager import SyncManager

        repo, remote = mock_git_repo_with_remote

        # Create local commit
        (repo / "local_file.txt").write_text("Local content")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Local commit"],
            cwd=repo, capture_output=True
        )

        # Create another clone and push from there
        other_clone = tmp_path / "other"
        subprocess.run(
            ["git", "clone", str(remote), str(other_clone)],
            capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "other@test.com"],
            cwd=other_clone, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Other"],
            cwd=other_clone, capture_output=True
        )
        (other_clone / "other_file.txt").write_text("Other content")
        subprocess.run(["git", "add", "."], cwd=other_clone, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Other commit"],
            cwd=other_clone, capture_output=True
        )
        subprocess.run(["git", "push"], cwd=other_clone, capture_output=True)

        # Now check divergence from original repo
        sync_mgr = SyncManager(repo)
        sync_mgr.fetch()

        info = sync_mgr.check_divergence()
        assert info.diverged is True
        assert info.local_ahead == 1
        assert info.remote_ahead == 1

    def test_push_success(self, mock_git_repo_with_remote):
        """Test successful push."""
        from src.sync_manager import SyncManager

        repo, _ = mock_git_repo_with_remote

        # Create local commit
        (repo / "new_file.txt").write_text("New content")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Local commit"],
            cwd=repo, capture_output=True
        )

        sync_mgr = SyncManager(repo)
        result = sync_mgr.push()

        assert result.success is True
        assert result.pushed_commits >= 1

    def test_push_nothing_to_push(self, mock_git_repo_with_remote):
        """Test push when already in sync."""
        from src.sync_manager import SyncManager

        repo, _ = mock_git_repo_with_remote
        sync_mgr = SyncManager(repo)

        result = sync_mgr.push()

        assert result.success is True
        assert result.pushed_commits == 0

    def test_push_no_remote(self, mock_git_repo):
        """Test push when no remote configured."""
        from src.sync_manager import SyncManager

        sync_mgr = SyncManager(mock_git_repo)
        result = sync_mgr.push()

        assert result.success is False
        assert "no remote" in result.message.lower() or "no upstream" in result.message.lower()

    def test_push_rejected_non_fast_forward(self, mock_git_repo_with_remote, tmp_path):
        """Test push is rejected when remote has diverged (non-fast-forward)."""
        from src.sync_manager import SyncManager

        repo, remote = mock_git_repo_with_remote

        # Create local commit
        (repo / "local_file.txt").write_text("Local content")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Local commit"],
            cwd=repo, capture_output=True
        )

        # Create another clone and push from there (causing divergence)
        other_clone = tmp_path / "other"
        subprocess.run(
            ["git", "clone", str(remote), str(other_clone)],
            capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "other@test.com"],
            cwd=other_clone, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Other"],
            cwd=other_clone, capture_output=True
        )
        (other_clone / "other_file.txt").write_text("Other content")
        subprocess.run(["git", "add", "."], cwd=other_clone, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Other commit"],
            cwd=other_clone, capture_output=True
        )
        subprocess.run(["git", "push"], cwd=other_clone, capture_output=True)

        # Now try to push from original repo - should be rejected
        sync_mgr = SyncManager(repo)
        result = sync_mgr.push()

        assert result.success is False
        # Should NOT force push
        assert "rejected" in result.message.lower() or "non-fast-forward" in result.message.lower()

    def test_attempt_rebase_success(self, mock_git_repo_with_remote, tmp_path):
        """Test successful rebase when remote is ahead (no conflicts)."""
        from src.sync_manager import SyncManager

        repo, remote = mock_git_repo_with_remote

        # Create local commit on different file
        (repo / "local_file.txt").write_text("Local content")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Local commit"],
            cwd=repo, capture_output=True
        )

        # Create another clone and push different file
        other_clone = tmp_path / "other"
        subprocess.run(
            ["git", "clone", str(remote), str(other_clone)],
            capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "other@test.com"],
            cwd=other_clone, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Other"],
            cwd=other_clone, capture_output=True
        )
        (other_clone / "other_file.txt").write_text("Other content")
        subprocess.run(["git", "add", "."], cwd=other_clone, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Other commit"],
            cwd=other_clone, capture_output=True
        )
        subprocess.run(["git", "push"], cwd=other_clone, capture_output=True)

        # Now rebase from original repo
        sync_mgr = SyncManager(repo)
        sync_mgr.fetch()

        result = sync_mgr.attempt_rebase()
        assert result is True

    def test_attempt_rebase_conflicts(self, mock_git_repo_with_remote, tmp_path):
        """Test rebase fails when there are conflicts."""
        from src.sync_manager import SyncManager

        repo, remote = mock_git_repo_with_remote

        # Create local commit modifying README.md
        (repo / "README.md").write_text("# Local changes")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Local README change"],
            cwd=repo, capture_output=True
        )

        # Create another clone and push conflicting README.md change
        other_clone = tmp_path / "other"
        subprocess.run(
            ["git", "clone", str(remote), str(other_clone)],
            capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "other@test.com"],
            cwd=other_clone, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Other"],
            cwd=other_clone, capture_output=True
        )
        (other_clone / "README.md").write_text("# Remote changes")
        subprocess.run(["git", "add", "."], cwd=other_clone, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Remote README change"],
            cwd=other_clone, capture_output=True
        )
        subprocess.run(["git", "push"], cwd=other_clone, capture_output=True)

        # Now try to rebase from original repo - should fail with conflicts
        sync_mgr = SyncManager(repo)
        sync_mgr.fetch()

        result = sync_mgr.attempt_rebase()
        assert result is False

    def test_sync_full_flow_local_ahead(self, mock_git_repo_with_remote):
        """Test full sync flow when local is ahead."""
        from src.sync_manager import SyncManager

        repo, _ = mock_git_repo_with_remote

        # Create local commits
        (repo / "file1.txt").write_text("Content 1")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Commit 1"],
            cwd=repo, capture_output=True
        )

        (repo / "file2.txt").write_text("Content 2")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Commit 2"],
            cwd=repo, capture_output=True
        )

        sync_mgr = SyncManager(repo)
        result = sync_mgr.sync()

        assert result.success is True
        assert result.pushed_commits == 2

    def test_sync_already_in_sync(self, mock_git_repo_with_remote):
        """Test sync when already in sync."""
        from src.sync_manager import SyncManager

        repo, _ = mock_git_repo_with_remote
        sync_mgr = SyncManager(repo)

        result = sync_mgr.sync()

        assert result.success is True
        assert result.pushed_commits == 0

    def test_sync_no_remote(self, mock_git_repo):
        """Test sync gracefully handles no remote."""
        from src.sync_manager import SyncManager

        sync_mgr = SyncManager(mock_git_repo)
        result = sync_mgr.sync()

        # Should succeed (nothing to do) or fail gracefully
        assert result is not None


class TestDivergenceInfo:
    """Tests for DivergenceInfo dataclass."""

    def test_divergence_info_creation(self):
        """Test creating DivergenceInfo."""
        from src.sync_manager import DivergenceInfo

        info = DivergenceInfo(
            diverged=True,
            local_ahead=3,
            remote_ahead=2,
            remote_branch="origin/main"
        )

        assert info.diverged is True
        assert info.local_ahead == 3
        assert info.remote_ahead == 2
        assert info.remote_branch == "origin/main"


class TestSyncResult:
    """Tests for SyncResult dataclass."""

    def test_sync_result_success(self):
        """Test successful SyncResult."""
        from src.sync_manager import SyncResult

        result = SyncResult(
            success=True,
            pushed_commits=5,
            message="Pushed 5 commits"
        )

        assert result.success is True
        assert result.pushed_commits == 5
        assert "5" in result.message

    def test_sync_result_failure(self):
        """Test failed SyncResult."""
        from src.sync_manager import SyncResult

        result = SyncResult(
            success=False,
            pushed_commits=0,
            message="Push rejected",
            conflicts=["file1.py", "file2.py"]
        )

        assert result.success is False
        assert len(result.conflicts) == 2
