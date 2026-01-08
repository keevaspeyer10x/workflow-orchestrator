# Phase 7 Task 2: Pattern Database

## Goal
Create PatternDatabase class in `src/learning/pattern_database.py` for file-based storage of conflict patterns.

## Interface

```python
class PatternDatabase:
    def store(pattern: ConflictPattern) -> None
    def lookup(pattern_hash: str) -> Optional[ConflictPattern]
    def find_similar(conflict: ConflictContext, threshold: float) -> list[PatternMatch]
    def update_outcome(pattern_hash: str, success: bool) -> None
    def prune_stale(days: int) -> int  # Remove unused patterns
```

## Storage Design

- Directory: `.claude/patterns/`
- One JSON file per pattern: `{pattern_hash}.json`
- Index file for fast lookups: `index.json`

### Index Structure
```json
{
  "patterns": {
    "hash1": {"type": "textual", "files": ["*.py"], "updated": "..."},
    "hash2": {"type": "semantic", "files": ["*.ts"], "updated": "..."}
  },
  "by_type": {
    "textual": ["hash1", "hash3"],
    "semantic": ["hash2"]
  }
}
```

## Implementation Plan

1. Create `src/learning/pattern_database.py`:
   - PatternDatabase class
   - Index management for fast lookups
   - File-based storage with JSON serialization
   - Similarity matching using pattern hasher (basic for now)
   - Stale pattern pruning

2. Create `tests/learning/test_pattern_database.py`:
   - Store and lookup tests
   - Update outcome tests
   - Find similar tests
   - Prune stale tests
   - Edge cases (empty, not found)

## Files to Create/Modify
- `src/learning/pattern_database.py` (NEW)
- `tests/learning/test_pattern_database.py` (NEW)
- `src/learning/__init__.py` (UPDATE - add PatternDatabase export)

## Dependencies
- Requires ConflictPattern from task-1 (DONE)

## Notes
- For find_similar, use basic matching on conflict_type and files for now
- Full pattern hasher integration will come in task-3
