# Phase 7 Task 3: Pattern Hasher

## Goal
Create pattern hashing logic in `src/learning/pattern_hasher.py` for identifying similar conflicts.

## Interface

```python
class PatternHasher:
    def compute_hash(conflict: ConflictContext) -> str
    def compute_similarity(hash1: str, hash2: str) -> float
```

## Hash Design

The hash should be "fuzzy" - similar conflicts should produce similar hashes.

Hash factors:
1. Normalized file paths (remove unique identifiers like timestamps, UUIDs)
2. Conflict type
3. Intent categories
4. Code structure patterns (basic: extensions, directory patterns)

## Approach: Locality-Sensitive Hashing (MinHash)

Use MinHash for set similarity:
1. Normalize file paths → set of tokens
2. Extract conflict type → token
3. Extract intent categories → set of tokens
4. Combine into shingles
5. Apply MinHash to generate hash signature

Similarity = Jaccard coefficient of MinHash signatures

## Files
- `src/learning/pattern_hasher.py` (NEW)
- `tests/learning/test_pattern_hasher.py` (NEW)
- `src/learning/__init__.py` (UPDATE)

## Dependencies
- ConflictPattern from task-1 (DONE)
