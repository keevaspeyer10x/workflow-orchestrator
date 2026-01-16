"""Tests for HookDetector - Phase 1 Detection & Fingerprinting."""

import pytest


class TestHookDetector:
    """Tests for detecting errors from hook output."""

    def test_detect_from_hook_output(self):
        """Parses hook stdout/stderr."""
        from src.healing.detectors.hook import HookDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = HookDetector(fp)

        hook_output = {
            "stdout": "",
            "stderr": "TypeError: 'NoneType' object is not subscriptable",
            "exit_code": 1,
            "hook_name": "pre-commit",
        }

        errors = detector.detect(hook_output)
        assert len(errors) == 1
        assert "TypeError" in errors[0].description
        assert errors[0].source == "hook"

    def test_detect_hook_exit_code(self):
        """Uses exit code in detection."""
        from src.healing.detectors.hook import HookDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = HookDetector(fp)

        # Exit code 0 - no error
        success_output = {
            "stdout": "Hook passed",
            "stderr": "",
            "exit_code": 0,
            "hook_name": "pre-push",
        }
        errors = detector.detect(success_output)
        assert len(errors) == 0

        # Exit code 1 - error
        failure_output = {
            "stdout": "",
            "stderr": "Hook failed",
            "exit_code": 1,
            "hook_name": "pre-push",
        }
        errors = detector.detect(failure_output)
        assert len(errors) == 1

    def test_detect_hook_context(self):
        """Includes hook name in error context."""
        from src.healing.detectors.hook import HookDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = HookDetector(fp)

        hook_output = {
            "stdout": "",
            "stderr": "Lint error: unused variable",
            "exit_code": 1,
            "hook_name": "pre-commit-lint",
        }

        errors = detector.detect(hook_output)
        assert len(errors) == 1
        # Hook name should be preserved somewhere in the error context
        assert errors[0].command is not None or "pre-commit-lint" in str(errors[0])
