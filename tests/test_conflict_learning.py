"""
Tests for Conflict Learning - CORE-023 Part 3

Tests for:
- Conflict pattern analysis from logs
- LEARN phase integration
- Auto-add roadmap suggestions
- Per-file resolution policies in config
"""

import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from src.schema import EventType, WorkflowEvent


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for testing."""
    return tmp_path


@pytest.fixture
def log_file(temp_dir):
    """Create a temporary log file path."""
    return temp_dir / ".workflow_log.jsonl"


@pytest.fixture
def roadmap_file(temp_dir):
    """Create a temporary ROADMAP.md file."""
    content = """# Roadmap

## Planned Features

- Feature A
- Feature B
"""
    file = temp_dir / "ROADMAP.md"
    file.write_text(content)
    return file


@pytest.fixture
def sample_conflict_events():
    """Sample conflict resolution events for testing."""
    return [
        {
            "timestamp": "2026-01-09T10:00:00+00:00",
            "event_type": "conflict_resolved",
            "workflow_id": "wf_001",
            "message": "Resolved conflict in src/cli.py",
            "details": {
                "file": "src/cli.py",
                "strategy": "3way",
                "confidence": 0.85,
                "resolution_time_ms": 1250,
            }
        },
        {
            "timestamp": "2026-01-09T10:05:00+00:00",
            "event_type": "conflict_resolved",
            "workflow_id": "wf_001",
            "message": "Resolved conflict in src/engine.py",
            "details": {
                "file": "src/engine.py",
                "strategy": "ours",
                "confidence": 1.0,
                "resolution_time_ms": 50,
            }
        },
        {
            "timestamp": "2026-01-09T10:10:00+00:00",
            "event_type": "conflict_resolved",
            "workflow_id": "wf_001",
            "message": "Resolved conflict in src/cli.py",
            "details": {
                "file": "src/cli.py",
                "strategy": "llm_merge",
                "confidence": 0.72,
                "resolution_time_ms": 3500,
                "llm_used": True,
                "llm_model": "gpt-4o",
            }
        },
        {
            "timestamp": "2026-01-09T10:15:00+00:00",
            "event_type": "conflict_resolved",
            "workflow_id": "wf_002",
            "message": "Resolved conflict in src/cli.py",
            "details": {
                "file": "src/cli.py",
                "strategy": "theirs",
                "confidence": 1.0,
                "resolution_time_ms": 30,
            }
        },
    ]


def write_events_to_log(log_file, events):
    """Helper to write events to log file."""
    with open(log_file, 'w') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')


# ============================================================================
# Conflict Summary Tests
# ============================================================================

class TestGetConflictSummary:
    """Tests for get_conflict_summary function."""

    def test_returns_empty_summary_when_no_log_file(self, temp_dir):
        """Should return empty summary when log file doesn't exist."""
        from src.resolution.learning import get_conflict_summary

        summary = get_conflict_summary(temp_dir)

        assert summary["total_conflicts"] == 0
        assert summary["resolved_count"] == 0
        assert summary["strategies"] == {}
        assert summary["files"] == {}

    def test_counts_resolutions_correctly(self, temp_dir, log_file, sample_conflict_events):
        """Should count total resolutions from log."""
        from src.resolution.learning import get_conflict_summary

        write_events_to_log(log_file, sample_conflict_events)
        summary = get_conflict_summary(temp_dir)

        assert summary["total_conflicts"] == 4
        assert summary["resolved_count"] == 4

    def test_groups_by_strategy(self, temp_dir, log_file, sample_conflict_events):
        """Should group resolutions by strategy used."""
        from src.resolution.learning import get_conflict_summary

        write_events_to_log(log_file, sample_conflict_events)
        summary = get_conflict_summary(temp_dir)

        assert summary["strategies"]["3way"] == 1
        assert summary["strategies"]["ours"] == 1
        assert summary["strategies"]["llm_merge"] == 1
        assert summary["strategies"]["theirs"] == 1

    def test_groups_by_file(self, temp_dir, log_file, sample_conflict_events):
        """Should group resolutions by file."""
        from src.resolution.learning import get_conflict_summary

        write_events_to_log(log_file, sample_conflict_events)
        summary = get_conflict_summary(temp_dir)

        assert summary["files"]["src/cli.py"] == 3
        assert summary["files"]["src/engine.py"] == 1

    def test_handles_malformed_entries(self, temp_dir, log_file):
        """Should skip malformed log entries gracefully."""
        from src.resolution.learning import get_conflict_summary

        with open(log_file, 'w') as f:
            f.write("invalid json\n")
            f.write('{"event_type": "conflict_resolved", "details": {"file": "test.py", "strategy": "ours"}}\n')
            f.write('{"event_type": "other_event"}\n')

        summary = get_conflict_summary(temp_dir)

        assert summary["total_conflicts"] == 1
        assert summary["files"]["test.py"] == 1

    def test_calculates_average_resolution_time(self, temp_dir, log_file, sample_conflict_events):
        """Should calculate average resolution time."""
        from src.resolution.learning import get_conflict_summary

        write_events_to_log(log_file, sample_conflict_events)
        summary = get_conflict_summary(temp_dir)

        # (1250 + 50 + 3500 + 30) / 4 = 1207.5
        assert summary["avg_resolution_time_ms"] == pytest.approx(1207.5, rel=0.01)


# ============================================================================
# Conflict Patterns Tests
# ============================================================================

class TestGetConflictPatterns:
    """Tests for get_conflict_patterns function."""

    def test_identifies_files_with_multiple_conflicts(self, temp_dir, log_file, sample_conflict_events):
        """Should identify files that had multiple conflicts."""
        from src.resolution.learning import get_conflict_patterns

        write_events_to_log(log_file, sample_conflict_events)
        patterns = get_conflict_patterns(temp_dir, threshold=2)

        assert len(patterns) == 1
        assert patterns[0]["file"] == "src/cli.py"
        assert patterns[0]["count"] == 3

    def test_respects_threshold(self, temp_dir, log_file, sample_conflict_events):
        """Should only return files exceeding threshold."""
        from src.resolution.learning import get_conflict_patterns

        write_events_to_log(log_file, sample_conflict_events)

        # Threshold of 5 should return nothing
        patterns = get_conflict_patterns(temp_dir, threshold=5)
        assert len(patterns) == 0

        # Threshold of 1 should return both files
        patterns = get_conflict_patterns(temp_dir, threshold=1)
        assert len(patterns) == 2

    def test_returns_empty_when_no_patterns(self, temp_dir, log_file):
        """Should return empty list when no patterns found."""
        from src.resolution.learning import get_conflict_patterns

        # Single event won't meet threshold
        events = [{
            "event_type": "conflict_resolved",
            "details": {"file": "test.py", "strategy": "ours"}
        }]
        write_events_to_log(log_file, events)

        patterns = get_conflict_patterns(temp_dir, threshold=3)
        assert patterns == []

    def test_includes_strategy_breakdown(self, temp_dir, log_file, sample_conflict_events):
        """Should include strategy usage per file."""
        from src.resolution.learning import get_conflict_patterns

        write_events_to_log(log_file, sample_conflict_events)
        patterns = get_conflict_patterns(temp_dir, threshold=2)

        cli_pattern = patterns[0]
        assert cli_pattern["strategies"]["3way"] == 1
        assert cli_pattern["strategies"]["llm_merge"] == 1
        assert cli_pattern["strategies"]["theirs"] == 1


# ============================================================================
# Roadmap Suggestions Tests
# ============================================================================

class TestSuggestRoadmapAdditions:
    """Tests for suggest_roadmap_additions function."""

    def test_generates_correct_markdown(self, temp_dir, log_file, sample_conflict_events):
        """Should generate correct markdown format for suggestions."""
        from src.resolution.learning import get_conflict_patterns, suggest_roadmap_additions

        write_events_to_log(log_file, sample_conflict_events)
        patterns = get_conflict_patterns(temp_dir, threshold=2)
        suggestions = suggest_roadmap_additions(patterns)

        assert len(suggestions) == 1
        assert "src/cli.py" in suggestions[0]
        assert "3 conflicts" in suggestions[0]

    def test_returns_empty_when_no_patterns(self):
        """Should return empty list when no patterns provided."""
        from src.resolution.learning import suggest_roadmap_additions

        suggestions = suggest_roadmap_additions([])
        assert suggestions == []


class TestAppendRoadmapSuggestion:
    """Tests for append_roadmap_suggestion function."""

    def test_appends_to_existing_roadmap(self, temp_dir, roadmap_file):
        """Should append suggestion to existing ROADMAP.md."""
        from src.resolution.learning import append_roadmap_suggestion

        suggestion = "- [ ] Refactor `src/cli.py` to reduce conflict frequency (had 3 conflicts)"

        append_roadmap_suggestion(temp_dir, suggestion)

        content = roadmap_file.read_text()
        assert suggestion in content
        assert "## Conflict-Related Suggestions" in content

    def test_creates_section_if_missing(self, temp_dir, roadmap_file):
        """Should create suggestions section if it doesn't exist."""
        from src.resolution.learning import append_roadmap_suggestion

        suggestion = "- [ ] Test suggestion"
        append_roadmap_suggestion(temp_dir, suggestion)

        content = roadmap_file.read_text()
        assert "## Conflict-Related Suggestions" in content
        assert suggestion in content

    def test_handles_missing_roadmap(self, temp_dir):
        """Should handle case when ROADMAP.md doesn't exist."""
        from src.resolution.learning import append_roadmap_suggestion

        # Should not raise an error
        result = append_roadmap_suggestion(temp_dir, "- [ ] Test")
        assert result is False  # Returns False when file doesn't exist


# ============================================================================
# Config Extension Tests
# ============================================================================

class TestUserConfigFilePolicy:
    """Tests for per-file resolution policies in UserConfig."""

    def test_returns_correct_policy_for_exact_match(self, tmp_path):
        """Should return correct policy for exact file match."""
        from src.user_config import UserConfig

        config_data = {
            "file_policies": {
                "package-lock.json": "regenerate",
                "Cargo.lock": "theirs",
            }
        }
        config = UserConfig(config_data)

        assert config.get_file_policy("package-lock.json") == "regenerate"
        assert config.get_file_policy("Cargo.lock") == "theirs"

    def test_returns_correct_policy_for_glob_match(self, tmp_path):
        """Should return correct policy for glob pattern match."""
        from src.user_config import UserConfig

        config_data = {
            "file_policies": {
                "*.lock": "theirs",
                ".env*": "ours",
            }
        }
        config = UserConfig(config_data)

        assert config.get_file_policy("yarn.lock") == "theirs"
        assert config.get_file_policy("poetry.lock") == "theirs"
        assert config.get_file_policy(".env.local") == "ours"

    def test_returns_none_for_unmatched(self):
        """Should return None for files without policy."""
        from src.user_config import UserConfig

        config_data = {
            "file_policies": {
                "package-lock.json": "regenerate",
            }
        }
        config = UserConfig(config_data)

        assert config.get_file_policy("src/main.py") is None
        assert config.get_file_policy("unknown.txt") is None

    def test_uses_defaults_for_generated_files(self):
        """Should use defaults from generated_files for known patterns."""
        from src.user_config import UserConfig

        # Load with defaults
        config = UserConfig.load()

        # Check defaults from generated_files
        assert config.get_generated_file_policy("package-lock.json") == "regenerate"
        assert config.get_generated_file_policy("yarn.lock") == "regenerate"

    def test_file_policies_override_generated_files(self, tmp_path):
        """file_policies should take precedence over generated_files."""
        from src.user_config import UserConfig

        config_data = {
            "generated_files": {
                "package-lock.json": "regenerate",
            },
            "file_policies": {
                "package-lock.json": "theirs",
            }
        }
        config = UserConfig(config_data)

        # file_policies takes precedence
        assert config.get_file_policy("package-lock.json") == "theirs"


# ============================================================================
# LEARN Phase Integration Tests
# ============================================================================

class TestFormatConflictSummary:
    """Tests for formatting conflict summary for LEARN phase."""

    def test_formats_summary_correctly(self, temp_dir, log_file, sample_conflict_events):
        """Should format summary in readable format."""
        from src.resolution.learning import format_conflict_summary, get_conflict_summary

        write_events_to_log(log_file, sample_conflict_events)
        summary = get_conflict_summary(temp_dir)
        formatted = format_conflict_summary(summary)

        assert "Total conflicts resolved: 4" in formatted
        assert "src/cli.py" in formatted
        assert "3way" in formatted or "llm_merge" in formatted

    def test_skips_when_no_conflicts(self):
        """Should return empty string when no conflicts."""
        from src.resolution.learning import format_conflict_summary

        summary = {
            "total_conflicts": 0,
            "resolved_count": 0,
            "strategies": {},
            "files": {},
        }
        formatted = format_conflict_summary(summary)

        assert formatted == ""


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Edge case tests for conflict learning."""

    def test_handles_empty_log_file(self, temp_dir, log_file):
        """Should handle empty log file."""
        from src.resolution.learning import get_conflict_summary

        log_file.write_text("")
        summary = get_conflict_summary(temp_dir)

        assert summary["total_conflicts"] == 0

    def test_handles_log_with_only_non_conflict_events(self, temp_dir, log_file):
        """Should handle log with only non-conflict events."""
        from src.resolution.learning import get_conflict_summary

        events = [
            {"event_type": "workflow_started", "workflow_id": "wf_001"},
            {"event_type": "phase_completed", "phase_id": "PLAN"},
        ]
        write_events_to_log(log_file, events)

        summary = get_conflict_summary(temp_dir)
        assert summary["total_conflicts"] == 0

    def test_handles_missing_details_field(self, temp_dir, log_file):
        """Should handle events missing details field."""
        from src.resolution.learning import get_conflict_summary

        events = [
            {"event_type": "conflict_resolved"},  # Missing details
            {"event_type": "conflict_resolved", "details": {}},  # Empty details
        ]
        write_events_to_log(log_file, events)

        summary = get_conflict_summary(temp_dir)
        # Should not crash, should skip invalid entries
        assert summary["total_conflicts"] == 0


# ============================================================================
# Full Integration Test
# ============================================================================

class TestFullIntegration:
    """Full integration test for conflict learning flow."""

    def test_full_learning_flow(self, temp_dir, log_file, roadmap_file, sample_conflict_events):
        """Test the full flow: log events -> analyze -> suggest -> append."""
        from src.resolution.learning import (
            get_conflict_summary,
            get_conflict_patterns,
            suggest_roadmap_additions,
            append_roadmap_suggestion,
        )

        # Step 1: Write conflict events to log
        write_events_to_log(log_file, sample_conflict_events)

        # Step 2: Get summary
        summary = get_conflict_summary(temp_dir)
        assert summary["total_conflicts"] == 4

        # Step 3: Get patterns
        patterns = get_conflict_patterns(temp_dir, threshold=3)
        assert len(patterns) == 1
        assert patterns[0]["file"] == "src/cli.py"

        # Step 4: Generate suggestions
        suggestions = suggest_roadmap_additions(patterns)
        assert len(suggestions) == 1

        # Step 5: Append to roadmap
        result = append_roadmap_suggestion(temp_dir, suggestions[0])
        assert result is True

        # Step 6: Verify roadmap was updated
        content = roadmap_file.read_text()
        assert "src/cli.py" in content
        assert "Conflict-Related Suggestions" in content
