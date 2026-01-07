# Test Cases: CORE-010 & CORE-011

## Engine Tests (tests/test_engine.py)

### get_skipped_items()

| ID | Test Case | Input | Expected Output |
|----|-----------|-------|-----------------|
| E1 | No skipped items | Phase with all completed items | Empty list `[]` |
| E2 | One skipped item | Phase with one skipped item, reason="Not applicable" | `[("item_id", "Not applicable")]` |
| E3 | Multiple skipped items | Phase with 2 skipped items | List with both items and reasons |
| E4 | Missing skip reason | Skipped item with None reason | `[("item_id", "No reason provided")]` |
| E5 | Invalid phase ID | Non-existent phase_id | Empty list `[]` |
| E6 | No active workflow | state=None | Empty list `[]` |

### get_all_skipped_items()

| ID | Test Case | Input | Expected Output |
|----|-----------|-------|-----------------|
| E7 | No skips anywhere | Workflow with no skipped items | Empty dict `{}` |
| E8 | Skips in one phase | Skip in PLAN only | `{"PLAN": [("item", "reason")]}` |
| E9 | Skips in multiple phases | Skips in PLAN and VERIFY | Dict with both phases |
| E10 | No active workflow | state=None | Empty dict `{}` |

### get_item_definition()

| ID | Test Case | Input | Expected Output |
|----|-----------|-------|-----------------|
| E11 | Item exists | Valid item_id | ChecklistItemDef object |
| E12 | Item not found | Unknown item_id | None |
| E13 | No workflow def | workflow_def=None | None |

### get_workflow_summary()

| ID | Test Case | Input | Expected Output |
|----|-----------|-------|-----------------|
| E14 | Mixed statuses | Phase with 2 completed, 1 skipped | `{"completed": 2, "skipped": 1, "total": 3}` |
| E15 | All completed | Phase with all completed | `{"completed": 3, "skipped": 0, "total": 3}` |
| E16 | No active workflow | state=None | Empty dict `{}` |

## CLI Tests (tests/test_cli.py)

### cmd_skip() Enhanced Output

| ID | Test Case | Verification |
|----|-----------|--------------|
| C1 | Skip shows separator | Output contains "=" * 60 |
| C2 | Skip shows item ID | Output contains "SKIPPING: {item_id}" |
| C3 | Skip shows reason | Output contains "Reason: {reason}" |
| C4 | Skip shows description | Output contains item description if available |

### cmd_advance() Shows Skipped Items

| ID | Test Case | Verification |
|----|-----------|--------------|
| C5 | Shows skipped count | Output contains "completed with N skipped item(s)" |
| C6 | Lists skipped items | Output contains each skipped item_id and reason |
| C7 | No skips, no extra output | Output does not mention skipped if none exist |

### cmd_finish() Completion Summary

| ID | Test Case | Verification |
|----|-----------|--------------|
| C8 | Shows task description | Output contains task from state |
| C9 | Shows duration | Output contains formatted duration |
| C10 | Shows phase summary | Output contains completed/skipped counts per phase |
| C11 | Shows skipped items list | Output contains all skipped items with reasons |
| C12 | Shows next steps prompt | Output contains PR suggestion and follow-up prompts |
| C13 | Handles missing times | Duration shows "N/A" if times unavailable |

## Helper Function Tests

### format_duration()

| ID | Test Case | Input | Expected Output |
|----|-----------|-------|-----------------|
| H1 | Hours and minutes | timedelta(hours=2, minutes=15) | "2h 15m" |
| H2 | Minutes only | timedelta(minutes=45) | "45m" |
| H3 | Less than a minute | timedelta(seconds=30) | "< 1m" |
| H4 | Zero duration | timedelta(0) | "< 1m" |

## Integration Tests

| ID | Test Case | Verification |
|----|-----------|--------------|
| I1 | Full workflow with skips | Skip items, advance, finish - verify all output |
| I2 | Workflow with no skips | Complete all items, finish - verify no skip mentions |
