"""Cascade detection for preventing fix ping-pong.

This module detects when fixes are causing cascading errors.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional


def _utcnow() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


@dataclass
class AppliedFix:
    """Record of an applied fix."""

    fix_id: str
    fingerprint: str
    affected_files: List[str]
    applied_at: datetime
    commit_sha: Optional[str] = None


@dataclass
class CascadeStatus:
    """Status of cascade detection for a file."""

    file_path: str
    modification_count: int
    is_hot: bool
    first_modification: Optional[datetime]
    last_modification: Optional[datetime]


class CascadeDetector:
    """Detect fix cascades (ping-pong fixes).

    This class tracks file modifications and detects when the same
    file is being modified too frequently, indicating a potential
    cascade of fixes causing more errors.

    A file is considered "hot" when it has been modified more than
    `max_mods_per_hour` times in the last hour.
    """

    def __init__(self, max_mods_per_hour: int = 3):
        """Initialize cascade detector.

        Args:
            max_mods_per_hour: Maximum modifications allowed per file per hour
        """
        self.max_mods_per_hour = max_mods_per_hour
        self._file_mods: Dict[str, List[datetime]] = defaultdict(list)
        self._recent_fixes: List[AppliedFix] = []

    def record_modification(self, file_path: str) -> None:
        """Record that a file was modified.

        Args:
            file_path: Path to the modified file
        """
        self._file_mods[file_path].append(_utcnow())
        self._cleanup_old_records()

    def record_fix(self, fix: AppliedFix) -> None:
        """Record an applied fix.

        Args:
            fix: The applied fix record
        """
        self._recent_fixes.append(fix)
        for file_path in fix.affected_files:
            self.record_modification(file_path)
        self._cleanup_old_records()

    def is_file_hot(self, file_path: str) -> bool:
        """Check if file has been modified too often recently.

        Args:
            file_path: Path to check

        Returns:
            True if file exceeds modification threshold
        """
        if file_path not in self._file_mods:
            return False

        one_hour_ago = _utcnow() - timedelta(hours=1)
        recent = [t for t in self._file_mods[file_path] if t > one_hour_ago]

        return len(recent) >= self.max_mods_per_hour

    def get_file_status(self, file_path: str) -> CascadeStatus:
        """Get cascade status for a file.

        Args:
            file_path: Path to check

        Returns:
            CascadeStatus with modification details
        """
        mods = self._file_mods.get(file_path, [])
        one_hour_ago = _utcnow() - timedelta(hours=1)
        recent = [t for t in mods if t > one_hour_ago]

        return CascadeStatus(
            file_path=file_path,
            modification_count=len(recent),
            is_hot=len(recent) >= self.max_mods_per_hour,
            first_modification=min(mods) if mods else None,
            last_modification=max(mods) if mods else None,
        )

    def check_cascade(
        self,
        error_file_path: Optional[str],
        error_timestamp: datetime,
    ) -> Optional[AppliedFix]:
        """Check if an error was likely caused by a recent fix.

        Args:
            error_file_path: File where the error occurred
            error_timestamp: When the error occurred

        Returns:
            The causing fix if detected, None otherwise
        """
        if not error_file_path:
            return None

        # Look for fixes that touched this file recently
        for fix in reversed(self._recent_fixes):
            if error_file_path in fix.affected_files:
                time_since_fix = error_timestamp - fix.applied_at
                if time_since_fix < timedelta(minutes=30):
                    return fix

        return None

    def get_hot_files(self) -> List[str]:
        """Get list of all hot files.

        Returns:
            List of file paths that are currently hot
        """
        hot = []
        one_hour_ago = _utcnow() - timedelta(hours=1)

        for file_path, mods in self._file_mods.items():
            recent = [t for t in mods if t > one_hour_ago]
            if len(recent) >= self.max_mods_per_hour:
                hot.append(file_path)

        return hot

    def get_recent_fixes(self, since: Optional[datetime] = None) -> List[AppliedFix]:
        """Get list of recent fixes.

        Args:
            since: Only return fixes after this time (default: last hour)

        Returns:
            List of recent fixes
        """
        if since is None:
            since = _utcnow() - timedelta(hours=1)

        return [fix for fix in self._recent_fixes if fix.applied_at > since]

    def _cleanup_old_records(self) -> None:
        """Remove records older than 24 hours."""
        cutoff = _utcnow() - timedelta(hours=24)

        # Clean file modifications
        for file_path in list(self._file_mods.keys()):
            self._file_mods[file_path] = [
                t for t in self._file_mods[file_path] if t > cutoff
            ]
            if not self._file_mods[file_path]:
                del self._file_mods[file_path]

        # Clean recent fixes
        self._recent_fixes = [f for f in self._recent_fixes if f.applied_at > cutoff]

    def reset(self) -> None:
        """Reset all tracking (for testing)."""
        self._file_mods.clear()
        self._recent_fixes.clear()


# Global cascade detector instance
_CASCADE_DETECTOR: CascadeDetector = None


def get_cascade_detector() -> CascadeDetector:
    """Get the global cascade detector instance."""
    global _CASCADE_DETECTOR
    if _CASCADE_DETECTOR is None:
        _CASCADE_DETECTOR = CascadeDetector()
    return _CASCADE_DETECTOR


def reset_cascade_detector() -> None:
    """Reset the global cascade detector (for testing)."""
    global _CASCADE_DETECTOR
    _CASCADE_DETECTOR = None
