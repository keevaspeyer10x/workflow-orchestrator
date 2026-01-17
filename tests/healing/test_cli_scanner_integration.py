"""Tests for CLI scanner integration."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCmdFinishIntegration:
    """Tests for scanner integration in cmd_finish."""

    @pytest.fixture
    def mock_scanner(self):
        """Create a mock PatternScanner."""
        scanner = MagicMock()
        scanner.scan_all = AsyncMock(
            return_value=MagicMock(
                sources_scanned=2,
                errors_extracted=5,
                patterns_created=3,
                patterns_updated=2,
            )
        )
        return scanner

    def test_scanner_called_on_finish(self, mock_scanner):
        """TC-FIN-001: Scanner called on successful finish."""
        from src.healing.cli_heal import _run_session_scan

        with patch("src.healing.scanner.PatternScanner") as MockScanner:
            MockScanner.return_value = mock_scanner

            result = asyncio.run(
                _run_session_scan(
                    working_dir=Path("/tmp"),
                    healing_client=MagicMock(),
                )
            )

            assert result is not None
            mock_scanner.scan_all.assert_called_once()

    def test_scanner_error_does_not_block(self, mock_scanner):
        """TC-FIN-002: Scanner error doesn't block finish."""
        from src.healing.cli_heal import _run_session_scan

        mock_scanner.scan_all = AsyncMock(side_effect=Exception("Scanner failed"))

        with patch("src.healing.scanner.PatternScanner") as MockScanner:
            MockScanner.return_value = mock_scanner

            # Should not raise, should return None
            result = asyncio.run(
                _run_session_scan(
                    working_dir=Path("/tmp"),
                    healing_client=MagicMock(),
                )
            )

            assert result is None

    def test_scanner_skipped_when_no_client(self):
        """TC-FIN-003: Scanner skipped when healing disabled."""
        from src.healing.cli_heal import _run_session_scan

        # With no healing client, should skip
        result = asyncio.run(
            _run_session_scan(
                working_dir=Path("/tmp"),
                healing_client=None,
            )
        )

        assert result is None


class TestCmdStartIntegration:
    """Tests for crash recovery in cmd_start."""

    @pytest.fixture
    def mock_scanner_with_orphan(self):
        """Create a mock scanner that has orphaned sessions."""
        scanner = MagicMock()
        scanner.has_orphaned_session = MagicMock(return_value=True)
        scanner.recover_orphaned = AsyncMock(
            return_value=MagicMock(
                errors_extracted=3,
                patterns_created=2,
            )
        )
        return scanner

    @pytest.fixture
    def mock_scanner_no_orphan(self):
        """Create a mock scanner with no orphaned sessions."""
        scanner = MagicMock()
        scanner.has_orphaned_session = MagicMock(return_value=False)
        return scanner

    def test_crash_recovery_called(self, mock_scanner_with_orphan):
        """TC-START-001: Crash recovery checked on start."""
        from src.healing.cli_heal import _check_crash_recovery

        with patch("src.healing.scanner.PatternScanner") as MockScanner:
            MockScanner.return_value = mock_scanner_with_orphan

            result = asyncio.run(
                _check_crash_recovery(working_dir=Path("/tmp"))
            )

            mock_scanner_with_orphan.has_orphaned_session.assert_called_once()
            mock_scanner_with_orphan.recover_orphaned.assert_called_once()
            assert result is not None

    def test_no_action_without_orphans(self, mock_scanner_no_orphan):
        """TC-START-002: No action when no orphaned sessions."""
        from src.healing.cli_heal import _check_crash_recovery

        # Add a mock recover_orphaned to verify it's not called
        mock_scanner_no_orphan.recover_orphaned = AsyncMock()

        with patch("src.healing.scanner.PatternScanner") as MockScanner:
            MockScanner.return_value = mock_scanner_no_orphan

            result = asyncio.run(
                _check_crash_recovery(working_dir=Path("/tmp"))
            )

            mock_scanner_no_orphan.has_orphaned_session.assert_called_once()
            # recover_orphaned should NOT be called
            mock_scanner_no_orphan.recover_orphaned.assert_not_called()
            assert result is None

    def test_recovery_error_does_not_block(self, mock_scanner_with_orphan):
        """TC-START-003: Recovery error doesn't block start."""
        from src.healing.cli_heal import _check_crash_recovery

        mock_scanner_with_orphan.recover_orphaned = AsyncMock(
            side_effect=Exception("Recovery failed")
        )

        with patch("src.healing.scanner.PatternScanner") as MockScanner:
            MockScanner.return_value = mock_scanner_with_orphan

            # Should not raise
            result = asyncio.run(
                _check_crash_recovery(working_dir=Path("/tmp"))
            )

            assert result is None


class TestHealBackfillEnhancement:
    """Tests for enhanced heal_backfill command."""

    @pytest.fixture
    def mock_scanner(self):
        """Create a mock scanner for backfill."""
        scanner = MagicMock()
        scanner.get_recommendations = MagicMock(
            return_value=[
                {
                    "source": "LEARNINGS.md",
                    "path": "/tmp/LEARNINGS.md",
                    "recommendation": "High value",
                    "exists": True,
                },
                {
                    "source": ".workflow_log.jsonl",
                    "path": "/tmp/.workflow_log.jsonl",
                    "recommendation": "High value",
                    "exists": True,
                },
            ]
        )
        scanner.scan_all = AsyncMock(
            return_value=MagicMock(
                sources_scanned=2,
                errors_extracted=5,
                patterns_created=3,
            )
        )
        return scanner

    def test_scan_only_shows_recommendations(self, mock_scanner):
        """TC-BF-001: --scan-only shows recommendations."""
        from src.healing.cli_heal import heal_backfill

        with patch("src.healing.scanner.PatternScanner") as MockScanner:
            MockScanner.return_value = mock_scanner
            with patch("src.healing.cli_heal._get_healing_client") as mock_client:
                mock_client.return_value = MagicMock()

                result = heal_backfill(scan_only=True)

                mock_scanner.get_recommendations.assert_called_once()
                # scan_all should NOT be called in scan_only mode
                mock_scanner.scan_all.assert_not_called()

    def test_days_parameter_passed(self, mock_scanner):
        """TC-BF-002: --days parameter passed to scanner."""
        from src.healing.cli_heal import heal_backfill

        with patch("src.healing.scanner.PatternScanner") as MockScanner:
            MockScanner.return_value = mock_scanner
            with patch("src.healing.cli_heal._get_healing_client") as mock_client:
                mock_client.return_value = MagicMock()

                heal_backfill(days=90)

                mock_scanner.scan_all.assert_called_once()
                call_kwargs = mock_scanner.scan_all.call_args
                assert call_kwargs[1].get("days") == 90 or call_kwargs[0][0] == 90

    def test_no_github_flag(self, mock_scanner):
        """TC-BF-003: --no-github skips GitHub."""
        from src.healing.cli_heal import heal_backfill

        with patch("src.healing.scanner.PatternScanner") as MockScanner:
            MockScanner.return_value = mock_scanner
            with patch("src.healing.cli_heal._get_healing_client") as mock_client:
                mock_client.return_value = MagicMock()

                heal_backfill(no_github=True)

                # Check that scanner was created with include_github=False
                call_kwargs = MockScanner.call_args[1]
                assert call_kwargs.get("include_github") is False

    def test_no_github_uses_scanner_not_backfill(self, mock_scanner):
        """TC-BF-005: --no-github uses scanner even with default days."""
        from src.healing.cli_heal import heal_backfill

        with patch("src.healing.scanner.PatternScanner") as MockScanner:
            MockScanner.return_value = mock_scanner
            with patch("src.healing.cli_heal._get_healing_client") as mock_client:
                mock_client.return_value = MagicMock()
                with patch("src.healing.backfill.HistoricalBackfill") as MockBackfill:
                    mock_backfill = MagicMock()
                    mock_backfill.backfill_workflow_logs = AsyncMock(return_value=5)
                    MockBackfill.return_value = mock_backfill

                    # Call with no_github but default days (30)
                    heal_backfill(no_github=True)

                    # Scanner should be used, not backfill
                    mock_scanner.scan_all.assert_called_once()
                    mock_backfill.backfill_workflow_logs.assert_not_called()

    def test_default_behavior_unchanged(self, mock_scanner):
        """TC-BF-004: Default behavior unchanged."""
        from src.healing.cli_heal import heal_backfill

        with patch("src.healing.scanner.PatternScanner") as MockScanner:
            MockScanner.return_value = mock_scanner
            with patch("src.healing.cli_heal._get_healing_client") as mock_client:
                mock_client.return_value = MagicMock()
                with patch("src.healing.backfill.HistoricalBackfill") as MockBackfill:
                    mock_backfill = MagicMock()
                    mock_backfill.backfill_workflow_logs = AsyncMock(return_value=5)
                    MockBackfill.return_value = mock_backfill

                    # Default call should still work
                    result = heal_backfill()

                    # Should still call backfill for backward compatibility
                    assert result == 0
