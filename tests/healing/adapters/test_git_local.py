"""Tests for local git adapter."""

import pytest
import tempfile
import subprocess
from pathlib import Path


class TestLocalGitAdapter:
    """Test LocalGitAdapter functionality."""

    @pytest.fixture
    def git_repo(self):
        """Create a temporary git repository for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            # Initialize git repo
            subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_path,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                capture_output=True,
            )
            # Create initial commit
            (repo_path / "README.md").write_text("# Test")
            subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=repo_path,
                capture_output=True,
            )
            yield repo_path

    @pytest.fixture
    def adapter(self, git_repo):
        """Create a LocalGitAdapter instance."""
        from src.healing.adapters.git_local import LocalGitAdapter

        return LocalGitAdapter(repo_path=git_repo)

    @pytest.mark.asyncio
    async def test_create_branch_new(self, adapter, git_repo):
        """GTL-001: create_branch() should create new branch from base."""
        await adapter.create_branch("feature-branch", base="HEAD")

        # Verify branch exists
        result = subprocess.run(
            ["git", "branch", "--list", "feature-branch"],
            cwd=git_repo,
            capture_output=True,
            text=True,
        )
        assert "feature-branch" in result.stdout

    @pytest.mark.asyncio
    async def test_create_branch_existing(self, adapter, git_repo):
        """GTL-002: create_branch() should raise error for existing branch."""
        from src.healing.adapters.git_local import GitBranchExistsError

        # Create branch first
        subprocess.run(
            ["git", "branch", "existing-branch"], cwd=git_repo, capture_output=True
        )

        with pytest.raises(GitBranchExistsError):
            await adapter.create_branch("existing-branch")

    @pytest.mark.asyncio
    async def test_apply_diff_valid(self, adapter, git_repo):
        """GTL-003: apply_diff() should create commit and return SHA."""
        # Make a change
        (git_repo / "test.txt").write_text("new content")

        sha = await adapter.apply_diff("", message="Test commit")

        assert sha is not None
        assert len(sha) == 40  # Git SHA is 40 hex chars

    @pytest.mark.asyncio
    async def test_merge_branch_clean(self, adapter, git_repo):
        """GTL-006: merge_branch() should succeed for clean merge."""
        # Create and switch to feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature"], cwd=git_repo, capture_output=True
        )
        (git_repo / "feature.txt").write_text("feature content")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Feature"], cwd=git_repo, capture_output=True
        )

        # Switch back to main
        subprocess.run(
            ["git", "checkout", "master"], cwd=git_repo, capture_output=True
        ) or subprocess.run(
            ["git", "checkout", "main"], cwd=git_repo, capture_output=True
        )

        await adapter.merge_branch("feature", into="HEAD")

        # Verify feature.txt exists after merge
        assert (git_repo / "feature.txt").exists()

    @pytest.mark.asyncio
    async def test_delete_branch_existing(self, adapter, git_repo):
        """GTL-008: delete_branch() should delete existing branch."""
        # Create branch
        subprocess.run(
            ["git", "branch", "to-delete"], cwd=git_repo, capture_output=True
        )

        await adapter.delete_branch("to-delete")

        # Verify branch is gone
        result = subprocess.run(
            ["git", "branch", "--list", "to-delete"],
            cwd=git_repo,
            capture_output=True,
            text=True,
        )
        assert "to-delete" not in result.stdout

    @pytest.mark.asyncio
    async def test_get_recent_commits(self, adapter, git_repo):
        """GTL-009: get_recent_commits() should return commit list."""
        result = await adapter.get_recent_commits(count=5)

        assert isinstance(result, list)
        assert len(result) >= 1  # At least initial commit
        assert "sha" in result[0] or "commit" in result[0]
