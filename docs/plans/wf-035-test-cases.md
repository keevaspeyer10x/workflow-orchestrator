# WF-035 Test Cases

## Test Strategy Overview

### Testing Pyramid
```
        ┌─────────────────┐
        │  Integration    │  ← End-to-end workflows (2 tests)
        │     Tests       │
        ├─────────────────┤
        │   Unit Tests    │  ← Component logic (15 tests)
        │                 │
        ├─────────────────┤
        │ Smoke Tests     │  ← Quick sanity (2 tests)
        └─────────────────┘
```

**Test Coverage Goals:**
- Unit tests: 90%+ coverage for new code
- Integration tests: Cover happy path + key error paths
- Smoke tests: Validate orchestrator dogfooding

---

## Unit Tests

### 1. Supervision Mode Configuration

#### Test: `test_supervision_mode_defaults_to_supervised()`
**File:** `tests/test_supervision_mode.py`
**Purpose:** Verify backward compatibility - workflows without supervision_mode default to supervised

```python
def test_supervision_mode_defaults_to_supervised():
    """Workflows without supervision_mode should default to supervised."""
    settings = WorkflowSettings()  # No supervision_mode specified
    assert settings.supervision_mode == "supervised"
```

**Expected:** PASS - Default is supervised

---

#### Test: `test_supervision_mode_validation()`
**File:** `tests/test_supervision_mode.py`
**Purpose:** Invalid supervision modes should be rejected

```python
@pytest.mark.parametrize("invalid_mode", [
    "invalid",
    "zero-human",  # Typo (should be zero_human)
    "SUPERVISED",  # Wrong case
    "",
    None
])
def test_supervision_mode_validation(invalid_mode):
    """Invalid supervision modes should raise validation error."""
    with pytest.raises(ValueError, match="supervision_mode must be one of"):
        WorkflowSettings(supervision_mode=invalid_mode)
```

**Expected:** PASS - All invalid modes rejected

---

#### Test: `test_valid_supervision_modes()`
**File:** `tests/test_supervision_mode.py`
**Purpose:** All valid modes should be accepted

```python
@pytest.mark.parametrize("valid_mode", ["supervised", "zero_human", "hybrid"])
def test_valid_supervision_modes(valid_mode):
    """All valid supervision modes should be accepted."""
    settings = WorkflowSettings(supervision_mode=valid_mode)
    assert settings.supervision_mode == valid_mode
```

**Expected:** PASS - supervised, zero_human, hybrid all accepted

---

### 2. Gate Skipping Logic

#### Test: `test_supervised_mode_blocks_manual_gates()`
**File:** `tests/test_gate_skipping.py`
**Purpose:** In supervised mode, manual gates should block (current behavior)

```python
def test_supervised_mode_blocks_manual_gates():
    """In supervised mode, manual gates should NOT be skipped."""
    settings = WorkflowSettings(supervision_mode="supervised")
    manager = StateManager(settings)

    gate_item = WorkflowItem(
        id="user_approval",
        name="User Approval",
        verification={"type": "manual_gate"}
    )

    should_skip = manager.handle_manual_gate(gate_item)
    assert should_skip is False  # Should NOT skip
```

**Expected:** PASS - Gate blocks in supervised mode

---

#### Test: `test_zero_human_mode_skips_manual_gates()`
**File:** `tests/test_gate_skipping.py`
**Purpose:** In zero_human mode, manual gates should be auto-skipped

```python
def test_zero_human_mode_skips_manual_gates():
    """In zero_human mode, manual gates should be skipped."""
    settings = WorkflowSettings(supervision_mode="zero_human")
    manager = StateManager(settings)

    gate_item = WorkflowItem(
        id="user_approval",
        name="User Approval",
        verification={"type": "manual_gate"}
    )

    should_skip = manager.handle_manual_gate(gate_item)
    assert should_skip is True  # Should skip
```

**Expected:** PASS - Gate skipped in zero_human mode

---

#### Test: `test_gate_skip_logged_with_warning()`
**File:** `tests/test_gate_skipping.py`
**Purpose:** When gate is skipped, warning should be logged for audit trail

```python
def test_gate_skip_logged_with_warning(caplog):
    """Skipped gates should log warning for audit trail."""
    settings = WorkflowSettings(supervision_mode="zero_human")
    manager = StateManager(settings)

    gate_item = WorkflowItem(id="user_approval", name="User Approval")

    with caplog.at_level(logging.WARNING):
        manager.handle_manual_gate(gate_item)

    assert "ZERO-HUMAN MODE" in caplog.text
    assert "Skipping manual gate: user_approval" in caplog.text
```

**Expected:** PASS - Warning logged

---

### 3. Review Fallback System

#### Test: `test_review_fallback_on_primary_failure()`
**File:** `tests/test_review_fallbacks.py`
**Purpose:** When primary model fails, fallback should be tried

```python
@pytest.mark.asyncio
async def test_review_fallback_on_primary_failure():
    """When primary model fails, should try fallback."""
    settings = ReviewSettings(
        fallbacks={
            "codex": ["openai/gpt-5.1", "anthropic/claude-opus-4"]
        }
    )
    engine = ReviewEngine(settings)

    # Mock: Primary fails, first fallback succeeds
    with mock.patch.object(engine, '_call_primary_model', side_effect=Exception("API Error")):
        with mock.patch.object(engine, '_call_fallback_model', return_value={"issues": []}):
            result = await engine.run_review_with_fallback("codex", [], "diff")

    assert result is not None
    assert result["model_used"] == "openai/gpt-5.1"  # Fallback used
```

**Expected:** PASS - Fallback tried and succeeded

---

#### Test: `test_review_fallback_exhausted()`
**File:** `tests/test_review_fallbacks.py`
**Purpose:** When all fallbacks fail, should return None

```python
@pytest.mark.asyncio
async def test_review_fallback_exhausted():
    """When all fallbacks fail, should return None."""
    settings = ReviewSettings(
        fallbacks={
            "codex": ["openai/gpt-5.1", "anthropic/claude-opus-4"]
        }
    )
    engine = ReviewEngine(settings)

    # Mock: All models fail
    with mock.patch.object(engine, '_call_primary_model', side_effect=Exception("Fail")):
        with mock.patch.object(engine, '_call_fallback_model', side_effect=Exception("Fail")):
            result = await engine.run_review_with_fallback("codex", [], "diff")

    assert result is None  # All fallbacks exhausted
```

**Expected:** PASS - Returns None when all fallbacks fail

---

#### Test: `test_minimum_reviews_met()`
**File:** `tests/test_review_fallbacks.py`
**Purpose:** When minimum reviews met, workflow should continue

```python
def test_minimum_reviews_met():
    """When minimum reviews met, should return True."""
    settings = ReviewSettings(minimum_required=3)
    engine = ReviewEngine(settings)

    completed_reviews = ["codex", "gemini", "grok"]  # 3 reviews
    result = engine.check_minimum_reviews(completed_reviews)

    assert result is True  # Minimum met, continue
```

**Expected:** PASS - 3 of 5 reviews is sufficient

---

#### Test: `test_insufficient_reviews_warn_mode()`
**File:** `tests/test_review_fallbacks.py`
**Purpose:** In warn mode, insufficient reviews should log warning but continue

```python
def test_insufficient_reviews_warn_mode(caplog):
    """In warn mode, insufficient reviews should log warning."""
    settings = ReviewSettings(
        minimum_required=3,
        on_insufficient_reviews="warn"
    )
    engine = ReviewEngine(settings)

    completed_reviews = ["codex"]  # Only 1 review

    with caplog.at_level(logging.WARNING):
        result = engine.check_minimum_reviews(completed_reviews)

    assert result is False  # Threshold not met
    assert "Only 1 of 3 required reviews completed" in caplog.text
```

**Expected:** PASS - Warning logged, workflow continues

---

#### Test: `test_insufficient_reviews_block_mode()`
**File:** `tests/test_review_fallbacks.py`
**Purpose:** In block mode, insufficient reviews should raise exception

```python
def test_insufficient_reviews_block_mode():
    """In block mode, insufficient reviews should block workflow."""
    settings = ReviewSettings(
        minimum_required=3,
        on_insufficient_reviews="block"
    )
    engine = ReviewEngine(settings)

    completed_reviews = ["codex"]  # Only 1 review

    with pytest.raises(InsufficientReviewsError, match="Only 1 of 3"):
        engine.check_minimum_reviews(completed_reviews)
```

**Expected:** PASS - Exception raised, workflow blocked

---

### 4. Smoke Test Framework

#### Test: `test_smoke_test_command_execution()`
**File:** `tests/test_smoke_tests.py`
**Purpose:** Smoke test command should execute and capture output

```python
def test_smoke_test_command_execution():
    """Smoke test command should execute successfully."""
    settings = WorkflowSettings(smoke_test_command="echo 'test passed'")
    manager = StateManager(settings)

    result = manager.execute_smoke_test()

    assert result.returncode == 0
    assert "test passed" in result.stdout
```

**Expected:** PASS - Command executes successfully

---

#### Test: `test_smoke_test_failure_captured()`
**File:** `tests/test_smoke_tests.py`
**Purpose:** Failed smoke tests should be captured with exit code

```python
def test_smoke_test_failure_captured():
    """Failed smoke tests should return non-zero exit code."""
    settings = WorkflowSettings(smoke_test_command="exit 1")
    manager = StateManager(settings)

    result = manager.execute_smoke_test()

    assert result.returncode == 1  # Failed
```

**Expected:** PASS - Failure captured

---

#### Test: `test_smoke_test_skipped_when_not_defined()`
**File:** `tests/test_smoke_tests.py`
**Purpose:** When smoke_test_command not set, item should be skippable

```python
def test_smoke_test_skipped_when_not_defined():
    """When smoke_test_command not set, smoke test should be skippable."""
    settings = WorkflowSettings()  # No smoke_test_command
    manager = StateManager(settings)

    item = WorkflowItem(
        id="automated_smoke_test",
        skip_conditions=["no_smoke_tests_defined"]
    )

    should_skip = manager.should_skip_item(item)
    assert should_skip is True  # Skip when not defined
```

**Expected:** PASS - Item skipped when command not set

---

### 5. OpenRouter Integration

#### Test: `test_openrouter_api_call()`
**File:** `tests/test_openrouter.py`
**Purpose:** OpenRouter API should be callable with correct format

```python
@pytest.mark.asyncio
async def test_openrouter_api_call():
    """OpenRouter API should accept correct request format."""
    provider = OpenRouterProvider(api_key="test_key")

    with aioresponses() as mock_api:
        mock_api.post(
            "https://openrouter.ai/api/v1/chat/completions",
            payload={
                "choices": [{"message": {"content": "Review result"}}]
            }
        )

        result = await provider.call_model(
            model="openai/gpt-5.1",
            prompt="Review this code"
        )

    assert result == "Review result"
```

**Expected:** PASS - API called correctly

---

#### Test: `test_openrouter_api_key_missing()`
**File:** `tests/test_openrouter.py`
**Purpose:** Missing API key should raise clear error

```python
def test_openrouter_api_key_missing():
    """Missing OpenRouter API key should raise error."""
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        OpenRouterProvider(api_key=None)
```

**Expected:** PASS - Clear error for missing API key

---

## Integration Tests

### 6. End-to-End Zero-Human Workflow

#### Test: `test_zero_human_workflow_completes_autonomously()`
**File:** `tests/integration/test_zero_human_workflow.py`
**Purpose:** Full workflow in zero_human mode should complete without manual intervention

```python
def test_zero_human_workflow_completes_autonomously():
    """Zero-human workflow should complete without human gates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create workflow with zero_human mode
        create_test_workflow(tmpdir, supervision_mode="zero_human")

        # Start workflow
        subprocess.run(
            ["orchestrator", "start", "Test autonomous"],
            cwd=tmpdir,
            check=True
        )

        # Complete all non-gate items
        complete_all_items(tmpdir)

        # Verify workflow can finish (no blocked gates)
        result = subprocess.run(
            ["orchestrator", "status"],
            cwd=tmpdir,
            capture_output=True,
            text=True
        )

        # Should not have any blocking gates
        assert "Blockers:" not in result.stdout or \
               "user_approval" not in result.stdout

        # Should be able to advance through all phases
        for phase in ["plan", "execute", "review", "verify", "learn"]:
            subprocess.run(["orchestrator", "advance"], cwd=tmpdir, check=True)

        # Should be able to finish
        result = subprocess.run(
            ["orchestrator", "finish"],
            cwd=tmpdir,
            capture_output=True,
            text=True
        )
        assert "WORKFLOW COMPLETED" in result.stdout
```

**Expected:** PASS - Workflow completes autonomously

---

#### Test: `test_supervised_workflow_blocks_at_gates()`
**File:** `tests/integration/test_supervised_workflow.py`
**Purpose:** Supervised workflow should still block at manual gates (backward compatibility)

```python
def test_supervised_workflow_blocks_at_gates():
    """Supervised workflow should block at manual gates (default behavior)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create workflow with supervised mode (default)
        create_test_workflow(tmpdir, supervision_mode="supervised")

        # Start workflow
        subprocess.run(
            ["orchestrator", "start", "Test supervised"],
            cwd=tmpdir,
            check=True
        )

        # Try to advance past PLAN phase (has user_approval gate)
        result = subprocess.run(
            ["orchestrator", "advance"],
            cwd=tmpdir,
            capture_output=True,
            text=True
        )

        # Should be blocked by user_approval
        assert "user_approval" in result.stdout
        assert "Blockers:" in result.stdout or "pending" in result.stdout
```

**Expected:** PASS - Gate blocks in supervised mode

---

### 7. Review Fallback Integration

#### Test: `test_review_fallback_when_primary_api_down()`
**File:** `tests/integration/test_review_integration.py`
**Purpose:** When primary review API unavailable, fallback should be used

```python
@pytest.mark.asyncio
async def test_review_fallback_when_primary_api_down():
    """When primary API down, fallback should be used automatically."""
    # Mock primary API as down
    with mock.patch.dict(os.environ, {"OPENAI_API_KEY": ""}):  # Primary unavailable
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}):
            settings = ReviewSettings(
                fallbacks={
                    "codex": ["openai/gpt-5.1"]  # OpenRouter fallback
                }
            )
            engine = ReviewEngine(settings)

            # Mock OpenRouter success
            with aioresponses() as mock_api:
                mock_api.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    payload={"choices": [{"message": {"content": "No issues"}}]}
                )

                result = await engine.run_review_with_fallback("codex", [], "diff")

            assert result is not None
            assert result["model_used"] == "openai/gpt-5.1"  # Fallback used
```

**Expected:** PASS - Fallback used when primary down

---

## Smoke Tests (Dogfooding)

### 8. Orchestrator CLI Smoke Test

#### Test: `test_orchestrator_cli_works()`
**File:** `tests/smoke/test_orchestrator_cli.py`
**Purpose:** Validate orchestrator CLI is functional (dogfooding)

```python
def test_orchestrator_cli_works():
    """Orchestrator CLI should respond to basic commands."""
    # Test --version
    result = subprocess.run(
        ["orchestrator", "--version"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "workflow-orchestrator" in result.stdout.lower()

    # Test status (even with no workflow)
    result = subprocess.run(
        ["orchestrator", "status"],
        capture_output=True,
        text=True
    )
    # Should not crash (exit code may be non-zero if no workflow)
    assert "No active workflow" in result.stdout or "Phase:" in result.stdout
```

**Expected:** PASS - CLI responds correctly

---

### 9. Workflow Lifecycle Smoke Test

#### Test: `test_workflow_lifecycle_basic()`
**File:** `tests/smoke/test_workflow_lifecycle.py`
**Purpose:** Basic workflow operations work (start, status, complete, finish)

```python
def test_workflow_lifecycle_basic():
    """Basic workflow lifecycle should work."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create minimal workflow
        create_minimal_workflow(tmpdir)

        # Start
        result = subprocess.run(
            ["orchestrator", "start", "Smoke test"],
            cwd=tmpdir,
            capture_output=True
        )
        assert result.returncode == 0

        # Status
        result = subprocess.run(
            ["orchestrator", "status"],
            cwd=tmpdir,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "Smoke test" in result.stdout

        # Complete item
        result = subprocess.run(
            ["orchestrator", "complete", "test_item", "--notes", "Done"],
            cwd=tmpdir,
            capture_output=True
        )
        assert result.returncode == 0
```

**Expected:** PASS - Basic operations work

---

## Test Execution Plan

### Local Development
```bash
# Unit tests (fast, run frequently)
pytest tests/ -v --ignore=tests/integration/ --ignore=tests/smoke/

# Integration tests (slower, run before commit)
pytest tests/integration/ -v

# Smoke tests (quick sanity check)
pytest tests/smoke/ -v

# All tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=src/workflow_orchestrator --cov-report=html
```

### CI/CD (GitHub Actions)
```yaml
- name: Run Unit Tests
  run: pytest tests/ -v --ignore=tests/integration/ --cov=src

- name: Run Integration Tests
  run: pytest tests/integration/ -v

- name: Run Smoke Tests
  run: pytest tests/smoke/ -v
```

---

## Coverage Goals

| Component | Target Coverage | Why |
|-----------|----------------|-----|
| `models.py` (supervision_mode) | 100% | Critical config, must be bulletproof |
| `state_manager.py` (gate logic) | 95% | Core workflow logic |
| `review_engine.py` (fallbacks) | 90% | Complex async code, need thorough testing |
| `review_providers.py` (OpenRouter) | 85% | External API, focus on error handling |
| CLI commands | 80% | Integration-level coverage sufficient |

**Overall Target:** 90%+ coverage for new code

---

## Test Data & Fixtures

### Fixture: `create_test_workflow()`
```python
def create_test_workflow(tmpdir, supervision_mode="supervised"):
    """Create minimal test workflow."""
    workflow_content = f"""
version: "1.0"
settings:
  supervision_mode: "{supervision_mode}"
  smoke_test_command: "echo 'test passed'"
phases:
  - id: "plan"
    name: "Plan"
    items:
      - id: "user_approval"
        name: "User Approval"
        verification:
          type: "manual_gate"
"""
    workflow_path = os.path.join(tmpdir, "workflow.yaml")
    with open(workflow_path, "w") as f:
        f.write(workflow_content)
    return workflow_path
```

### Fixture: `mock_review_api()`
```python
@pytest.fixture
def mock_review_api():
    """Mock review API responses."""
    with aioresponses() as mock_api:
        # Mock primary model
        mock_api.post(
            "https://api.openai.com/v1/chat/completions",
            payload={"choices": [{"message": {"content": "Review result"}}]}
        )
        # Mock OpenRouter fallback
        mock_api.post(
            "https://openrouter.ai/api/v1/chat/completions",
            payload={"choices": [{"message": {"content": "Fallback result"}}]}
        )
        yield mock_api
```

---

## Manual Test Cases (For User Validation)

### Manual Test 1: Zero-Human Workflow End-to-End
**Steps:**
1. Create test project with `workflow.yaml` containing `supervision_mode: "zero_human"`
2. Run `orchestrator start "Test feature"`
3. Observe that `user_approval` is auto-skipped with warning
4. Complete implementation items
5. Observe that `manual_smoke_test` is auto-skipped
6. Run `orchestrator finish`

**Expected:** Workflow completes without manual gates blocking

---

### Manual Test 2: Review Fallback Behavior
**Steps:**
1. Set `OPENAI_API_KEY=""` (simulate primary API down)
2. Set `OPENROUTER_API_KEY=<valid_key>`
3. Run workflow with REVIEW phase
4. Check `.workflow_log.jsonl` for fallback usage

**Expected:** Logs show fallback model used, review completes successfully

---

### Manual Test 3: Backward Compatibility
**Steps:**
1. Use existing `workflow.yaml` WITHOUT `supervision_mode` setting
2. Run `orchestrator start "Test"`
3. Observe behavior at `user_approval` gate

**Expected:** Gate blocks (supervised mode is default), no breaking changes

---

## Test Completion Criteria

- [ ] All 15 unit tests written and passing
- [ ] Both integration tests passing (zero_human + supervised)
- [ ] Both smoke tests passing (CLI + lifecycle)
- [ ] Code coverage ≥90% for new code
- [ ] All manual test cases validated by user
- [ ] CI/CD pipeline includes all test suites
- [ ] Test documentation complete (this file)
