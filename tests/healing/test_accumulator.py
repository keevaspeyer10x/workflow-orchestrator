"""Tests for ErrorAccumulator - Phase 1 Detection & Fingerprinting."""

from datetime import datetime
import pytest


class TestBasicOperations:
    """Basic accumulator operations."""

    def test_add_new_error_returns_true(self):
        """First occurrence returns True."""
        from src.healing.accumulator import ErrorAccumulator
        from src.healing.models import ErrorEvent

        acc = ErrorAccumulator()

        error = ErrorEvent(
            error_id="err-001",
            timestamp=datetime.now(),
            source="subprocess",
            description="Test error",
            fingerprint="abc123def456",
        )

        result = acc.add(error)
        assert result is True

    def test_add_duplicate_returns_false(self):
        """Duplicate fingerprint returns False."""
        from src.healing.accumulator import ErrorAccumulator
        from src.healing.models import ErrorEvent

        acc = ErrorAccumulator()

        error1 = ErrorEvent(
            error_id="err-001",
            timestamp=datetime.now(),
            source="subprocess",
            description="Test error",
            fingerprint="abc123def456",
        )

        error2 = ErrorEvent(
            error_id="err-002",
            timestamp=datetime.now(),
            source="subprocess",
            description="Test error",
            fingerprint="abc123def456",  # Same fingerprint
        )

        assert acc.add(error1) is True
        assert acc.add(error2) is False  # Duplicate

    def test_get_unique_errors(self):
        """Returns deduplicated list."""
        from src.healing.accumulator import ErrorAccumulator
        from src.healing.models import ErrorEvent

        acc = ErrorAccumulator()

        # Add 5 errors with 3 unique fingerprints
        for i in range(5):
            error = ErrorEvent(
                error_id=f"err-{i}",
                timestamp=datetime.now(),
                source="subprocess",
                description=f"Error {i % 3}",
                fingerprint=f"fp{i % 3}",  # Only 3 unique
            )
            acc.add(error)

        unique = acc.get_unique_errors()
        assert len(unique) == 3

    def test_get_count(self):
        """Returns occurrence count for fingerprint."""
        from src.healing.accumulator import ErrorAccumulator
        from src.healing.models import ErrorEvent

        acc = ErrorAccumulator()

        # Add same fingerprint 5 times
        for i in range(5):
            error = ErrorEvent(
                error_id=f"err-{i}",
                timestamp=datetime.now(),
                source="subprocess",
                description="Same error",
                fingerprint="repeated_fp",
            )
            acc.add(error)

        assert acc.get_count("repeated_fp") == 5
        assert acc.get_count("nonexistent") == 0

    def test_clear(self):
        """Empties all internal state."""
        from src.healing.accumulator import ErrorAccumulator
        from src.healing.models import ErrorEvent

        acc = ErrorAccumulator()

        error = ErrorEvent(
            error_id="err-001",
            timestamp=datetime.now(),
            source="subprocess",
            description="Test error",
            fingerprint="abc123",
        )

        acc.add(error)
        assert len(acc.get_unique_errors()) == 1

        acc.clear()
        assert len(acc.get_unique_errors()) == 0
        assert acc.get_count("abc123") == 0


class TestSummary:
    """Summary statistics tests."""

    def test_summary_unique_errors(self):
        """Correct unique count."""
        from src.healing.accumulator import ErrorAccumulator
        from src.healing.models import ErrorEvent

        acc = ErrorAccumulator()

        for i in range(3):
            error = ErrorEvent(
                error_id=f"err-{i}",
                timestamp=datetime.now(),
                source="subprocess",
                description=f"Error {i}",
                fingerprint=f"fp{i}",
            )
            acc.add(error)

        summary = acc.get_summary()
        assert summary["unique_errors"] == 3

    def test_summary_total_occurrences(self):
        """Correct total count."""
        from src.healing.accumulator import ErrorAccumulator
        from src.healing.models import ErrorEvent

        acc = ErrorAccumulator()

        # 3 unique errors, some repeated
        for i in range(10):
            error = ErrorEvent(
                error_id=f"err-{i}",
                timestamp=datetime.now(),
                source="subprocess",
                description=f"Error {i % 3}",
                fingerprint=f"fp{i % 3}",
            )
            acc.add(error)

        summary = acc.get_summary()
        assert summary["total_occurrences"] == 10

    def test_summary_by_type(self):
        """Groups by error type."""
        from src.healing.accumulator import ErrorAccumulator
        from src.healing.models import ErrorEvent

        acc = ErrorAccumulator()

        types = ["TypeError", "TypeError", "ValueError", "ImportError"]
        for i, error_type in enumerate(types):
            error = ErrorEvent(
                error_id=f"err-{i}",
                timestamp=datetime.now(),
                source="subprocess",
                description=f"{error_type}: something",
                error_type=error_type,
                fingerprint=f"fp{i}",
            )
            acc.add(error)

        summary = acc.get_summary()
        by_type = summary["by_type"]
        assert by_type.get("TypeError", 0) == 2
        assert by_type.get("ValueError", 0) == 1
        assert by_type.get("ImportError", 0) == 1


class TestEdgeCases:
    """Edge case tests."""

    def test_accumulator_empty(self):
        """Handles empty state gracefully."""
        from src.healing.accumulator import ErrorAccumulator

        acc = ErrorAccumulator()

        assert len(acc.get_unique_errors()) == 0
        assert acc.get_count("anything") == 0
        summary = acc.get_summary()
        assert summary["unique_errors"] == 0
        assert summary["total_occurrences"] == 0

    def test_accumulator_single_error(self):
        """Handles single error."""
        from src.healing.accumulator import ErrorAccumulator
        from src.healing.models import ErrorEvent

        acc = ErrorAccumulator()

        error = ErrorEvent(
            error_id="err-001",
            timestamp=datetime.now(),
            source="subprocess",
            description="Solo error",
            fingerprint="solo_fp",
        )

        acc.add(error)

        assert len(acc.get_unique_errors()) == 1
        assert acc.get_count("solo_fp") == 1
        summary = acc.get_summary()
        assert summary["unique_errors"] == 1
        assert summary["total_occurrences"] == 1

    def test_accumulator_many_duplicates(self):
        """Handles many duplicates efficiently."""
        from src.healing.accumulator import ErrorAccumulator
        from src.healing.models import ErrorEvent

        acc = ErrorAccumulator()

        # Add same error 1000 times
        for i in range(1000):
            error = ErrorEvent(
                error_id=f"err-{i}",
                timestamp=datetime.now(),
                source="subprocess",
                description="Repeated error",
                fingerprint="same_fp",
            )
            acc.add(error)

        assert len(acc.get_unique_errors()) == 1
        assert acc.get_count("same_fp") == 1000
        summary = acc.get_summary()
        assert summary["unique_errors"] == 1
        assert summary["total_occurrences"] == 1000
