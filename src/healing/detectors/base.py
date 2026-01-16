"""Base detector for error detection.

This module provides the abstract base class for all error detectors.
"""

from abc import ABC, abstractmethod
from typing import Any, List

from ..fingerprint import Fingerprinter
from ..models import ErrorEvent


class BaseDetector(ABC):
    """Abstract base class for error detectors.

    All detectors must implement the detect() method to parse
    their specific source format and return ErrorEvent instances.
    """

    def __init__(self, fingerprinter: Fingerprinter):
        """Initialize detector with fingerprinter.

        Args:
            fingerprinter: Fingerprinter instance for hashing errors.
        """
        self.fingerprinter = fingerprinter

    @abstractmethod
    def detect(self, source: Any) -> List[ErrorEvent]:
        """Detect errors from source.

        Args:
            source: Source-specific input (file path, string, dict, etc.)

        Returns:
            List of detected ErrorEvent instances with fingerprints.
        """
        pass

    def _fingerprint(self, error: ErrorEvent) -> ErrorEvent:
        """Add fingerprints to error.

        Args:
            error: Error event without fingerprints.

        Returns:
            Same error event with fingerprint and fingerprint_coarse set.
        """
        error.fingerprint = self.fingerprinter.fingerprint(error)
        error.fingerprint_coarse = self.fingerprinter.fingerprint_coarse(error)
        return error
