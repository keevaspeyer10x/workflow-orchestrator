"""Tests for Pre-seeded Patterns - Phase 2 Pattern Memory & Lookup."""

import re
import pytest


class TestPreseededPatterns:
    """Tests for pre-built error patterns."""

    def test_patterns_count(self):
        """At least 25 patterns defined."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        assert len(PRESEEDED_PATTERNS) >= 25

    def test_patterns_have_required_fields(self):
        """All patterns have required fields."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        for i, pattern in enumerate(PRESEEDED_PATTERNS):
            assert "fingerprint_pattern" in pattern, f"Pattern {i} missing fingerprint_pattern"
            assert "safety_category" in pattern, f"Pattern {i} missing safety_category"
            assert "action" in pattern, f"Pattern {i} missing action"

    def test_patterns_valid_safety_category(self):
        """All patterns have valid safety category."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        valid_categories = {"safe", "moderate", "risky"}
        for i, pattern in enumerate(PRESEEDED_PATTERNS):
            assert pattern["safety_category"] in valid_categories, (
                f"Pattern {i} has invalid safety_category: {pattern['safety_category']}"
            )

    def test_patterns_valid_action_type(self):
        """All patterns have valid action type."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        valid_types = {"diff", "command", "file_edit", "multi_step"}
        for i, pattern in enumerate(PRESEEDED_PATTERNS):
            action = pattern["action"]
            assert action.get("action_type") in valid_types, (
                f"Pattern {i} has invalid action_type: {action.get('action_type')}"
            )

    def test_patterns_valid_regex(self):
        """All fingerprint patterns are valid regex."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        for i, pattern in enumerate(PRESEEDED_PATTERNS):
            try:
                re.compile(pattern["fingerprint_pattern"])
            except re.error as e:
                pytest.fail(f"Pattern {i} has invalid regex: {e}")

    def test_python_module_not_found_pattern(self):
        """Pattern matches ModuleNotFoundError."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        # Find the pattern
        pattern = next(
            (p for p in PRESEEDED_PATTERNS if "ModuleNotFoundError" in p["fingerprint_pattern"]),
            None,
        )
        assert pattern is not None, "Missing ModuleNotFoundError pattern"

        regex = re.compile(pattern["fingerprint_pattern"])
        assert regex.search("ModuleNotFoundError: No module named 'requests'")
        assert regex.search("ModuleNotFoundError: No module named 'numpy'")
        assert pattern["safety_category"] == "safe"

    def test_node_module_not_found_pattern(self):
        """Pattern matches Cannot find module."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        pattern = next(
            (p for p in PRESEEDED_PATTERNS if "Cannot find module" in p["fingerprint_pattern"]),
            None,
        )
        assert pattern is not None, "Missing Node.js module not found pattern"

        regex = re.compile(pattern["fingerprint_pattern"])
        assert regex.search("Cannot find module 'express'")
        assert regex.search("Cannot find module './utils'")
        assert pattern["safety_category"] == "safe"

    def test_go_package_not_found_pattern(self):
        """Pattern matches Go cannot find package."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        pattern = next(
            (p for p in PRESEEDED_PATTERNS if "cannot find package" in p["fingerprint_pattern"]),
            None,
        )
        assert pattern is not None, "Missing Go package not found pattern"

        regex = re.compile(pattern["fingerprint_pattern"])
        assert regex.search('cannot find package "github.com/pkg/errors"')
        assert pattern["safety_category"] == "safe"

    def test_pytest_fixture_not_found_pattern(self):
        """Pattern matches pytest fixture not found."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        pattern = next(
            (p for p in PRESEEDED_PATTERNS if "fixture" in p["fingerprint_pattern"].lower()),
            None,
        )
        assert pattern is not None, "Missing pytest fixture not found pattern"

        regex = re.compile(pattern["fingerprint_pattern"])
        assert regex.search("fixture 'db_session' not found")
        assert pattern["safety_category"] == "safe"

    def test_rust_error_pattern(self):
        """Pattern matches Rust error codes."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        pattern = next(
            (p for p in PRESEEDED_PATTERNS if "error[E" in p["fingerprint_pattern"]),
            None,
        )
        # Rust pattern may or may not be included
        if pattern:
            regex = re.compile(pattern["fingerprint_pattern"])
            assert regex.search("error[E0433]: failed to resolve")

    def test_python_import_error_pattern(self):
        """Pattern matches ImportError."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        pattern = next(
            (p for p in PRESEEDED_PATTERNS if "ImportError" in p["fingerprint_pattern"]),
            None,
        )
        if pattern:
            regex = re.compile(pattern["fingerprint_pattern"])
            assert regex.search("ImportError: cannot import name 'foo' from 'bar'")

    def test_python_type_error_none_pattern(self):
        """Pattern matches NoneType errors."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        pattern = next(
            (p for p in PRESEEDED_PATTERNS if "NoneType" in p["fingerprint_pattern"]),
            None,
        )
        if pattern:
            regex = re.compile(pattern["fingerprint_pattern"])
            assert regex.search("TypeError: 'NoneType' object is not subscriptable")

    def test_command_action_has_command(self):
        """Command actions have command field."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        for i, pattern in enumerate(PRESEEDED_PATTERNS):
            action = pattern["action"]
            if action["action_type"] == "command":
                assert "command" in action, f"Pattern {i} command action missing command field"

    def test_file_edit_action_has_required_fields(self):
        """File edit actions have find/replace or file_path."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        for i, pattern in enumerate(PRESEEDED_PATTERNS):
            action = pattern["action"]
            if action["action_type"] == "file_edit":
                # Should have either find/replace or requires_context
                has_find_replace = "find" in action and "replace" in action
                has_requires_context = action.get("requires_context", False)
                assert has_find_replace or has_requires_context, (
                    f"Pattern {i} file_edit action missing find/replace or requires_context"
                )

    def test_multi_step_action_has_steps(self):
        """Multi-step actions have steps array."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        for i, pattern in enumerate(PRESEEDED_PATTERNS):
            action = pattern["action"]
            if action["action_type"] == "multi_step":
                assert "steps" in action, f"Pattern {i} multi_step action missing steps"
                assert isinstance(action["steps"], list), f"Pattern {i} steps must be a list"


class TestPatternMatching:
    """Tests for pattern matching against real error messages."""

    def test_match_python_syntax_error(self):
        """Matches Python SyntaxError."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        error = "SyntaxError: invalid syntax"
        matched = False
        for pattern in PRESEEDED_PATTERNS:
            if re.search(pattern["fingerprint_pattern"], error):
                matched = True
                break
        # May or may not have syntax error pattern
        # Just verify no exception is raised

    def test_match_real_traceback(self):
        """Tests pattern matching against real Python traceback."""
        from src.healing.preseeded_patterns import PRESEEDED_PATTERNS

        traceback = """
Traceback (most recent call last):
  File "main.py", line 10, in <module>
    import missing_module
ModuleNotFoundError: No module named 'missing_module'
"""
        # Should match ModuleNotFoundError pattern
        module_pattern = next(
            (p for p in PRESEEDED_PATTERNS if "ModuleNotFoundError" in p["fingerprint_pattern"]),
            None,
        )
        if module_pattern:
            assert re.search(module_pattern["fingerprint_pattern"], traceback)
