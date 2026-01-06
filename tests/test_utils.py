"""
Tests for src/utils.py - Reusable utilities
"""

import pytest
import time
from unittest.mock import patch, MagicMock

from src.utils import retry_with_backoff, slugify


class TestRetryWithBackoff:
    """Tests for the retry_with_backoff decorator."""

    def test_successful_first_attempt(self):
        """TC-RTY-001: No retry when function succeeds."""
        call_count = 0

        @retry_with_backoff(max_retries=3)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_func()
        assert result == "success"
        assert call_count == 1

    def test_success_after_retries(self):
        """TC-RTY-002: Retries until success within limit."""
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Not yet")
            return "success"

        result = fails_twice()
        assert result == "success"
        assert call_count == 3

    def test_all_retries_exhausted(self):
        """TC-RTY-003: Raises last error after max retries."""
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError(f"Attempt {call_count}")

        with pytest.raises(ValueError, match="Attempt 3"):
            always_fails()
        assert call_count == 3

    def test_exponential_backoff_timing(self):
        """TC-RTY-004: Delays follow exponential pattern."""
        delays = []

        @retry_with_backoff(max_retries=4, base_delay=0.1, exceptions=(ValueError,))
        def track_timing():
            delays.append(time.time())
            raise ValueError("fail")

        with pytest.raises(ValueError):
            track_timing()

        # Check delays between calls (should be ~0.1, ~0.2, ~0.4)
        assert len(delays) == 4
        delay1 = delays[1] - delays[0]
        delay2 = delays[2] - delays[1]
        delay3 = delays[3] - delays[2]

        # Allow some tolerance for timing
        assert 0.05 < delay1 < 0.2  # ~0.1
        assert 0.1 < delay2 < 0.4   # ~0.2
        assert 0.2 < delay3 < 0.8   # ~0.4

    def test_max_delay_respected(self):
        """TC-RTY-005: Delay never exceeds max_delay."""
        delays = []

        @retry_with_backoff(max_retries=5, base_delay=1.0, max_delay=0.15, exceptions=(ValueError,))
        def track_timing():
            delays.append(time.time())
            raise ValueError("fail")

        with pytest.raises(ValueError):
            track_timing()

        # All delays should be capped at max_delay
        for i in range(1, len(delays)):
            delay = delays[i] - delays[i-1]
            assert delay < 0.25  # max_delay + tolerance

    def test_specific_exception_types(self):
        """TC-RTY-006: Only catches specified exceptions."""
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.01, exceptions=(ValueError,))
        def raises_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("Wrong type")

        # TypeError should propagate immediately (not caught)
        with pytest.raises(TypeError, match="Wrong type"):
            raises_type_error()
        assert call_count == 1  # Only one attempt

    def test_function_signature_preserved(self):
        """TC-RTY-007: Decorated function keeps name/docstring."""
        @retry_with_backoff()
        def my_function():
            """My docstring."""
            return 42

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."


class TestSlugify:
    """Tests for the slugify function."""

    def test_basic_slugify(self):
        """Basic text is converted to slug."""
        assert slugify("Hello World") == "hello-world"

    def test_special_characters_removed(self):
        """Special characters are removed."""
        assert slugify("Hello, World!") == "hello-world"

    def test_underscores_to_hyphens(self):
        """Underscores are converted to hyphens."""
        assert slugify("hello_world") == "hello-world"

    def test_multiple_spaces_collapsed(self):
        """Multiple spaces become single hyphen."""
        assert slugify("hello   world") == "hello-world"

    def test_max_length_truncation(self):
        """Long slugs are truncated."""
        long_text = "a" * 50
        result = slugify(long_text, max_length=10)
        assert len(result) <= 10

    def test_trailing_hyphens_removed(self):
        """Trailing hyphens are removed after truncation."""
        assert slugify("hello-world-test", max_length=12) == "hello-world"

    def test_empty_string_returns_untitled(self):
        """Empty input returns 'untitled'."""
        assert slugify("") == "untitled"
        assert slugify("!!!") == "untitled"

    def test_numbers_preserved(self):
        """Numbers are kept in slug."""
        assert slugify("Version 2.0") == "version-20"
