"""Tests for state_version module - integrity and checksum logic."""

import pytest
from src.state_version import compute_state_checksum


class TestComputeStateChecksum:
    """Tests for compute_state_checksum function."""

    def test_excludes_checksum_field(self):
        """Checksum should not include _checksum field."""
        data1 = {"key": "value", "_checksum": "abc123"}
        data2 = {"key": "value", "_checksum": "xyz789"}

        assert compute_state_checksum(data1) == compute_state_checksum(data2)

    def test_excludes_updated_at_field(self):
        """Checksum should not include _updated_at field."""
        data1 = {"key": "value", "_updated_at": "2026-01-16T12:00:00Z"}
        data2 = {"key": "value", "_updated_at": "2026-01-17T12:00:00Z"}

        assert compute_state_checksum(data1) == compute_state_checksum(data2)

    def test_excludes_version_field(self):
        """Checksum should not include _version field.

        This is the bug fix for issue #94 - _version was being included
        in checksum on save but popped before verification on load,
        causing false integrity warnings.
        """
        data1 = {"key": "value", "_version": "3.0"}
        data2 = {"key": "value", "_version": "4.0"}
        data3 = {"key": "value"}  # No version at all

        # All should produce same checksum
        assert compute_state_checksum(data1) == compute_state_checksum(data2)
        assert compute_state_checksum(data1) == compute_state_checksum(data3)

    def test_includes_actual_data(self):
        """Checksum should include actual state data."""
        data1 = {"key": "value1"}
        data2 = {"key": "value2"}

        assert compute_state_checksum(data1) != compute_state_checksum(data2)

    def test_checksum_is_deterministic(self):
        """Same data should always produce same checksum."""
        data = {"key": "value", "nested": {"a": 1, "b": 2}}

        checksum1 = compute_state_checksum(data)
        checksum2 = compute_state_checksum(data)

        assert checksum1 == checksum2

    def test_checksum_format(self):
        """Checksum should be 32 hex characters (SHA256 truncated)."""
        data = {"key": "value"}
        checksum = compute_state_checksum(data)

        assert len(checksum) == 32
        assert all(c in "0123456789abcdef" for c in checksum)
