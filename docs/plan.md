# CORE-023-P3: Conflict Resolution - Learning & Config

## Overview

Add learning from conflict patterns and configuration support to the conflict resolution system.

## Deliverables

### 1. Conflict Learning Module (`src/resolution/learning.py`)

Create a module that:
- Aggregates conflict resolution data from `.workflow_log.jsonl`
- Identifies patterns (e.g., files with frequent conflicts)
- Generates summaries for the LEARN phase
- Suggests roadmap additions when patterns detected

**Key Functions:**
- `get_conflict_summary(working_dir)` - Returns conflict stats for LEARN phase
- `get_conflict_patterns(working_dir, session_window)` - Identifies repeat offenders
- `suggest_roadmap_additions(patterns)` - Generates ROADMAP suggestions

### 2. LEARN Phase Integration

Modify the LEARN phase to surface conflict data:
- Add conflict summary output during `document_learnings` item
- Show: most conflicted files, strategies used, resolution success rate
- Display suggestions based on patterns (e.g., "src/cli.py had conflicts 5 times")

### 3. Auto-add Roadmap Suggestions

When conflict patterns are detected:
- Format suggestion as markdown (consistent with existing ROADMAP.md format)
- Append to ROADMAP.md under "## Conflict-Related Suggestions"
- Log the action with a message like "Added suggestion to ROADMAP.md: ..."
- Inform user (don't ask) - this is an automatic learning action

### 4. Extended Config File Support (`src/user_config.py`)

Extend UserConfig to support:
- Per-file resolution policies (e.g., "package-lock.json" -> "regenerate")
- Additional sensitive file globs (override defaults)
- LLM enable/disable flag (already exists, verify)

**Config schema addition:**
```yaml
resolution:
  file_policies:
    "package-lock.json": "regenerate"
    "*.lock": "theirs"
    ".env*": "ours"
```

### 5. Tests (`tests/test_conflict_learning.py`)

Test coverage for:
- `get_conflict_summary()` - returns correct stats from log
- `get_conflict_patterns()` - identifies repeat conflict files
- `suggest_roadmap_additions()` - generates correct markdown
- `UserConfig.get_file_policy()` - returns correct policy for path
- Integration with LEARN phase

### 6. Documentation Update (CLAUDE.md)

Add section on:
- Configuration options for conflict resolution
- How conflict learning works
- Per-file resolution policies

## Implementation Order

1. Extend `UserConfig` with per-file policies
2. Create `src/resolution/learning.py`
3. Add roadmap suggestion logic
4. Integrate with LEARN phase (CLI output)
5. Write tests
6. Update CLAUDE.md

## Files to Modify/Create

| File | Action |
|------|--------|
| `src/user_config.py` | Extend with file_policies |
| `src/resolution/learning.py` | Create new module |
| `src/resolution/__init__.py` | Export new functions |
| `tests/test_conflict_learning.py` | Create new test file |
| `CLAUDE.md` | Add configuration docs |

## Dependencies

- Existing `src/resolution/logger.py` (log format)
- Existing `src/user_config.py` (config patterns)
- Existing `src/schema.py` (EventType.CONFLICT_RESOLVED)
