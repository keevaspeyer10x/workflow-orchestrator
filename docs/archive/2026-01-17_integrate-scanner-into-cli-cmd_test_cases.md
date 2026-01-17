# Test Cases: Intelligent File Scanning

## ScanState Tests

### TC-STATE-001: Load empty state
**Given**: No state file exists
**When**: `ScanState.load()` is called
**Then**: Returns empty state with default values

### TC-STATE-002: Load existing state
**Given**: State file exists with hashes and watermark
**When**: `ScanState.load()` is called
**Then**: Returns state with preserved values

### TC-STATE-003: Save state atomically
**Given**: ScanState with data
**When**: `state.save()` is called
**Then**: File is written atomically (temp + rename)

### TC-STATE-004: Hash tracking
**Given**: ScanState with file_hashes
**When**: `state.is_changed("file.md", new_hash)` is called
**Then**: Returns True if hash differs, False if same

### TC-STATE-005: Session tracking
**Given**: ScanState with ingested_sessions
**When**: `state.is_session_ingested("wf_123")` is called
**Then**: Returns True if in list, False otherwise

## PatternScanner Tests

### TC-SCAN-001: Scan unchanged file
**Given**: File with same hash as in state
**When**: `scanner.scan_all()` is called
**Then**: File is skipped, no patterns extracted

### TC-SCAN-002: Scan changed file
**Given**: File with different hash than state
**When**: `scanner.scan_all()` is called
**Then**: File is parsed, patterns extracted, hash updated

### TC-SCAN-003: Scan new file
**Given**: File not in state
**When**: `scanner.scan_all()` is called
**Then**: File is parsed, patterns extracted, hash added

### TC-SCAN-004: Skip files over size limit
**Given**: File larger than max_file_size (10MB)
**When**: `scanner.scan_all()` is called
**Then**: File is skipped with warning, not error

### TC-SCAN-005: Show recommendations
**Given**: Multiple scannable sources exist
**When**: `scanner.scan_and_show_recommendations()` is called
**Then**: Returns list of ScanResult with recommendations

### TC-SCAN-006: Days filter
**Given**: Files older than 30 days and newer than 30 days
**When**: `scanner.scan_all(days=30)` is called
**Then**: Only files modified in last 30 days are scanned

### TC-SCAN-007: Deduplication
**Given**: Pattern already exists in database
**When**: Same error is scanned again
**Then**: Occurrence count incremented, no duplicate created

## GitHubIssueParser Tests

### TC-GH-001: Parse closed issues
**Given**: Mock gh CLI output with closed issues
**When**: `parser.fetch_closed_issues()` is called
**Then**: Returns list of issue dicts

### TC-GH-002: Filter by labels
**Given**: Issues with various labels
**When**: `parser.fetch_closed_issues(labels=["bug"])` is called
**Then**: Only issues with "bug" label returned

### TC-GH-003: Extract errors from body
**Given**: Issue body with Python traceback
**When**: `parser.extract_errors(issue)` is called
**Then**: Returns ErrorEvent with parsed traceback

### TC-GH-004: Handle gh not installed
**Given**: gh CLI not in PATH
**When**: `parser.fetch_closed_issues()` is called
**Then**: Returns empty list with warning logged

### TC-GH-005: Watermark filtering
**Given**: Issues before and after watermark date
**When**: `parser.fetch_closed_issues(since=watermark)` is called
**Then**: Only issues closed after watermark returned

## Integration Tests

### TC-INT-001: End-to-end scan
**Given**: Repo with LEARNINGS.md, workflow logs, and GitHub issues
**When**: Full scan is performed
**Then**: All sources scanned, patterns stored, state updated

### TC-INT-002: Crash recovery
**Given**: Previous session didn't complete (no state update)
**When**: New session starts
**Then**: Orphaned logs from previous session are ingested

### TC-INT-003: Re-run idempotency
**Given**: Scan already completed
**When**: Scan is run again
**Then**: No new patterns created, occurrence counts may increment

## CLI Tests

### TC-CLI-001: backfill with scan
**Given**: `orchestrator heal backfill`
**When**: Command executed
**Then**: Scan runs first, shows recommendations, then backfills

### TC-CLI-002: backfill --scan-only
**Given**: `orchestrator heal backfill --scan-only`
**When**: Command executed
**Then**: Only shows recommendations, no backfill

### TC-CLI-003: backfill --days 90
**Given**: `orchestrator heal backfill --days 90`
**When**: Command executed
**Then**: Scans sources from last 90 days

### TC-CLI-004: backfill --no-github
**Given**: `orchestrator heal backfill --no-github`
**When**: Command executed
**Then**: Skips GitHub issue scanning

## Edge Cases

### TC-EDGE-001: Empty LEARNINGS.md
**Given**: LEARNINGS.md exists but is empty
**When**: Scan is performed
**Then**: No errors, file marked as scanned

### TC-EDGE-002: Malformed JSON in state
**Given**: State file has invalid JSON
**When**: `ScanState.load()` is called
**Then**: Returns empty state, logs warning

### TC-EDGE-003: No scannable sources
**Given**: Repo with no logs or LEARNINGS.md
**When**: Scan is performed
**Then**: Empty result, no errors

### TC-EDGE-004: GitHub API error
**Given**: GitHub API returns error
**When**: Scan is performed
**Then**: Local sources still scanned, warning logged for GitHub
