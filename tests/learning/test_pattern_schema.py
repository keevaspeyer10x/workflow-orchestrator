"""
Tests for pattern memory schema models.

Tests cover:
- ConflictPattern dataclass creation and validation
- PatternMatch dataclass and similarity scoring
- ResolutionOutcome recording
- PatternState lifecycle transitions
- Serialization/deserialization
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Any
import json


class TestPatternState:
    """Tests for PatternState enum."""

    def test_all_states_exist(self):
        """Verify all expected pattern states are defined."""
        from src.learning.pattern_schema import PatternState

        assert hasattr(PatternState, 'ACTIVE')
        assert hasattr(PatternState, 'SUGGESTING')
        assert hasattr(PatternState, 'DORMANT')
        assert hasattr(PatternState, 'DEPRECATED')

    def test_state_values_are_strings(self):
        """State values should be lowercase strings for serialization."""
        from src.learning.pattern_schema import PatternState

        assert PatternState.ACTIVE.value == "active"
        assert PatternState.SUGGESTING.value == "suggesting"
        assert PatternState.DORMANT.value == "dormant"
        assert PatternState.DEPRECATED.value == "deprecated"


class TestConflictPattern:
    """Tests for ConflictPattern dataclass."""

    def test_create_minimal_pattern(self):
        """Create pattern with only required fields."""
        from src.learning.pattern_schema import ConflictPattern, PatternState

        pattern = ConflictPattern(
            pattern_hash="abc123",
            conflict_type="textual",
            resolution_strategy="agent1_primary",
        )

        assert pattern.pattern_hash == "abc123"
        assert pattern.conflict_type == "textual"
        assert pattern.resolution_strategy == "agent1_primary"
        assert pattern.files_involved == []
        assert pattern.intent_categories == []
        assert pattern.success_rate == 0.0
        assert pattern.use_count == 0
        assert pattern.state == PatternState.ACTIVE

    def test_create_full_pattern(self):
        """Create pattern with all fields specified."""
        from src.learning.pattern_schema import ConflictPattern, PatternState

        now = datetime.now(timezone.utc)
        pattern = ConflictPattern(
            pattern_hash="def456",
            conflict_type="semantic",
            files_involved=["src/api.py", "src/models.py"],
            intent_categories=["add_feature", "refactor"],
            resolution_strategy="merge",
            success_rate=0.85,
            last_used=now,
            use_count=10,
            created_at=now - timedelta(days=7),
            confidence=0.9,
            state=PatternState.ACTIVE,
        )

        assert pattern.pattern_hash == "def456"
        assert pattern.conflict_type == "semantic"
        assert pattern.files_involved == ["src/api.py", "src/models.py"]
        assert pattern.intent_categories == ["add_feature", "refactor"]
        assert pattern.resolution_strategy == "merge"
        assert pattern.success_rate == 0.85
        assert pattern.last_used == now
        assert pattern.use_count == 10
        assert pattern.confidence == 0.9
        assert pattern.state == PatternState.ACTIVE

    def test_pattern_to_dict(self):
        """Pattern should serialize to dictionary."""
        from src.learning.pattern_schema import ConflictPattern, PatternState

        pattern = ConflictPattern(
            pattern_hash="hash123",
            conflict_type="dependency",
            resolution_strategy="agent2_primary",
            files_involved=["package.json"],
        )

        d = pattern.to_dict()

        assert isinstance(d, dict)
        assert d["pattern_hash"] == "hash123"
        assert d["conflict_type"] == "dependency"
        assert d["resolution_strategy"] == "agent2_primary"
        assert d["files_involved"] == ["package.json"]
        assert d["state"] == "active"

    def test_pattern_from_dict(self):
        """Pattern should deserialize from dictionary."""
        from src.learning.pattern_schema import ConflictPattern, PatternState

        data = {
            "pattern_hash": "fromdict123",
            "conflict_type": "textual",
            "resolution_strategy": "merge",
            "files_involved": ["a.py", "b.py"],
            "intent_categories": ["bug_fix"],
            "success_rate": 0.75,
            "use_count": 5,
            "confidence": 0.8,
            "state": "suggesting",
            "created_at": "2026-01-01T00:00:00+00:00",
            "last_used": "2026-01-07T12:00:00+00:00",
        }

        pattern = ConflictPattern.from_dict(data)

        assert pattern.pattern_hash == "fromdict123"
        assert pattern.conflict_type == "textual"
        assert pattern.resolution_strategy == "merge"
        assert pattern.files_involved == ["a.py", "b.py"]
        assert pattern.intent_categories == ["bug_fix"]
        assert pattern.success_rate == 0.75
        assert pattern.use_count == 5
        assert pattern.confidence == 0.8
        assert pattern.state == PatternState.SUGGESTING

    def test_pattern_roundtrip(self):
        """Pattern should survive dict -> json -> dict -> pattern."""
        from src.learning.pattern_schema import ConflictPattern, PatternState

        original = ConflictPattern(
            pattern_hash="roundtrip",
            conflict_type="semantic",
            resolution_strategy="fresh_synthesis",
            files_involved=["x.py"],
            intent_categories=["perf"],
            success_rate=0.95,
            use_count=20,
            confidence=0.99,
        )

        json_str = json.dumps(original.to_dict())
        restored = ConflictPattern.from_dict(json.loads(json_str))

        assert restored.pattern_hash == original.pattern_hash
        assert restored.conflict_type == original.conflict_type
        assert restored.resolution_strategy == original.resolution_strategy
        assert restored.success_rate == original.success_rate

    def test_update_success_rate(self):
        """Pattern should update success rate correctly."""
        from src.learning.pattern_schema import ConflictPattern

        pattern = ConflictPattern(
            pattern_hash="update_test",
            conflict_type="textual",
            resolution_strategy="merge",
            success_rate=0.5,
            use_count=2,
        )

        # Record a success
        pattern.record_outcome(success=True)

        assert pattern.use_count == 3
        # (0.5 * 2 + 1) / 3 = 2 / 3 ≈ 0.667
        assert 0.66 < pattern.success_rate < 0.68

    def test_record_failure_decreases_rate(self):
        """Recording failure should decrease success rate."""
        from src.learning.pattern_schema import ConflictPattern

        pattern = ConflictPattern(
            pattern_hash="fail_test",
            conflict_type="textual",
            resolution_strategy="merge",
            success_rate=0.8,
            use_count=5,
        )

        pattern.record_outcome(success=False)

        assert pattern.use_count == 6
        # (0.8 * 5 + 0) / 6 = 4 / 6 ≈ 0.667
        assert 0.66 < pattern.success_rate < 0.68


class TestPatternMatch:
    """Tests for PatternMatch dataclass."""

    def test_create_pattern_match(self):
        """Create a pattern match result."""
        from src.learning.pattern_schema import ConflictPattern, PatternMatch

        pattern = ConflictPattern(
            pattern_hash="match_test",
            conflict_type="textual",
            resolution_strategy="merge",
        )

        match = PatternMatch(
            pattern=pattern,
            similarity_score=0.85,
            matched_on=["conflict_type", "files_pattern"],
            suggested_strategy="merge",
        )

        assert match.pattern == pattern
        assert match.similarity_score == 0.85
        assert match.matched_on == ["conflict_type", "files_pattern"]
        assert match.suggested_strategy == "merge"

    def test_match_is_strong(self):
        """Test threshold for strong match."""
        from src.learning.pattern_schema import ConflictPattern, PatternMatch

        pattern = ConflictPattern(
            pattern_hash="strong",
            conflict_type="textual",
            resolution_strategy="merge",
        )

        strong_match = PatternMatch(
            pattern=pattern,
            similarity_score=0.9,
            matched_on=["all"],
            suggested_strategy="merge",
        )

        weak_match = PatternMatch(
            pattern=pattern,
            similarity_score=0.4,
            matched_on=["type_only"],
            suggested_strategy="merge",
        )

        assert strong_match.is_strong_match()
        assert not weak_match.is_strong_match()

    def test_match_to_dict(self):
        """PatternMatch should serialize."""
        from src.learning.pattern_schema import ConflictPattern, PatternMatch

        pattern = ConflictPattern(
            pattern_hash="serialize",
            conflict_type="semantic",
            resolution_strategy="agent1_primary",
        )

        match = PatternMatch(
            pattern=pattern,
            similarity_score=0.75,
            matched_on=["files", "type"],
            suggested_strategy="agent1_primary",
        )

        d = match.to_dict()

        assert d["similarity_score"] == 0.75
        assert d["matched_on"] == ["files", "type"]
        assert d["suggested_strategy"] == "agent1_primary"
        assert "pattern" in d


class TestResolutionOutcome:
    """Tests for ResolutionOutcome dataclass."""

    def test_create_success_outcome(self):
        """Create a successful resolution outcome."""
        from src.learning.pattern_schema import ResolutionOutcome, ValidationResult

        outcome = ResolutionOutcome(
            pattern_hash="outcome_test",
            conflict_id="conflict_123",
            success=True,
            strategy_used="merge",
            validation_result=ValidationResult.PASSED,
            duration_seconds=45.5,
        )

        assert outcome.pattern_hash == "outcome_test"
        assert outcome.conflict_id == "conflict_123"
        assert outcome.success is True
        assert outcome.strategy_used == "merge"
        assert outcome.validation_result == ValidationResult.PASSED
        assert outcome.duration_seconds == 45.5

    def test_create_failure_outcome(self):
        """Create a failed resolution outcome."""
        from src.learning.pattern_schema import ResolutionOutcome, ValidationResult

        outcome = ResolutionOutcome(
            pattern_hash="fail_outcome",
            conflict_id="conflict_456",
            success=False,
            strategy_used="agent2_primary",
            validation_result=ValidationResult.FAILED,
            duration_seconds=120.0,
            error_message="Tests failed",
        )

        assert outcome.success is False
        assert outcome.validation_result == ValidationResult.FAILED
        assert outcome.error_message == "Tests failed"

    def test_outcome_has_timestamp(self):
        """Outcome should have automatic timestamp."""
        from src.learning.pattern_schema import ResolutionOutcome, ValidationResult

        before = datetime.now(timezone.utc)

        outcome = ResolutionOutcome(
            pattern_hash="time_test",
            conflict_id="c1",
            success=True,
            strategy_used="merge",
            validation_result=ValidationResult.PASSED,
        )

        after = datetime.now(timezone.utc)

        assert before <= outcome.timestamp <= after

    def test_outcome_to_dict(self):
        """Outcome should serialize to dict."""
        from src.learning.pattern_schema import ResolutionOutcome, ValidationResult

        outcome = ResolutionOutcome(
            pattern_hash="dict_test",
            conflict_id="c2",
            success=True,
            strategy_used="merge",
            validation_result=ValidationResult.PASSED,
            duration_seconds=30.0,
        )

        d = outcome.to_dict()

        assert d["pattern_hash"] == "dict_test"
        assert d["conflict_id"] == "c2"
        assert d["success"] is True
        assert d["validation_result"] == "passed"
        assert d["duration_seconds"] == 30.0

    def test_outcome_from_dict(self):
        """Outcome should deserialize from dict."""
        from src.learning.pattern_schema import ResolutionOutcome, ValidationResult

        data = {
            "pattern_hash": "from_dict",
            "conflict_id": "c3",
            "success": False,
            "strategy_used": "agent1_primary",
            "validation_result": "partial",
            "duration_seconds": 60.0,
            "error_message": "Some tests skipped",
            "timestamp": "2026-01-08T10:00:00+00:00",
        }

        outcome = ResolutionOutcome.from_dict(data)

        assert outcome.pattern_hash == "from_dict"
        assert outcome.success is False
        assert outcome.validation_result == ValidationResult.PARTIAL
        assert outcome.error_message == "Some tests skipped"


class TestValidationResult:
    """Tests for ValidationResult enum."""

    def test_all_results_exist(self):
        """Verify all expected validation results are defined."""
        from src.learning.pattern_schema import ValidationResult

        assert hasattr(ValidationResult, 'PASSED')
        assert hasattr(ValidationResult, 'FAILED')
        assert hasattr(ValidationResult, 'PARTIAL')
        assert hasattr(ValidationResult, 'SKIPPED')

    def test_result_values(self):
        """Result values should be lowercase strings."""
        from src.learning.pattern_schema import ValidationResult

        assert ValidationResult.PASSED.value == "passed"
        assert ValidationResult.FAILED.value == "failed"
        assert ValidationResult.PARTIAL.value == "partial"
        assert ValidationResult.SKIPPED.value == "skipped"


class TestPatternStateTransitions:
    """Tests for pattern lifecycle state transitions."""

    def test_decay_confidence_moves_to_suggesting(self):
        """When confidence drops below threshold, state becomes SUGGESTING."""
        from src.learning.pattern_schema import ConflictPattern, PatternState

        pattern = ConflictPattern(
            pattern_hash="decay_test",
            conflict_type="textual",
            resolution_strategy="merge",
            confidence=0.6,  # Just above threshold
            state=PatternState.ACTIVE,
        )

        # Decay confidence below threshold
        pattern.decay_confidence(0.2)  # Now 0.4

        assert pattern.confidence == pytest.approx(0.4, rel=0.01)
        assert pattern.state == PatternState.SUGGESTING

    def test_further_decay_moves_to_dormant(self):
        """When confidence drops very low, state becomes DORMANT."""
        from src.learning.pattern_schema import ConflictPattern, PatternState

        pattern = ConflictPattern(
            pattern_hash="dormant_test",
            conflict_type="textual",
            resolution_strategy="merge",
            confidence=0.3,
            state=PatternState.SUGGESTING,
        )

        # Decay to dormant threshold
        pattern.decay_confidence(0.2)  # Now 0.1

        assert pattern.confidence == pytest.approx(0.1, rel=0.01)
        assert pattern.state == PatternState.DORMANT

    def test_repeated_failures_deprecates(self):
        """Repeated validation failures should deprecate pattern."""
        from src.learning.pattern_schema import ConflictPattern, PatternState

        pattern = ConflictPattern(
            pattern_hash="deprecate_test",
            conflict_type="textual",
            resolution_strategy="merge",
            state=PatternState.ACTIVE,
        )

        # Simulate 3 consecutive failures
        for _ in range(3):
            pattern.record_outcome(success=False)

        assert pattern.state == PatternState.DEPRECATED

    def test_success_boosts_confidence(self):
        """Successful outcomes should boost confidence."""
        from src.learning.pattern_schema import ConflictPattern, PatternState

        pattern = ConflictPattern(
            pattern_hash="boost_test",
            conflict_type="textual",
            resolution_strategy="merge",
            confidence=0.4,
            state=PatternState.SUGGESTING,
        )

        # Record success
        pattern.record_outcome(success=True)

        # Confidence should increase
        assert pattern.confidence > 0.4
        # If confidence exceeds threshold, should become ACTIVE
        if pattern.confidence >= 0.5:
            assert pattern.state == PatternState.ACTIVE
