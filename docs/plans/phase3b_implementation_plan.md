# Phase 3b Implementation Plan: Two-Tier Feedback System

## Overview
Split Phase 3a's single-file feedback system into a two-tier architecture with anonymization and sync capabilities.

## Design Decisions (Approved)
- **Migration**: Auto-split on first run (seamless upgrade)
- **Sync Target**: GitHub Gist (simple, free, version-controlled)
- **Hash Algorithm**: SHA256 (secure, irreversible)
- **Sync Default**: Opt-in enabled (developer is solo user)

## Architecture

### File Structure
```
.workflow_feedback.jsonl              # Phase 3a (legacy, migrated automatically)
.workflow_tool_feedback.jsonl         # Phase 3b - anonymized, shareable
.workflow_process_feedback.jsonl      # Phase 3b - private, local-only
```

### Data Flow
```
Workflow Complete
    ↓
capture_feedback()
    ↓
├─→ extract_tool_data()    → anonymize() → .workflow_tool_feedback.jsonl
└─→ extract_process_data()             → .workflow_process_feedback.jsonl
    ↓
review (--tool / --process / both)
    ↓
sync (tool feedback only)
    ↓
GitHub Gist (central aggregation)
```

## Implementation Tasks

### Task 1: Add Migration Logic
**File**: `src/cli.py`
**Function**: `migrate_legacy_feedback(working_dir)`

**Logic**:
1. Check if `.workflow_feedback.jsonl` exists and new files don't
2. Read legacy entries
3. For each entry, split into:
   - Tool feedback: Hash workflow_id, strip repo/task, detect repo_type
   - Process feedback: Keep all original data
4. Write to new files: `.workflow_tool_feedback.jsonl` + `.workflow_process_feedback.jsonl`
5. Rename legacy file to `.workflow_feedback.jsonl.migrated` (backup)
6. Print migration summary

**Call site**: Beginning of `cmd_feedback_capture()` and `cmd_feedback_review()`

### Task 2: Refactor `cmd_feedback_capture()`
**File**: `src/cli.py:3863-4044`

**Changes**:
1. Run migration check at start
2. Split feedback extraction into two functions:
   - `extract_tool_feedback()` - Phase timings, items skipped, orchestrator errors, reviews status
   - `extract_process_feedback()` - Task, repo, learnings, challenges, project errors
3. Add `anonymize_tool_feedback()` helper:
   - Hash workflow_id with SHA256
   - Strip repo URL (but detect repo_type: python/javascript/go/rust)
   - Remove task description
   - Keep: timestamp, version, repo_type, phases, duration, tool metrics
4. Save to two files instead of one

**Signature**:
```python
def extract_tool_feedback(state, log_events) -> dict
def extract_process_feedback(state, log_events) -> dict
def anonymize_tool_feedback(tool_data) -> dict
def detect_repo_type(working_dir) -> str  # python/js/go/rust
```

### Task 3: Refactor `cmd_feedback_review()`
**File**: `src/cli.py:4046-4254`

**Changes**:
1. Run migration check at start
2. Add `--tool` and `--process` flags (default: both)
3. Update file loading logic:
   - `--tool`: Load `.workflow_tool_feedback.jsonl`
   - `--process`: Load `.workflow_process_feedback.jsonl`
   - Default: Load both files
4. Adjust pattern detection for tool vs process feedback:
   - Tool patterns: Items skipped, orchestrator errors, phase timings, review success
   - Process patterns: Project errors, learnings, challenges
5. Update output format to show "Tool Feedback" vs "Process Feedback" sections

### Task 4: Implement `cmd_feedback_sync()`
**File**: `src/cli.py` (new function)

**Signature**:
```python
def cmd_feedback_sync(args):
    """Upload anonymized tool feedback to GitHub Gist."""
```

**Logic**:
1. Check opt-in status: `orchestrator config get feedback_sync` (default: true)
2. Load `.workflow_tool_feedback.jsonl`
3. Filter: Only entries without `synced_at` field
4. Verify anonymization (double-check no repo/task/code)
5. Create/update GitHub Gist:
   - Gist name: `workflow-orchestrator-feedback-<username>`
   - File: `tool_feedback.jsonl`
   - Append new entries to existing content
6. Mark entries as synced: Add `synced_at` timestamp to local file
7. Print sync summary

**Flags**:
- `--dry-run`: Show what would be uploaded without uploading
- `--force`: Re-sync all entries (remove synced_at timestamps)
- `--status`: Show sync statistics

**GitHub API**:
```python
import os
import requests

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')  # User must set
GIST_API = 'https://api.github.com/gists'

# Create gist
response = requests.post(GIST_API, headers={'Authorization': f'token {GITHUB_TOKEN}'},
                        json={'files': {'tool_feedback.jsonl': {'content': data}},
                              'description': 'workflow-orchestrator tool feedback',
                              'public': False})
```

### Task 5: Add CLI Argument Parsers
**File**: `src/cli.py` (main() function)

**New subcommands**:
```python
# Existing: orchestrator feedback (capture)
feedback_parser = subparsers.add_parser('feedback', ...)
feedback_parser.add_argument('--interactive', action='store_true')
# No changes needed to capture command

# Update: orchestrator feedback review
review_parser.add_subparser('review', ...)
review_parser.add_argument('--tool', action='store_true', help='Review tool feedback only')
review_parser.add_argument('--process', action='store_true', help='Review process feedback only')
review_parser.add_argument('--days', type=int, default=7)
review_parser.add_argument('--all', action='store_true')
review_parser.add_argument('--suggest', action='store_true')

# New: orchestrator feedback sync
sync_parser = subparsers.add_parser('sync', ...)
sync_parser.add_argument('--dry-run', action='store_true')
sync_parser.add_argument('--force', action='store_true')
sync_parser.add_argument('--status', action='store_true')
```

### Task 6: Helper Functions

**Anonymization**:
```python
def anonymize_tool_feedback(feedback: dict) -> dict:
    """Remove PII from tool feedback."""
    import hashlib

    # Hash workflow_id
    if 'workflow_id' in feedback:
        hashed = hashlib.sha256(feedback['workflow_id'].encode()).hexdigest()
        feedback['workflow_id_hash'] = hashed
        del feedback['workflow_id']

    # Remove repo URL (keep type only)
    if 'repo' in feedback:
        del feedback['repo']

    # Remove task description
    if 'task' in feedback:
        del feedback['task']

    return feedback
```

**Repo Type Detection**:
```python
def detect_repo_type(working_dir: Path) -> str:
    """Detect repository language type."""
    if (working_dir / 'setup.py').exists() or (working_dir / 'pyproject.toml').exists():
        return 'python'
    elif (working_dir / 'package.json').exists():
        return 'javascript'
    elif (working_dir / 'go.mod').exists():
        return 'go'
    elif (working_dir / 'Cargo.toml').exists():
        return 'rust'
    return 'unknown'
```

**Migration**:
```python
def migrate_legacy_feedback(working_dir: Path) -> bool:
    """Migrate Phase 3a feedback to Phase 3b two-tier system."""
    legacy_file = working_dir / '.workflow_feedback.jsonl'
    tool_file = working_dir / '.workflow_tool_feedback.jsonl'
    process_file = working_dir / '.workflow_process_feedback.jsonl'

    # Skip if already migrated
    if not legacy_file.exists() or (tool_file.exists() and process_file.exists()):
        return False

    print("Migrating feedback to two-tier system...")

    # Read legacy entries
    with open(legacy_file) as f:
        entries = [json.loads(line) for line in f]

    # Split and save
    for entry in entries:
        tool_data = extract_tool_feedback_from_entry(entry)
        process_data = extract_process_feedback_from_entry(entry)

        with open(tool_file, 'a') as f:
            f.write(json.dumps(anonymize_tool_feedback(tool_data)) + '\n')

        with open(process_file, 'a') as f:
            f.write(json.dumps(process_data) + '\n')

    # Backup legacy file
    legacy_file.rename(working_dir / '.workflow_feedback.jsonl.migrated')

    print(f"✓ Migrated {len(entries)} entries to two-tier system")
    return True
```

### Task 7: Update Documentation
**File**: `CLAUDE.md`

Add section:
```markdown
## Feedback System (Two-Tier)

The orchestrator collects two types of feedback:

1. **Tool Feedback** (`.workflow_tool_feedback.jsonl`) - About orchestrator itself
   - Anonymized (workflow_id hashed, no repo/task names)
   - Optionally synced to maintainer
   - Helps improve orchestrator features

2. **Process Feedback** (`.workflow_process_feedback.jsonl`) - About your project
   - Private, stays local
   - Contains learnings, challenges, project-specific data

Commands:
- `orchestrator feedback` - Capture feedback (automatic in LEARN phase)
- `orchestrator feedback review` - Analyze patterns
- `orchestrator feedback review --tool` - Review tool patterns only
- `orchestrator feedback review --process` - Review process patterns only
- `orchestrator feedback sync` - Upload anonymized tool feedback
- `orchestrator feedback sync --dry-run` - Preview what would be uploaded
- `orchestrator config set feedback_sync false` - Disable sync
```

## Testing Strategy

### Unit Tests (New)
**File**: `tests/test_feedback.py` (create)

Tests:
1. `test_anonymize_tool_feedback()` - Verify workflow_id hashed, repo/task removed
2. `test_detect_repo_type()` - Verify language detection
3. `test_migrate_legacy_feedback()` - Verify split and backup
4. `test_extract_tool_feedback()` - Verify tool data extraction
5. `test_extract_process_feedback()` - Verify process data extraction
6. `test_verify_no_pii_in_tool_feedback()` - Security test

### Manual Testing
1. **Migration**: Run on repo with existing `.workflow_feedback.jsonl`
2. **Capture**: Run `orchestrator feedback` and verify two files created
3. **Review**: Test `--tool`, `--process`, and default (both)
4. **Sync**: Test `--dry-run` shows correct data
5. **Anonymization**: Manually inspect `.workflow_tool_feedback.jsonl` - no PII

### Integration Testing
1. Complete a full workflow → feedback capture → review → sync
2. Verify legacy migration happens only once
3. Verify process feedback never uploaded in sync

## File Changes Summary

**Modified**:
- `src/cli.py` - Refactor capture/review, add sync command

**Created**:
- `docs/plans/phase3b_implementation_plan.md` - This file
- `tests/test_feedback.py` - Unit tests

**Auto-generated** (by migration):
- `.workflow_feedback.jsonl.migrated` - Backup of legacy file

## Success Criteria

- [ ] Legacy feedback auto-migrates to two-tier system
- [ ] Tool feedback properly anonymized (no repo/task, workflow_id hashed)
- [ ] Process feedback contains full project context
- [ ] `orchestrator feedback review --tool` shows tool patterns
- [ ] `orchestrator feedback review --process` shows process patterns
- [ ] `orchestrator feedback sync` uploads to GitHub Gist
- [ ] `orchestrator feedback sync --dry-run` shows preview
- [ ] Sync respects opt-in/opt-out config
- [ ] All tests pass
- [ ] Documentation updated

## Rollout Plan

1. **Phase 3b.1**: Migration + Split (Tasks 1-2)
2. **Phase 3b.2**: Review Updates (Task 3)
3. **Phase 3b.3**: Sync Implementation (Task 4)
4. **Phase 3b.4**: Testing + Documentation (Tasks 6-7)

## Risks & Mitigations

**Risk 1**: Migration fails on malformed legacy data
- Mitigation: Wrap in try/except, skip malformed entries, log warnings

**Risk 2**: GitHub API rate limits on sync
- Mitigation: Track sync timestamps, batch uploads, use conditional requests

**Risk 3**: Accidental PII leakage in tool feedback
- Mitigation: Double verification in sync command, --dry-run preview, unit tests

**Risk 4**: User has GITHUB_TOKEN not set
- Mitigation: Clear error message, fallback to manual upload instructions
