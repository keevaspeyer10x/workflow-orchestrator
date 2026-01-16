"""Error accumulator for deduplication.

This module provides session-level error accumulation and deduplication.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from .models import ErrorEvent


@dataclass
class ErrorAccumulator:
    """Accumulate and deduplicate errors within a session.

    Uses fingerprints to deduplicate errors, tracking:
    - First occurrence of each unique error
    - Count of occurrences per fingerprint
    - First seen timestamp
    """

    _errors: Dict[str, ErrorEvent] = field(default_factory=dict)
    _counts: Dict[str, int] = field(default_factory=dict)
    _first_seen: Dict[str, datetime] = field(default_factory=dict)

    def add(self, error: ErrorEvent) -> bool:
        """Add error to accumulator.

        Args:
            error: Error event to add. Must have fingerprint set.

        Returns:
            True if this is a new error, False if duplicate.
        """
        if not error.fingerprint:
            raise ValueError("Error must have fingerprint set")

        fp = error.fingerprint

        if fp in self._errors:
            # Duplicate - increment count
            self._counts[fp] = self._counts.get(fp, 1) + 1
            return False

        # New error
        self._errors[fp] = error
        self._counts[fp] = 1
        self._first_seen[fp] = error.timestamp
        return True

    def get_unique_errors(self) -> List[ErrorEvent]:
        """Get list of unique errors.

        Returns:
            List of unique ErrorEvent instances (first occurrence of each).
        """
        return list(self._errors.values())

    def get_count(self, fingerprint: str) -> int:
        """Get occurrence count for a fingerprint.

        Args:
            fingerprint: Error fingerprint.

        Returns:
            Number of occurrences, 0 if not found.
        """
        return self._counts.get(fingerprint, 0)

    def get_first_seen(self, fingerprint: str) -> Optional[datetime]:
        """Get first seen timestamp for a fingerprint.

        Args:
            fingerprint: Error fingerprint.

        Returns:
            First seen datetime, None if not found.
        """
        return self._first_seen.get(fingerprint)

    def get_summary(self) -> Dict:
        """Get summary statistics.

        Returns:
            Dict with:
            - unique_errors: Number of unique errors
            - total_occurrences: Total count of all occurrences
            - by_type: Dict of error_type -> count
        """
        by_type: Dict[str, int] = {}
        for error in self._errors.values():
            error_type = error.error_type or "Unknown"
            by_type[error_type] = by_type.get(error_type, 0) + 1

        return {
            "unique_errors": len(self._errors),
            "total_occurrences": sum(self._counts.values()),
            "by_type": by_type,
        }

    def clear(self) -> None:
        """Clear all accumulated errors."""
        self._errors.clear()
        self._counts.clear()
        self._first_seen.clear()
