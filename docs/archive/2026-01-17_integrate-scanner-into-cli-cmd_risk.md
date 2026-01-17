# Risk Analysis: Intelligent File Scanning

## Risk Matrix

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| GitHub API rate limiting | MEDIUM | MEDIUM | Use watermark for incremental fetches, cache results |
| Large files causing OOM | MEDIUM | LOW | Stream-process large files, set size limits |
| gh CLI not installed | LOW | MEDIUM | Graceful fallback, skip GitHub scanning with warning |
| Sensitive data in issues | HIGH | LOW | Same scrubbing as existing backfill |
| Session-end hook slows finish | MEDIUM | LOW | Async/background processing option |
| State file corruption | MEDIUM | LOW | JSON validation, backup before write |

## Detailed Analysis

### 1. GitHub API Rate Limiting

**Risk**: Hitting GitHub API limits if scanning frequently.

**Mitigation**:
- Use watermark (`closed:>YYYY-MM-DD`) for delta fetches
- Only fetch issues with relevant labels (bug, error, fix)
- Default to 30-day window, configurable
- Cache issue data in state file

**Impact if unmitigated**: Scanner fails, but local sources still work.

### 2. Large Files / OOM

**Risk**: Very large log files causing memory issues.

**Mitigation**:
- Stream-process JSONL files line by line (already done in backfill)
- Set max file size limit (10MB default)
- Skip files over limit with warning

**Impact if unmitigated**: Process crash on large repos.

### 3. gh CLI Dependency

**Risk**: `gh` CLI not installed or not authenticated.

**Mitigation**:
- Check `shutil.which("gh")` before attempting
- Skip GitHub scanning gracefully with info message
- Document gh CLI requirement in help text

**Impact if unmitigated**: Minor - local sources still valuable.

### 4. Sensitive Data in Issues

**Risk**: Error patterns from issues may contain secrets/PII.

**Mitigation**:
- Apply same `SecretScrubber` as existing backfill
- Issues are public anyway (if using public repo)
- Only extract error patterns, not full issue text

**Impact if unmitigated**: Secrets stored in pattern database.

### 5. Session-End Hook Performance

**Risk**: Scanning slows down `orchestrator finish`.

**Mitigation**:
- Incremental scanning (only changed files)
- Hash-based skip for unchanged files
- Optional: async processing with spinner
- Typical scan: <1s for most repos

**Impact if unmitigated**: User annoyance, but tolerable.

### 6. State File Corruption

**Risk**: Invalid JSON or partial write corrupts state.

**Mitigation**:
- Validate JSON on load with fallback to empty state
- Write to temp file, then atomic rename
- Include schema version for future migrations

**Impact if unmitigated**: Re-scan all files (safe, just slower).

## Security Considerations

1. **Secret Scrubbing**: All extracted patterns go through `SecretScrubber`
2. **No Code Execution**: Parsing only, no eval or subprocess from file content
3. **GitHub Auth**: Uses user's existing `gh` auth, no new credentials stored

## Dependencies

| Dependency | Purpose | Fallback |
|------------|---------|----------|
| `gh` CLI | GitHub issue fetching | Skip GitHub, warn user |
| Supabase | Pattern storage | Local-only mode (existing) |
| File system | Log file access | Standard error handling |

## Rollback Plan

If issues discovered post-deployment:
1. Disable scanner in `cmd_finish` via env var `ORCHESTRATOR_SKIP_SCAN=1`
2. State file can be deleted to reset (safe re-scan)
3. No database migrations, patterns are additive only
