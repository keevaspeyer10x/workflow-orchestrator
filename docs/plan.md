# Plan: WF-010 Auto-Run Third-Party Reviews

## Overview
Automatically run third-party model reviews when completing REVIEW phase items.

## Implementation

### Changes to `src/cli.py`

1. **REVIEW_ITEM_MAPPING** - Maps workflow item IDs to review types:
   - `security_review` → `security` (Codex)
   - `quality_review` → `quality` (Codex)
   - `architecture_review` → `holistic` (Gemini)

2. **run_auto_review()** - Helper function that:
   - Creates ReviewRouter instance
   - Executes the specified review type
   - Returns (success, notes, error_message) tuple
   - Captures model used, duration, and findings in notes

3. **cmd_complete()** modifications:
   - Checks if item is in REVIEW_ITEM_MAPPING
   - Auto-runs review before completing
   - Blocks if review fails or finds blocking issues
   - Appends review notes to completion notes

### New CLI flag
- `--skip-auto-review` - Bypass auto-review (not recommended)

## Status
✅ Completed
