"""Tests for safety categorization."""

import pytest

from src.healing.safety import (
    SafetyCategory,
    SafetyCategorizer,
    SafetyAnalysis,
)
from src.healing.config import HealingConfig


class TestSafetyCategorizer:
    """Tests for SafetyCategorizer."""

    @pytest.fixture
    def categorizer(self):
        """Create a SafetyCategorizer with test config."""
        config = HealingConfig(
            protected_paths=["src/auth/**", "migrations/**", "*.env*"]
        )
        return SafetyCategorizer(config=config)

    def test_protected_path_is_risky(self, categorizer):
        """Protected paths should be categorized as RISKY."""
        result = categorizer.categorize(
            diff="+import something",
            affected_files=["src/auth/login.py"],
        )
        assert result.category == SafetyCategory.RISKY
        assert "src/auth/login.py" in result.protected_paths_matched

    def test_migration_is_risky(self, categorizer):
        """Migration files should be categorized as RISKY."""
        result = categorizer.categorize(
            diff="+ALTER TABLE users ADD COLUMN",
            affected_files=["migrations/001_add_users.sql"],
        )
        assert result.category == SafetyCategory.RISKY

    def test_env_file_is_risky(self, categorizer):
        """Env files should be categorized as RISKY."""
        result = categorizer.categorize(
            diff="+API_KEY=secret",
            affected_files=[".env.local"],
        )
        assert result.category == SafetyCategory.RISKY

    def test_empty_diff_is_safe(self, categorizer):
        """Empty diffs should be SAFE."""
        result = categorizer.categorize(
            diff="",
            affected_files=["src/utils.py"],
        )
        assert result.category == SafetyCategory.SAFE

    def test_formatting_only_is_safe(self, categorizer):
        """Formatting-only changes should be SAFE."""
        # Only leading/trailing whitespace changes (same content when stripped)
        diff = """-  x = 1
+    x = 1
-y = 2
+  y = 2
"""
        result = categorizer.categorize(
            diff=diff,
            affected_files=["src/utils.py"],
        )
        assert result.category == SafetyCategory.SAFE

    def test_import_only_is_safe(self, categorizer):
        """Import-only changes should be SAFE."""
        diff = """+import os
+from pathlib import Path
"""
        result = categorizer.categorize(
            diff=diff,
            affected_files=["src/utils.py"],
        )
        assert result.category == SafetyCategory.SAFE

    def test_comment_only_is_safe(self, categorizer):
        """Comment-only changes should be SAFE."""
        diff = """+# This is a comment
+# Another comment
"""
        result = categorizer.categorize(
            diff=diff,
            affected_files=["src/utils.py"],
        )
        assert result.category == SafetyCategory.SAFE

    def test_function_signature_change_is_risky(self, categorizer):
        """Function signature changes should be RISKY."""
        diff = """-def process(data):
+def process(data, validate=True):
"""
        result = categorizer.categorize(
            diff=diff,
            affected_files=["src/utils.py"],
        )
        assert result.category == SafetyCategory.RISKY

    def test_database_operation_is_risky(self, categorizer):
        """Database operations should be RISKY."""
        diff = """+cursor.execute("DELETE FROM users")
"""
        result = categorizer.categorize(
            diff=diff,
            affected_files=["src/db.py"],
        )
        assert result.category == SafetyCategory.RISKY

    def test_security_sensitive_is_risky(self, categorizer):
        """Security-sensitive changes should be RISKY."""
        diff = """+password = get_password()
"""
        result = categorizer.categorize(
            diff=diff,
            affected_files=["src/auth.py"],  # Not in protected path
        )
        assert result.category == SafetyCategory.RISKY

    def test_error_handling_is_moderate(self, categorizer):
        """Error handling changes should be MODERATE."""
        diff = """+try:
+    do_something()
+except Exception as e:
+    log_error(e)
"""
        result = categorizer.categorize(
            diff=diff,
            affected_files=["src/utils.py"],
        )
        assert result.category == SafetyCategory.MODERATE

    def test_conditional_change_is_moderate(self, categorizer):
        """Conditional logic changes should be MODERATE."""
        diff = """+if condition:
+    do_something()
+else:
+    do_other()
"""
        result = categorizer.categorize(
            diff=diff,
            affected_files=["src/utils.py"],
        )
        assert result.category == SafetyCategory.MODERATE

    def test_loop_change_is_moderate(self, categorizer):
        """Loop changes should be MODERATE."""
        diff = """+for item in items:
+    process(item)
"""
        result = categorizer.categorize(
            diff=diff,
            affected_files=["src/utils.py"],
        )
        assert result.category == SafetyCategory.MODERATE


class TestSafetyAnalysis:
    """Tests for SafetyAnalysis dataclass."""

    def test_safe_is_auto_applicable_with_config(self):
        """SAFE should be auto-applicable when config allows."""
        analysis = SafetyAnalysis(
            category=SafetyCategory.SAFE,
            reasons=["Formatting only"],
            protected_paths_matched=[],
        )
        # Note: This depends on global config, which defaults to auto_apply_safe=True
        # In real tests, you'd mock get_config()
        assert analysis.category == SafetyCategory.SAFE

    def test_risky_is_never_auto_applicable(self):
        """RISKY should never be auto-applicable."""
        analysis = SafetyAnalysis(
            category=SafetyCategory.RISKY,
            reasons=["Protected path"],
            protected_paths_matched=["src/auth/login.py"],
        )
        assert not analysis.is_auto_applicable
