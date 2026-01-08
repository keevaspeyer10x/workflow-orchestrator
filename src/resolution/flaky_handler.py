"""
Flaky Test Handler (Phase 5)

Tracks test flakiness and provides:
- History tracking for each test
- Flakiness score calculation
- Retry mechanism for flaky tests
- Score adjustment for flaky failures
- Persistence to disk

Flakiness is detected by counting transitions between pass/fail states.
A test that alternates frequently is considered flaky.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .schema import FlakyTestRecord

logger = logging.getLogger(__name__)


class FlakyTestHandler:
    """
    Handles flaky test detection, retry, and scoring.

    Maintains a persistent database of test outcomes to detect
    flakiness over time.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        max_retries: int = 3,
        max_history: int = 20,
        flakiness_threshold: float = 0.3,
        quarantine_threshold: float = 0.8,
    ):
        """
        Initialize flaky test handler.

        Args:
            db_path: Path to flaky test database JSON file
            max_retries: Maximum retries for flaky tests
            max_history: Maximum outcomes to keep per test
            flakiness_threshold: Score above which test is considered flaky
            quarantine_threshold: Score above which test is quarantined
        """
        self.db_path = db_path or Path(".flaky_tests.json")
        self.max_retries = max_retries
        self.max_history = max_history
        self.flakiness_threshold = flakiness_threshold
        self.quarantine_threshold = quarantine_threshold

        self._records: dict[str, FlakyTestRecord] = {}
        self.load()

    def load(self) -> None:
        """Load flaky test data from disk."""
        if not self.db_path.exists():
            self._records = {}
            return

        try:
            with open(self.db_path, 'r') as f:
                data = json.load(f)

            self._records = {}
            for name, record_data in data.items():
                self._records[name] = FlakyTestRecord(
                    test_name=name,
                    outcomes=record_data.get("outcomes", []),
                    last_updated=datetime.fromisoformat(
                        record_data.get("last_updated", datetime.now(timezone.utc).isoformat())
                    ),
                )

            logger.info(f"Loaded {len(self._records)} flaky test records")

        except Exception as e:
            logger.warning(f"Failed to load flaky test data: {e}")
            self._records = {}

    def save(self) -> None:
        """Save flaky test data to disk."""
        try:
            data = {}
            for name, record in self._records.items():
                data[name] = {
                    "outcomes": record.outcomes,
                    "last_updated": record.last_updated.isoformat(),
                }

            with open(self.db_path, 'w') as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved {len(self._records)} flaky test records")

        except Exception as e:
            logger.error(f"Failed to save flaky test data: {e}")

    def record_outcome(self, test_name: str, passed: bool) -> None:
        """
        Record a test outcome.

        Args:
            test_name: Full test name (e.g., "test_auth.py::test_login")
            passed: Whether the test passed
        """
        if test_name not in self._records:
            self._records[test_name] = FlakyTestRecord(test_name=test_name)

        record = self._records[test_name]
        record.outcomes.append(passed)
        record.last_updated = datetime.now(timezone.utc)

        # Keep only last N outcomes
        if len(record.outcomes) > self.max_history:
            record.outcomes = record.outcomes[-self.max_history:]

    def get_history(self, test_name: str) -> list[bool]:
        """Get outcome history for a test."""
        if test_name not in self._records:
            return []
        return list(self._records[test_name].outcomes)

    def get_flakiness_score(self, test_name: str) -> float:
        """
        Get flakiness score for a test.

        Returns 0.0 for stable tests, up to 1.0 for very flaky tests.
        """
        if test_name not in self._records:
            return 0.0

        record = self._records[test_name]
        return record.flakiness_score

    def is_flaky(self, test_name: str) -> bool:
        """Check if a test is considered flaky."""
        return self.get_flakiness_score(test_name) >= self.flakiness_threshold

    def is_quarantined(self, test_name: str) -> bool:
        """Check if a test should be quarantined (very flaky)."""
        return self.get_flakiness_score(test_name) >= self.quarantine_threshold

    def should_retry(self, test_name: str, current_attempt: int) -> bool:
        """
        Check if a failed test should be retried.

        Args:
            test_name: The test name
            current_attempt: Current attempt number (1-indexed)

        Returns:
            True if should retry, False otherwise
        """
        if current_attempt >= self.max_retries:
            return False

        # Only retry if test is known to be flaky
        if not self.is_flaky(test_name):
            return False

        return True

    def get_failure_weight(self, test_name: str) -> float:
        """
        Get weight for a test failure in scoring.

        Flaky test failures have reduced weight.
        Returns 0.0-1.0 (lower = less weight).
        """
        score = self.get_flakiness_score(test_name)

        if score >= self.quarantine_threshold:
            # Quarantined tests have minimal weight
            return 0.1
        elif score >= self.flakiness_threshold:
            # Flaky tests have reduced weight
            return 0.5
        else:
            # Stable tests have full weight
            return 1.0

    def get_flaky_tests(self) -> list[str]:
        """Get list of all flaky tests."""
        return [
            name for name, record in self._records.items()
            if record.flakiness_score >= self.flakiness_threshold
        ]

    def get_quarantined_tests(self) -> list[str]:
        """Get list of quarantined tests."""
        return [
            name for name, record in self._records.items()
            if record.flakiness_score >= self.quarantine_threshold
        ]

    def run_with_retry(
        self,
        test_name: str,
        run_func,
        *args,
        **kwargs,
    ) -> dict:
        """
        Run a test with automatic retry for flaky tests.

        Args:
            test_name: The test name
            run_func: Function to run the test (returns dict with 'passed' key)
            *args, **kwargs: Arguments to pass to run_func

        Returns:
            Final test result dict
        """
        for attempt in range(1, self.max_retries + 1):
            result = run_func(*args, **kwargs)
            passed = result.get("passed", False)

            self.record_outcome(test_name, passed)

            if passed:
                return result

            if not self.should_retry(test_name, attempt):
                break

            logger.info(
                f"Retrying flaky test {test_name} "
                f"(attempt {attempt + 1}/{self.max_retries})"
            )

        return result

    def adjust_test_results(
        self,
        results: dict[str, bool],
    ) -> tuple[dict[str, bool], list[str]]:
        """
        Adjust test results based on flakiness.

        Quarantined tests are marked as passed but noted.

        Args:
            results: Dict of test_name -> passed

        Returns:
            Tuple of (adjusted_results, quarantined_tests)
        """
        adjusted = {}
        quarantined = []

        for test_name, passed in results.items():
            if not passed and self.is_quarantined(test_name):
                # Override quarantined test failures
                adjusted[test_name] = True
                quarantined.append(test_name)
                logger.warning(
                    f"Quarantined test {test_name} failure ignored "
                    f"(flakiness: {self.get_flakiness_score(test_name):.2f})"
                )
            else:
                adjusted[test_name] = passed

        return adjusted, quarantined

    def get_summary(self) -> dict:
        """Get summary of flaky test status."""
        flaky = self.get_flaky_tests()
        quarantined = self.get_quarantined_tests()

        return {
            "total_tracked": len(self._records),
            "flaky_count": len(flaky),
            "quarantined_count": len(quarantined),
            "flaky_tests": flaky,
            "quarantined_tests": quarantined,
        }
