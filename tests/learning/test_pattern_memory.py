"""
Tests for ConflictPatternMemory - the main interface for pattern-based resolution.

Tests cover:
- Recording resolutions
- Suggesting resolutions for similar conflicts
- Getting success rates
- Integration with PatternDatabase and PatternHasher
"""

import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def temp_storage():
    """Create a temporary directory for pattern storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def pattern_memory(temp_storage):
    """Create a ConflictPatternMemory with temporary storage."""
    from src.learning.pattern_memory import ConflictPatternMemory
    return ConflictPatternMemory(storage_dir=temp_storage)


class TestRecordResolution:
    """Tests for recording resolutions."""

    def test_record_creates_pattern(self, pattern_memory):
        """Recording a resolution creates a pattern."""
        from src.learning.pattern_schema import ValidationResult

        pattern_memory.record_resolution(
            conflict_type="textual",
            files_involved=["src/api.py"],
            intent_categories=["bug_fix"],
            resolution_strategy="merge",
            success=True,
            validation_result=ValidationResult.PASSED,
        )

        # Should have created a pattern
        assert pattern_memory.count_patterns() == 1

    def test_record_updates_existing_pattern(self, pattern_memory):
        """Recording same conflict type updates existing pattern."""
        from src.learning.pattern_schema import ValidationResult

        # Record first resolution
        pattern_memory.record_resolution(
            conflict_type="textual",
            files_involved=["src/api.py"],
            intent_categories=["bug_fix"],
            resolution_strategy="merge",
            success=True,
            validation_result=ValidationResult.PASSED,
        )

        # Record another resolution for same pattern
        pattern_memory.record_resolution(
            conflict_type="textual",
            files_involved=["src/api.py"],
            intent_categories=["bug_fix"],
            resolution_strategy="merge",
            success=True,
            validation_result=ValidationResult.PASSED,
        )

        # Should still have one pattern (updated)
        assert pattern_memory.count_patterns() == 1

    def test_record_tracks_success_rate(self, pattern_memory):
        """Recording tracks success rate."""
        from src.learning.pattern_schema import ValidationResult

        # Record success
        pattern_memory.record_resolution(
            conflict_type="textual",
            files_involved=["src/api.py"],
            intent_categories=[],
            resolution_strategy="merge",
            success=True,
            validation_result=ValidationResult.PASSED,
        )

        # Record failure
        pattern_memory.record_resolution(
            conflict_type="textual",
            files_involved=["src/api.py"],
            intent_categories=[],
            resolution_strategy="merge",
            success=False,
            validation_result=ValidationResult.FAILED,
        )

        # Success rate should be 0.5
        hash_val = pattern_memory._compute_hash(
            conflict_type="textual",
            files_involved=["src/api.py"],
            intent_categories=[],
        )
        rate = pattern_memory.get_success_rate(hash_val)
        assert 0.4 <= rate <= 0.6


class TestSuggestResolution:
    """Tests for suggesting resolutions."""

    def test_suggest_returns_strategy_for_known_pattern(self, pattern_memory):
        """Suggest returns strategy for a known pattern."""
        from src.learning.pattern_schema import ValidationResult

        # Record a successful resolution
        pattern_memory.record_resolution(
            conflict_type="textual",
            files_involved=["src/api.py"],
            intent_categories=["bug_fix"],
            resolution_strategy="merge",
            success=True,
            validation_result=ValidationResult.PASSED,
        )

        # Suggest for same conflict
        suggestion = pattern_memory.suggest_resolution(
            conflict_type="textual",
            files_involved=["src/api.py"],
            intent_categories=["bug_fix"],
        )

        assert suggestion is not None
        assert suggestion.strategy == "merge"

    def test_suggest_returns_none_for_unknown(self, pattern_memory):
        """Suggest returns None for unknown pattern."""
        suggestion = pattern_memory.suggest_resolution(
            conflict_type="dependency",
            files_involved=["package.json"],
            intent_categories=["upgrade"],
        )

        assert suggestion is None

    def test_suggest_prefers_high_success_rate(self, pattern_memory):
        """Suggest prefers strategies with higher success rates."""
        from src.learning.pattern_schema import ValidationResult

        # Record successful merge
        for _ in range(5):
            pattern_memory.record_resolution(
                conflict_type="textual",
                files_involved=["src/api.py"],
                intent_categories=["refactor"],
                resolution_strategy="merge",
                success=True,
                validation_result=ValidationResult.PASSED,
            )

        suggestion = pattern_memory.suggest_resolution(
            conflict_type="textual",
            files_involved=["src/api.py"],
            intent_categories=["refactor"],
        )

        assert suggestion is not None
        assert suggestion.confidence > 0.8

    def test_suggest_includes_confidence(self, pattern_memory):
        """Suggestions include confidence score."""
        from src.learning.pattern_schema import ValidationResult

        pattern_memory.record_resolution(
            conflict_type="semantic",
            files_involved=["src/models.py"],
            intent_categories=["add_feature"],
            resolution_strategy="agent1_primary",
            success=True,
            validation_result=ValidationResult.PASSED,
        )

        suggestion = pattern_memory.suggest_resolution(
            conflict_type="semantic",
            files_involved=["src/models.py"],
            intent_categories=["add_feature"],
        )

        assert suggestion is not None
        assert 0.0 <= suggestion.confidence <= 1.0


class TestGetSuccessRate:
    """Tests for getting success rates."""

    def test_success_rate_for_known_pattern(self, pattern_memory):
        """Get success rate for known pattern."""
        from src.learning.pattern_schema import ValidationResult

        pattern_memory.record_resolution(
            conflict_type="textual",
            files_involved=["test.py"],
            intent_categories=[],
            resolution_strategy="merge",
            success=True,
            validation_result=ValidationResult.PASSED,
        )

        hash_val = pattern_memory._compute_hash(
            conflict_type="textual",
            files_involved=["test.py"],
            intent_categories=[],
        )

        rate = pattern_memory.get_success_rate(hash_val)
        assert rate == 1.0

    def test_success_rate_unknown_returns_zero(self, pattern_memory):
        """Unknown pattern returns 0.0 success rate."""
        rate = pattern_memory.get_success_rate("unknown_hash")
        assert rate == 0.0


class TestPatternMemoryIntegration:
    """Integration tests with PatternDatabase and PatternHasher."""

    def test_uses_similarity_for_suggestions(self, pattern_memory):
        """Uses pattern similarity for suggestions on similar conflicts."""
        from src.learning.pattern_schema import ValidationResult

        # Record resolution for one conflict
        pattern_memory.record_resolution(
            conflict_type="textual",
            files_involved=["src/api/routes.py"],
            intent_categories=["bug_fix"],
            resolution_strategy="merge",
            success=True,
            validation_result=ValidationResult.PASSED,
        )

        # Suggest for similar conflict (same type, similar file)
        suggestion = pattern_memory.suggest_resolution(
            conflict_type="textual",
            files_involved=["src/api/handlers.py"],
            intent_categories=["bug_fix"],
        )

        # Should find a suggestion based on similarity
        assert suggestion is not None

    def test_persistence_across_instances(self, temp_storage):
        """Patterns persist across instances."""
        from src.learning.pattern_memory import ConflictPatternMemory
        from src.learning.pattern_schema import ValidationResult

        # Create first instance and record
        memory1 = ConflictPatternMemory(storage_dir=temp_storage)
        memory1.record_resolution(
            conflict_type="textual",
            files_involved=["persistent.py"],
            intent_categories=[],
            resolution_strategy="merge",
            success=True,
            validation_result=ValidationResult.PASSED,
        )

        # Create second instance
        memory2 = ConflictPatternMemory(storage_dir=temp_storage)

        # Should find the pattern
        suggestion = memory2.suggest_resolution(
            conflict_type="textual",
            files_involved=["persistent.py"],
            intent_categories=[],
        )

        assert suggestion is not None
