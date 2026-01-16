import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY
from src.cli import cmd_finish
from src.schema import ItemStatus
from src.sync_manager import SyncResult

class TestFinishCommitSyncUX:
    """Test suite for Issue #63: commit_and_sync UX improvements."""

    @pytest.fixture
    def mock_engine(self):
        engine = MagicMock()
        engine.state = MagicMock()
        # Mock phases structure
        learn_phase = MagicMock()
        learn_phase.items = {}
        engine.state.phases = {"LEARN": learn_phase}
        # Mock can_advance checks
        engine.can_advance_phase.return_value = (True, [], [])
        engine.validate_reviews_completed.return_value = (True, [])
        # Mock task_description to be a string (fix for regex error)
        engine.state.task_description = "Complete commit_and_sync"
        # Mock timestamps
        engine.state.created_at = None
        engine.state.completed_at = None
        # Mock summary to avoid attribute errors
        engine.get_workflow_summary.return_value = {}
        engine.get_all_skipped_items.return_value = {}
        engine.state.metadata = {}
        return engine

    @pytest.fixture
    def mock_args(self):
        args = MagicMock()
        args.dir = '.'
        args.notes = "Done"
        args.abandon = False
        args.no_push = False
        args.continue_sync = False
        args.skip_item_check = False
        args.skip_review_check = False
        args.skip_learn = True # Skip learning report generation
        args.no_close_issues = True
        return args

    @patch('src.cli.get_engine')
    @patch('src.cli.SyncManager')
    @patch('src.cli.SessionManager') 
    @patch('src.cli.OrchestratorPaths')
    def test_finish_updates_skipped_item_on_success(self, mock_paths, mock_session, mock_sync_cls, mock_get_engine, mock_engine, mock_args):
        """Should update commit_and_sync status to COMPLETED if auto-sync succeeds."""
        # Configure mock paths to avoid MagicMock directory creation
        mock_paths.return_value.orchestrator_dir = Path("mock_orch_dir")
        
        mock_get_engine.return_value = mock_engine
        
        # Setup sync success
        mock_sync_mgr = mock_sync_cls.return_value
        mock_sync_mgr.get_remote_tracking_branch.return_value = "origin/main"
        mock_sync_mgr.sync.return_value = SyncResult(success=True, pushed_commits=1, message="Pushed")
        
        # Setup commit_and_sync item as SKIPPED
        item = MagicMock()
        item.status = ItemStatus.SKIPPED
        mock_engine.state.phases["LEARN"].items["commit_and_sync"] = item
        
        cmd_finish(mock_args)
        
        # Verify status update
        assert item.status == ItemStatus.COMPLETED
        assert item.notes == "Auto-completed via CORE-031 sync"
        mock_engine.save_state.assert_called()

    @patch('src.cli.get_engine')
    @patch('src.cli.SyncManager')
    @patch('src.cli.SessionManager')
    @patch('src.cli.OrchestratorPaths')
    def test_finish_keeps_skipped_on_sync_failure(self, mock_paths, mock_session, mock_sync_cls, mock_get_engine, mock_engine, mock_args):
        """Should keep commit_and_sync as SKIPPED if auto-sync fails."""
        # Configure mock paths to avoid MagicMock directory creation
        mock_paths.return_value.orchestrator_dir = Path("mock_orch_dir")

        mock_get_engine.return_value = mock_engine
        
        # Setup sync failure
        mock_sync_mgr = mock_sync_cls.return_value
        mock_sync_mgr.get_remote_tracking_branch.return_value = "origin/main"
        mock_sync_mgr.sync.return_value = SyncResult(success=False, pushed_commits=0, message="Network error")
        
        # Setup commit_and_sync item as SKIPPED
        item = MagicMock()
        item.status = ItemStatus.SKIPPED
        mock_engine.state.phases["LEARN"].items["commit_and_sync"] = item
        
        cmd_finish(mock_args)
        
        # Verify status UNCHANGED
        assert item.status == ItemStatus.SKIPPED
        mock_engine.save_state.assert_not_called() # Save only happens if status changes in that block

    @patch('src.cli.get_engine')
    @patch('src.cli.SyncManager')
    @patch('src.cli.SessionManager')
    @patch('src.cli.OrchestratorPaths')
    def test_finish_keeps_skipped_on_no_push(self, mock_paths, mock_session, mock_sync_cls, mock_get_engine, mock_engine, mock_args):
        """Should keep commit_and_sync as SKIPPED if --no-push is used."""
        # Configure mock paths to avoid MagicMock directory creation
        mock_paths.return_value.orchestrator_dir = Path("mock_orch_dir")

        mock_get_engine.return_value = mock_engine
        mock_args.no_push = True
        
        # Setup commit_and_sync item as SKIPPED
        item = MagicMock()
        item.status = ItemStatus.SKIPPED
        mock_engine.state.phases["LEARN"].items["commit_and_sync"] = item
        
        cmd_finish(mock_args)
        
        # Verify sync not called
        mock_sync_cls.assert_not_called()
        
        # Verify status UNCHANGED
        assert item.status == ItemStatus.SKIPPED
        
    @patch('src.cli.get_engine')
    @patch('src.cli.SyncManager')
    @patch('src.cli.SessionManager')
    @patch('src.cli.OrchestratorPaths')
    def test_finish_ignores_already_completed(self, mock_paths, mock_session, mock_sync_cls, mock_get_engine, mock_engine, mock_args):
        """Should not modify status if already COMPLETED."""
        # Configure mock paths to avoid MagicMock directory creation
        mock_paths.return_value.orchestrator_dir = Path("mock_orch_dir")

        mock_get_engine.return_value = mock_engine
        
        # Setup sync success
        mock_sync_mgr = mock_sync_cls.return_value
        mock_sync_mgr.get_remote_tracking_branch.return_value = "origin/main"
        mock_sync_mgr.sync.return_value = SyncResult(success=True, pushed_commits=1, message="Pushed")
        
        # Setup commit_and_sync item as COMPLETED
        item = MagicMock()
        item.status = ItemStatus.COMPLETED
        item.notes = "Original notes"
        mock_engine.state.phases["LEARN"].items["commit_and_sync"] = item
        
        cmd_finish(mock_args)
        
        # Verify status UNCHANGED
        assert item.status == ItemStatus.COMPLETED
        assert item.notes == "Original notes" # Should not be overwritten