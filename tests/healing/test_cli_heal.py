"""Tests for CLI heal commands - Phase 4."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import os


class TestHealStatus:
    """Tests for heal_status command."""

    def test_heal_status_basic(self):
        """heal_status returns 0 and shows environment."""
        with patch.dict(os.environ, {"HEALING_ENABLED": "true"}):
            from src.healing.cli_heal import heal_status

            # Mock the async helper
            with patch('src.healing.cli_heal._get_healing_client', return_value=AsyncMock(return_value=None)):
                result = heal_status()
                assert result == 0

    def test_heal_status_kill_switch(self):
        """heal_status shows kill switch warning when active."""
        with patch.dict(os.environ, {"HEALING_KILL_SWITCH": "true"}):
            from src.healing.cli_heal import heal_status
            from src.healing.config import reset_config

            reset_config()

            with patch('src.healing.cli_heal._get_healing_client', return_value=AsyncMock(return_value=None)):
                result = heal_status()
                assert result == 0


class TestHealApply:
    """Tests for heal_apply command."""

    def test_heal_apply_dry_run(self):
        """heal_apply --dry-run shows preview without applying."""
        from src.healing.cli_heal import heal_apply
        import asyncio

        mock_client = MagicMock()

        with patch('src.healing.cli_heal._get_healing_client') as mock_get_client:
            # Make async mock return a valid client
            mock_get_client.return_value = mock_client

            with patch('src.healing.cli_heal.asyncio.run') as mock_run:
                mock_run.return_value = mock_client

                result = heal_apply("fix-123", dry_run=True)
                # Dry run should succeed (return 0)
                assert result == 0

    def test_heal_apply_no_supabase(self):
        """heal_apply fails gracefully without Supabase."""
        from src.healing.cli_heal import heal_apply

        with patch('src.healing.cli_heal._get_healing_client') as mock_client:
            mock_client.return_value = None

            result = heal_apply("fix-123")
            assert result == 1


class TestHealIgnore:
    """Tests for heal_ignore command."""

    def test_heal_ignore_missing_reason(self):
        """heal_ignore fails without reason."""
        from src.healing.cli_heal import heal_ignore

        result = heal_ignore("fp123", "")
        assert result == 1

    def test_heal_ignore_no_supabase(self):
        """heal_ignore fails gracefully without Supabase."""
        from src.healing.cli_heal import heal_ignore

        with patch('src.healing.cli_heal._get_healing_client') as mock_client:
            mock_client.return_value = None

            result = heal_ignore("fp123", "false positive")
            assert result == 1


class TestHealUnquarantine:
    """Tests for heal_unquarantine command."""

    def test_heal_unquarantine_missing_reason(self):
        """heal_unquarantine fails without reason."""
        from src.healing.cli_heal import heal_unquarantine

        result = heal_unquarantine("fp123", "")
        assert result == 1


class TestHealExplain:
    """Tests for heal_explain command."""

    def test_heal_explain_no_supabase(self):
        """heal_explain fails gracefully without Supabase."""
        from src.healing.cli_heal import heal_explain

        with patch('src.healing.cli_heal._get_healing_client') as mock_client:
            mock_client.return_value = None

            result = heal_explain("fp123")
            assert result == 1


class TestHealExport:
    """Tests for heal_export command."""

    def test_heal_export_no_supabase(self):
        """heal_export fails gracefully without Supabase."""
        from src.healing.cli_heal import heal_export

        with patch('src.healing.cli_heal._get_healing_client') as mock_client:
            mock_client.return_value = None

            result = heal_export(format="json")
            assert result == 1


class TestHealBackfill:
    """Tests for heal_backfill command."""

    def test_heal_backfill_no_supabase(self):
        """heal_backfill fails gracefully without Supabase."""
        from src.healing.cli_heal import heal_backfill

        with patch('src.healing.cli_heal._get_healing_client') as mock_client:
            mock_client.return_value = None

            result = heal_backfill()
            assert result == 1

    def test_heal_backfill_dry_run(self, tmp_path):
        """heal_backfill --dry-run counts logs without processing."""
        from src.healing.cli_heal import heal_backfill

        # Create a test log file
        log_file = tmp_path / ".workflow_log.jsonl"
        log_file.write_text('{"event_type": "error", "description": "Test error"}\n')

        with patch('src.healing.cli_heal._get_healing_client') as mock_client:
            mock_client.return_value = MagicMock()

            result = heal_backfill(log_dir=str(tmp_path), dry_run=True)
            assert result == 0
