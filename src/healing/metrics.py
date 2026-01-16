"""Metrics Collection - Phase 5 Observability & Hardening.

Collects and reports metrics for the healing system dashboard.

Metrics tracked:
- Detection rate (errors detected / total failures)
- Auto-fix rate (auto-applied / detected)
- Success rate (successful fixes / applied)
- Cost history (daily spend)
- Pattern growth (new patterns over time)
- Top errors (most frequent patterns)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .supabase_client import HealingSupabaseClient


@dataclass
class DashboardMetrics:
    """Aggregated metrics for dashboard display."""

    # Rates
    detection_rate: float = 0.0  # errors detected / total failures
    auto_fix_rate: float = 0.0   # auto-applied / detected
    success_rate: float = 0.0    # successful / applied

    # Counts
    total_errors_detected: int = 0
    total_fixes_applied: int = 0
    total_fixes_successful: int = 0

    # Cost
    total_cost_usd: float = 0.0
    daily_cost_usd: float = 0.0

    # Patterns
    total_patterns: int = 0
    new_patterns_this_period: int = 0

    # Top errors
    top_errors: list[dict] = None

    def __post_init__(self):
        if self.top_errors is None:
            self.top_errors = []


class HealingMetrics:
    """Collect and report metrics from Supabase.

    Usage:
        metrics = HealingMetrics(supabase_client)
        dashboard = await metrics.get_dashboard_data(days=30)
        print(f"Success rate: {dashboard.success_rate:.1%}")
    """

    def __init__(self, supabase: "HealingSupabaseClient"):
        self.supabase = supabase

    async def get_dashboard_data(self, days: int = 30) -> DashboardMetrics:
        """Get aggregated metrics for dashboard.

        Args:
            days: Number of days to analyze

        Returns:
            DashboardMetrics with aggregated data
        """
        start_date = datetime.utcnow() - timedelta(days=days)

        # Fetch data from Supabase in parallel
        import asyncio
        results = await asyncio.gather(
            self._get_error_counts(start_date),
            self._get_fix_counts(start_date),
            self._get_cost_data(start_date),
            self._get_pattern_counts(start_date),
            self._get_top_errors(start_date, limit=10),
            return_exceptions=True,
        )

        # Unpack results, handling any exceptions
        error_counts = results[0] if not isinstance(results[0], Exception) else {}
        fix_counts = results[1] if not isinstance(results[1], Exception) else {}
        cost_data = results[2] if not isinstance(results[2], Exception) else {}
        pattern_counts = results[3] if not isinstance(results[3], Exception) else {}
        top_errors = results[4] if not isinstance(results[4], Exception) else []

        # Calculate rates
        detected = error_counts.get("detected", 0)
        applied = fix_counts.get("applied", 0)
        successful = fix_counts.get("successful", 0)

        detection_rate = detected / max(1, error_counts.get("total_failures", 1))
        auto_fix_rate = applied / max(1, detected)
        success_rate = successful / max(1, applied)

        return DashboardMetrics(
            detection_rate=detection_rate,
            auto_fix_rate=auto_fix_rate,
            success_rate=success_rate,
            total_errors_detected=detected,
            total_fixes_applied=applied,
            total_fixes_successful=successful,
            total_cost_usd=cost_data.get("total", 0.0),
            daily_cost_usd=cost_data.get("daily_avg", 0.0),
            total_patterns=pattern_counts.get("total", 0),
            new_patterns_this_period=pattern_counts.get("new", 0),
            top_errors=top_errors,
        )

    async def _get_error_counts(self, start_date: datetime) -> dict:
        """Get error detection counts."""
        try:
            return await self.supabase.get_error_counts(start_date)
        except Exception:
            return {"detected": 0, "total_failures": 0}

    async def _get_fix_counts(self, start_date: datetime) -> dict:
        """Get fix application counts."""
        try:
            return await self.supabase.get_fix_counts(start_date)
        except Exception:
            return {"applied": 0, "successful": 0}

    async def _get_cost_data(self, start_date: datetime) -> dict:
        """Get cost tracking data."""
        try:
            return await self.supabase.get_cost_data(start_date)
        except Exception:
            return {"total": 0.0, "daily_avg": 0.0}

    async def _get_pattern_counts(self, start_date: datetime) -> dict:
        """Get pattern counts."""
        try:
            return await self.supabase.get_pattern_counts(start_date)
        except Exception:
            return {"total": 0, "new": 0}

    async def _get_top_errors(self, start_date: datetime, limit: int = 10) -> list[dict]:
        """Get most frequent errors."""
        try:
            return await self.supabase.get_top_errors(start_date, limit)
        except Exception:
            return []

    async def get_cost_history(self, days: int = 30) -> list[dict]:
        """Get daily cost history.

        Args:
            days: Number of days

        Returns:
            List of {date, cost_usd} dicts
        """
        start_date = datetime.utcnow() - timedelta(days=days)
        try:
            return await self.supabase.get_daily_costs(start_date)
        except Exception:
            return []

    async def get_pattern_growth(self, days: int = 30) -> list[dict]:
        """Get pattern count over time.

        Args:
            days: Number of days

        Returns:
            List of {date, count} dicts
        """
        start_date = datetime.utcnow() - timedelta(days=days)
        try:
            return await self.supabase.get_pattern_growth(start_date)
        except Exception:
            return []
