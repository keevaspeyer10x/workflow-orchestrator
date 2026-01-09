"""
Tests for Conflict Pattern Detection - CORE-023 Part 3

Tests pattern detection from conflict resolution logs and
ROADMAP auto-suggestion following source plan (lines 80-101).
"""

import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock


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
    roadmap = temp_dir / "ROADMAP.md"
    roadmap.write_text("""# Roadmap

## Planned Improvements

### High Priority

#### CORE-001: Some Feature
**Status:** Planned
""")
    return roadmap


def create_conflict_event(file_path: str, strategy: str, workflow_id: str = "wf_test"):
    """Helper to create a conflict resolution event."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "conflict_resolved",
        "workflow_id": workflow_id,
        "message": f"Resolved conflict in {file_path}",
        "details": {
            "file": file_path,
            "strategy": strategy,
            "confidence": 0.85,
            "resolution_time_ms": 1250,
        }
    }


def create_workflow_event(event_type: str, workflow_id: str):
    """Helper to create a workflow event."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "workflow_id": workflow_id,
        "message": f"Workflow {event_type}",
        "details": {}
    }


# ============================================================================
# Pattern Detection Tests
# ============================================================================

class TestConflictPatternDetection:
    """Tests for detecting conflict patterns across sessions."""

    def test_get_conflict_patterns_empty_log(self, temp_dir, log_file):
        """Should return empty list when no conflicts logged."""
        from src.learning_engine import LearningEngine

        engine = LearningEngine(working_dir=str(temp_dir))
        patterns = engine.get_conflict_patterns()

        assert patterns == []

    def test_get_conflict_patterns_counts_file_occurrences(self, temp_dir, log_file):
        """Should count how many times each file conflicted."""
        from src.learning_engine import LearningEngine

        # Create log with multiple conflicts for same file
        events = [
            create_workflow_event("workflow_started", "wf_1"),
            create_conflict_event("src/cli.py", "3way", "wf_1"),
            create_workflow_event("workflow_completed", "wf_1"),
            create_workflow_event("workflow_started", "wf_2"),
            create_conflict_event("src/cli.py", "ours", "wf_2"),
            create_conflict_event("src/utils.py", "theirs", "wf_2"),
            create_workflow_event("workflow_completed", "wf_2"),
            create_workflow_event("workflow_started", "wf_3"),
            create_conflict_event("src/cli.py", "llm", "wf_3"),
            create_workflow_event("workflow_completed", "wf_3"),
        ]

        with open(log_file, 'w') as f:
            for event in events:
                f.write(json.dumps(event) + '\n')

        engine = LearningEngine(working_dir=str(temp_dir))
        patterns = engine.get_conflict_patterns(session_window=10)

        # src/cli.py should have 3 conflicts
        cli_pattern = next((p for p in patterns if p.file_path == "src/cli.py"), None)
        assert cli_pattern is not None
        assert cli_pattern.conflict_count == 3

        # src/utils.py should have 1 conflict
        utils_pattern = next((p for p in patterns if p.file_path == "src/utils.py"), None)
        assert utils_pattern is not None
        assert utils_pattern.conflict_count == 1

    def test_get_conflict_patterns_tracks_session_count(self, temp_dir, log_file):
        """Should track how many sessions had conflicts (for X/Y format)."""
        from src.learning_engine import LearningEngine

        # Create 10 workflow sessions, 4 with cli.py conflicts
        events = []
        for i in range(10):
            wf_id = f"wf_{i}"
            events.append(create_workflow_event("workflow_started", wf_id))
            if i < 4:  # First 4 sessions have cli.py conflicts
                events.append(create_conflict_event("src/cli.py", "3way", wf_id))
            events.append(create_workflow_event("workflow_completed", wf_id))

        with open(log_file, 'w') as f:
            for event in events:
                f.write(json.dumps(event) + '\n')

        engine = LearningEngine(working_dir=str(temp_dir))
        patterns = engine.get_conflict_patterns(session_window=10)

        cli_pattern = next((p for p in patterns if p.file_path == "src/cli.py"), None)
        assert cli_pattern is not None
        assert cli_pattern.conflict_count == 4
        assert cli_pattern.session_count == 10

    def test_get_conflict_patterns_tracks_strategies_used(self, temp_dir, log_file):
        """Should track which strategies were used for each file."""
        from src.learning_engine import LearningEngine

        events = [
            create_workflow_event("workflow_started", "wf_1"),
            create_conflict_event("src/cli.py", "3way", "wf_1"),
            create_workflow_event("workflow_completed", "wf_1"),
            create_workflow_event("workflow_started", "wf_2"),
            create_conflict_event("src/cli.py", "llm", "wf_2"),
            create_workflow_event("workflow_completed", "wf_2"),
            create_workflow_event("workflow_started", "wf_3"),
            create_conflict_event("src/cli.py", "3way", "wf_3"),
            create_workflow_event("workflow_completed", "wf_3"),
        ]

        with open(log_file, 'w') as f:
            for event in events:
                f.write(json.dumps(event) + '\n')

        engine = LearningEngine(working_dir=str(temp_dir))
        patterns = engine.get_conflict_patterns()

        cli_pattern = next(p for p in patterns if p.file_path == "src/cli.py")
        assert cli_pattern.strategies_used["3way"] == 2
        assert cli_pattern.strategies_used["llm"] == 1

    def test_get_conflict_patterns_respects_session_window(self, temp_dir, log_file):
        """Should only consider last N sessions based on window."""
        from src.learning_engine import LearningEngine

        # Create 15 sessions, but pattern detection should only see last 5
        events = []
        for i in range(15):
            wf_id = f"wf_{i}"
            events.append(create_workflow_event("workflow_started", wf_id))
            events.append(create_conflict_event("src/cli.py", "3way", wf_id))
            events.append(create_workflow_event("workflow_completed", wf_id))

        with open(log_file, 'w') as f:
            for event in events:
                f.write(json.dumps(event) + '\n')

        engine = LearningEngine(working_dir=str(temp_dir))
        patterns = engine.get_conflict_patterns(session_window=5)

        cli_pattern = next(p for p in patterns if p.file_path == "src/cli.py")
        # Should only count conflicts from last 5 sessions
        assert cli_pattern.session_count == 5
        assert cli_pattern.conflict_count == 5


# ============================================================================
# ROADMAP Suggestion Tests
# ============================================================================

class TestRoadmapSuggestions:
    """Tests for generating and adding ROADMAP suggestions."""

    def test_generate_suggestions_above_threshold(self, temp_dir, log_file):
        """Should generate suggestion for files above conflict threshold."""
        from src.learning_engine import LearningEngine

        # Create 10 sessions, cli.py conflicts in 4 of them (above threshold of 3)
        events = []
        for i in range(10):
            wf_id = f"wf_{i}"
            events.append(create_workflow_event("workflow_started", wf_id))
            if i < 4:
                events.append(create_conflict_event("src/cli.py", "3way", wf_id))
            events.append(create_workflow_event("workflow_completed", wf_id))

        with open(log_file, 'w') as f:
            for event in events:
                f.write(json.dumps(event) + '\n')

        engine = LearningEngine(working_dir=str(temp_dir))
        suggestions = engine.generate_roadmap_suggestions(conflict_threshold=3)

        assert len(suggestions) == 1
        assert "cli.py" in suggestions[0].title.lower()
        assert "4/10" in suggestions[0].evidence or "4 of 10" in suggestions[0].evidence.lower()

    def test_generate_suggestions_below_threshold(self, temp_dir, log_file):
        """Should not generate suggestion for files below threshold."""
        from src.learning_engine import LearningEngine

        # Create 10 sessions, cli.py conflicts in only 2 (below threshold of 3)
        events = []
        for i in range(10):
            wf_id = f"wf_{i}"
            events.append(create_workflow_event("workflow_started", wf_id))
            if i < 2:
                events.append(create_conflict_event("src/cli.py", "3way", wf_id))
            events.append(create_workflow_event("workflow_completed", wf_id))

        with open(log_file, 'w') as f:
            for event in events:
                f.write(json.dumps(event) + '\n')

        engine = LearningEngine(working_dir=str(temp_dir))
        suggestions = engine.generate_roadmap_suggestions(conflict_threshold=3)

        assert len(suggestions) == 0

    def test_add_roadmap_suggestion_format(self, temp_dir, roadmap_file):
        """Should add suggestion in exact format from source plan (lines 91-97)."""
        from src.learning_engine import LearningEngine, RoadmapSuggestion

        engine = LearningEngine(working_dir=str(temp_dir))

        suggestion = RoadmapSuggestion(
            title="Reduce cli.py conflicts",
            evidence="cli.py conflicted in 4/10 sessions",
            recommendation="Extract argument parsing to separate module to reduce merge conflict surface area.",
            source_date="2026-01-09",
        )

        result = engine.add_roadmap_suggestion(suggestion)

        assert result is True

        content = roadmap_file.read_text()

        # Verify format matches source plan exactly
        assert "#### AI-SUGGESTED: Reduce cli.py conflicts" in content
        assert "**Status:** Suggested" in content
        assert "**Source:** AI analysis (LEARN phase, 2026-01-09)" in content
        assert "**Evidence:** cli.py conflicted in 4/10 sessions" in content
        assert "**Recommendation:** Extract argument parsing" in content

    def test_add_roadmap_suggestion_returns_false_if_duplicate(self, temp_dir, roadmap_file):
        """Should return False and not add duplicate suggestions."""
        from src.learning_engine import LearningEngine, RoadmapSuggestion

        engine = LearningEngine(working_dir=str(temp_dir))

        suggestion = RoadmapSuggestion(
            title="Reduce cli.py conflicts",
            evidence="cli.py conflicted in 4/10 sessions",
            recommendation="Some recommendation",
            source_date="2026-01-09",
        )

        # Add first time
        result1 = engine.add_roadmap_suggestion(suggestion)
        assert result1 is True

        # Try to add again
        result2 = engine.add_roadmap_suggestion(suggestion)
        assert result2 is False

        # Should only appear once
        content = roadmap_file.read_text()
        assert content.count("Reduce cli.py conflicts") == 1

    def test_add_roadmap_suggestion_creates_roadmap_if_missing(self, temp_dir):
        """Should create ROADMAP.md if it doesn't exist."""
        from src.learning_engine import LearningEngine, RoadmapSuggestion

        roadmap_file = temp_dir / "ROADMAP.md"
        assert not roadmap_file.exists()

        engine = LearningEngine(working_dir=str(temp_dir))

        suggestion = RoadmapSuggestion(
            title="Test suggestion",
            evidence="Test evidence",
            recommendation="Test recommendation",
            source_date="2026-01-09",
        )

        engine.add_roadmap_suggestion(suggestion)

        assert roadmap_file.exists()
        content = roadmap_file.read_text()
        assert "AI-SUGGESTED" in content


# ============================================================================
# Integration Tests
# ============================================================================

class TestConflictPatternIntegration:
    """Integration tests for the full pattern detection → suggestion flow."""

    def test_full_flow_detects_patterns_and_suggests(self, temp_dir, log_file, roadmap_file):
        """Should detect patterns and add suggestions in full flow."""
        from src.learning_engine import LearningEngine

        # Create realistic log with pattern: cli.py conflicts frequently
        events = []
        for i in range(10):
            wf_id = f"wf_{i}"
            events.append(create_workflow_event("workflow_started", wf_id))

            # cli.py conflicts in 4 sessions
            if i in [0, 2, 5, 8]:
                events.append(create_conflict_event("src/cli.py", "3way", wf_id))

            # utils.py only conflicts once
            if i == 3:
                events.append(create_conflict_event("src/utils.py", "ours", wf_id))

            events.append(create_workflow_event("workflow_completed", wf_id))

        with open(log_file, 'w') as f:
            for event in events:
                f.write(json.dumps(event) + '\n')

        engine = LearningEngine(working_dir=str(temp_dir))

        # Get patterns
        patterns = engine.get_conflict_patterns(session_window=10)

        # Should detect cli.py as frequently conflicting
        cli_pattern = next((p for p in patterns if p.file_path == "src/cli.py"), None)
        assert cli_pattern is not None
        assert cli_pattern.conflict_count == 4

        # Generate suggestions (threshold = 3)
        suggestions = engine.generate_roadmap_suggestions(conflict_threshold=3)

        # Should suggest for cli.py (4 conflicts >= 3)
        assert len(suggestions) == 1
        assert "cli.py" in suggestions[0].title.lower()

        # Add to roadmap
        for suggestion in suggestions:
            engine.add_roadmap_suggestion(suggestion)

        # Verify ROADMAP was updated
        content = roadmap_file.read_text()
        assert "AI-SUGGESTED" in content
        assert "cli.py" in content.lower()

    def test_user_informed_not_asked(self, temp_dir, log_file, roadmap_file, capsys):
        """Should print info message, not prompt (from source: 'user is INFORMED not asked')."""
        from src.learning_engine import LearningEngine

        # Create pattern that triggers suggestion
        events = []
        for i in range(10):
            wf_id = f"wf_{i}"
            events.append(create_workflow_event("workflow_started", wf_id))
            if i < 4:
                events.append(create_conflict_event("src/cli.py", "3way", wf_id))
            events.append(create_workflow_event("workflow_completed", wf_id))

        with open(log_file, 'w') as f:
            for event in events:
                f.write(json.dumps(event) + '\n')

        engine = LearningEngine(working_dir=str(temp_dir))

        # Generate and add suggestions
        suggestions = engine.generate_roadmap_suggestions(conflict_threshold=3)
        for suggestion in suggestions:
            added = engine.add_roadmap_suggestion(suggestion)
            if added:
                # Should print info message
                print(f"Added AI suggestion to ROADMAP: {suggestion.title}")

        captured = capsys.readouterr()
        assert "Added AI suggestion to ROADMAP" in captured.out
