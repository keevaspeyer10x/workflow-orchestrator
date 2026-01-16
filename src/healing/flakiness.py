"""Flakiness Detection - Phase 5 Observability & Hardening.

Detects intermittently-failing errors that appear randomly.

A flaky error is one that:
- Has high variance in occurrence timing
- Doesn't follow a consistent pattern
- May resolve on retry without fixes

This helps avoid applying fixes to transient issues.
"""

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .supabase_client import HealingSupabaseClient


@dataclass
class FlakinessResult:
    """Result of flakiness analysis."""
    is_flaky: bool
    determinism_score: float  # 0.0 = always flaky, 1.0 = deterministic
    occurrence_count: int
    variance_seconds: float
    recommendation: str


class FlakinessDetector:
    """Detect flaky errors that appear intermittently.

    Usage:
        detector = FlakinessDetector(supabase_client)
        result = await detector.analyze(fingerprint)
        if result.is_flaky:
            print("This error may be transient - consider retrying first")
    """

    # Variance threshold for flakiness (1 hour in seconds)
    VARIANCE_THRESHOLD = 3600

    # Minimum occurrences needed for analysis
    MIN_OCCURRENCES = 3

    def __init__(self, supabase: "HealingSupabaseClient"):
        self.supabase = supabase

    async def is_flaky(self, fingerprint: str, window_hours: int = 24) -> bool:
        """Check if an error appears intermittently.

        Args:
            fingerprint: Error fingerprint to check
            window_hours: Time window for analysis

        Returns:
            True if the error is likely flaky
        """
        result = await self.analyze(fingerprint, window_hours)
        return result.is_flaky

    async def analyze(
        self,
        fingerprint: str,
        window_hours: int = 24
    ) -> FlakinessResult:
        """Perform full flakiness analysis.

        Args:
            fingerprint: Error fingerprint to analyze
            window_hours: Time window for analysis

        Returns:
            FlakinessResult with analysis details
        """
        occurrences = await self._get_occurrences(fingerprint, window_hours)

        if len(occurrences) < self.MIN_OCCURRENCES:
            # Not enough data - assume deterministic
            return FlakinessResult(
                is_flaky=False,
                determinism_score=1.0,
                occurrence_count=len(occurrences),
                variance_seconds=0.0,
                recommendation="Insufficient data for flakiness analysis"
            )

        # Calculate intervals between occurrences
        intervals = [
            (occurrences[i + 1] - occurrences[i]).total_seconds()
            for i in range(len(occurrences) - 1)
        ]

        # Calculate variance
        if len(intervals) < 2:
            variance = 0.0
        else:
            variance = statistics.variance(intervals)

        # Calculate determinism score (inverse of normalized variance)
        # High variance = low determinism
        max_variance = self.VARIANCE_THRESHOLD * 10  # Scale for reasonable scores
        determinism_score = max(0.0, 1.0 - (variance / max_variance))
        determinism_score = min(1.0, determinism_score)

        is_flaky = variance > self.VARIANCE_THRESHOLD

        # Generate recommendation
        if is_flaky:
            recommendation = (
                "This error appears intermittently. Consider: "
                "1) Retrying the operation, "
                "2) Checking for race conditions, "
                "3) Investigating external dependencies"
            )
        else:
            recommendation = "Error appears deterministic - fix should be reliable"

        return FlakinessResult(
            is_flaky=is_flaky,
            determinism_score=determinism_score,
            occurrence_count=len(occurrences),
            variance_seconds=variance,
            recommendation=recommendation
        )

    async def get_determinism_score(self, fingerprint: str) -> float:
        """Get determinism score for an error pattern.

        Args:
            fingerprint: Error fingerprint

        Returns:
            Score from 0.0 (always flaky) to 1.0 (always deterministic)
        """
        result = await self.analyze(fingerprint)
        return result.determinism_score

    async def flag_flaky_patterns(self, threshold: float = 0.5) -> list[str]:
        """Find all patterns that appear flaky.

        Args:
            threshold: Determinism score below which to flag

        Returns:
            List of fingerprints for flaky patterns
        """
        try:
            patterns = await self.supabase.get_all_patterns()
            flaky = []

            for pattern in patterns:
                fingerprint = pattern.get("fingerprint")
                if fingerprint:
                    score = await self.get_determinism_score(fingerprint)
                    if score < threshold:
                        flaky.append(fingerprint)

            return flaky
        except Exception:
            return []

    async def _get_occurrences(
        self,
        fingerprint: str,
        window_hours: int
    ) -> list[datetime]:
        """Get occurrence timestamps for an error.

        Args:
            fingerprint: Error fingerprint
            window_hours: Time window

        Returns:
            List of occurrence timestamps, sorted chronologically
        """
        try:
            start_time = datetime.utcnow() - timedelta(hours=window_hours)
            occurrences = await self.supabase.get_error_occurrences(
                fingerprint,
                start_time
            )

            # Parse timestamps if strings
            result = []
            for occ in occurrences:
                if isinstance(occ, datetime):
                    result.append(occ)
                elif isinstance(occ, str):
                    result.append(
                        datetime.fromisoformat(occ.replace("Z", "+00:00")).replace(tzinfo=None)
                    )

            return sorted(result)
        except Exception:
            return []
