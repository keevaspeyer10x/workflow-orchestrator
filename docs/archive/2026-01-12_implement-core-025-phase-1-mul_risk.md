# Risk Analysis: CORE-024 & WF-034

## Executive Summary

**Overall Risk Level:** MEDIUM

**Key Risks:**
1. **CRITICAL:** Secret leakage in session logs (CORE-024)
2. **HIGH:** Performance overhead from logging (CORE-024)
3. **HIGH:** Session transcript parsing brittleness (WF-034 Phase 2)
4. **MEDIUM:** Backward compatibility with existing workflows (WF-034)

**Mitigation:** All critical/high risks have concrete mitigation strategies.

---

## CORE-024 Risks

### RISK-1: Secret Leakage in Session Logs
**Severity:** CRITICAL
**Probability:** MEDIUM (without mitigation)
**Impact:** Secrets exposed in log files could be committed to git, shared, or compromised

**Scenarios:**
1. Pattern-based scrubbing misses custom secret formats
2. SecretsManager not initialized (secrets not known to scrubber)
3. Secrets in complex data structures (JSON, base64 encoded)
4. New secret types added without updating scrubbing patterns

**Mitigation Strategies:**

**M1.1: Conservative Scrubbing Patterns**
- Use broad patterns (e.g., any 32+ char alphanumeric string)
- Over-redact rather than under-redact
- Test against real secret formats (API keys, tokens, JWTs)

**M1.2: Multi-Layer Scrubbing**
```python
class SecretScrubber:
    def scrub(self, text: str) -> str:
        # Layer 1: Known secrets from SecretsManager
        text = self._scrub_known_secrets(text)

        # Layer 2: Pattern-based scrubbing
        text = self._scrub_patterns(text)

        # Layer 3: Heuristic scrubbing (base64, hex, etc.)
        text = self._scrub_heuristics(text)

        return text
```

**M1.3: Scrubbing Validation**
- Unit tests with real secret examples
- Integration test: verify no secrets in output
- Add to CI/CD: fail if secrets detected in test logs
- Logging of scrubbing statistics (X secrets redacted)

**M1.4: Safe by Default**
- Scrub BEFORE writing to disk (never write raw)
- Add warning header to session logs:
  ```
  # WARNING: This file has been automatically scrubbed for secrets.
  # Do not manually edit. Review before sharing.
  # Scrubbed: 2026-01-12 14:30:00 UTC
  ```

**M1.5: .gitignore Protection**
- Add `.orchestrator/sessions/` to .gitignore
- Document in CLAUDE.md: "Session logs should never be committed"
- Consider adding git hook to block commits of session logs

**Residual Risk:** LOW (with all mitigations)

---

### RISK-2: Performance Overhead from Logging
**Severity:** HIGH
**Probability:** MEDIUM
**Impact:** Workflow execution slows down, degraded user experience

**Scenarios:**
1. Session logging adds 20%+ overhead to workflow execution
2. Large transcripts (100+ MB) cause disk I/O bottlenecks
3. Secret scrubbing regex patterns are computationally expensive
4. Synchronous logging blocks workflow operations

**Mitigation Strategies:**

**M2.1: Asynchronous Logging**
```python
class SessionLogger:
    def __init__(self):
        self._log_queue = queue.Queue()
        self._worker_thread = threading.Thread(target=self._log_worker)
        self._worker_thread.start()

    def log_event(self, event: dict):
        # Non-blocking: queue event and return immediately
        self._log_queue.put(event)

    def _log_worker(self):
        # Background thread writes to disk
        while True:
            event = self._log_queue.get()
            self._write_to_disk(event)
```

**M2.2: Efficient Scrubbing**
- Compile regex patterns once (not per-scrub)
- Use compiled patterns: `re.compile()` at init time
- Benchmark: scrubbing should be <1ms per KB of text
- Add caching for repeated scrubbing of same secrets

**M2.3: Log Rotation**
- Set max log file size (e.g., 50 MB)
- Rotate to new file when limit reached
- Compress old logs (gzip) to save disk space
- Auto-cleanup logs older than 90 days (configurable)

**M2.4: Performance Monitoring**
- Track logging overhead (time spent logging vs workflow execution)
- Warn if overhead exceeds 5%
- Add `--no-session-log` flag for performance-critical scenarios

**M2.5: Lazy Loading**
- Don't load entire session into memory
- Stream logs line-by-line when viewing
- Use `tail` for recent events, not full file read

**Success Criteria:**
- Logging overhead < 5% of workflow execution time
- Session log writes complete within 100ms (async)
- No noticeable slowdown in CLI responsiveness

**Residual Risk:** LOW (with all mitigations)

---

### RISK-3: Session Log Storage Growth
**Severity:** MEDIUM
**Probability:** HIGH (over time)
**Impact:** Disk space exhaustion, degraded performance

**Scenarios:**
1. Session logs accumulate to 10+ GB over months
2. Users run out of disk space
3. Log analysis becomes slow due to large dataset

**Mitigation Strategies:**

**M3.1: Automatic Cleanup**
```python
# Configuration
DEFAULT_LOG_RETENTION_DAYS = 90

# Auto-cleanup on session start
def cleanup_old_sessions(retention_days: int):
    cutoff = datetime.now() - timedelta(days=retention_days)
    for log_file in session_dir.glob("*.log"):
        if log_file.stat().st_mtime < cutoff.timestamp():
            log_file.unlink()  # Delete old log
```

**M3.2: Compression**
- Compress logs older than 7 days (gzip)
- Typical compression ratio: 10:1 for text logs
- Transparent decompression when viewing

**M3.3: User Configuration**
```yaml
# ~/.orchestrator/config.yaml
session_logging:
  enabled: true
  retention_days: 90
  max_total_size_mb: 500
  compression:
    enabled: true
    after_days: 7
```

**M3.4: Warning Messages**
```bash
$ orchestrator sessions list
WARNING: Session logs using 450 MB of 500 MB limit.
Run 'orchestrator sessions cleanup' to free space.
```

**Residual Risk:** LOW (with auto-cleanup)

---

### RISK-4: Session Transcript Parsing Brittleness
**Severity:** MEDIUM
**Probability:** MEDIUM
**Impact:** Session analysis produces incorrect results, false positives/negatives

**Scenarios:**
1. Log format changes break parsing logic
2. Multi-line outputs parsed incorrectly
3. Timestamps in different formats
4. Unicode/encoding issues

**Mitigation Strategies:**

**M4.1: Structured Logging**
- Use JSON Lines format (`.jsonl`) instead of plain text
- Each event is a complete JSON object
- Easy to parse, version-safe

```json
{"timestamp": "2026-01-12T14:30:00Z", "type": "command", "data": {"command": "orchestrator status"}}
{"timestamp": "2026-01-12T14:30:01Z", "type": "output", "data": {"text": "Phase: PLAN\nProgress: 1/7"}}
```

**M4.2: Schema Versioning**
```python
class SessionEvent:
    schema_version: str = "1.0"  # Version the log format
    timestamp: datetime
    event_type: str
    data: dict
```

**M4.3: Fallback to Plain Text**
- If structured parsing fails, fall back to plain text search
- Graceful degradation: "Unable to parse session, showing raw log"

**M4.4: Comprehensive Testing**
- Test parsing with real session logs
- Test edge cases (multi-line, unicode, timestamps)
- Regression tests: keep sample logs in test fixtures

**Residual Risk:** LOW (with structured logging)

---

## WF-034 Risks

### RISK-5: Workflow.yaml Changes Break Existing Workflows
**Severity:** MEDIUM
**Probability:** MEDIUM
**Impact:** Active workflows fail when new items added

**Scenarios:**
1. User has active workflow when workflow.yaml updated
2. New required items cause workflow to fail validation
3. Existing .workflow_state.json incompatible with new schema

**Mitigation Strategies:**

**M5.1: Backward Compatibility**
- New items have unique IDs (not conflicting with old items)
- Workflow engine handles unknown items gracefully
- Version lock: workflows use the workflow.yaml version from start time

**M5.2: Default Workflow vs Project Workflow**
- Only update `src/default_workflow.yaml` (bundled template)
- Project-specific `workflow.yaml` is never auto-updated
- User must manually merge new items if desired

**M5.3: Migration Path**
```bash
# Show diff between bundled and project workflow
orchestrator diff-workflow

# Merge new items interactively
orchestrator update-workflow --interactive
```

**M5.4: Documentation**
- CLAUDE.md explains workflow update process
- CHANGELOG documents workflow.yaml changes
- Migration guide for each breaking change

**Residual Risk:** LOW (project workflows unaffected)

---

### RISK-6: Adherence Validation False Positives
**Severity:** MEDIUM
**Probability:** MEDIUM
**Impact:** Agents flagged for violations they didn't commit, user frustration

**Scenarios:**
1. Parallel execution detected as sequential (false negative)
2. Reviews marked as missing when actually deferred (false positive)
3. Plan agent usage not detected due to log format changes

**Mitigation Strategies:**

**M6.1: Conservative Validation**
- Only flag CLEAR violations (high confidence)
- Use warnings (⚠) for uncertain issues
- Provide explanations: "Why was this flagged?"

**M6.2: Manual Override**
```bash
# If validation is incorrect, user can override
orchestrator validate-adherence --ignore parallel_execution --reason "Tasks not parallelizable"
```

**M6.3: Validation Accuracy Testing**
- Unit tests with known-good and known-bad workflows
- Test against real session logs
- Measure false positive/negative rates
- Target: <5% false positive rate

**M6.4: Detailed Output**
```
✗ Parallel execution: FAIL
  Reason: Found 3 Task tool calls in separate messages (msg_001, msg_003, msg_007)
  Expected: All Task calls in single message
  Evidence: [Show excerpt from session log]

  If this is incorrect, run:
  orchestrator validate-adherence --ignore parallel_execution
```

**Residual Risk:** LOW (with explanations and override)

---

### RISK-7: Feedback Fatigue
**Severity:** LOW
**Probability:** HIGH
**Impact:** Users ignore feedback prompts, low data quality

**Scenarios:**
1. Feedback capture prompt shown every workflow (annoying)
2. Questions are too generic (not actionable)
3. Users skip feedback (no value from data)

**Mitigation Strategies:**

**M7.1: Smart Prompting**
- Only prompt for feedback on "interesting" workflows
  - First workflow in a project
  - Workflows with errors/challenges
  - Long-running workflows (>1 hour)
  - Workflows using new features (parallel agents, reviews)
- Skip feedback for routine workflows (simple bugfixes, docs)

**M7.2: Minimal Friction**
```bash
# Quick feedback (1-liner)
orchestrator feedback --quick "Parallel agents worked great, saved 40% time"

# Full feedback (interactive)
orchestrator feedback --interactive

# Skip feedback
orchestrator finish --no-feedback
```

**M7.3: Show Value**
- Display feedback analysis to users
- "Your feedback helped identify pattern: X"
- Generate roadmap suggestions from feedback

**M7.4: Optional by Default**
- Feedback is optional (can skip)
- No blocking prompts
- Default: capture basic stats, skip questions

**Residual Risk:** LOW (optional feature)

---

### RISK-8: Adherence Validation Depends on Session Logs (Circular Dependency)
**Severity:** MEDIUM
**Probability:** LOW
**Impact:** AdherenceValidator breaks if session logging is disabled

**Scenarios:**
1. User disables session logging (performance, privacy)
2. AdherenceValidator tries to read non-existent session logs
3. Validation fails with cryptic error

**Mitigation Strategies:**

**M8.1: Graceful Degradation**
```python
def validate_adherence(workflow_id: str) -> AdherenceReport:
    session_log = get_session_log(workflow_id)

    if not session_log:
        return AdherenceReport(
            error="Session logging not enabled. Cannot validate adherence.",
            recommendation="Enable session logging: orchestrator config set session_logging.enabled true"
        )
```

**M8.2: Dual Data Sources**
- Primary: Session transcripts (detailed)
- Fallback: Workflow event log (`.workflow_log.jsonl`)
- Workflow log has less detail but sufficient for basic validation

**M8.3: Clear Documentation**
- CLAUDE.md: "Adherence validation requires session logging enabled"
- `orchestrator validate-adherence` shows clear error if no logs

**Residual Risk:** LOW (fallback to workflow log)

---

## Integration Risks

### RISK-9: Session Logging Interferes with Workflow State
**Severity:** MEDIUM
**Probability:** LOW
**Impact:** Workflow state corruption, lost progress

**Scenarios:**
1. SessionLogger modifies workflow state accidentally
2. Race conditions between logging and state updates
3. Session log conflicts with .workflow_state.json

**Mitigation Strategies:**

**M9.1: Read-Only Access**
```python
class SessionLogger:
    def __init__(self, state_manager: StateManager):
        # SessionLogger only READS state, never writes
        self._state_manager = state_manager  # Read-only reference
```

**M9.2: Separate Storage**
- Session logs: `.orchestrator/sessions/`
- Workflow state: `.workflow_state.json`
- No shared files, no conflicts

**M9.3: Atomic Operations**
- Session logging uses atomic writes (write to temp file, then rename)
- No partial writes that could corrupt logs

**M9.4: Testing**
- Integration test: run full workflow with logging enabled
- Verify state consistency before and after
- Test concurrent operations (state update + logging)

**Residual Risk:** LOW (isolated systems)

---

### RISK-10: WF-034 Meta-Workflow Creates Infinite Loop
**Severity:** LOW
**Probability:** LOW
**Impact:** Orchestrator hangs or crashes

**Scenarios:**
1. Using `orchestrator-meta.yaml` to work on orchestrator itself
2. Meta-workflow calls `orchestrator validate-adherence`
3. Validation triggers meta-workflow again (loop)

**Mitigation Strategies:**

**M10.1: Loop Detection**
```python
class WorkflowEngine:
    _recursion_depth = 0
    MAX_RECURSION_DEPTH = 3

    def start(self, task: str):
        if self._recursion_depth > self.MAX_RECURSION_DEPTH:
            raise RecursionError("Meta-workflow recursion detected")
        self._recursion_depth += 1
```

**M10.2: Explicit Opt-In**
- Meta-workflow is NOT default
- User must explicitly use `--workflow orchestrator-meta.yaml`
- Documentation warns about dogfooding complexity

**M10.3: Validation is Read-Only**
- `validate-adherence` only reads logs, doesn't modify state
- No triggers, no side effects
- Cannot start new workflows

**Residual Risk:** VERY LOW (defensive coding)

---

## Security Risks

### RISK-11: Session Logs Contain Sensitive Project Data
**Severity:** MEDIUM
**Probability:** HIGH
**Impact:** Code snippets, file paths, error messages in logs could expose sensitive info

**Scenarios:**
1. Session logs contain code snippets with business logic
2. Error messages reveal file paths, usernames, system info
3. Logs contain PII (customer data in test fixtures)

**Mitigation Strategies:**

**M11.1: Document Sensitivity**
- CLAUDE.md: "Session logs may contain code and error messages. Do not share publicly."
- Add warning to session logs: "Contains project-specific data. Do not commit to public repos."

**M11.2: .gitignore by Default**
- `.orchestrator/sessions/` in .gitignore
- Prevent accidental commits

**M11.3: Optional PII Scrubbing**
```yaml
# config.yaml
session_logging:
  scrub_pii: true  # Experimental: redact emails, names, etc.
```

**M11.4: User Control**
- User can disable session logging entirely
- User can manually delete session logs
- `orchestrator sessions cleanup --all` deletes all logs

**Residual Risk:** MEDIUM (inherent trade-off: logging vs privacy)

---

## Deployment Risks

### RISK-12: Breaking Changes in Auto-Updates
**Severity:** MEDIUM
**Probability:** LOW
**Impact:** Users auto-update to broken version, workflows fail

**Scenarios:**
1. New version of orchestrator has bug in session logging
2. Auto-update breaks existing workflows
3. User unable to roll back easily

**Mitigation Strategies:**

**M12.1: Staged Rollout**
- Release to canary users first (developer's own repos)
- Monitor for errors before broad rollout
- Use feature flags for new features

**M12.2: Version Pinning**
```yaml
# config.yaml
auto_update:
  enabled: true
  channel: stable  # stable, beta, canary
  pin_version: "2.5.0"  # Optional: don't update beyond this version
```

**M12.3: Rollback Mechanism**
```bash
# If new version breaks, roll back
orchestrator rollback --to-version 2.4.0
```

**M12.4: Comprehensive Testing**
- All new features have integration tests
- CI/CD runs full test suite before release
- Test against multiple Python versions (3.8-3.12)

**Residual Risk:** LOW (staged rollout + testing)

---

## Risk Summary Table

| Risk | Severity | Probability | Residual Risk | Key Mitigation |
|------|----------|-------------|---------------|----------------|
| RISK-1: Secret leakage | CRITICAL | MEDIUM | LOW | Multi-layer scrubbing, validation |
| RISK-2: Performance overhead | HIGH | MEDIUM | LOW | Async logging, <5% overhead |
| RISK-3: Storage growth | MEDIUM | HIGH | LOW | Auto-cleanup, compression |
| RISK-4: Parsing brittleness | MEDIUM | MEDIUM | LOW | Structured logging (JSONL) |
| RISK-5: Breaking workflows | MEDIUM | MEDIUM | LOW | Version lock, backward compat |
| RISK-6: False positives | MEDIUM | MEDIUM | LOW | Conservative validation, overrides |
| RISK-7: Feedback fatigue | LOW | HIGH | LOW | Smart prompting, optional |
| RISK-8: Circular dependency | MEDIUM | LOW | LOW | Dual data sources, graceful degradation |
| RISK-9: State corruption | MEDIUM | LOW | LOW | Read-only access, separate storage |
| RISK-10: Infinite loop | LOW | LOW | VERY LOW | Loop detection, opt-in |
| RISK-11: Sensitive data exposure | MEDIUM | HIGH | MEDIUM | .gitignore, documentation, user control |
| RISK-12: Breaking updates | MEDIUM | LOW | LOW | Staged rollout, testing |

---

## Risk Acceptance

**Accepted Risks:**
1. **RISK-11 (Sensitive data in logs):** Residual risk MEDIUM - Inherent trade-off between debugging and privacy. Mitigation: user control, .gitignore, documentation.

**All other risks mitigated to LOW or VERY LOW.**

---

## Monitoring and Rollback Plan

**Monitoring:**
- Track session logging overhead (performance metrics)
- Monitor secret scrubbing effectiveness (test suite)
- Track adherence validation accuracy (false positive rate)
- Monitor user feedback on new features

**Rollback Triggers:**
- Session logging adds >10% overhead
- Secret leakage detected in logs (critical)
- Adherence validation false positive rate >20%
- User reports breaking changes

**Rollback Process:**
1. Disable feature via config flag (immediate)
2. Release hotfix to revert changes (within 24 hours)
3. Communicate issue to users (GitHub issue, CHANGELOG)
4. Post-mortem and fix root cause

---

## Conclusion

**Risk Assessment:** MEDIUM overall risk, but all critical/high risks have concrete mitigations.

**Key Success Factors:**
1. Multi-layer secret scrubbing (RISK-1)
2. Async logging with <5% overhead (RISK-2)
3. Structured logging format (RISK-4)
4. Backward compatibility for workflows (RISK-5)
5. Comprehensive testing (RISK-12)

**Recommendation:** **PROCEED** with implementation. Risks are manageable with planned mitigations.
