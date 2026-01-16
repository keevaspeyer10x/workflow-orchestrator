"""Tests for context extraction module - Phase 6 Intelligent Pattern Filtering."""

import pytest
from datetime import datetime, timedelta

from src.healing.context_extraction import (
    detect_language,
    detect_error_category,
    detect_framework,
    detect_package_manager,
    extract_context,
    wilson_score,
    calculate_recency_score,
    calculate_context_overlap,
    calculate_relevance_score,
    is_eligible_for_cross_project,
)
from src.healing.models import PatternContext


class TestDetectLanguage:
    """Tests for language detection."""

    def test_detect_language_python_patterns(self):
        """Python error patterns detected correctly."""
        desc = "ModuleNotFoundError: No module named 'requests'"
        lang, conf = detect_language(desc)
        assert lang == "python"
        assert conf >= 0.5

    def test_detect_language_python_traceback(self):
        """Python traceback detected."""
        desc = 'Traceback (most recent call last):\n  File "main.py", line 10'
        lang, conf = detect_language(desc)
        assert lang == "python"
        assert conf >= 0.5

    def test_detect_language_javascript_patterns(self):
        """JavaScript error patterns detected."""
        desc = "ReferenceError: foo is not defined\n  at main.js:10:5"
        lang, conf = detect_language(desc)
        assert lang == "javascript"
        assert conf >= 0.5

    def test_detect_language_javascript_npm(self):
        """npm errors detected as JavaScript."""
        desc = "npm ERR! code E404\nnpm ERR! 404 Not Found"
        lang, conf = detect_language(desc)
        assert lang == "javascript"
        assert conf >= 0.5

    def test_detect_language_go_patterns(self):
        """Go error patterns detected."""
        desc = "panic: runtime error: index out of range [0]"
        lang, conf = detect_language(desc)
        assert lang == "go"
        assert conf >= 0.5

    def test_detect_language_rust_patterns(self):
        """Rust error patterns detected."""
        desc = "error[E0432]: unresolved import `foo`"
        lang, conf = detect_language(desc)
        assert lang == "rust"
        assert conf >= 0.5

    def test_detect_language_file_extension_python(self):
        """File extension takes precedence - Python."""
        desc = "Some generic error"
        lang, conf = detect_language(desc, file_path="src/main.py")
        assert lang == "python"
        assert conf == 0.95

    def test_detect_language_file_extension_javascript(self):
        """File extension takes precedence - JavaScript."""
        desc = "Some generic error"
        lang, conf = detect_language(desc, file_path="src/app.tsx")
        assert lang == "javascript"
        assert conf == 0.95

    def test_detect_language_file_extension_go(self):
        """File extension takes precedence - Go."""
        desc = "Some generic error"
        lang, conf = detect_language(desc, file_path="cmd/main.go")
        assert lang == "go"
        assert conf == 0.95

    def test_detect_language_unknown(self):
        """Returns None for unknown patterns."""
        desc = "Something went wrong"
        lang, conf = detect_language(desc)
        assert lang is None
        assert conf == 0.0


class TestDetectErrorCategory:
    """Tests for error category detection."""

    def test_detect_category_dependency(self):
        """Dependency errors detected."""
        desc = "ModuleNotFoundError: No module named 'foo'"
        cat, conf = detect_error_category(desc)
        assert cat == "dependency"
        assert conf >= 0.6

    def test_detect_category_syntax(self):
        """Syntax errors detected."""
        desc = "SyntaxError: invalid syntax"
        cat, conf = detect_error_category(desc)
        assert cat == "syntax"
        assert conf >= 0.6

    def test_detect_category_runtime(self):
        """Runtime errors detected."""
        desc = "RuntimeError: maximum recursion depth exceeded"
        cat, conf = detect_error_category(desc)
        assert cat == "runtime"
        assert conf >= 0.6

    def test_detect_category_network(self):
        """Network errors detected."""
        desc = "ConnectionError: Connection refused"
        cat, conf = detect_error_category(desc)
        assert cat == "network"
        assert conf >= 0.6

    def test_detect_category_permission(self):
        """Permission errors detected."""
        desc = "PermissionError: [Errno 13] Permission denied"
        cat, conf = detect_error_category(desc)
        assert cat == "permission"
        assert conf >= 0.6

    def test_detect_category_unknown(self):
        """Returns None for unknown categories."""
        desc = "An unexpected situation occurred"
        cat, conf = detect_error_category(desc)
        assert cat is None
        assert conf == 0.0


class TestDetectFramework:
    """Tests for framework detection."""

    def test_detect_framework_react(self):
        """React framework detected."""
        desc = "React error: Invalid hook call"
        framework = detect_framework(desc)
        assert framework == "react"

    def test_detect_framework_django(self):
        """Django framework detected."""
        desc = "Error in views.py"
        framework = detect_framework(desc, file_path="myapp/views.py")
        assert framework == "django"

    def test_detect_framework_pytest(self):
        """Pytest framework detected."""
        desc = "pytest collected 5 items"
        framework = detect_framework(desc)
        assert framework == "pytest"

    def test_detect_framework_none(self):
        """Returns None when no framework detected."""
        desc = "Generic error"
        framework = detect_framework(desc)
        assert framework is None


class TestDetectPackageManager:
    """Tests for package manager detection."""

    def test_detect_pip(self):
        """pip detected."""
        desc = "pip install requests failed"
        pm = detect_package_manager(desc)
        assert pm == "pip"

    def test_detect_npm(self):
        """npm detected."""
        desc = "npm ERR! code E404"
        pm = detect_package_manager(desc)
        assert pm == "npm"

    def test_detect_cargo(self):
        """cargo detected."""
        desc = "cargo build failed"
        pm = detect_package_manager(desc)
        assert pm == "cargo"

    def test_detect_none(self):
        """Returns None when no package manager detected."""
        desc = "Generic error"
        pm = detect_package_manager(desc)
        assert pm is None


class TestExtractContext:
    """Tests for main extract_context function."""

    def test_extract_context_python_dependency(self):
        """Extracts full context for Python dependency error."""
        ctx = extract_context(
            description="ModuleNotFoundError: No module named 'requests'",
            error_type="ModuleNotFoundError",
            file_path="src/main.py",
        )
        assert ctx.language == "python"
        assert ctx.error_category == "dependency"
        assert ctx.extraction_confidence > 0.5

    def test_extract_context_javascript_syntax(self):
        """Extracts full context for JavaScript syntax error."""
        ctx = extract_context(
            description="SyntaxError: Unexpected token",
            file_path="src/app.js",
        )
        assert ctx.language == "javascript"
        assert ctx.error_category == "syntax"

    def test_extract_context_to_dict(self):
        """Context can be converted to dict."""
        ctx = extract_context(
            description="ModuleNotFoundError: No module named 'foo'",
            file_path="test.py",
        )
        d = ctx.to_dict()
        assert "language" in d
        assert d["language"] == "python"


class TestWilsonScore:
    """Tests for Wilson score calculation."""

    def test_wilson_score_sample_size(self):
        """1/1 (100%) should score lower than 95/100 (95%)."""
        # 1 success out of 1 - high uncertainty
        small_sample = wilson_score(1, 1)
        # 95 successes out of 100 - more confidence
        large_sample = wilson_score(95, 100)
        
        # Despite 100% vs 95%, small sample should score lower
        assert small_sample < large_sample

    def test_wilson_score_zero_total(self):
        """Returns 0.5 (neutral) for no data."""
        score = wilson_score(0, 0)
        assert score == 0.5

    def test_wilson_score_all_success(self):
        """High score for many successes."""
        score = wilson_score(100, 100)
        assert score > 0.9
        assert score <= 1.0

    def test_wilson_score_all_failure(self):
        """Low score for all failures."""
        score = wilson_score(0, 100)
        assert score < 0.1

    def test_wilson_score_50_percent(self):
        """50% success rate."""
        score = wilson_score(50, 100)
        assert 0.35 < score < 0.55


class TestRecencyScore:
    """Tests for recency score calculation."""

    def test_recency_score_recent(self):
        """Recent success scores near 1.0."""
        now = datetime.utcnow()
        score = calculate_recency_score(now)
        assert score > 0.95

    def test_recency_score_30_days(self):
        """30-day old success scores ~0.5 (half-life)."""
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        score = calculate_recency_score(thirty_days_ago)
        # Should be approximately 0.5 (within tolerance)
        assert 0.4 < score < 0.6

    def test_recency_score_60_days(self):
        """60-day old success scores ~0.25."""
        sixty_days_ago = datetime.utcnow() - timedelta(days=60)
        score = calculate_recency_score(sixty_days_ago)
        assert 0.2 < score < 0.35

    def test_recency_score_none(self):
        """Returns 0.5 for unknown last_success."""
        score = calculate_recency_score(None)
        assert score == 0.5


class TestContextOverlap:
    """Tests for context overlap calculation."""

    def test_context_overlap_full_match(self):
        """Same context returns high score."""
        pattern_ctx = {"language": "python", "error_category": "dependency"}
        query_ctx = PatternContext(language="python", error_category="dependency")
        score = calculate_context_overlap(pattern_ctx, query_ctx)
        assert score > 0.8

    def test_context_overlap_language_match_only(self):
        """Language match scores higher than just category."""
        pattern_ctx = {"language": "python", "error_category": "syntax"}
        query_ctx = PatternContext(language="python", error_category="dependency")
        score = calculate_context_overlap(pattern_ctx, query_ctx)
        # Should be partial match - language matches but not category
        assert 0.4 < score < 0.8

    def test_context_overlap_no_match(self):
        """Different contexts score low."""
        pattern_ctx = {"language": "python", "error_category": "dependency"}
        query_ctx = PatternContext(language="javascript", error_category="syntax")
        score = calculate_context_overlap(pattern_ctx, query_ctx)
        assert score < 0.5

    def test_context_overlap_empty_pattern(self):
        """Empty pattern context returns neutral."""
        score = calculate_context_overlap({}, PatternContext(language="python"))
        assert score == 0.5

    def test_context_overlap_partial(self):
        """Partial match when pattern has no constraint."""
        pattern_ctx = {"language": "python"}  # No category constraint
        query_ctx = PatternContext(language="python", error_category="dependency")
        score = calculate_context_overlap(pattern_ctx, query_ctx)
        assert score > 0.5  # Should get partial credit


class TestRelevanceScore:
    """Tests for full relevance score calculation."""

    def test_relevance_score_high_quality_pattern(self):
        """High-quality pattern scores well."""
        pattern = {
            "success_count": 95,
            "failure_count": 5,
            "project_count": 5,
            "context": {"language": "python"},
            "last_success_at": datetime.utcnow().isoformat(),
            "risk_level": "low",
        }
        query_ctx = PatternContext(language="python")
        score = calculate_relevance_score(pattern, query_ctx, "proj-1", ["proj-1"])
        assert score > 0.7

    def test_relevance_score_same_project_boost(self):
        """Same project gets 1.2x multiplier."""
        pattern = {
            "success_count": 50,
            "failure_count": 50,
            "project_count": 3,
            "context": {"language": "python"},
        }
        query_ctx = PatternContext(language="python")
        
        # Score with same project
        score_same = calculate_relevance_score(
            pattern, query_ctx, "proj-1", ["proj-1", "proj-2"]
        )
        # Score with different project
        score_diff = calculate_relevance_score(
            pattern, query_ctx, "proj-3", ["proj-1", "proj-2"]
        )
        
        # Same project should score higher
        assert score_same > score_diff

    def test_relevance_score_risk_penalty(self):
        """Higher risk reduces score."""
        base_pattern = {
            "success_count": 90,
            "failure_count": 10,
            "project_count": 3,
            "context": {"language": "python"},
        }
        query_ctx = PatternContext(language="python")
        
        low_risk = {**base_pattern, "risk_level": "low"}
        high_risk = {**base_pattern, "risk_level": "high"}
        
        score_low = calculate_relevance_score(low_risk, query_ctx, "p", [])
        score_high = calculate_relevance_score(high_risk, query_ctx, "p", [])
        
        assert score_low > score_high


class TestCrossProjectEligibility:
    """Tests for cross-project eligibility guardrails."""

    def test_eligible_meets_all_criteria(self):
        """Pattern meeting all criteria is eligible."""
        # Need high enough success rate for Wilson score >= 0.7
        # Wilson(20, 22) ≈ 0.72 which passes
        pattern = {
            "project_count": 5,
            "success_count": 20,
            "failure_count": 2,
        }
        assert is_eligible_for_cross_project(pattern) is True

    def test_ineligible_few_projects(self):
        """Pattern with <3 projects is not eligible."""
        pattern = {
            "project_count": 2,  # Less than 3
            "success_count": 10,
            "failure_count": 0,
        }
        assert is_eligible_for_cross_project(pattern) is False

    def test_ineligible_few_successes(self):
        """Pattern with <5 successes is not eligible."""
        pattern = {
            "project_count": 5,
            "success_count": 4,  # Less than 5
            "failure_count": 0,
        }
        assert is_eligible_for_cross_project(pattern) is False

    def test_ineligible_low_wilson(self):
        """Pattern with low Wilson score is not eligible."""
        pattern = {
            "project_count": 5,
            "success_count": 5,
            "failure_count": 10,  # 33% success rate
        }
        assert is_eligible_for_cross_project(pattern) is False

    def test_eligible_at_threshold(self):
        """Pattern at minimum thresholds (3 projects, 5 successes, Wilson >= 0.7)."""
        # Wilson score needs enough data to be confident
        # With 5 successes and 0 failures, Wilson ≈ 0.57 (not enough)
        # Need ~15+ successes with 0 failures to get Wilson >= 0.7
        pattern = {
            "project_count": 3,  # Minimum projects
            "success_count": 15,  # Wilson(15,15) ≈ 0.78 >= 0.7
            "failure_count": 0,
        }
        assert is_eligible_for_cross_project(pattern) is True
