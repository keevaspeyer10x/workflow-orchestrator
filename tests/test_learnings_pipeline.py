"""
Tests for WF-007: Learnings to Roadmap Pipeline

These tests verify the automatic suggestion of roadmap items
based on captured learnings during the LEARN phase.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

# Import will fail until we implement the module
try:
    from src.learnings_pipeline import (
        analyze_learnings,
        categorize_suggestion,
        format_roadmap_entry,
        RoadmapSuggestion,
    )
    PIPELINE_AVAILABLE = True
except ImportError:
    PIPELINE_AVAILABLE = False


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_learnings():
    """Sample LEARNINGS.md content with actionable patterns."""
    return """# Learnings

## Session: 2026-01-07

### What Worked Well
- The review routing system worked effectively
- Tests caught several edge cases early

### What Could Be Improved
- API retry logic was duplicated in 3 places - should extract to utility
- Test setup took 20 minutes due to missing documentation
- Model context window exceeded during large file review - need chunked review

### Unexpected Challenges
- Next time, we should validate inputs before processing
- Need to add better error messages for common failures

### Process Observations
- The workflow could improve with better phase summaries
"""


class TestPatternDetection:
    """Tests for detecting actionable patterns in learnings."""

    @pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="Pipeline module not implemented")
    def test_pattern_should(self, sample_learnings, temp_dir):
        """L1: Detect 'should X' pattern."""
        learnings_file = temp_dir / "LEARNINGS.md"
        learnings_file.write_text(sample_learnings)

        suggestions = analyze_learnings(learnings_file)

        # Should find "should extract to utility"
        should_patterns = [s for s in suggestions if "extract" in s.description.lower()]
        assert len(should_patterns) >= 1

    @pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="Pipeline module not implemented")
    def test_pattern_next_time(self, sample_learnings, temp_dir):
        """L2: Detect 'next time X' pattern."""
        learnings_file = temp_dir / "LEARNINGS.md"
        learnings_file.write_text(sample_learnings)

        suggestions = analyze_learnings(learnings_file)

        # Should find "Next time, we should validate"
        next_time_patterns = [s for s in suggestions if "validate" in s.description.lower()]
        assert len(next_time_patterns) >= 1

    @pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="Pipeline module not implemented")
    def test_pattern_need_to(self, sample_learnings, temp_dir):
        """L3: Detect 'need to X' pattern."""
        learnings_file = temp_dir / "LEARNINGS.md"
        learnings_file.write_text(sample_learnings)

        suggestions = analyze_learnings(learnings_file)

        # Should find "need chunked review" and "need to add better error"
        need_patterns = [s for s in suggestions if "need" in s.source_text.lower()]
        assert len(need_patterns) >= 1

    @pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="Pipeline module not implemented")
    def test_no_patterns(self, temp_dir):
        """L4: No actionable patterns returns empty list."""
        learnings_file = temp_dir / "LEARNINGS.md"
        learnings_file.write_text("""# Learnings

## Session: 2026-01-07

### What Worked Well
- Everything was great
- No issues at all
""")

        suggestions = analyze_learnings(learnings_file)

        assert len(suggestions) == 0


class TestSuggestionCategorization:
    """Tests for categorizing suggestions with roadmap prefixes."""

    @pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="Pipeline module not implemented")
    def test_categorize_core_suggestion(self):
        """L5: Core functionality gets CORE- prefix."""
        suggestion = RoadmapSuggestion(
            description="Add chunked file review for large files",
            source_text="Model context window exceeded during large file review",
            category=None,
        )

        categorized = categorize_suggestion(suggestion)

        assert categorized.prefix == "CORE"

    @pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="Pipeline module not implemented")
    def test_categorize_workflow_suggestion(self):
        """L6: Workflow improvements get WF- prefix."""
        suggestion = RoadmapSuggestion(
            description="Add better phase summaries",
            source_text="The workflow could improve with better phase summaries",
            category=None,
        )

        categorized = categorize_suggestion(suggestion)

        assert categorized.prefix == "WF"

    @pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="Pipeline module not implemented")
    def test_categorize_architecture_suggestion(self):
        """L7: Architecture changes get ARCH- prefix."""
        suggestion = RoadmapSuggestion(
            description="Extract API retry utility",
            source_text="API retry logic was duplicated - should extract to utility",
            category=None,
        )

        categorized = categorize_suggestion(suggestion)

        assert categorized.prefix == "ARCH"


class TestRoadmapFormatting:
    """Tests for formatting suggestions as roadmap entries."""

    @pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="Pipeline module not implemented")
    def test_format_roadmap_entry(self):
        """L8: Generate valid roadmap markdown entry."""
        suggestion = RoadmapSuggestion(
            description="Add chunked file review for large files",
            source_text="Model context window exceeded during large file review",
            prefix="CORE",
        )

        entry = format_roadmap_entry(suggestion, id_number=20)

        assert "### CORE-020" in entry
        assert "Status:** Suggested" in entry
        assert "Source:** LEARNINGS.md" in entry
        assert "chunked file review" in entry.lower()

    @pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="Pipeline module not implemented")
    def test_format_includes_source_quote(self):
        """L9: Entry includes original learning as quote."""
        suggestion = RoadmapSuggestion(
            description="Extract retry utility",
            source_text="API retry logic was duplicated in 3 places",
            prefix="ARCH",
        )

        entry = format_roadmap_entry(suggestion, id_number=3)

        assert ">" in entry  # Blockquote marker
        assert "duplicated" in entry


class TestMultipleLearnings:
    """Tests for handling multiple learnings."""

    @pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="Pipeline module not implemented")
    def test_multiple_learnings_parsed(self, sample_learnings, temp_dir):
        """L10: Multiple learnings all extracted."""
        learnings_file = temp_dir / "LEARNINGS.md"
        learnings_file.write_text(sample_learnings)

        suggestions = analyze_learnings(learnings_file)

        # Should find multiple suggestions
        assert len(suggestions) >= 3

    @pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="Pipeline module not implemented")
    def test_duplicate_detection(self, temp_dir):
        """L11: Same suggestion twice is deduplicated."""
        learnings_file = temp_dir / "LEARNINGS.md"
        learnings_file.write_text("""# Learnings

- We should add validation
- Next time we should add validation
- Need to add validation
""")

        suggestions = analyze_learnings(learnings_file)

        # Should deduplicate similar suggestions
        validation_suggestions = [s for s in suggestions if "validation" in s.description.lower()]
        assert len(validation_suggestions) <= 2  # Allow some variation but not 3 exact copies


class TestLearningsFileHandling:
    """Tests for learnings file reading and parsing."""

    @pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="Pipeline module not implemented")
    def test_missing_file_returns_empty(self, temp_dir):
        """L12: Missing LEARNINGS.md returns empty list."""
        nonexistent = temp_dir / "nonexistent.md"

        suggestions = analyze_learnings(nonexistent)

        assert suggestions == []

    @pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="Pipeline module not implemented")
    def test_empty_file_returns_empty(self, temp_dir):
        """L13: Empty file returns empty list."""
        learnings_file = temp_dir / "LEARNINGS.md"
        learnings_file.write_text("")

        suggestions = analyze_learnings(learnings_file)

        assert suggestions == []
