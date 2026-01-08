# Phase 7 Task 4: Pattern Memory Integration

## Goal
Create ConflictPatternMemory class in `src/learning/pattern_memory.py` - the main interface like git rerere for agents.

## Interface

```python
class ConflictPatternMemory:
    def record_resolution(conflict, resolution, outcome) -> None
    def suggest_resolution(conflict) -> Optional[Resolution]
    def get_success_rate(pattern_hash) -> float
```

## Integration Points
- Called by ResolutionPipeline after resolution attempt
- Consulted before generating new candidates

## Uses
- PatternDatabase (task-2) for storage
- PatternHasher (task-3) for similarity matching

## Files
- `src/learning/pattern_memory.py` (NEW)
- `tests/learning/test_pattern_memory.py` (NEW)
