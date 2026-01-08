"""
Pattern database for file-based storage of conflict patterns.

Provides persistent storage and retrieval of conflict patterns
using JSON files in .claude/patterns/ directory.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .pattern_schema import ConflictPattern, PatternMatch, PatternState

logger = logging.getLogger(__name__)


class PatternDatabase:
    """
    File-based storage for conflict patterns.

    Stores patterns as individual JSON files with an index for fast lookups.

    Storage structure:
    - .claude/patterns/
      - index.json (pattern metadata and type groupings)
      - {pattern_hash}.json (full pattern data)
    """

    DEFAULT_STORAGE_DIR = Path(".claude/patterns")

    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize the pattern database.

        Args:
            storage_dir: Directory for pattern storage (default: .claude/patterns)
        """
        self._storage_dir = storage_dir or self.DEFAULT_STORAGE_DIR
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self._storage_dir / "index.json"

        # Ensure index exists
        if not self._index_file.exists():
            self._save_index({"patterns": {}, "by_type": {}})

    def store(self, pattern: ConflictPattern) -> None:
        """
        Store a pattern in the database.

        If pattern already exists, it will be updated.

        Args:
            pattern: The pattern to store
        """
        # Save pattern file
        pattern_file = self._storage_dir / f"{pattern.pattern_hash}.json"
        with open(pattern_file, "w") as f:
            json.dump(pattern.to_dict(), f, indent=2)

        # Update index
        index = self._load_index()

        # Add/update pattern entry
        index["patterns"][pattern.pattern_hash] = {
            "type": pattern.conflict_type,
            "files": pattern.files_involved[:3],  # First 3 files for preview
            "strategy": pattern.resolution_strategy,
            "success_rate": pattern.success_rate,
            "updated": datetime.now(timezone.utc).isoformat(),
        }

        # Update type grouping
        if pattern.conflict_type not in index["by_type"]:
            index["by_type"][pattern.conflict_type] = []

        if pattern.pattern_hash not in index["by_type"][pattern.conflict_type]:
            index["by_type"][pattern.conflict_type].append(pattern.pattern_hash)

        self._save_index(index)
        logger.debug(f"Stored pattern: {pattern.pattern_hash}")

    def lookup(self, pattern_hash: str) -> Optional[ConflictPattern]:
        """
        Look up a pattern by its hash.

        Args:
            pattern_hash: The pattern hash to look up

        Returns:
            The pattern if found, None otherwise
        """
        pattern_file = self._storage_dir / f"{pattern_hash}.json"

        if not pattern_file.exists():
            return None

        try:
            with open(pattern_file) as f:
                data = json.load(f)
            return ConflictPattern.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error loading pattern {pattern_hash}: {e}")
            return None

    def find_similar(
        self,
        conflict_type: str,
        files_involved: list[str],
        threshold: float = 0.3,
    ) -> list[PatternMatch]:
        """
        Find patterns similar to a given conflict.

        Args:
            conflict_type: Type of conflict to match
            files_involved: Files involved in the conflict
            threshold: Minimum similarity score (0.0 to 1.0)

        Returns:
            List of PatternMatch objects, sorted by similarity descending
        """
        index = self._load_index()
        matches: list[PatternMatch] = []

        # Get candidate patterns (same type gets highest priority)
        candidates = set()

        # Same type candidates
        if conflict_type in index["by_type"]:
            candidates.update(index["by_type"][conflict_type])

        # Also consider all patterns for file matching
        candidates.update(index["patterns"].keys())

        for pattern_hash in candidates:
            pattern = self.lookup(pattern_hash)
            if pattern is None:
                continue

            # Skip deprecated patterns
            if pattern.state == PatternState.DEPRECATED:
                continue

            # Calculate similarity
            score, matched_on = self._calculate_similarity(
                pattern, conflict_type, files_involved
            )

            if score >= threshold:
                matches.append(PatternMatch(
                    pattern=pattern,
                    similarity_score=score,
                    matched_on=matched_on,
                    suggested_strategy=pattern.resolution_strategy,
                ))

        # Sort by similarity descending
        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        return matches

    def _calculate_similarity(
        self,
        pattern: ConflictPattern,
        conflict_type: str,
        files_involved: list[str],
    ) -> tuple[float, list[str]]:
        """
        Calculate similarity between a pattern and conflict characteristics.

        Returns:
            Tuple of (similarity_score, matched_on_factors)
        """
        score = 0.0
        matched_on = []

        # Type matching (weight: 0.4)
        if pattern.conflict_type == conflict_type:
            score += 0.4
            matched_on.append("conflict_type")

        # File pattern matching (weight: 0.3)
        if pattern.files_involved and files_involved:
            file_overlap = self._calculate_file_overlap(
                pattern.files_involved, files_involved
            )
            score += 0.3 * file_overlap
            if file_overlap > 0:
                matched_on.append("files")

        # Success rate bonus (weight: 0.2)
        # Patterns with higher success rates are more relevant
        score += 0.2 * pattern.success_rate
        if pattern.success_rate > 0.5:
            matched_on.append("high_success_rate")

        # State bonus (weight: 0.1)
        # Active patterns get a bonus
        if pattern.state == PatternState.ACTIVE:
            score += 0.1
            matched_on.append("active_state")

        return min(1.0, score), matched_on

    def _calculate_file_overlap(
        self,
        pattern_files: list[str],
        conflict_files: list[str],
    ) -> float:
        """
        Calculate overlap between file lists.

        Uses Jaccard similarity on directory prefixes.
        """
        if not pattern_files or not conflict_files:
            return 0.0

        # Extract directory patterns
        pattern_dirs = {Path(f).parent.as_posix() for f in pattern_files}
        conflict_dirs = {Path(f).parent.as_posix() for f in conflict_files}

        intersection = pattern_dirs & conflict_dirs
        union = pattern_dirs | conflict_dirs

        if not union:
            return 0.0

        return len(intersection) / len(union)

    def update_outcome(self, pattern_hash: str, success: bool) -> None:
        """
        Update a pattern's outcome after it was applied.

        Args:
            pattern_hash: The pattern to update
            success: Whether the resolution was successful

        Raises:
            KeyError: If pattern not found
        """
        pattern = self.lookup(pattern_hash)
        if pattern is None:
            raise KeyError(f"Pattern not found: {pattern_hash}")

        pattern.record_outcome(success)
        self.store(pattern)

        logger.debug(f"Updated pattern {pattern_hash} outcome: success={success}")

    def prune_stale(self, days: int) -> int:
        """
        Remove patterns that haven't been used in N days.

        Args:
            days: Number of days after which patterns are considered stale

        Returns:
            Number of patterns removed
        """
        index = self._load_index()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        removed = 0

        patterns_to_remove = []

        for pattern_hash in list(index["patterns"].keys()):
            pattern = self.lookup(pattern_hash)
            if pattern is None:
                patterns_to_remove.append(pattern_hash)
                continue

            if pattern.last_used and pattern.last_used < cutoff:
                patterns_to_remove.append(pattern_hash)

        for pattern_hash in patterns_to_remove:
            self._remove_pattern(pattern_hash)
            removed += 1

        logger.info(f"Pruned {removed} stale patterns (older than {days} days)")
        return removed

    def _remove_pattern(self, pattern_hash: str) -> None:
        """Remove a pattern from storage and index."""
        # Remove file
        pattern_file = self._storage_dir / f"{pattern_hash}.json"
        if pattern_file.exists():
            pattern_file.unlink()

        # Update index
        index = self._load_index()

        if pattern_hash in index["patterns"]:
            pattern_type = index["patterns"][pattern_hash].get("type")
            del index["patterns"][pattern_hash]

            # Remove from type grouping
            if pattern_type and pattern_type in index["by_type"]:
                if pattern_hash in index["by_type"][pattern_type]:
                    index["by_type"][pattern_type].remove(pattern_hash)

        self._save_index(index)

    def get_all(self) -> list[ConflictPattern]:
        """Get all stored patterns."""
        index = self._load_index()
        patterns = []

        for pattern_hash in index["patterns"]:
            pattern = self.lookup(pattern_hash)
            if pattern:
                patterns.append(pattern)

        return patterns

    def count(self) -> int:
        """Get count of stored patterns."""
        index = self._load_index()
        return len(index["patterns"])

    def _load_index(self) -> dict:
        """Load the pattern index."""
        if not self._index_file.exists():
            return {"patterns": {}, "by_type": {}}

        try:
            with open(self._index_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading index: {e}")
            return {"patterns": {}, "by_type": {}}

    def _save_index(self, index: dict) -> None:
        """Save the pattern index."""
        with open(self._index_file, "w") as f:
            json.dump(index, f, indent=2)
