# Test Cases: Phase 3b Two-Tier Feedback System

## Unit Tests

### Test Suite: Anonymization

#### TC-1.1: Anonymize Tool Feedback - Basic
**Function**: `anonymize_tool_feedback()`

**Input**:
```python
{
    'timestamp': '2026-01-11T10:00:00Z',
    'workflow_id': 'wf_abc123',
    'task': 'Add user authentication',
    'repo': 'https://github.com/user/private-repo',
    'orchestrator_version': '2.6.0',
    'phases': {'PLAN': 300, 'EXECUTE': 600}
}
```

**Expected Output**:
```python
{
    'timestamp': '2026-01-11T10:00:00Z',
    'workflow_id_hash': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',  # SHA256 of 'wf_abc123'
    'orchestrator_version': '2.6.0',
    'phases': {'PLAN': 300, 'EXECUTE': 600}
}
```

**Assertions**:
- `workflow_id` removed, `workflow_id_hash` added
- `task` removed
- `repo` removed
- Other fields preserved

---

#### TC-1.2: Anonymize Tool Feedback - Verify Hash Consistency
**Purpose**: Ensure same workflow_id produces same hash

**Test**:
```python
feedback1 = {'workflow_id': 'wf_test123'}
feedback2 = {'workflow_id': 'wf_test123'}

hash1 = anonymize_tool_feedback(feedback1)['workflow_id_hash']
hash2 = anonymize_tool_feedback(feedback2)['workflow_id_hash']

assert hash1 == hash2  # Deterministic hashing
```

---

#### TC-1.3: Anonymize Tool Feedback - No PII Leakage
**Purpose**: Comprehensive check for PII in output

**Test**:
```python
feedback = {
    'workflow_id': 'wf_secret',
    'task': 'Fix security vulnerability in payment system',
    'repo': 'https://github.com/acme-corp/secret-project',
    'learnings': 'Database credentials were hardcoded',
    'challenges': 'OAuth integration with Stripe',
    'code_snippet': 'def process_payment(card_number):',
    'orchestrator_version': '2.6.0'
}

tool = anonymize_tool_feedback(feedback)

# Verify no PII
assert 'workflow_id' not in tool
assert 'task' not in tool
assert 'repo' not in tool
assert 'learnings' not in tool
assert 'challenges' not in tool
assert 'code_snippet' not in tool
assert 'secret' not in json.dumps(tool).lower()
assert 'payment' not in json.dumps(tool).lower()
assert 'acme-corp' not in json.dumps(tool).lower()
```

---

### Test Suite: Migration

#### TC-2.1: Migrate Legacy Feedback - Happy Path
**Function**: `migrate_legacy_feedback()`

**Setup**:
```python
# Create legacy file with 3 entries
legacy_content = [
    {'timestamp': '2026-01-10T10:00:00Z', 'workflow_id': 'wf_1', 'task': 'Task 1', 'repo': 'repo1', 'learnings': 'Learning 1'},
    {'timestamp': '2026-01-10T11:00:00Z', 'workflow_id': 'wf_2', 'task': 'Task 2', 'repo': 'repo2', 'learnings': 'Learning 2'},
    {'timestamp': '2026-01-10T12:00:00Z', 'workflow_id': 'wf_3', 'task': 'Task 3', 'repo': 'repo3', 'learnings': 'Learning 3'}
]
```

**Expected Behavior**:
1. `.workflow_feedback.jsonl` renamed to `.workflow_feedback.jsonl.migrated`
2. `.workflow_tool_feedback.jsonl` created with 3 anonymized entries
3. `.workflow_process_feedback.jsonl` created with 3 full entries
4. Entry count matches (3 in, 3 out in each file)

**Assertions**:
```python
assert not (working_dir / '.workflow_feedback.jsonl').exists()
assert (working_dir / '.workflow_feedback.jsonl.migrated').exists()
assert (working_dir / '.workflow_tool_feedback.jsonl').exists()
assert (working_dir / '.workflow_process_feedback.jsonl').exists()

# Verify counts
tool_entries = read_jsonl('.workflow_tool_feedback.jsonl')
process_entries = read_jsonl('.workflow_process_feedback.jsonl')
assert len(tool_entries) == 3
assert len(process_entries) == 3

# Verify anonymization
for entry in tool_entries:
    assert 'workflow_id_hash' in entry
    assert 'task' not in entry
    assert 'repo' not in entry
```

---

#### TC-2.2: Migrate Legacy Feedback - Already Migrated
**Purpose**: Ensure idempotency

**Setup**:
- `.workflow_tool_feedback.jsonl` already exists
- `.workflow_process_feedback.jsonl` already exists

**Expected Behavior**:
- Migration skipped
- No changes to existing files
- Return `False` (not migrated)

---

#### TC-2.3: Migrate Legacy Feedback - Malformed Entry
**Purpose**: Handle corrupt data gracefully

**Setup**:
```python
legacy_content = [
    {'timestamp': '2026-01-10T10:00:00Z', 'workflow_id': 'wf_1'},  # Valid
    'invalid json line',  # Malformed
    {'timestamp': '2026-01-10T12:00:00Z', 'workflow_id': 'wf_3'}   # Valid
]
```

**Expected Behavior**:
- 2 entries migrated successfully
- 1 entry skipped with warning
- Migration completes (doesn't fail)
- Print: "✓ Migrated 2 entries (1 failed)"

---

#### TC-2.4: Migrate Legacy Feedback - Empty File
**Purpose**: Handle edge case

**Setup**:
- `.workflow_feedback.jsonl` exists but is empty

**Expected Behavior**:
- Migration completes
- Empty `.workflow_tool_feedback.jsonl` created
- Empty `.workflow_process_feedback.jsonl` created
- Original renamed to `.migrated`

---

### Test Suite: Repo Type Detection

#### TC-3.1: Detect Python Repository
**Function**: `detect_repo_type()`

**Setup**: Create temp directory with `setup.py`

**Expected**: `'python'`

---

#### TC-3.2: Detect JavaScript Repository
**Setup**: Create temp directory with `package.json`

**Expected**: `'javascript'`

---

#### TC-3.3: Detect Go Repository
**Setup**: Create temp directory with `go.mod`

**Expected**: `'go'`

---

#### TC-3.4: Detect Rust Repository
**Setup**: Create temp directory with `Cargo.toml`

**Expected**: `'rust'`

---

#### TC-3.5: Detect Unknown Repository
**Setup**: Create temp directory with no language markers

**Expected**: `'unknown'`

---

### Test Suite: Feedback Extraction

#### TC-4.1: Extract Tool Feedback from Entry
**Function**: `extract_tool_feedback_from_entry()`

**Input**:
```python
{
    'timestamp': '2026-01-11T10:00:00Z',
    'workflow_id': 'wf_123',
    'task': 'User task',
    'repo': 'github.com/user/repo',
    'phases': {'PLAN': 300, 'EXECUTE': 600},
    'reviews_performed': True,
    'errors_count': 2,
    'items_skipped_count': 1,
    'learnings': 'Project-specific learning'
}
```

**Expected Output**:
```python
{
    'timestamp': '2026-01-11T10:00:00Z',
    'workflow_id': 'wf_123',  # Will be hashed later
    'phases': {'PLAN': 300, 'EXECUTE': 600},
    'reviews_performed': True,
    'errors_count': 2,
    'items_skipped_count': 1
}
```

**Assertions**:
- Contains: timestamp, workflow_id, phases, reviews_performed
- Excludes: task, repo, learnings

---

#### TC-4.2: Extract Process Feedback from Entry
**Function**: `extract_process_feedback_from_entry()`

**Input**: Same as TC-4.1

**Expected Output**:
```python
{
    'timestamp': '2026-01-11T10:00:00Z',
    'workflow_id': 'wf_123',
    'task': 'User task',
    'repo': 'github.com/user/repo',
    'learnings': 'Project-specific learning'
}
```

**Assertions**:
- Contains: timestamp, workflow_id, task, repo, learnings
- Excludes: phases (tool-specific metric)

---

## Integration Tests

### Test Suite: End-to-End Feedback Capture

#### TC-5.1: Capture Feedback - Auto Mode
**Command**: `orchestrator feedback --auto`

**Setup**:
- Active workflow with `.workflow_state.json`
- Populated `.workflow_log.jsonl`

**Expected Behavior**:
1. Migration runs if needed
2. Two files created/updated:
   - `.workflow_tool_feedback.jsonl` (anonymized)
   - `.workflow_process_feedback.jsonl` (full context)
3. Entries appended (not overwritten)
4. Print: "✓ Feedback saved to .workflow_tool_feedback.jsonl and .workflow_process_feedback.jsonl"

**Verification**:
```bash
# Tool feedback anonymized
jq '.workflow_id_hash' .workflow_tool_feedback.jsonl  # Should exist
jq '.task' .workflow_tool_feedback.jsonl              # Should be null
jq '.repo' .workflow_tool_feedback.jsonl              # Should be null

# Process feedback full
jq '.task' .workflow_process_feedback.jsonl           # Should exist
jq '.repo' .workflow_process_feedback.jsonl           # Should exist
```

---

#### TC-5.2: Capture Feedback - Opt-Out
**Command**: `ORCHESTRATOR_SKIP_FEEDBACK=1 orchestrator feedback --auto`

**Expected Behavior**:
- Print: "Feedback capture disabled (ORCHESTRATOR_SKIP_FEEDBACK=1)"
- No files created/modified
- Exit cleanly

---

### Test Suite: Feedback Review

#### TC-6.1: Review Tool Feedback
**Command**: `orchestrator feedback review --tool`

**Setup**:
- `.workflow_tool_feedback.jsonl` with 5 entries
- Entry 1-3: reviews_performed=true
- Entry 4-5: reviews_performed=false

**Expected Output**:
```
Feedback Review - Tool Patterns (last 7 days, 5 workflows)
============================================================

⚠ Reviews rarely performed (3 of 5 workflows, 60%)
   → Suggestion: Add review reminders or enforcement

SUMMARY:
  • Total workflows: 5
  • Reviews performed: 60%
```

---

#### TC-6.2: Review Process Feedback
**Command**: `orchestrator feedback review --process`

**Setup**:
- `.workflow_process_feedback.jsonl` with 3 entries
- Entry 1: learnings="TDD works well"
- Entry 2: learnings="Mocks tricky"
- Entry 3: learnings="TDD works well"

**Expected Output**:
```
Feedback Review - Process Patterns (last 7 days, 3 workflows)
============================================================

LEARNINGS:
  1. TDD works well
  2. Mocks tricky
  3. TDD works well
```

---

#### TC-6.3: Review Both (Default)
**Command**: `orchestrator feedback review`

**Expected Output**:
- Shows both tool and process sections
- Combined statistics

---

### Test Suite: Feedback Sync

#### TC-7.1: Sync - Dry Run
**Command**: `orchestrator feedback sync --dry-run`

**Setup**:
- `.workflow_tool_feedback.jsonl` with 2 entries (not synced)

**Expected Output**:
```
Dry Run - Would upload 2 entries:

Entry 1:
{
  "timestamp": "2026-01-11T10:00:00Z",
  "workflow_id_hash": "abc123...",
  "phases": {...}
}

Entry 2:
{...}

No data was uploaded (dry run mode).
```

**Assertions**:
- No API calls made
- No `synced_at` timestamps added
- Files unchanged

---

#### TC-7.2: Sync - Missing GITHUB_TOKEN
**Command**: `orchestrator feedback sync`

**Setup**: Unset `GITHUB_TOKEN` environment variable

**Expected Output**:
```
✗ GITHUB_TOKEN not set. Required for sync.

Setup:
1. Create token: https://github.com/settings/tokens
2. Set token: export GITHUB_TOKEN=ghp_xxx
3. Retry: orchestrator feedback sync

Exit code: 1
```

---

#### TC-7.3: Sync - Success
**Command**: `orchestrator feedback sync`

**Setup**:
- `GITHUB_TOKEN` set
- `.workflow_tool_feedback.jsonl` with 2 unsynced entries

**Expected Behavior**:
1. POST to GitHub Gist API
2. Entries marked with `synced_at` timestamp
3. Print: "✓ Synced 2 entries to GitHub Gist"

**Verification**:
```bash
# Verify synced_at added
jq '.synced_at' .workflow_tool_feedback.jsonl  # Should exist for all entries
```

---

#### TC-7.4: Sync - Already Synced
**Command**: `orchestrator feedback sync`

**Setup**:
- All entries have `synced_at` timestamp

**Expected Output**:
```
✓ No new entries to sync (all up to date)
```

---

#### TC-7.5: Sync - Rate Limit
**Setup**: Mock GitHub API to return 403 rate limit

**Expected Output**:
```
✗ GitHub API rate limit exceeded
  Rate limit resets at: 2026-01-11 11:00:00 UTC
  Try again in: 45 minutes

Exit code: 1
```

---

## Manual Test Cases

### Manual TC-1: Full Workflow with Feedback
**Steps**:
1. Start workflow: `orchestrator start "Test task"`
2. Complete PLAN phase
3. Complete EXECUTE phase
4. Complete REVIEW phase
5. Complete VERIFY phase
6. Complete LEARN phase (includes feedback capture)
7. Verify feedback files created

**Verification**:
```bash
ls -la .workflow_*feedback.jsonl
jq . .workflow_tool_feedback.jsonl
jq . .workflow_process_feedback.jsonl
orchestrator feedback review
```

---

### Manual TC-2: Migration from Phase 3a
**Steps**:
1. Create legacy `.workflow_feedback.jsonl` with test data
2. Run: `orchestrator feedback --auto`
3. Verify migration message appears
4. Verify new files created
5. Verify legacy file renamed to `.migrated`
6. Run again: `orchestrator feedback --auto`
7. Verify no migration message (idempotent)

---

### Manual TC-3: Sync Workflow
**Steps**:
1. Set `GITHUB_TOKEN` environment variable
2. Run: `orchestrator feedback sync --dry-run`
3. Review output for PII
4. Run: `orchestrator feedback sync`
5. Verify GitHub Gist created
6. Verify `synced_at` timestamps added
7. Run again: `orchestrator feedback sync`
8. Verify "No new entries" message

---

### Manual TC-4: Review Patterns
**Steps**:
1. Create 5 workflows with varying patterns
2. Run: `orchestrator feedback review`
3. Verify patterns detected (repeated errors, skips)
4. Run: `orchestrator feedback review --suggest`
5. Approve adding suggestions to ROADMAP.md
6. Verify suggestions appended

---

## Test Data

### Sample Legacy Feedback Entry (Phase 3a)
```json
{
  "timestamp": "2026-01-11T10:00:00Z",
  "mode": "auto",
  "workflow_id": "wf_abc123",
  "task": "Add user authentication",
  "repo": "https://github.com/user/my-app",
  "parallel_agents_used": true,
  "reviews_performed": false,
  "errors_count": 2,
  "errors_summary": ["pytest not found", "lint failed"],
  "items_skipped_count": 1,
  "items_skipped_reasons": ["visual_tests: Not applicable"],
  "learnings": "OAuth integration was tricky",
  "duration_seconds": 1800,
  "phases": {
    "PLAN": 300,
    "EXECUTE": 900,
    "REVIEW": 300,
    "VERIFY": 200,
    "LEARN": 100
  }
}
```

### Expected Tool Feedback (Phase 3b)
```json
{
  "timestamp": "2026-01-11T10:00:00Z",
  "workflow_id_hash": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
  "orchestrator_version": "2.6.0",
  "repo_type": "python",
  "duration_seconds": 1800,
  "phases": {
    "PLAN": 300,
    "EXECUTE": 900,
    "REVIEW": 300,
    "VERIFY": 200,
    "LEARN": 100
  },
  "parallel_agents_used": true,
  "reviews_performed": false,
  "errors_count": 2,
  "items_skipped_count": 1,
  "mode": "auto"
}
```

### Expected Process Feedback (Phase 3b)
```json
{
  "timestamp": "2026-01-11T10:00:00Z",
  "workflow_id": "wf_abc123",
  "task": "Add user authentication",
  "repo": "https://github.com/user/my-app",
  "parallel_agents_used": true,
  "errors_summary": ["pytest not found", "lint failed"],
  "items_skipped_reasons": ["visual_tests: Not applicable"],
  "learnings": "OAuth integration was tricky",
  "mode": "auto"
}
```

## Test Coverage Goals

- **Unit Tests**: 90%+ coverage for anonymization, migration, extraction logic
- **Integration Tests**: All CLI commands (capture, review, sync)
- **Manual Tests**: End-to-end workflows, edge cases, error scenarios

## Test Execution

```bash
# Run unit tests
pytest tests/test_feedback.py -v

# Run integration tests
pytest tests/test_feedback_integration.py -v

# Run manual tests
./tests/manual_test_feedback.sh

# Coverage report
pytest --cov=src --cov-report=html tests/
```
