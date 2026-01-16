"""Tests for Fingerprinter - Phase 1 Detection & Fingerprinting."""

from datetime import datetime
import pytest


class TestBasicFingerprinting:
    """Basic fingerprinting tests."""

    def test_fingerprint_same_error_same_hash(self):
        """Same error produces same fingerprint."""
        from src.healing.fingerprint import Fingerprinter
        from src.healing.models import ErrorEvent

        fp = Fingerprinter()

        error1 = ErrorEvent(
            error_id="err-001",
            timestamp=datetime(2026, 1, 16, 12, 0, 0),
            source="subprocess",
            description="TypeError: 'NoneType' is not subscriptable",
        )

        error2 = ErrorEvent(
            error_id="err-002",
            timestamp=datetime(2026, 1, 16, 13, 0, 0),  # Different time
            source="subprocess",
            description="TypeError: 'NoneType' is not subscriptable",  # Same error
        )

        assert fp.fingerprint(error1) == fp.fingerprint(error2)

    def test_fingerprint_different_error_different_hash(self):
        """Different errors produce different fingerprints."""
        from src.healing.fingerprint import Fingerprinter
        from src.healing.models import ErrorEvent

        fp = Fingerprinter()

        error1 = ErrorEvent(
            error_id="err-001",
            timestamp=datetime(2026, 1, 16, 12, 0, 0),
            source="subprocess",
            description="TypeError: 'NoneType' is not subscriptable",
        )

        error2 = ErrorEvent(
            error_id="err-002",
            timestamp=datetime(2026, 1, 16, 12, 0, 0),
            source="subprocess",
            description="ValueError: invalid literal for int()",
        )

        assert fp.fingerprint(error1) != fp.fingerprint(error2)

    def test_fingerprint_length(self):
        """Fingerprint is 16 hex characters."""
        from src.healing.fingerprint import Fingerprinter
        from src.healing.models import ErrorEvent

        fp = Fingerprinter()
        error = ErrorEvent(
            error_id="err-001",
            timestamp=datetime.now(),
            source="subprocess",
            description="Test error",
        )

        result = fp.fingerprint(error)
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_fingerprint_coarse_length(self):
        """Coarse fingerprint is 8 hex characters."""
        from src.healing.fingerprint import Fingerprinter
        from src.healing.models import ErrorEvent

        fp = Fingerprinter()
        error = ErrorEvent(
            error_id="err-001",
            timestamp=datetime.now(),
            source="subprocess",
            description="TypeError: something",
        )

        result = fp.fingerprint_coarse(error)
        assert len(result) == 8
        assert all(c in "0123456789abcdef" for c in result)


class TestNormalization:
    """Tests for normalization patterns."""

    def test_normalize_file_paths(self):
        """Normalizes absolute file paths."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        text = 'File "/home/user/project/src/main.py", line 10'
        result = fp._normalize(text)
        assert "/home/user/project/src" not in result
        assert "<path>/main.py" in result

    def test_normalize_line_numbers(self):
        """Normalizes line numbers."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        text = "Error in foo.py:123"
        result = fp._normalize(text)
        assert ":123" not in result
        assert "foo.py:<line>" in result

    def test_normalize_uuids(self):
        """Normalizes UUIDs."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        text = "Session 550e8400-e29b-41d4-a716-446655440000 failed"
        result = fp._normalize(text)
        assert "550e8400-e29b-41d4-a716-446655440000" not in result
        assert "<uuid>" in result

    def test_normalize_timestamps(self):
        """Normalizes various timestamp formats."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()

        # ISO format
        text1 = "Error at 2026-01-16T14:30:00Z"
        result1 = fp._normalize(text1)
        assert "2026-01-16T14:30:00Z" not in result1
        assert "<timestamp>" in result1

        # Space-separated
        text2 = "Error at 2026-01-16 14:30:00"
        result2 = fp._normalize(text2)
        assert "2026-01-16 14:30:00" not in result2

    def test_normalize_memory_addresses(self):
        """Normalizes memory addresses."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        text = "Segfault at 0x7fff12345678"
        result = fp._normalize(text)
        assert "0x7fff12345678" not in result
        assert "<addr>" in result

    def test_normalize_temp_paths(self):
        """Normalizes temp paths."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        text = "File /tmp/pytest-abc123/test.txt not found"
        result = fp._normalize(text)
        assert "/tmp/pytest-abc123/" not in result
        # Note: File path pattern catches this first, normalizing to <path>/test.txt
        # This is acceptable behavior - the variable part is still normalized
        assert "<path>/" in result or "<tmpdir>/" in result

    def test_normalize_pids(self):
        """Normalizes process IDs."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        text = "Process pid=12345 crashed"
        result = fp._normalize(text)
        assert "pid=12345" not in result
        assert "pid=<pid>" in result

    def test_normalize_long_strings(self):
        """Normalizes long quoted strings."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        long_string = "x" * 30
        text = f'Error: "{long_string}" is invalid'
        result = fp._normalize(text)
        assert long_string not in result
        assert '"<string>"' in result


class TestErrorTypeExtraction:
    """Tests for error type extraction."""

    def test_extract_error_type_python(self):
        """Extracts Python TypeError."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        result = fp._extract_error_type("TypeError: 'NoneType' is not subscriptable")
        assert result == "TypeError"

    def test_extract_error_type_python_exception(self):
        """Extracts Python ValueError."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        result = fp._extract_error_type("ValueError: invalid literal for int()")
        assert result == "ValueError"

    def test_extract_error_type_node(self):
        """Extracts Node.js Error."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        result = fp._extract_error_type("Error: Cannot find module 'foo'")
        assert result == "Error"

    def test_extract_error_type_rust(self):
        """Extracts Rust compiler error."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        result = fp._extract_error_type("error[E0001]: expected type")
        assert result == "RustError_E0001"

    def test_extract_error_type_go(self):
        """Extracts Go panic."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        result = fp._extract_error_type("panic: runtime error: index out of range")
        assert result == "GoPanic"

    def test_extract_error_type_unknown(self):
        """Falls back to UnknownError."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        result = fp._extract_error_type("Something went wrong")
        assert result == "UnknownError"


class TestStackFrameExtraction:
    """Tests for stack frame extraction."""

    def test_extract_top_frame_python(self):
        """Extracts Python stack frame."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        stack = '''Traceback (most recent call last):
  File "/home/user/project/src/main.py", line 10, in main
    x = data[0]
TypeError: 'NoneType' is not subscriptable'''
        result = fp._extract_top_frame(stack)
        assert result == "main.py:main"

    def test_extract_top_frame_node(self):
        """Extracts Node.js stack frame."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        stack = """Error: Cannot find module
    at foo (/home/user/app/bar.js:10:5)
    at Module._compile (internal/modules/cjs/loader.js:1063:30)"""
        result = fp._extract_top_frame(stack)
        assert result == "bar.js:foo"

    def test_extract_top_frame_none(self):
        """Returns None for unparseable traces."""
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        result = fp._extract_top_frame("Just some random text")
        assert result is None


class TestStabilityTests:
    """Comprehensive stability tests - fingerprints must be stable across variations."""

    def test_fingerprint_stability_100_variations(self):
        """Same error with variations produces same fingerprint."""
        from src.healing.fingerprint import Fingerprinter
        from src.healing.models import ErrorEvent

        fp = Fingerprinter()

        # Base error
        base = ErrorEvent(
            error_id="err-base",
            timestamp=datetime(2026, 1, 16, 12, 0, 0),
            source="subprocess",
            description="TypeError: 'NoneType' object is not subscriptable",
            stack_trace='File "/home/user/project/main.py", line 42, in main\n    x = data[0]',
        )
        base_fp = fp.fingerprint(base)

        # 100 variations with different paths, timestamps, line numbers
        for i in range(100):
            variation = ErrorEvent(
                error_id=f"err-{i}",
                timestamp=datetime(2026, 1, 16, 12 + i % 12, i % 60, 0),
                source="subprocess",
                description="TypeError: 'NoneType' object is not subscriptable",
                stack_trace=f'File "/home/user{i}/project{i}/main.py", line {i+1}, in main\n    x = data[0]',
            )
            assert fp.fingerprint(variation) == base_fp, f"Variation {i} failed"

    def test_fingerprint_stability_cross_machine(self):
        """Different absolute paths, same relative -> same fingerprint."""
        from src.healing.fingerprint import Fingerprinter
        from src.healing.models import ErrorEvent

        fp = Fingerprinter()

        # Same error from different machines
        linux_error = ErrorEvent(
            error_id="err-linux",
            timestamp=datetime(2026, 1, 16, 12, 0, 0),
            source="subprocess",
            description="ImportError: No module named 'foo'",
            stack_trace='File "/home/linux_user/myproject/app.py", line 10, in load',
        )

        mac_error = ErrorEvent(
            error_id="err-mac",
            timestamp=datetime(2026, 1, 16, 13, 0, 0),
            source="subprocess",
            description="ImportError: No module named 'foo'",
            stack_trace='File "/Users/mac_user/myproject/app.py", line 10, in load',
        )

        assert fp.fingerprint(linux_error) == fp.fingerprint(mac_error)

    def test_fingerprint_stability_timestamp_variation(self):
        """Different timestamps -> same fingerprint."""
        from src.healing.fingerprint import Fingerprinter
        from src.healing.models import ErrorEvent

        fp = Fingerprinter()

        error1 = ErrorEvent(
            error_id="err-1",
            timestamp=datetime(2026, 1, 16, 12, 0, 0),
            source="subprocess",
            description="Error at 2026-01-16T12:00:00Z: Connection refused",
        )

        error2 = ErrorEvent(
            error_id="err-2",
            timestamp=datetime(2026, 1, 17, 14, 30, 0),
            source="subprocess",
            description="Error at 2026-01-17T14:30:00Z: Connection refused",
        )

        assert fp.fingerprint(error1) == fp.fingerprint(error2)
