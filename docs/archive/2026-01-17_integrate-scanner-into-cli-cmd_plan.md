# Intelligent File Scanning for Backfill

## Overview

Add intelligent file scanning to the healing backfill system that:
1. Automatically discovers learnable content at session end
2. Provides recommendations for each source found
3. Handles deduplication gracefully on re-runs
4. Integrates with ongoing healing workflow (not periodic backfill)

## Architecture: Session-End Hook with Incremental Scanning

Based on multi-model consensus (Claude, GPT, Gemini, Grok, DeepSeek), we use a **session-end hook** architecture that triggers at `orchestrator finish`.

```
┌─────────────────────────────────────────────────────┐
│              Session End Hook (Primary)             │
│  • Scan session artifacts (manifest-driven)         │
│  • Check LEARNINGS.md hash                          │
│  • GitHub issues since watermark                    │
│  • Update state file + pattern store                │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│         Crash Recovery at Session Start             │
│  • If previous session didn't complete, ingest its  │
│    orphaned logs before proceeding                  │
└─────────────────────────────────────────────────────┘
```

## Components

### 1. ScanState (State Tracking)

Portable JSON file at `.orchestrator/scan_state.json`:

```json
{
  "last_scan": "2026-01-17T12:00:00Z",
  "file_hashes": {
    "LEARNINGS.md": "a1b2c3d4...",
    ".workflow_log.jsonl": "e5f6g7h8..."
  },
  "github_watermark": "2026-01-14T00:00:00Z",
  "ingested_sessions": ["wf_abc123", "wf_def456"]
}
```

### 2. PatternSource Protocol

Each source implements incremental scanning:

```python
class PatternSource(Protocol):
    def scan_incremental(self, state: ScanState) -> list[ScanResult]
    def get_recommendation(self) -> str
```

### 3. Sources to Scan

| Source | Parser | Recommendation Logic |
|--------|--------|----------------------|
| `.workflow_log.jsonl` | WorkflowLogDetector | "High value - structured error events" |
| `LEARNINGS.md` | TranscriptDetector | "High value - documented errors and fixes" |
| `.wfo_logs/*.log` | TranscriptDetector | "Medium value - parallel agent errors" |
| `.orchestrator/sessions/*` | TranscriptDetector | "Medium value - session transcripts (last 30 days)" |
| GitHub closed issues | GitHubIssueParser (new) | "High value - resolved bugs with labels: bug, error, fix" |

### 4. Scanner Module

New file: `src/healing/scanner.py`

```python
@dataclass
class ScanResult:
    source: str           # "workflow_log", "learnings_md", "github_issue"
    path: str             # File path or issue URL
    errors_found: int     # Number of errors extracted
    recommendation: str   # Why this source is valuable

@dataclass
class ScanSummary:
    sources_scanned: list[ScanResult]
    errors_extracted: int
    patterns_created: int
    patterns_updated: int  # Existing patterns with incremented count

class PatternScanner:
    def scan_all(self, days: int = 30) -> ScanSummary
    def scan_and_show_recommendations(self) -> list[ScanResult]
```

### 5. Integration Points

#### A. Session-End Hook (in `cmd_finish`)

```python
# In cli.py cmd_finish(), after workflow completion:
if healing_enabled:
    scanner = PatternScanner(client)
    summary = await scanner.scan_all()
    if summary.errors_extracted > 0:
        click.echo(f"Learning: Found {summary.errors_extracted} errors, "
                   f"created {summary.patterns_created} new patterns")
```

#### B. Crash Recovery (in `cmd_start`)

```python
# In cli.py cmd_start(), at session start:
scanner = PatternScanner(client)
if scanner.has_orphaned_session():
    click.echo("Recovering learnings from previous incomplete session...")
    await scanner.recover_orphaned()
```

#### C. Manual Trigger (CLI)

```bash
# Existing backfill command enhanced with scanning:
orchestrator heal backfill              # Scan + backfill (default)
orchestrator heal backfill --scan-only  # Just show recommendations
orchestrator heal backfill --days 90    # Scan last 90 days
orchestrator heal backfill --no-github  # Skip GitHub API
```

## Deduplication Strategy

Already handled by existing infrastructure:

1. **Fingerprinting**: Each error gets a unique fingerprint (SHA256 of type + normalized message + stack frame)
2. **Upsert on record**: `record_historical_error()` checks if fingerprint exists
3. **Increment vs Insert**: Existing patterns get `occurrence_count++`, new patterns are inserted

Re-running backfill on same files is safe - it just increments occurrence counts.

## GitHub Integration

New parser using `gh` CLI:

```python
class GitHubIssueParser:
    def fetch_closed_issues(self, since: datetime, labels: list[str]) -> list[dict]:
        """Fetch closed issues since watermark with bug/error/fix labels."""
        cmd = f"gh issue list --state closed --json title,body,labels,closedAt"
        # Filter by labels and date

    def extract_errors(self, issue: dict) -> list[ErrorEvent]:
        """Parse issue body for error patterns (stack traces, error messages)."""
        # Use TranscriptDetector-style regex parsing
```

## Files to Create/Modify

### New Files
- `src/healing/scanner.py` - Main scanner module (~200 lines)
- `src/healing/github_parser.py` - GitHub issue parser (~100 lines)
- `tests/healing/test_scanner.py` - Scanner tests (~150 lines)
- `tests/healing/test_github_parser.py` - GitHub parser tests (~80 lines)

### Modified Files
- `src/healing/backfill.py` - Integrate scanner as default behavior
- `src/cli.py` - Add scan integration to cmd_finish, cmd_start
- `src/healing/__init__.py` - Export new modules

## Execution Plan

**Sequential execution** - This is a single cohesive feature with tight dependencies:
1. Scanner depends on state tracking
2. GitHub parser depends on scanner infrastructure
3. CLI integration depends on scanner
4. Tests depend on all components

## Test Strategy

1. **Unit tests for ScanState**: Load, save, hash tracking
2. **Unit tests for scanner**: Mock sources, verify incremental behavior
3. **Unit tests for GitHub parser**: Mock gh CLI output
4. **Integration test**: End-to-end scan with real files

## Acceptance Criteria

1. ✅ `orchestrator finish` automatically scans for learnable content
2. ✅ `orchestrator heal backfill` shows recommendations before processing
3. ✅ Re-running backfill doesn't create duplicates
4. ✅ GitHub closed issues are scanned (with --days flag)
5. ✅ State file tracks what's been processed
6. ✅ Crash recovery ingests orphaned sessions
