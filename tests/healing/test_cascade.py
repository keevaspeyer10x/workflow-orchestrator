"""Tests for cascade detection."""

import pytest
from datetime import datetime, timedelta, timezone

from src.healing.cascade import (
    CascadeDetector,
    AppliedFix,
    CascadeStatus,
    get_cascade_detector,
    reset_cascade_detector,
)


def _utcnow() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class TestCascadeDetector:
    """Tests for CascadeDetector."""

    @pytest.fixture
    def detector(self):
        """Create a fresh CascadeDetector."""
        return CascadeDetector(max_mods_per_hour=3)

    def test_new_file_not_hot(self, detector):
        """New files should not be hot."""
        assert not detector.is_file_hot("src/new_file.py")

    def test_file_becomes_hot(self, detector):
        """Files should become hot after many modifications."""
        for _ in range(3):
            detector.record_modification("src/utils.py")

        assert detector.is_file_hot("src/utils.py")

    def test_file_not_hot_below_threshold(self, detector):
        """Files below threshold should not be hot."""
        detector.record_modification("src/utils.py")
        detector.record_modification("src/utils.py")

        assert not detector.is_file_hot("src/utils.py")

    def test_record_fix(self, detector):
        """Recording a fix should track affected files."""
        fix = AppliedFix(
            fix_id="fix-1",
            fingerprint="abc123",
            affected_files=["src/a.py", "src/b.py"],
            applied_at=_utcnow(),
        )
        detector.record_fix(fix)

        # Both files should have one modification
        status_a = detector.get_file_status("src/a.py")
        status_b = detector.get_file_status("src/b.py")

        assert status_a.modification_count == 1
        assert status_b.modification_count == 1

    def test_check_cascade_detects_recent_fix(self, detector):
        """Should detect cascade when error is in recently fixed file."""
        fix = AppliedFix(
            fix_id="fix-1",
            fingerprint="abc123",
            affected_files=["src/utils.py"],
            applied_at=_utcnow(),
        )
        detector.record_fix(fix)

        # Error in same file shortly after
        causing_fix = detector.check_cascade(
            error_file_path="src/utils.py",
            error_timestamp=_utcnow(),
        )

        assert causing_fix is not None
        assert causing_fix.fix_id == "fix-1"

    def test_check_cascade_ignores_old_fix(self, detector):
        """Should not detect cascade for old fixes."""
        fix = AppliedFix(
            fix_id="fix-1",
            fingerprint="abc123",
            affected_files=["src/utils.py"],
            applied_at=_utcnow() - timedelta(hours=1),
        )
        detector.record_fix(fix)

        # Error much later
        causing_fix = detector.check_cascade(
            error_file_path="src/utils.py",
            error_timestamp=_utcnow(),
        )

        assert causing_fix is None

    def test_check_cascade_ignores_different_file(self, detector):
        """Should not detect cascade for different files."""
        fix = AppliedFix(
            fix_id="fix-1",
            fingerprint="abc123",
            affected_files=["src/utils.py"],
            applied_at=_utcnow(),
        )
        detector.record_fix(fix)

        causing_fix = detector.check_cascade(
            error_file_path="src/other.py",
            error_timestamp=_utcnow(),
        )

        assert causing_fix is None

    def test_get_hot_files(self, detector):
        """Should list all hot files."""
        for _ in range(3):
            detector.record_modification("src/hot1.py")
            detector.record_modification("src/hot2.py")

        detector.record_modification("src/not_hot.py")

        hot_files = detector.get_hot_files()
        assert "src/hot1.py" in hot_files
        assert "src/hot2.py" in hot_files
        assert "src/not_hot.py" not in hot_files

    def test_get_recent_fixes(self, detector):
        """Should return recent fixes."""
        fix1 = AppliedFix(
            fix_id="fix-1",
            fingerprint="abc123",
            affected_files=["src/a.py"],
            applied_at=_utcnow(),
        )
        fix2 = AppliedFix(
            fix_id="fix-2",
            fingerprint="def456",
            affected_files=["src/b.py"],
            applied_at=_utcnow() - timedelta(hours=2),
        )
        detector.record_fix(fix1)
        detector.record_fix(fix2)

        # Should only return fix1 (fix2 is > 1 hour old)
        recent = detector.get_recent_fixes()
        assert len(recent) == 1
        assert recent[0].fix_id == "fix-1"

    def test_reset(self, detector):
        """Reset should clear all tracking."""
        detector.record_modification("src/utils.py")
        detector.record_fix(
            AppliedFix(
                fix_id="fix-1",
                fingerprint="abc123",
                affected_files=["src/a.py"],
                applied_at=_utcnow(),
            )
        )

        detector.reset()

        assert not detector.get_hot_files()
        assert not detector.get_recent_fixes()


class TestCascadeStatus:
    """Tests for CascadeStatus dataclass."""

    def test_cascade_status_properties(self):
        """CascadeStatus should have all expected properties."""
        status = CascadeStatus(
            file_path="src/utils.py",
            modification_count=5,
            is_hot=True,
            first_modification=_utcnow(),
            last_modification=_utcnow(),
        )

        assert status.file_path == "src/utils.py"
        assert status.modification_count == 5
        assert status.is_hot


class TestGlobalCascadeDetector:
    """Tests for global cascade detector functions."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset detector before each test."""
        reset_cascade_detector()
        yield
        reset_cascade_detector()

    def test_get_cascade_detector(self):
        """Should return a singleton."""
        detector1 = get_cascade_detector()
        detector2 = get_cascade_detector()
        assert detector1 is detector2

    def test_reset_creates_new_instance(self):
        """Reset should create a new instance."""
        detector1 = get_cascade_detector()
        reset_cascade_detector()
        detector2 = get_cascade_detector()
        assert detector1 is not detector2
