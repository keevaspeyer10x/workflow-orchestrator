"""
Tests for pattern hashing logic.

Tests cover:
- Hash computation
- Similarity calculation
- Normalization of file paths
- Edge cases
"""

import pytest


class TestPatternHasherCompute:
    """Tests for computing pattern hashes."""

    def test_compute_hash_returns_string(self):
        """compute_hash returns a string hash."""
        from src.learning.pattern_hasher import PatternHasher

        hasher = PatternHasher()
        hash_val = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["src/api.py"],
            intent_categories=["bug_fix"],
        )

        assert isinstance(hash_val, str)
        assert len(hash_val) > 0

    def test_same_inputs_same_hash(self):
        """Same inputs produce the same hash."""
        from src.learning.pattern_hasher import PatternHasher

        hasher = PatternHasher()
        hash1 = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["src/api.py", "src/utils.py"],
            intent_categories=["feature"],
        )
        hash2 = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["src/api.py", "src/utils.py"],
            intent_categories=["feature"],
        )

        assert hash1 == hash2

    def test_different_types_different_hash(self):
        """Different conflict types produce different hashes."""
        from src.learning.pattern_hasher import PatternHasher

        hasher = PatternHasher()
        hash1 = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["src/api.py"],
            intent_categories=[],
        )
        hash2 = hasher.compute_hash(
            conflict_type="semantic",
            files_involved=["src/api.py"],
            intent_categories=[],
        )

        assert hash1 != hash2

    def test_empty_files_handled(self):
        """Empty file list is handled gracefully."""
        from src.learning.pattern_hasher import PatternHasher

        hasher = PatternHasher()
        hash_val = hasher.compute_hash(
            conflict_type="textual",
            files_involved=[],
            intent_categories=[],
        )

        assert isinstance(hash_val, str)
        assert len(hash_val) > 0


class TestPatternHasherSimilarity:
    """Tests for computing similarity between hashes."""

    def test_identical_hashes_similarity_one(self):
        """Identical hashes have similarity 1.0."""
        from src.learning.pattern_hasher import PatternHasher

        hasher = PatternHasher()
        hash1 = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["src/api.py"],
            intent_categories=["fix"],
        )

        similarity = hasher.compute_similarity(hash1, hash1)
        assert similarity == 1.0

    def test_completely_different_low_similarity(self):
        """Very different conflicts have low similarity."""
        from src.learning.pattern_hasher import PatternHasher

        hasher = PatternHasher()
        hash1 = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["src/api.py"],
            intent_categories=["add_feature"],
        )
        hash2 = hasher.compute_hash(
            conflict_type="dependency",
            files_involved=["package.json", "yarn.lock"],
            intent_categories=["upgrade"],
        )

        similarity = hasher.compute_similarity(hash1, hash2)
        assert similarity < 0.5

    def test_similar_conflicts_high_similarity(self):
        """Similar conflicts have high similarity."""
        from src.learning.pattern_hasher import PatternHasher

        hasher = PatternHasher()
        hash1 = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["src/api.py", "src/utils.py"],
            intent_categories=["bug_fix"],
        )
        hash2 = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["src/api.py", "src/helpers.py"],
            intent_categories=["bug_fix"],
        )

        similarity = hasher.compute_similarity(hash1, hash2)
        assert similarity > 0.5

    def test_similarity_is_symmetric(self):
        """Similarity is symmetric: sim(a,b) == sim(b,a)."""
        from src.learning.pattern_hasher import PatternHasher

        hasher = PatternHasher()
        hash1 = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["a.py"],
            intent_categories=["x"],
        )
        hash2 = hasher.compute_hash(
            conflict_type="semantic",
            files_involved=["b.py"],
            intent_categories=["y"],
        )

        sim_ab = hasher.compute_similarity(hash1, hash2)
        sim_ba = hasher.compute_similarity(hash2, hash1)

        assert sim_ab == sim_ba


class TestPatternHasherNormalization:
    """Tests for file path normalization."""

    def test_normalizes_uuids(self):
        """UUIDs in paths are normalized."""
        from src.learning.pattern_hasher import PatternHasher

        hasher = PatternHasher()
        hash1 = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["uploads/abc12345-def4-5678-9abc-def012345678/file.txt"],
            intent_categories=[],
        )
        hash2 = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["uploads/11122233-4445-5667-7889-9aabbccddeef/file.txt"],
            intent_categories=[],
        )

        # Should be similar because UUIDs are normalized
        similarity = hasher.compute_similarity(hash1, hash2)
        assert similarity > 0.6  # Normalized paths should be quite similar

    def test_normalizes_timestamps(self):
        """Timestamps in paths are normalized."""
        from src.learning.pattern_hasher import PatternHasher

        hasher = PatternHasher()
        hash1 = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["logs/2026-01-01_12-00-00.log"],
            intent_categories=[],
        )
        hash2 = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["logs/2026-12-31_23-59-59.log"],
            intent_categories=[],
        )

        similarity = hasher.compute_similarity(hash1, hash2)
        assert similarity > 0.7

    def test_preserves_directory_structure(self):
        """Directory structure is preserved in hash."""
        from src.learning.pattern_hasher import PatternHasher

        hasher = PatternHasher()
        hash1 = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["src/api/routes.py"],
            intent_categories=[],
        )
        hash2 = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["tests/api/test_routes.py"],
            intent_categories=[],
        )

        # Should be somewhat similar (both in api-related dirs)
        similarity = hasher.compute_similarity(hash1, hash2)
        assert 0.3 < similarity < 0.9


class TestPatternHasherEdgeCases:
    """Edge case tests."""

    def test_empty_intent_categories(self):
        """Empty intent categories are handled."""
        from src.learning.pattern_hasher import PatternHasher

        hasher = PatternHasher()
        hash_val = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["file.py"],
            intent_categories=[],
        )

        assert isinstance(hash_val, str)

    def test_many_files(self):
        """Many files are handled efficiently."""
        from src.learning.pattern_hasher import PatternHasher

        hasher = PatternHasher()
        files = [f"src/module_{i}/file.py" for i in range(100)]

        hash_val = hasher.compute_hash(
            conflict_type="textual",
            files_involved=files,
            intent_categories=["large_refactor"],
        )

        assert isinstance(hash_val, str)

    def test_special_characters_in_paths(self):
        """Special characters in paths are handled."""
        from src.learning.pattern_hasher import PatternHasher

        hasher = PatternHasher()
        hash_val = hasher.compute_hash(
            conflict_type="textual",
            files_involved=["src/my-module/file_v2.py"],
            intent_categories=["update"],
        )

        assert isinstance(hash_val, str)
