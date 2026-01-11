# Risk Analysis: Phase 3b Two-Tier Feedback System

## High-Risk Items

### Risk 1: Data Loss During Migration
**Severity**: HIGH
**Likelihood**: MEDIUM

**Description**: Auto-migration on first run could fail mid-process, corrupting or losing feedback data.

**Impact**:
- Loss of historical feedback data
- Incomplete migration state (some entries split, others not)
- User confusion if migration partially completes

**Mitigation**:
1. **Backup first**: Rename original to `.workflow_feedback.jsonl.migrated` BEFORE writing new files
2. **Atomic writes**: Write to temp files, then rename (atomic operation)
3. **Validation**: Count entries before/after, verify totals match
4. **Error handling**: Wrap entire migration in try/except, rollback on failure
5. **Idempotency**: Check if migration already complete (both new files exist)

**Contingency**:
- If migration fails, restore from `.workflow_feedback.jsonl.migrated`
- Log detailed error for debugging
- Manual migration option: `orchestrator feedback migrate --manual`

---

### Risk 2: Accidental PII Leakage in Tool Feedback
**Severity**: CRITICAL
**Likelihood**: LOW

**Description**: Anonymization logic could miss PII (repo names, task descriptions, code snippets) in tool feedback that gets synced.

**Impact**:
- Privacy violation if private repo names/code uploaded
- Trust loss with users
- Potential security issue if sensitive task descriptions leaked

**Mitigation**:
1. **Whitelist approach**: Only include known-safe fields (phases, duration, repo_type)
2. **Double verification**: `verify_anonymization()` checks tool feedback before sync
3. **Dry-run default**: `orchestrator feedback sync --dry-run` shows what WOULD be uploaded
4. **Unit tests**: Comprehensive test suite verifying no PII in output
5. **Manual review**: Developer (you) manually inspects first sync

**Test Cases**:
```python
def test_no_pii_in_tool_feedback():
    feedback = {...}  # Full feedback with PII
    tool = anonymize_tool_feedback(feedback)

    assert 'repo' not in tool
    assert 'task' not in tool
    assert 'workflow_id' not in tool
    assert 'workflow_id_hash' in tool
    assert tool['repo_type'] in ['python', 'javascript', 'go', 'rust', 'unknown']
```

**Contingency**:
- If PII leaked, immediately delete GitHub Gist
- Audit all synced data
- Fix anonymization logic
- Re-sync with corrected data

---

### Risk 3: GitHub API Rate Limits on Sync
**Severity**: MEDIUM
**Likelihood**: MEDIUM

**Description**: Frequent sync operations could hit GitHub API rate limits (5000 requests/hour authenticated, 60/hour unauthenticated).

**Impact**:
- Sync command fails with rate limit error
- User frustration if sync consistently fails
- Data not uploaded for analysis

**Mitigation**:
1. **Track sync timestamps**: Only sync new entries (not synced before)
2. **Batch uploads**: Combine multiple entries into single API call
3. **Conditional requests**: Use `If-None-Match` headers to avoid redundant updates
4. **Rate limit detection**: Parse `X-RateLimit-Remaining` header
5. **Exponential backoff**: Retry with increasing delays

**Code**:
```python
response = requests.post(...)
if response.status_code == 403 and 'rate limit' in response.text.lower():
    reset_time = response.headers.get('X-RateLimit-Reset')
    print(f"Rate limited. Try again after {reset_time}")
    sys.exit(1)
```

**Contingency**:
- Clear error message with retry time
- Manual upload instructions as fallback
- Consider batch sync (weekly instead of per-workflow)

---

## Medium-Risk Items

### Risk 4: Malformed Legacy Feedback Data
**Severity**: MEDIUM
**Likelihood**: MEDIUM

**Description**: Existing `.workflow_feedback.jsonl` might have malformed JSON or unexpected schema.

**Impact**:
- Migration fails completely
- Some entries skipped silently
- User stuck on old system

**Mitigation**:
1. **Graceful parsing**: Wrap JSON loads in try/except per line
2. **Skip and log**: Continue migration even if some entries fail
3. **Summary report**: Print "Migrated X/Y entries, Z failed"
4. **Schema validation**: Check for required fields before processing

**Code**:
```python
migrated, failed = 0, 0
for line in f:
    try:
        entry = json.loads(line)
        # Migrate entry
        migrated += 1
    except Exception as e:
        logger.warning(f"Failed to migrate entry: {e}")
        failed += 1

print(f"✓ Migrated {migrated} entries ({failed} failed)")
```

---

### Risk 5: GITHUB_TOKEN Not Set for Sync
**Severity**: LOW
**Likelihood**: HIGH

**Description**: User runs `orchestrator feedback sync` without setting `GITHUB_TOKEN` environment variable.

**Impact**:
- Sync command fails with auth error
- User confusion about setup requirements

**Mitigation**:
1. **Early check**: Verify `GITHUB_TOKEN` exists before attempting sync
2. **Clear error message**: Show setup instructions
3. **Documentation**: Update CLAUDE.md with token setup steps
4. **Fallback instructions**: Show manual upload option

**Code**:
```python
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
if not GITHUB_TOKEN:
    print("✗ GITHUB_TOKEN not set. Required for sync.")
    print("\nSetup:")
    print("1. Create token: https://github.com/settings/tokens")
    print("2. Set token: export GITHUB_TOKEN=ghp_xxx")
    print("3. Retry: orchestrator feedback sync")
    sys.exit(1)
```

---

### Risk 6: Sync Opt-in Confusion
**Severity**: LOW
**Likelihood**: MEDIUM

**Description**: User confused about whether sync is enabled by default (it is for developer, but might not want it).

**Impact**:
- Unexpected data uploads
- Privacy concerns
- Loss of trust

**Mitigation**:
1. **First-run notice**: On first sync attempt, show clear message
2. **Config visibility**: `orchestrator status` shows sync status
3. **Easy opt-out**: `orchestrator config set feedback_sync false`
4. **Dry-run reminder**: Print "Use --dry-run to preview" on first sync

**Message**:
```
📤 Feedback sync is ENABLED by default (you're the developer).

This uploads anonymized tool feedback to GitHub Gist for analysis:
  ✓ Includes: Phase timings, items skipped, orchestrator errors
  ✗ Excludes: Repo name, task description, code, learnings

Preview: orchestrator feedback sync --dry-run
Disable: orchestrator config set feedback_sync false

Continue with sync? (y/n):
```

---

## Low-Risk Items

### Risk 7: File Path Collisions
**Severity**: LOW
**Likelihood**: LOW

**Description**: New files (`.workflow_tool_feedback.jsonl`, `.workflow_process_feedback.jsonl`) might conflict with user's existing files.

**Impact**:
- Overwriting user data
- Confusion about file purpose

**Mitigation**:
1. **Check before write**: Verify file doesn't exist or is owned by orchestrator
2. **Clear naming**: Use `.workflow_*` prefix (consistent with existing files)
3. **Gitignore**: Add to `.gitignore` recommendations

---

### Risk 8: Backward Compatibility
**Severity**: LOW
**Likelihood**: LOW

**Description**: Old orchestrator versions might not understand new two-tier format.

**Impact**:
- Users on old version can't read new feedback
- Confusion if downgrading

**Mitigation**:
1. **Migration preserves legacy**: `.workflow_feedback.jsonl.migrated` remains as backup
2. **Version detection**: Check orchestrator version before reading files
3. **Graceful degradation**: Old version ignores new files

---

## Risk Summary

| Risk | Severity | Likelihood | Priority |
|------|----------|------------|----------|
| Data Loss During Migration | HIGH | MEDIUM | 1 |
| PII Leakage | CRITICAL | LOW | 2 |
| GitHub API Rate Limits | MEDIUM | MEDIUM | 3 |
| Malformed Legacy Data | MEDIUM | MEDIUM | 4 |
| GITHUB_TOKEN Not Set | LOW | HIGH | 5 |
| Sync Opt-in Confusion | LOW | MEDIUM | 6 |
| File Path Collisions | LOW | LOW | 7 |
| Backward Compatibility | LOW | LOW | 8 |

## Mitigation Priority

**Critical Path** (must address before shipping):
1. ✅ Data loss prevention (backup + atomic writes)
2. ✅ PII leakage prevention (whitelist + verification + dry-run)
3. ✅ Token check with clear error message

**High Priority** (address during implementation):
4. ✅ Rate limit handling
5. ✅ Malformed data handling
6. ✅ Sync opt-in clarity

**Low Priority** (can defer):
7. File path collision check
8. Backward compatibility handling

## Testing Focus

Based on risks, prioritize testing:
1. **Migration safety**: Test with various malformed inputs
2. **Anonymization**: Comprehensive PII detection tests
3. **Sync reliability**: Test rate limits, auth failures, network errors
4. **Error recovery**: Test rollback scenarios
