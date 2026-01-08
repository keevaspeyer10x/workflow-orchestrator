# Phase 7 Task 1: Pattern Memory Schema

## Goal
Create data models for conflict pattern memory in `src/learning/pattern_schema.py`

## Models to Create

### 1. ConflictPattern
Records a conflict pattern with its characteristics and resolution history.

**Fields:**
- `pattern_hash: str` - Computed from conflict characteristics
- `conflict_type: str` - Type: textual, semantic, dependency, etc.
- `files_involved: list[str]` - File patterns (normalized)
- `intent_categories: list[str]` - Extracted intent categories
- `resolution_strategy: str` - Successful strategy: agent1_primary, merge, etc.
- `success_rate: float` - 0.0 to 1.0
- `last_used: datetime` - When pattern was last matched
- `use_count: int` - Number of times applied
- `created_at: datetime` - When first recorded
- `confidence: float` - Current confidence level (for lifecycle)

### 2. PatternMatch
Result of matching a conflict to known patterns.

**Fields:**
- `pattern: ConflictPattern` - The matched pattern
- `similarity_score: float` - How closely it matches (0.0 to 1.0)
- `matched_on: list[str]` - What factors contributed to match
- `suggested_strategy: str` - Strategy to try based on pattern

### 3. ResolutionOutcome
Success/failure record for a pattern application.

**Fields:**
- `pattern_hash: str` - Pattern that was applied
- `conflict_id: str` - Unique ID of the conflict
- `success: bool` - Whether resolution succeeded
- `strategy_used: str` - Actual strategy applied
- `validation_result: str` - PASSED, FAILED, PARTIAL
- `timestamp: datetime` - When outcome was recorded
- `duration_seconds: float` - Time to resolve

## Implementation Plan

1. Create `src/learning/pattern_schema.py` with:
   - PatternState enum (ACTIVE, SUGGESTING, DORMANT, DEPRECATED)
   - ConflictPattern dataclass
   - PatternMatch dataclass
   - ResolutionOutcome dataclass
   - Helper functions for serialization/deserialization

2. Create `tests/learning/test_pattern_schema.py` with:
   - Unit tests for each dataclass
   - Serialization/deserialization tests
   - Pattern state transition tests
   - Edge case tests

## Files to Create/Modify
- `src/learning/pattern_schema.py` (NEW)
- `tests/learning/test_pattern_schema.py` (NEW)
- `src/learning/__init__.py` (UPDATE - add exports)

## Dependencies
None - this is the first task in Phase 7.

## Risks
- Schema might need adjustment as we implement pattern database (task-2)
- Keep design flexible for future extensions
