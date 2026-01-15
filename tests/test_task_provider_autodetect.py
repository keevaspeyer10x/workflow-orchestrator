
import pytest
from unittest.mock import patch, MagicMock
from src.task_provider import get_task_provider
from src.task_provider.backends.local import LocalTaskProvider
from src.task_provider.backends.github import GitHubTaskProvider
from src.cli import cmd_task_list, cmd_task_add

class TestTaskProviderAutoDetect:
    """Test suite for Issue #64: Auto-detection of task provider."""

    @patch('src.task_provider.backends.github.GitHubTaskProvider.is_available')
    def test_get_provider_defaults_to_github_when_available(self, mock_available):
        """Should return GitHub provider when available."""
        mock_available.return_value = True
        
        provider = get_task_provider(None)
        
        assert isinstance(provider, GitHubTaskProvider)
        mock_available.assert_called_once()

    @patch('src.task_provider.backends.github.GitHubTaskProvider.is_available')
    def test_get_provider_falls_back_to_local_when_github_unavailable(self, mock_available):
        """Should fall back to Local provider when GitHub is unavailable."""
        mock_available.return_value = False
        
        provider = get_task_provider(None)
        
        assert isinstance(provider, LocalTaskProvider)

    def test_get_provider_respects_explicit_local(self):
        """Should return Local provider when explicitly requested."""
        provider = get_task_provider('local')
        assert isinstance(provider, LocalTaskProvider)

    @patch('src.task_provider.backends.github.GitHubTaskProvider.is_available')
    def test_get_provider_respects_explicit_github(self, mock_available):
        """Should return GitHub provider when explicitly requested, even if unavailable check isn't run by factory."""
        # Note: The factory doesn't check is_available() if explicitly requested
        provider = get_task_provider('github')
        assert isinstance(provider, GitHubTaskProvider)

    @patch('src.cli.get_task_provider')
    def test_cli_task_list_uses_auto_detect(self, mock_get_provider):
        """CLI task list command should call get_task_provider with None by default."""
        args = MagicMock()
        args.provider = None
        args.status = None
        args.priority = None
        
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        
        cmd_task_list(args)
        
        # Verify it called get_task_provider(None) -> auto-detect
        mock_get_provider.assert_called_with(None)
        mock_provider.list_tasks.assert_called()

    @patch('src.cli.get_task_provider')
    def test_cli_task_add_uses_auto_detect(self, mock_get_provider):
        """CLI task add command should call get_task_provider with None by default."""
        args = MagicMock()
        args.provider = None
        args.title = "Test Task"
        args.description = "Description"
        args.priority = "P2"
        args.labels = ""
        
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        
        cmd_task_add(args)
        
        # Verify it called get_task_provider(None) -> auto-detect
        mock_get_provider.assert_called_with(None)
        mock_provider.create_task.assert_called()

    @patch('src.cli.get_task_provider')
    def test_cli_task_list_respects_flag(self, mock_get_provider):
        """CLI task list command should pass explicit provider flag."""
        args = MagicMock()
        args.provider = 'local'
        args.status = None
        args.priority = None
        
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        
        cmd_task_list(args)
        
        mock_get_provider.assert_called_with('local')
