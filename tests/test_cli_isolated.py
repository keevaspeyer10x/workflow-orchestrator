"""Integration tests for CLI worktree isolation - CORE-025 Phase 4"""

import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from src.cli import cmd_start, cmd_finish, cmd_doctor

class TestCliIsolated:
    """Integration tests for CLI worktree commands"""

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
    def mock_args(self, git_repo):
        """Mock CLI arguments"""
        args = MagicMock()
        args.dir = str(git_repo)
        args.task = "Test Task"
        args.isolated = True
        args.workflow = None
        args.project = None
        args.constraints = []
        args.no_archive = False
        args.test_command = None
        args.build_command = None
        return args

    def test_start_isolated_creates_worktree(self, git_repo, mock_args, capsys):
        """Test orchestrator start --isolated"""
        # Ensure .orchestrator is ignored so repo isn't dirty
        (git_repo / ".gitignore").write_text(".orchestrator/\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=git_repo, check=True)
        subprocess.run(["git", "commit", "-m", "Ignore orchestrator"], cwd=git_repo, check=True)

        # Run start command
        cmd_start(mock_args)

        # Check output
        captured = capsys.readouterr()
        assert "Created isolated worktree" in captured.out
        assert "wf-" in captured.out

        # Verify worktree creation
        worktrees_dir = git_repo / ".orchestrator" / "worktrees"
        assert worktrees_dir.exists()
        
        # Should be one worktree
        worktrees = list(worktrees_dir.iterdir())
        assert len(worktrees) == 1
        worktree_path = worktrees[0]
        
        assert worktree_path.is_dir()
        assert (worktree_path / ".git").is_file()  # Worktrees have a .git file, not dir

        # Verify session metadata
        from src.path_resolver import OrchestratorPaths
        from src.session_manager import SessionManager
        
        paths = OrchestratorPaths(base_dir=git_repo)
        session_mgr = SessionManager(paths)
        session_id = session_mgr.get_current_session()
        
        assert session_id is not None
        info = session_mgr.get_session_info(session_id)
        
        assert info['isolated'] is True
        assert info['worktree_path'] == str(worktree_path)
        assert info['original_branch'] is not None

    def test_start_isolated_fails_on_dirty_repo(self, git_repo, mock_args, capsys):
        """Test start --isolated fails with dirty working directory"""
        # Make repo dirty
        (git_repo / "new_file.txt").write_text("uncommitted")

        # Run start command - should exit
        with pytest.raises(SystemExit):
            cmd_start(mock_args)

        captured = capsys.readouterr()
        assert "Commit or stash your changes" in captured.out

        # No worktree should be created
        worktrees_dir = git_repo / ".orchestrator" / "worktrees"
        assert not worktrees_dir.exists()

    def test_finish_isolated_merges_changes(self, git_repo, mock_args, capsys):
        """Test orchestrator finish merges worktree changes"""
        # Ensure .orchestrator is ignored
        (git_repo / ".gitignore").write_text(".orchestrator/\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=git_repo, check=True)
        subprocess.run(["git", "commit", "-m", "Ignore orchestrator"], cwd=git_repo, check=True)

        # 1. Start isolated session
        cmd_start(mock_args)
        
        # Get session info
        from src.path_resolver import OrchestratorPaths
        from src.session_manager import SessionManager
        paths = OrchestratorPaths(base_dir=git_repo)
        session_mgr = SessionManager(paths)
        session_id = session_mgr.get_current_session()
        info = session_mgr.get_session_info(session_id)
        worktree_path = Path(info['worktree_path'])
        
        # 2. Make changes in worktree
        (worktree_path / "feature.txt").write_text("Feature content")
        subprocess.run(["git", "add", "."], cwd=worktree_path, check=True)
        subprocess.run(["git", "commit", "-m", "Add feature"], cwd=worktree_path, check=True)
        
        # 3. Finish session
        args = MagicMock()
        args.dir = str(git_repo)
        args.notes = "Completed feature"
        
        # Mock engine to avoid full workflow execution
        with patch('src.cli.get_engine') as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.state.completed_at = "timestamp"
            mock_get_engine.return_value = mock_engine
            
            cmd_finish(args)

        # 4. Verify merge
        captured = capsys.readouterr()
        assert "Merged 1 commits" in captured.out
        
        # Check file exists in original repo
        assert (git_repo / "feature.txt").exists()
        assert (git_repo / "feature.txt").read_text() == "Feature content"
        
        # Check worktree removed
        assert not worktree_path.exists()

    def test_doctor_command(self, git_repo, mock_args, capsys):
        """Test orchestrator doctor"""
        # Ensure .orchestrator is ignored
        (git_repo / ".gitignore").write_text(".orchestrator/\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=git_repo, check=True)
        subprocess.run(["git", "commit", "-m", "Ignore orchestrator"], cwd=git_repo, check=True)

        # Start session
        cmd_start(mock_args)
        
        # Run doctor
        args = MagicMock()
        args.dir = str(git_repo)
        args.cleanup = False
        args.fix = False
        
        cmd_doctor(args)
        
        captured = capsys.readouterr()
        assert "WORKTREE STATUS" in captured.out
        assert "active" in captured.out

    def test_doctor_cleanup_orphans(self, git_repo, capsys):
        """Test doctor --cleanup"""
        # Create orphaned worktree
        from src.worktree_manager import WorktreeManager
        wt_manager = WorktreeManager(git_repo)
        
        # Make dummy session ID
        session_id = "orphan12"
        wt_manager.create(session_id)
        
        # Run doctor cleanup
        args = MagicMock()
        args.dir = str(git_repo)
        args.cleanup = True
        args.fix = False
        
        cmd_doctor(args)
        
        captured = capsys.readouterr()
        assert f"Removed orphaned worktree: {session_id}" in captured.out
        
        # Verify gone
        path = wt_manager.get_worktree_path(session_id)
        assert path is None
