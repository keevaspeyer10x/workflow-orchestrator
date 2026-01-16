"""Tests for TranscriptDetector - Phase 1 Detection & Fingerprinting."""

import pytest


class TestTranscriptDetector:
    """Tests for detecting errors from conversation transcripts."""

    def test_detect_no_errors_in_transcript(self):
        """Clean conversation returns empty."""
        from src.healing.detectors.transcript import TranscriptDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = TranscriptDetector(fp)

        transcript = """User: How do I print hello world?
Assistant: You can use print("Hello World")
User: Thanks!"""

        errors = detector.detect(transcript)
        assert len(errors) == 0

    def test_detect_error_mentioned(self):
        """Finds error in conversation text."""
        from src.healing.detectors.transcript import TranscriptDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = TranscriptDetector(fp)

        transcript = """User: I'm getting this error:
TypeError: 'NoneType' object is not subscriptable
Assistant: This error occurs when..."""

        errors = detector.detect(transcript)
        assert len(errors) == 1
        assert "TypeError" in errors[0].description

    def test_detect_error_with_context(self):
        """Extracts surrounding context."""
        from src.healing.detectors.transcript import TranscriptDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = TranscriptDetector(fp)

        transcript = """User: Running the test:
Traceback (most recent call last):
  File "test.py", line 10, in test_main
    result = main()
ValueError: invalid input
The test is failing."""

        errors = detector.detect(transcript)
        assert len(errors) == 1
        # Should have some context from the transcript
        assert errors[0].source == "transcript"

    def test_detect_multiple_errors(self):
        """Finds all errors in transcript."""
        from src.healing.detectors.transcript import TranscriptDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = TranscriptDetector(fp)

        transcript = """User: First error:
TypeError: cannot concatenate 'str' and 'int'
Assistant: Let me fix that...
User: Now I get:
ImportError: No module named 'foo'"""

        errors = detector.detect(transcript)
        assert len(errors) == 2

    def test_detect_associates_workflow_id(self):
        """Links to workflow context."""
        from src.healing.detectors.transcript import TranscriptDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = TranscriptDetector(fp, workflow_id="wf-001")

        transcript = """User: Error:
ValueError: bad value"""

        errors = detector.detect(transcript)
        assert len(errors) == 1
        assert errors[0].workflow_id == "wf-001"
