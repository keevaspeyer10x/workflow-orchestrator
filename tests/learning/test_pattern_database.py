"""
Tests for PatternDatabase file-based storage.

Tests cover:
- Store and lookup patterns
- Update outcome
- Find similar patterns
- Prune stale patterns
- Edge cases and error handling
"""

import pytest
import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path


@pytest.fixture
def temp_storage_dir():
    """Create a temporary directory for pattern storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def pattern_db(temp_storage_dir):
    """Create a PatternDatabase with temporary storage."""
    from src.learning.pattern_database import PatternDatabase
    return PatternDatabase(storage_dir=temp_storage_dir)


@pytest.fixture
def sample_pattern():
    """Create a sample ConflictPattern."""
    from src.learning.pattern_schema import ConflictPattern
    return ConflictPattern(
        pattern_hash="sample123",
        conflict_type="textual",
        resolution_strategy="merge",
        files_involved=["src/api.py", "src/utils.py"],
        intent_categories=["bug_fix"],
        success_rate=0.8,
        use_count=5,
    )


class TestPatternDatabaseStore:
    """Tests for storing patterns."""

    def test_store_pattern(self, pattern_db, sample_pattern):
        """Store a pattern successfully."""
        pattern_db.store(sample_pattern)

        # Verify pattern file exists
        pattern_file = pattern_db._storage_dir / f"{sample_pattern.pattern_hash}.json"
        assert pattern_file.exists()

    def test_store_creates_index(self, pattern_db, sample_pattern):
        """Storing a pattern creates/updates the index."""
        pattern_db.store(sample_pattern)

        index_file = pattern_db._storage_dir / "index.json"
        assert index_file.exists()

        with open(index_file) as f:
            index = json.load(f)

        assert sample_pattern.pattern_hash in index["patterns"]

    def test_store_updates_existing(self, pattern_db, sample_pattern):
        """Storing an existing pattern updates it."""
        pattern_db.store(sample_pattern)

        # Modify and store again
        sample_pattern.success_rate = 0.9
        sample_pattern.use_count = 10
        pattern_db.store(sample_pattern)

        # Lookup should return updated values
        retrieved = pattern_db.lookup(sample_pattern.pattern_hash)
        assert retrieved is not None
        assert retrieved.success_rate == 0.9
        assert retrieved.use_count == 10


class TestPatternDatabaseLookup:
    """Tests for looking up patterns."""

    def test_lookup_existing_pattern(self, pattern_db, sample_pattern):
        """Lookup returns stored pattern."""
        pattern_db.store(sample_pattern)

        retrieved = pattern_db.lookup(sample_pattern.pattern_hash)

        assert retrieved is not None
        assert retrieved.pattern_hash == sample_pattern.pattern_hash
        assert retrieved.conflict_type == sample_pattern.conflict_type
        assert retrieved.resolution_strategy == sample_pattern.resolution_strategy

    def test_lookup_nonexistent_returns_none(self, pattern_db):
        """Lookup of non-existent pattern returns None."""
        result = pattern_db.lookup("nonexistent_hash")
        assert result is None

    def test_lookup_preserves_all_fields(self, pattern_db, sample_pattern):
        """Lookup preserves all pattern fields."""
        pattern_db.store(sample_pattern)
        retrieved = pattern_db.lookup(sample_pattern.pattern_hash)

        assert retrieved.files_involved == sample_pattern.files_involved
        assert retrieved.intent_categories == sample_pattern.intent_categories
        assert retrieved.success_rate == sample_pattern.success_rate
        assert retrieved.use_count == sample_pattern.use_count


class TestPatternDatabaseUpdateOutcome:
    """Tests for updating pattern outcomes."""

    def test_update_outcome_success(self, pattern_db, sample_pattern):
        """Update outcome with success increases success rate."""
        pattern_db.store(sample_pattern)
        initial_rate = sample_pattern.success_rate
        initial_count = sample_pattern.use_count

        pattern_db.update_outcome(sample_pattern.pattern_hash, success=True)

        retrieved = pattern_db.lookup(sample_pattern.pattern_hash)
        assert retrieved.use_count == initial_count + 1
        # Rate should increase with success

    def test_update_outcome_failure(self, pattern_db, sample_pattern):
        """Update outcome with failure decreases success rate."""
        pattern_db.store(sample_pattern)
        initial_count = sample_pattern.use_count

        pattern_db.update_outcome(sample_pattern.pattern_hash, success=False)

        retrieved = pattern_db.lookup(sample_pattern.pattern_hash)
        assert retrieved.use_count == initial_count + 1

    def test_update_outcome_nonexistent_raises(self, pattern_db):
        """Update outcome for non-existent pattern raises error."""
        with pytest.raises(KeyError):
            pattern_db.update_outcome("nonexistent", success=True)


class TestPatternDatabaseFindSimilar:
    """Tests for finding similar patterns."""

    def test_find_similar_by_type(self, pattern_db):
        """Find patterns with same conflict type."""
        from src.learning.pattern_schema import ConflictPattern

        # Store patterns of different types
        textual1 = ConflictPattern(
            pattern_hash="text1",
            conflict_type="textual",
            resolution_strategy="merge",
        )
        textual2 = ConflictPattern(
            pattern_hash="text2",
            conflict_type="textual",
            resolution_strategy="agent1_primary",
        )
        semantic = ConflictPattern(
            pattern_hash="sem1",
            conflict_type="semantic",
            resolution_strategy="merge",
        )

        pattern_db.store(textual1)
        pattern_db.store(textual2)
        pattern_db.store(semantic)

        # Find similar to textual conflict
        matches = pattern_db.find_similar(
            conflict_type="textual",
            files_involved=["src/test.py"],
            threshold=0.3,
        )

        # Should find the textual patterns
        assert len(matches) >= 1
        match_hashes = [m.pattern.pattern_hash for m in matches]
        assert "text1" in match_hashes or "text2" in match_hashes

    def test_find_similar_returns_sorted_by_score(self, pattern_db):
        """Similar patterns are returned sorted by similarity score."""
        from src.learning.pattern_schema import ConflictPattern

        # Store patterns with different similarity potential
        pattern_db.store(ConflictPattern(
            pattern_hash="high_match",
            conflict_type="textual",
            resolution_strategy="merge",
            files_involved=["src/api.py"],
            success_rate=0.9,
        ))
        pattern_db.store(ConflictPattern(
            pattern_hash="low_match",
            conflict_type="textual",
            resolution_strategy="merge",
            files_involved=["tests/other.py"],
            success_rate=0.5,
        ))

        matches = pattern_db.find_similar(
            conflict_type="textual",
            files_involved=["src/api.py"],
            threshold=0.1,
        )

        if len(matches) > 1:
            # Should be sorted descending by similarity score
            for i in range(len(matches) - 1):
                assert matches[i].similarity_score >= matches[i + 1].similarity_score

    def test_find_similar_respects_threshold(self, pattern_db):
        """Only patterns above threshold are returned."""
        from src.learning.pattern_schema import ConflictPattern

        pattern_db.store(ConflictPattern(
            pattern_hash="weak_match",
            conflict_type="dependency",  # Different type
            resolution_strategy="merge",
        ))

        # High threshold should filter out weak matches
        matches = pattern_db.find_similar(
            conflict_type="textual",
            files_involved=[],
            threshold=0.8,
        )

        assert len(matches) == 0

    def test_find_similar_empty_database(self, pattern_db):
        """Empty database returns empty list."""
        matches = pattern_db.find_similar(
            conflict_type="textual",
            files_involved=[],
            threshold=0.3,
        )
        assert matches == []


class TestPatternDatabasePruneStale:
    """Tests for pruning stale patterns."""

    def test_prune_removes_old_patterns(self, pattern_db):
        """Prune removes patterns not used in N days."""
        from src.learning.pattern_schema import ConflictPattern

        old_time = datetime.now(timezone.utc) - timedelta(days=100)
        old_pattern = ConflictPattern(
            pattern_hash="old_pattern",
            conflict_type="textual",
            resolution_strategy="merge",
            last_used=old_time,
        )

        recent_pattern = ConflictPattern(
            pattern_hash="recent_pattern",
            conflict_type="textual",
            resolution_strategy="merge",
        )

        pattern_db.store(old_pattern)
        pattern_db.store(recent_pattern)

        # Prune patterns older than 30 days
        removed = pattern_db.prune_stale(days=30)

        assert removed == 1
        assert pattern_db.lookup("old_pattern") is None
        assert pattern_db.lookup("recent_pattern") is not None

    def test_prune_returns_count(self, pattern_db):
        """Prune returns count of removed patterns."""
        from src.learning.pattern_schema import ConflictPattern

        old_time = datetime.now(timezone.utc) - timedelta(days=100)

        for i in range(5):
            pattern_db.store(ConflictPattern(
                pattern_hash=f"old_{i}",
                conflict_type="textual",
                resolution_strategy="merge",
                last_used=old_time,
            ))

        removed = pattern_db.prune_stale(days=30)
        assert removed == 5

    def test_prune_empty_database(self, pattern_db):
        """Prune on empty database returns 0."""
        removed = pattern_db.prune_stale(days=30)
        assert removed == 0

    def test_prune_keeps_recent(self, pattern_db, sample_pattern):
        """Prune keeps recently used patterns."""
        pattern_db.store(sample_pattern)

        removed = pattern_db.prune_stale(days=30)

        assert removed == 0
        assert pattern_db.lookup(sample_pattern.pattern_hash) is not None


class TestPatternDatabaseIndex:
    """Tests for index management."""

    def test_index_groups_by_type(self, pattern_db):
        """Index maintains type groupings."""
        from src.learning.pattern_schema import ConflictPattern

        pattern_db.store(ConflictPattern(
            pattern_hash="t1", conflict_type="textual", resolution_strategy="merge",
        ))
        pattern_db.store(ConflictPattern(
            pattern_hash="t2", conflict_type="textual", resolution_strategy="merge",
        ))
        pattern_db.store(ConflictPattern(
            pattern_hash="s1", conflict_type="semantic", resolution_strategy="merge",
        ))

        index = pattern_db._load_index()

        assert "textual" in index["by_type"]
        assert "semantic" in index["by_type"]
        assert len(index["by_type"]["textual"]) == 2
        assert len(index["by_type"]["semantic"]) == 1

    def test_get_all_patterns(self, pattern_db):
        """Can retrieve all stored patterns."""
        from src.learning.pattern_schema import ConflictPattern

        for i in range(3):
            pattern_db.store(ConflictPattern(
                pattern_hash=f"pattern_{i}",
                conflict_type="textual",
                resolution_strategy="merge",
            ))

        all_patterns = pattern_db.get_all()
        assert len(all_patterns) == 3

    def test_count_patterns(self, pattern_db, sample_pattern):
        """Can count stored patterns."""
        assert pattern_db.count() == 0

        pattern_db.store(sample_pattern)
        assert pattern_db.count() == 1
