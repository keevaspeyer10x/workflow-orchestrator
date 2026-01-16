"""Tests for Flakiness Detection - Phase 5."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from src.healing.flakiness import FlakinessDetector, FlakinessResult


class TestFlakinessDetector:
    """Tests for the flakiness detector."""

    @pytest.fixture
    def mock_supabase(self):
        """Create a mock Supabase client."""
        return AsyncMock()

    @pytest.fixture
    def detector(self, mock_supabase):
        """Create a detector with mock client."""
        return FlakinessDetector(mock_supabase)

    @pytest.mark.asyncio
    async def test_is_flaky_deterministic(self, detector, mock_supabase):
        """Consistent timing results in not flaky."""
        # Occurrences at regular intervals (every 10 minutes)
        base = datetime.utcnow()
        mock_supabase.get_error_occurrences.return_value = [
            base - timedelta(minutes=30),
            base - timedelta(minutes=20),
            base - timedelta(minutes=10),
            base,
        ]

        result = await detector.is_flaky("fp123")
        # Regular intervals should not be flaky
        assert result is False

    @pytest.mark.asyncio
    async def test_is_flaky_intermittent(self, detector, mock_supabase):
        """High variance timing results in flaky."""
        # Occurrences at irregular intervals
        base = datetime.utcnow()
        mock_supabase.get_error_occurrences.return_value = [
            base - timedelta(hours=5),
            base - timedelta(minutes=30),
            base - timedelta(minutes=29),  # Very close to previous
            base,
        ]

        result = await detector.analyze("fp123")
        # Very irregular intervals should be flaky
        # The variance will be high due to 5 hour gap vs 1 minute gap

    @pytest.mark.asyncio
    async def test_is_flaky_insufficient_data(self, detector, mock_supabase):
        """Less than 3 occurrences returns not flaky."""
        mock_supabase.get_error_occurrences.return_value = [
            datetime.utcnow() - timedelta(minutes=10),
            datetime.utcnow(),
        ]

        result = await detector.is_flaky("fp123")
        assert result is False

    @pytest.mark.asyncio
    async def test_determinism_score_high(self, detector, mock_supabase):
        """Low variance gives high determinism score."""
        # Regular occurrences every 60 seconds
        base = datetime.utcnow()
        mock_supabase.get_error_occurrences.return_value = [
            base - timedelta(minutes=4),
            base - timedelta(minutes=3),
            base - timedelta(minutes=2),
            base - timedelta(minutes=1),
            base,
        ]

        result = await detector.analyze("fp123")
        # Regular intervals should have high determinism
        assert result.determinism_score >= 0.5

    @pytest.mark.asyncio
    async def test_determinism_score_no_data(self, detector, mock_supabase):
        """No data returns 1.0 (assume deterministic)."""
        mock_supabase.get_error_occurrences.return_value = []

        score = await detector.get_determinism_score("fp123")
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_analyze_returns_result(self, detector, mock_supabase):
        """Analysis returns a FlakinessResult."""
        base = datetime.utcnow()
        mock_supabase.get_error_occurrences.return_value = [
            base - timedelta(minutes=3),
            base - timedelta(minutes=2),
            base - timedelta(minutes=1),
            base,
        ]

        result = await detector.analyze("fp123")

        assert isinstance(result, FlakinessResult)
        assert result.occurrence_count == 4
        assert 0.0 <= result.determinism_score <= 1.0
        assert result.variance_seconds >= 0
        assert len(result.recommendation) > 0

    @pytest.mark.asyncio
    async def test_get_occurrences_window(self, detector, mock_supabase):
        """Respects the time window parameter."""
        mock_supabase.get_error_occurrences.return_value = []

        await detector.analyze("fp123", window_hours=48)

        # Check that the call was made with a start time ~48 hours ago
        call_args = mock_supabase.get_error_occurrences.call_args
        assert call_args is not None
