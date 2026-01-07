# Implementation Plan: CORE-010 & CORE-011

## Overview

Implement two related features that improve visibility and accountability at workflow skip/completion:

1. **CORE-010: Enhanced Skip Visibility** - Make skipped items more visible to force deliberate consideration
2. **CORE-011: Workflow Completion Summary & Next Steps** - Show comprehensive summary and prompt for next steps

## Implementation Steps

### Phase 1: Engine Methods (src/engine.py)

Add three new methods to `WorkflowEngine`:

1. **`get_skipped_items(phase_id: str) -> list[tuple[str, str]]`**
   - Returns list of (item_id, skip_reason) for skipped items in a phase
   - Used by cmd_advance to show skipped items from completed phase

2. **`get_all_skipped_items() -> dict[str, list[tuple[str, str]]]`**
   - Returns all skipped items grouped by phase
   - Used by cmd_finish for full summary

3. **`get_item_definition(item_id: str) -> Optional[ChecklistItemDef]`**
   - Gets the workflow definition for an item by ID
   - Used by cmd_skip to show item description/implications

4. **`get_workflow_summary() -> dict`**
   - Returns summary of items per phase (completed, skipped, total)
   - Used by cmd_finish for completion summary

### Phase 2: CLI Updates (src/cli.py)

1. **Update `cmd_skip()`**:
   - Add enhanced output showing item being skipped with visual separator
   - Show item description (from definition) if available
   - Display "Implications" section

2. **Update `cmd_advance()`**:
   - After successful advance, show skipped items from the completed phase
   - Format: `Phase X completed with N skipped item(s):`

3. **Update `cmd_finish()`**:
   - Add `print_completion_summary()` function:
     - Task description
     - Duration (if start/end times available)
     - Phase summary table (completed/skipped/total per phase)
     - Skipped items list
   - Add `print_next_steps_prompt()` function:
     - Suggest creating PR
     - Suggest continuing discussion
     - Prompt for next actions

### Phase 3: Helper Functions

1. **`format_duration(timedelta) -> str`**
   - Format duration as "Xh Ym" or "Xm Ys"

2. **`get_pr_title(state) -> str`**
   - Generate suggested PR title from task description

## Files to Modify

| File | Changes |
|------|---------|
| `src/engine.py` | Add 4 methods: `get_skipped_items`, `get_all_skipped_items`, `get_item_definition`, `get_workflow_summary` |
| `src/cli.py` | Update `cmd_skip`, `cmd_advance`, `cmd_finish`; add helper functions |
| `tests/test_engine.py` | Add tests for new engine methods |
| `tests/test_cli.py` | Add tests for CLI output changes |

## Test Cases

### Engine Tests
- `test_get_skipped_items_returns_empty_for_no_skips`
- `test_get_skipped_items_returns_skipped_with_reasons`
- `test_get_all_skipped_items_groups_by_phase`
- `test_get_item_definition_finds_item`
- `test_get_item_definition_returns_none_for_unknown`
- `test_get_workflow_summary_counts_correctly`

### CLI Tests
- `test_cmd_skip_shows_enhanced_output`
- `test_cmd_advance_shows_skipped_items`
- `test_cmd_finish_shows_completion_summary`
- `test_cmd_finish_shows_next_steps_prompt`
- `test_format_duration`

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing CLI output parsing | Low | Medium | Changes are additive, existing success/error indicators unchanged |
| Performance with many skipped items | Low | Low | Summary is O(n) where n = items, typical workflows have <50 items |
| Duration calculation edge cases | Medium | Low | Handle None start/end times gracefully |

## Dependencies

- No external dependencies
- Uses existing `ItemStatus.SKIPPED` enum
- Uses existing `skip_reason` field on `ItemState`
