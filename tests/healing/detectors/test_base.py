"""Tests for BaseDetector - Phase 1 Detection & Fingerprinting."""

from datetime import datetime
import pytest


class TestBaseDetector:
    """Tests for abstract base detector."""

    def test_base_detector_fingerprint_adds_hashes(self):
        """Adds both fingerprint and fingerprint_coarse."""
        from src.healing.detectors.base import BaseDetector
        from src.healing.fingerprint import Fingerprinter
        from src.healing.models import ErrorEvent

        # Create a concrete implementation for testing
        class TestDetector(BaseDetector):
            def detect(self, source):
                return []

        fp = Fingerprinter()
        detector = TestDetector(fp)

        error = ErrorEvent(
            error_id="err-001",
            timestamp=datetime.now(),
            source="subprocess",
            description="TypeError: test error",
        )

        # Before fingerprinting
        assert error.fingerprint is None
        assert error.fingerprint_coarse is None

        # After fingerprinting
        result = detector._fingerprint(error)
        assert result.fingerprint is not None
        assert result.fingerprint_coarse is not None
        assert len(result.fingerprint) == 16
        assert len(result.fingerprint_coarse) == 8

    def test_base_detector_abstract_detect(self):
        """Cannot instantiate abstract class."""
        from src.healing.detectors.base import BaseDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()

        with pytest.raises(TypeError):
            BaseDetector(fp)
