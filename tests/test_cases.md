# Test Cases: CORE-024 & WF-034

## Test Strategy

**Test Levels:**
1. **Unit Tests** - Test individual functions and classes in isolation
2. **Integration Tests** - Test component interactions (SessionLogger + SecretsManager, AdherenceValidator + SessionLogger)
3. **End-to-End Tests** - Test full workflows with logging and validation
4. **Manual Tests** - User acceptance testing for CLI commands and output formats

**Coverage Goals:**
- Unit test coverage: >90%
- Integration test coverage: >80%
- Critical paths: 100% (secret scrubbing, validation logic)

---

## CORE-024 Test Cases

### Unit Tests - SessionLogger

#### TC-CORE-024-U-001: Session Initialization
**Description:** Test session creation with valid task description

**Test Steps:**
```python
def test_session_initialization():
    logger = SessionLogger(session_dir=tmp_dir, secrets_manager=mock_secrets)
    session = logger.start_session("Implement feature X")

    assert session.session_id is not None
    assert session.task_description == "Implement feature X"
    assert session.start_time is not None
    assert session.log_file.exists()
```

**Expected Result:** Session created with unique ID, log file created in `.orchestrator/sessions/`

**Priority:** HIGH

---

#### TC-CORE-024-U-002: Session ID Format
**Description:** Test session ID follows naming convention

**Test Steps:**
```python
def test_session_id_format():
    logger = SessionLogger(session_dir=tmp_dir, secrets_manager=mock_secrets)
    session = logger.start_session("Implement CORE-024")

    # Format: YYYY-MM-DD_HH-MM-SS_task-slug
    assert re.match(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_\w+', session.session_id)
```

**Expected Result:** Session ID follows format: `2026-01-12_14-30-15_implement-core-024`

**Priority:** MEDIUM

---

#### TC-CORE-024-U-003: Event Logging
**Description:** Test logging various event types

**Test Steps:**
```python
def test_event_logging():
    logger = SessionLogger(session_dir=tmp_dir, secrets_manager=mock_secrets)
    session = logger.start_session("Test workflow")

    logger.log_event("command", {"command": "orchestrator status"})
    logger.log_event("output", {"text": "Phase: PLAN"})
    logger.log_event("error", {"message": "Test failed"})

    session_log = read_session_log(session.log_file)
    assert len(session_log["events"]) == 3
    assert session_log["events"][0]["type"] == "command"
```

**Expected Result:** All events logged with correct types and data

**Priority:** HIGH

---

### Unit Tests - Secret Scrubbing

#### TC-CORE-024-U-004: Pattern-Based Secret Scrubbing
**Description:** Test scrubbing of API keys, tokens, and other secrets using regex patterns

**Test Steps:**
```python
def test_pattern_based_scrubbing():
    scrubber = SecretScrubber(secrets_manager=None)

    # Test various secret formats
    assert scrubber.scrub("API_KEY=sk-abc123def456") == "API_KEY=[REDACTED:API_KEY]"
    assert scrubber.scrub("Bearer eyJhbGciOiJIUz...") == "Bearer [REDACTED:TOKEN]"
    assert scrubber.scrub("https://user:pass@example.com") == "https://[REDACTED:CREDENTIALS]@example.com"
```

**Expected Result:** Secrets detected and redacted with appropriate labels

**Priority:** CRITICAL (security)

---

#### TC-CORE-024-U-005: SecretsManager Integration Scrubbing
**Description:** Test scrubbing of known secrets from SecretsManager

**Test Steps:**
```python
def test_secrets_manager_scrubbing():
    mock_secrets = MockSecretsManager()
    mock_secrets.add_secret("OPENAI_API_KEY", "sk-1234567890abcdef")

    scrubber = SecretScrubber(secrets_manager=mock_secrets)
    text = "Using key: sk-1234567890abcdef to call API"
    result = scrubber.scrub(text)

    assert "sk-1234567890abcdef" not in result
    assert "[REDACTED:OPENAI_API_KEY]" in result
```

**Expected Result:** Known secrets from SecretsManager are redacted with their names

**Priority:** CRITICAL (security)

---

#### TC-CORE-024-U-006: Multi-Layer Scrubbing
**Description:** Test that all scrubbing layers are applied (pattern + SecretsManager + heuristic)

**Test Steps:**
```python
def test_multi_layer_scrubbing():
    mock_secrets = MockSecretsManager()
    mock_secrets.add_secret("CUSTOM_TOKEN", "custom_secret_value")

    scrubber = SecretScrubber(secrets_manager=mock_secrets)
    text = """
    API_KEY=sk-unknown123
    CUSTOM_TOKEN=custom_secret_value
    Random long string: aB3dEf9H1jKlMnOpQrStUvWxYzAbCdEfGh
    """
    result = scrubber.scrub(text)

    # Layer 1: Known secret from SecretsManager
    assert "custom_secret_value" not in result
    assert "[REDACTED:CUSTOM_TOKEN]" in result

    # Layer 2: Pattern-based (API_KEY)
    assert "sk-unknown123" not in result

    # Layer 3: Heuristic (long alphanumeric string)
    assert "aB3dEf9H1jKlMnOpQrStUvWxYzAbCdEfGh" not in result
```

**Expected Result:** All secret types detected and scrubbed

**Priority:** CRITICAL (security)

---

#### TC-CORE-024-U-007: Scrubbing Doesn't Over-Redact
**Description:** Test that scrubbing doesn't redact safe content

**Test Steps:**
```python
def test_no_false_positives():
    scrubber = SecretScrubber(secrets_manager=None)

    safe_text = """
    File path: /home/user/project/src/main.py
    Short string: abc123
    Email: user@example.com
    Hex color: #FF5733
    """
    result = scrubber.scrub(safe_text)

    # Should NOT be redacted
    assert "/home/user/project/src/main.py" in result
    assert "abc123" in result  # Too short for heuristic
    assert "user@example.com" in result
    assert "#FF5733" in result
```

**Expected Result:** Safe content is not redacted (no false positives)

**Priority:** HIGH

---

#### TC-CORE-024-U-008: Scrubbing Performance
**Description:** Test that scrubbing is fast enough for real-time logging

**Test Steps:**
```python
def test_scrubbing_performance():
    scrubber = SecretScrubber(secrets_manager=mock_secrets)
    large_text = "Some text " * 1000  # 10 KB of text

    start_time = time.time()
    result = scrubber.scrub(large_text)
    duration = time.time() - start_time

    # Should complete in <1ms per KB
    assert duration < 0.01  # 10ms for 10KB = 1ms/KB
```

**Expected Result:** Scrubbing completes within performance budget (<1ms/KB)

**Priority:** HIGH

---

### Unit Tests - Session Analysis

#### TC-CORE-024-U-009: Completion Rate Calculation
**Description:** Test calculation of workflow completion rate

**Test Steps:**
```python
def test_completion_rate():
    sessions = [
        SessionContext(status="completed"),
        SessionContext(status="completed"),
        SessionContext(status="abandoned"),
        SessionContext(status="completed"),
    ]

    analyzer = SessionAnalyzer()
    completion_rate = analyzer.completion_rate(sessions)

    assert completion_rate == 0.75  # 3/4 = 75%
```

**Expected Result:** Correct completion rate calculated

**Priority:** MEDIUM

---

#### TC-CORE-024-U-010: Failure Point Detection
**Description:** Test identification of most common failure points

**Test Steps:**
```python
def test_failure_point_detection():
    sessions = [
        SessionContext(failed_phase="REVIEW"),
        SessionContext(failed_phase="REVIEW"),
        SessionContext(failed_phase="EXECUTE"),
        SessionContext(failed_phase="REVIEW"),
    ]

    analyzer = SessionAnalyzer()
    failure_points = analyzer.failure_points(sessions)

    assert failure_points["REVIEW"] == 3
    assert failure_points["EXECUTE"] == 1
```

**Expected Result:** Failure points correctly counted and ranked

**Priority:** MEDIUM

---

### Integration Tests - SessionLogger + WorkflowEngine

#### TC-CORE-024-I-001: Full Workflow Logging
**Description:** Test that entire workflow is logged from start to finish

**Test Steps:**
```python
def test_full_workflow_logging(tmp_dir):
    engine = WorkflowEngine(session_logger=SessionLogger(tmp_dir))
    engine.start_workflow("Test task")

    engine.complete_item("check_roadmap")
    engine.advance_phase()
    engine.finish_workflow()

    session_log = read_session_log(tmp_dir)
    assert "workflow_started" in [e["type"] for e in session_log["events"]]
    assert "item_completed" in [e["type"] for e in session_log["events"]]
    assert "phase_advanced" in [e["type"] for e in session_log["events"]]
    assert "workflow_finished" in [e["type"] for e in session_log["events"]]
```

**Expected Result:** All workflow events logged in order

**Priority:** HIGH

---

#### TC-CORE-024-I-002: No Secrets in Session Log File
**Description:** Integration test verifying no secrets written to disk

**Test Steps:**
```python
def test_no_secrets_on_disk(tmp_dir):
    secrets_manager = RealSecretsManager()
    secrets_manager.set_secret("TEST_SECRET", "super_secret_value_12345")

    logger = SessionLogger(tmp_dir, secrets_manager)
    session = logger.start_session("Test")

    logger.log_event("command", {"command": "export TEST_SECRET=super_secret_value_12345"})
    logger.end_session("completed")

    # Read raw log file
    log_content = session.log_file.read_text()

    # Verify secret NOT in file
    assert "super_secret_value_12345" not in log_content
    # Verify redaction marker IS in file
    assert "[REDACTED:TEST_SECRET]" in log_content
```

**Expected Result:** Secret values never written to disk, only redaction markers

**Priority:** CRITICAL (security)

---

### Integration Tests - CLI Commands

#### TC-CORE-024-I-003: `orchestrator sessions list` Command
**Description:** Test listing all sessions

**Test Steps:**
```bash
# Setup: Create 3 sessions
orchestrator start "Task 1" && orchestrator finish
orchestrator start "Task 2" && orchestrator finish
orchestrator start "Task 3" && orchestrator finish

# Test
output=$(orchestrator sessions list)

# Verify
assert output contains "Task 1"
assert output contains "Task 2"
assert output contains "Task 3"
assert output contains 3 session IDs
```

**Expected Result:** All sessions listed with task descriptions

**Priority:** HIGH

---

#### TC-CORE-024-I-004: `orchestrator sessions view` Command
**Description:** Test viewing a session transcript

**Test Steps:**
```bash
# Setup
orchestrator start "Test task" && orchestrator finish
session_id=$(orchestrator sessions list | grep "Test task" | awk '{print $1}')

# Test
output=$(orchestrator sessions view $session_id)

# Verify
assert output contains "Test task"
assert output contains "workflow_started"
assert output contains "workflow_finished"
```

**Expected Result:** Session transcript displayed with all events

**Priority:** HIGH

---

#### TC-CORE-024-I-005: `orchestrator sessions analyze` Command
**Description:** Test session analysis output

**Test Steps:**
```bash
# Setup: Create sessions with various outcomes
for i in {1..10}; do
    orchestrator start "Task $i"
    if [ $((i % 3)) -eq 0 ]; then
        # Abandon 1/3 of workflows
        orchestrator finish --abandon
    else
        orchestrator finish
    fi
done

# Test
output=$(orchestrator sessions analyze --last 10)

# Verify
assert output contains "Workflow Completion Rate: 67%"
assert output contains "Total Sessions: 10"
assert output contains "Most Common Failure Point"
```

**Expected Result:** Analysis shows accurate statistics

**Priority:** MEDIUM

---

### End-to-End Tests

#### TC-CORE-024-E2E-001: Full Workflow with Real Secrets
**Description:** E2E test with real secrets to verify scrubbing works end-to-end

**Test Steps:**
1. Set up real secrets using SOPS or env vars
2. Start workflow
3. Execute commands that use secrets (API calls, git operations)
4. Complete workflow
5. Read session log file
6. Verify no secrets in log

**Expected Result:** Real secrets are scrubbed in actual session logs

**Priority:** CRITICAL (security)

**Environment:** Requires real secrets (run in CI with test secrets)

---

#### TC-CORE-024-E2E-002: Performance Overhead Measurement
**Description:** Measure actual performance overhead of session logging

**Test Steps:**
1. Run workflow without session logging (baseline)
2. Run identical workflow with session logging enabled
3. Compare execution times
4. Calculate overhead percentage

**Expected Result:** Overhead <5% of baseline execution time

**Priority:** HIGH

**Metrics:**
- Baseline time: X seconds
- With logging: Y seconds
- Overhead: ((Y - X) / X) * 100% < 5%

---

## WF-034 Test Cases

### Unit Tests - AdherenceValidator

#### TC-WF-034-U-001: Plan Agent Detection
**Description:** Test detection of Plan agent usage

**Test Steps:**
```python
def test_plan_agent_detection():
    session_log = create_mock_session([
        {"type": "tool_use", "tool": "Task", "params": {"subagent_type": "Plan"}},
        {"type": "tool_use", "tool": "Task", "params": {"subagent_type": "general-purpose"}},
    ])

    validator = AdherenceValidator(session_log)
    result = validator.check_plan_agent_usage()

    assert result.used == True
    assert result.confidence == "high"
```

**Expected Result:** Plan agent usage detected correctly

**Priority:** MEDIUM

---

#### TC-WF-034-U-002: Parallel Execution Detection (Positive Case)
**Description:** Test detection of correct parallel execution (multiple Task calls in single message)

**Test Steps:**
```python
def test_parallel_execution_correct():
    session_log = create_mock_session([
        {
            "type": "assistant_message",
            "tool_uses": [
                {"tool": "Task", "description": "Implement auth"},
                {"tool": "Task", "description": "Implement API"},
                {"tool": "Task", "description": "Write tests"},
            ]
        }
    ])

    validator = AdherenceValidator(session_log)
    result = validator.check_parallel_execution()

    assert result.correct == True
    assert result.parallel_count == 3
```

**Expected Result:** Parallel execution detected as correct

**Priority:** HIGH

---

#### TC-WF-034-U-003: Parallel Execution Detection (Negative Case)
**Description:** Test detection of incorrect sequential execution

**Test Steps:**
```python
def test_parallel_execution_incorrect():
    session_log = create_mock_session([
        {"type": "assistant_message", "tool_uses": [{"tool": "Task", "description": "Implement auth"}]},
        {"type": "user_message", "content": "OK"},
        {"type": "assistant_message", "tool_uses": [{"tool": "Task", "description": "Implement API"}]},
        {"type": "user_message", "content": "OK"},
        {"type": "assistant_message", "tool_uses": [{"tool": "Task", "description": "Write tests"}]},
    ])

    validator = AdherenceValidator(session_log)
    result = validator.check_parallel_execution()

    assert result.correct == False
    assert result.sequential_count == 3
    assert "separate messages" in result.explanation
```

**Expected Result:** Sequential execution detected as incorrect

**Priority:** HIGH

---

#### TC-WF-034-U-004: Review Detection
**Description:** Test detection of third-party model reviews

**Test Steps:**
```python
def test_review_detection():
    workflow_log = create_mock_workflow_log([
        {"type": "review_completed", "model": "gemini-2.0-flash", "result": "passed"},
        {"type": "review_completed", "model": "gpt-5.2-max", "result": "passed"},
        {"type": "review_completed", "model": "claude-opus-4", "result": "passed"},
    ])

    validator = AdherenceValidator(workflow_log=workflow_log)
    result = validator.check_reviews()

    assert result.reviews_performed == 3
    assert result.models == ["gemini-2.0-flash", "gpt-5.2-max", "claude-opus-4"]
    assert result.all_passed == True
```

**Expected Result:** Reviews correctly counted and validated

**Priority:** MEDIUM

---

#### TC-WF-034-U-005: Agent Verification Detection
**Description:** Test detection of agent output verification (Read tool calls after Task completions)

**Test Steps:**
```python
def test_agent_verification():
    session_log = create_mock_session([
        {"type": "tool_use", "tool": "Task", "description": "Implement feature"},
        {"type": "tool_result", "tool": "Task", "status": "completed"},
        {"type": "tool_use", "tool": "Read", "file": "src/feature.py"},
        {"type": "tool_use", "tool": "Read", "file": "tests/test_feature.py"},
    ])

    validator = AdherenceValidator(session_log)
    result = validator.check_agent_verification()

    assert result.verifications == 2  # 2 Read calls after Task completion
    assert result.verified == True
```

**Expected Result:** Agent verification detected when files read after Task completion

**Priority:** MEDIUM

---

#### TC-WF-034-U-006: Adherence Score Calculation
**Description:** Test overall adherence score calculation

**Test Steps:**
```python
def test_adherence_score():
    validator = AdherenceValidator(session_log, workflow_log)

    # Mock results: 5/7 criteria met
    validator._check_results = {
        "plan_agent": CheckResult(passed=True),
        "parallel_execution": CheckResult(passed=False),
        "reviews": CheckResult(passed=True),
        "verification": CheckResult(passed=True),
        "status_checks": CheckResult(passed=True),
        "required_items": CheckResult(passed=True),
        "learnings": CheckResult(passed=False),
    }

    score = validator.calculate_score()
    assert score == pytest.approx(0.71, abs=0.01)  # 5/7 = 71%
```

**Expected Result:** Score calculated correctly as percentage of criteria met

**Priority:** MEDIUM

---

### Integration Tests - WF-034 Workflow Changes

#### TC-WF-034-I-001: Phase 0 Item Appears in PLAN Phase
**Description:** Test that `parallel_execution_check` item appears when workflow started

**Test Steps:**
```bash
orchestrator start "Test task"
output=$(orchestrator status)

assert output contains "parallel_execution_check"
assert output contains "Assess Parallel Execution Opportunity"
assert output contains "[critical] Are there 2+ independent tasks"
```

**Expected Result:** New planning guidance item appears in PLAN phase

**Priority:** HIGH

---

#### TC-WF-034-I-002: Phase 1 Item Appears in LEARN Phase
**Description:** Test that `workflow_adherence_check` item appears in LEARN phase

**Test Steps:**
```bash
orchestrator start "Test task"
# Complete all phases until LEARN
orchestrator advance  # to EXECUTE
orchestrator advance  # to REVIEW
orchestrator advance  # to VERIFY
orchestrator advance  # to LEARN

output=$(orchestrator status)

assert output contains "workflow_adherence_check"
assert output contains "Workflow Adherence Self-Assessment"
assert output contains "[check] Did you use parallel agents"
```

**Expected Result:** Self-assessment checklist appears in LEARN phase

**Priority:** HIGH

---

### Integration Tests - Feedback Capture

#### TC-WF-034-I-003: Feedback Capture Interactive Mode
**Description:** Test interactive feedback capture

**Test Steps:**
```bash
orchestrator start "Test" && orchestrator finish

# Simulate interactive input
orchestrator feedback --interactive <<EOF
yes
Parallel execution worked well
Coordination overhead
Better task decomposition
yes
Good first experience
EOF

# Verify feedback saved
cat .workflow_feedback.jsonl | jq -r '.multi_agents_used'
assert output == "true"
```

**Expected Result:** Feedback captured and saved to JSONL file

**Priority:** MEDIUM

---

#### TC-WF-034-I-004: Feedback Schema Validation
**Description:** Test that feedback follows correct schema

**Test Steps:**
```python
def test_feedback_schema():
    feedback_file = Path(".workflow_feedback.jsonl")
    feedback = json.loads(feedback_file.read_text())

    # Required fields
    assert "workflow_id" in feedback
    assert "task" in feedback
    assert "timestamp" in feedback
    assert "multi_agents_used" in feedback
    assert "what_went_well" in feedback

    # Timestamp is valid ISO 8601
    datetime.fromisoformat(feedback["timestamp"])
```

**Expected Result:** Feedback follows defined schema with all required fields

**Priority:** MEDIUM

---

### End-to-End Tests - Full Adherence Validation

#### TC-WF-034-E2E-001: Full Workflow with Adherence Validation
**Description:** E2E test of entire workflow with validation

**Test Steps:**
1. Start workflow
2. Use Plan agent (correct)
3. Launch parallel agents in single message (correct)
4. Run third-party reviews (correct)
5. Verify agent output by reading files (correct)
6. Run frequent status checks (correct)
7. Complete all required items (correct)
8. Document detailed learnings (correct)
9. Finish workflow
10. Run `orchestrator validate-adherence`

**Expected Result:** Adherence score 100% (7/7 criteria met)

**Priority:** HIGH

---

#### TC-WF-034-E2E-002: Workflow with Violations
**Description:** E2E test with intentional adherence violations

**Test Steps:**
1. Start workflow
2. Skip Plan agent (violation)
3. Launch agents sequentially in separate messages (violation)
4. Skip third-party reviews (violation)
5. Don't verify agent output (violation)
6. Rarely check status (violation)
7. Skip required items (violation)
8. Minimal learnings (violation)
9. Finish workflow
10. Run `orchestrator validate-adherence`

**Expected Result:** Adherence score 0% (0/7 criteria met), all violations detected

**Priority:** HIGH

---

### Manual Test Cases

#### TC-CORE-024-M-001: Session Log Readability
**Description:** Manual verification that session logs are human-readable

**Test Steps:**
1. Run a workflow with session logging
2. Open session log file in text editor
3. Verify format is readable
4. Check that events are in chronological order
5. Verify timestamps are clear

**Expected Result:** Session log is easy to read and understand for debugging

**Priority:** MEDIUM

---

#### TC-CORE-024-M-002: Secret Scrubbing Visual Verification
**Description:** Manual spot-check of secret scrubbing in logs

**Test Steps:**
1. Set up test secrets
2. Run workflow that uses secrets
3. Open session log file
4. Search for secret values (should not find)
5. Verify redaction markers present

**Expected Result:** No secrets visible, all replaced with `[REDACTED:*]` markers

**Priority:** CRITICAL (security)

---

#### TC-WF-034-M-001: Adherence Report Readability
**Description:** Manual verification that adherence validation output is clear

**Test Steps:**
1. Run workflow
2. Run `orchestrator validate-adherence`
3. Review output
4. Check that violations are clearly explained
5. Verify recommendations are actionable

**Expected Result:** Adherence report is clear, actionable, and helpful

**Priority:** MEDIUM

---

## Test Data

### Mock Session Logs

**Good Parallel Execution:**
```json
{
  "events": [
    {
      "type": "assistant_message",
      "timestamp": "2026-01-12T14:30:00Z",
      "tool_uses": [
        {"tool": "Task", "description": "Implement auth", "subagent_type": "general-purpose"},
        {"tool": "Task", "description": "Implement API", "subagent_type": "general-purpose"},
        {"tool": "Task", "description": "Write tests", "subagent_type": "general-purpose"}
      ]
    }
  ]
}
```

**Bad Sequential Execution:**
```json
{
  "events": [
    {"type": "assistant_message", "timestamp": "2026-01-12T14:30:00Z", "tool_uses": [{"tool": "Task", "description": "Implement auth"}]},
    {"type": "user_message", "timestamp": "2026-01-12T14:35:00Z", "content": "Done"},
    {"type": "assistant_message", "timestamp": "2026-01-12T14:36:00Z", "tool_uses": [{"tool": "Task", "description": "Implement API"}]}
  ]
}
```

### Test Secrets

**Safe Test Secrets (for unit/integration tests):**
```
TEST_API_KEY=sk-test-1234567890abcdef
TEST_TOKEN=Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
TEST_PASSWORD=super_secret_password_123
```

**NOTE:** Never use real secrets in tests. Always use mock values.

---

## Test Execution Plan

### Phase 1: Unit Tests (Day 1-2)
- CORE-024 unit tests (SessionLogger, SecretScrubber)
- WF-034 unit tests (AdherenceValidator)
- Goal: >90% unit test coverage

### Phase 2: Integration Tests (Day 3-4)
- CORE-024 integration (SessionLogger + WorkflowEngine)
- WF-034 integration (AdherenceValidator + SessionLogger)
- CLI command tests
- Goal: >80% integration test coverage

### Phase 3: E2E Tests (Day 5)
- Full workflow with logging and validation
- Performance overhead measurement
- Security verification (no secrets in logs)

### Phase 4: Manual Tests (Day 6)
- User acceptance testing
- Output readability verification
- Documentation review

---

## Test Automation

**Continuous Integration:**
```yaml
# .github/workflows/test.yml
name: Test CORE-024 & WF-034
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run unit tests
        run: pytest tests/test_session_logger.py tests/test_adherence_validator.py -v
      - name: Run integration tests
        run: pytest tests/integration/ -v
      - name: Security scan (no secrets in logs)
        run: |
          pytest tests/test_security.py -v
          grep -r "sk-[a-zA-Z0-9]" .orchestrator/sessions/ && exit 1 || exit 0
```

---

## Success Criteria

**Test Phase Complete When:**
- [ ] All unit tests pass (>90% coverage)
- [ ] All integration tests pass (>80% coverage)
- [ ] All E2E tests pass
- [ ] Security tests verify no secrets in logs (100% pass rate)
- [ ] Performance tests show <5% overhead
- [ ] Manual tests confirm output readability
- [ ] CI/CD pipeline runs all tests automatically

---

## Test Metrics

**Target Metrics:**
- Unit test coverage: >90%
- Integration test coverage: >80%
- E2E test coverage: 100% of critical paths
- Secret scrubbing accuracy: 100% (no false negatives)
- False positive rate: <5% (scrubbing doesn't over-redact)
- Performance overhead: <5% of baseline execution time
- Test execution time: <2 minutes for full suite

---

## Notes

**Testing Philosophy:**
- Test behavior, not implementation
- Use real components (avoid excessive mocking)
- Test critical paths exhaustively (security, validation logic)
- Automated tests run on every commit
- Manual tests for UX verification

**Test Data Management:**
- Use fixtures for common test data
- Never commit real secrets to test files
- Use temporary directories for test output
- Clean up test artifacts after each test
