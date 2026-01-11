# WF-035: Zero-Human Mode - Remove Manual Gate Blockers

## Implementation Plan

### Overview
Enable fully autonomous AI workflows by removing manual gate blockers and adding intelligent fallback mechanisms. This allows workflows to run end-to-end without human intervention while maintaining safety through multi-model reviews and automated testing.

### Architecture Decision
**Supervision Mode System:** Introduce a `supervision_mode` setting that controls gate behavior:
- `supervised` (default): Current behavior, requires human approval at gates
- `zero_human`: Skip manual gates with warning logs (fully autonomous)
- `hybrid`: Risk-based gates with timeout fallback (future enhancement)

---

## Phase 1: Configuration System (2 hours)

### 1.1 Update Workflow Schema
**File:** `src/workflow_orchestrator/models.py`

Add to `WorkflowSettings` model:
```python
class WorkflowSettings(BaseModel):
    supervision_mode: str = "supervised"  # supervised | zero_human | hybrid
    smoke_test_command: Optional[str] = None
    reviews: ReviewSettings = ReviewSettings()
```

Add new `ReviewSettings` model:
```python
class ReviewSettings(BaseModel):
    enabled: bool = True
    minimum_required: int = 3  # At least 3 of 5 models
    fallbacks: Dict[str, List[str]] = {
        "codex": ["openai/gpt-5.1", "anthropic/claude-opus-4"],
        "gemini": ["google/gemini-3-pro", "anthropic/claude-opus-4"],
        "grok": ["x-ai/grok-4.1", "anthropic/claude-opus-4"]
    }
    on_insufficient_reviews: str = "warn"  # warn | block
```

### 1.2 Add CLI Flag
**File:** `src/workflow_orchestrator/cli.py`

Add global option to override supervision mode:
```bash
orchestrator --supervision-mode zero_human start "Task"
```

### 1.3 Validation
Add schema validation:
- `supervision_mode` must be in: `supervised`, `zero_human`, `hybrid`
- `minimum_required` must be 1-5 (number of review models)
- `on_insufficient_reviews` must be: `warn`, `block`

---

## Phase 2: Gate Skipping Logic (3 hours)

### 2.1 Update Manual Gate Handler
**File:** `src/workflow_orchestrator/state_manager.py`

Modify `handle_manual_gate()` to check supervision mode:
```python
def handle_manual_gate(self, item: WorkflowItem) -> bool:
    """
    Returns True if gate should be skipped, False otherwise.
    """
    supervision_mode = self.state.workflow.settings.supervision_mode

    if supervision_mode == "zero_human":
        logger.warning(
            f"[ZERO-HUMAN MODE] Skipping manual gate: {item.id} ({item.name}). "
            f"Autonomous operation enabled - no human approval required."
        )
        return True  # Skip gate

    elif supervision_mode == "hybrid":
        # Future: Implement risk-based + timeout logic
        return self._evaluate_hybrid_gate(item)

    else:  # supervised (default)
        return False  # Require human approval
```

### 2.2 Update Workflow YAML
**File:** `workflow.yaml` and `src/default_workflow.yaml`

Update PLAN phase user_approval:
```yaml
- id: "user_approval"
  name: "Get User Approval"
  description: "User must approve the plan before execution (skipped in zero_human mode)"
  verification:
    type: "manual_gate"
  notes:
    - "[zero-human] Auto-skipped with warning logged"
    - "[supervised] Requires explicit approval (default behavior)"
    - "[hybrid] Auto-approves after timeout for low-risk changes (future)"
```

Update VERIFY phase manual_smoke_test:
```yaml
- id: "manual_smoke_test"
  name: "Manual Smoke Test (Deprecated)"
  description: "Manual verification of core functionality (replaced by automated_smoke_test)"
  verification:
    type: "manual_gate"
  notes:
    - "⚠️ DEPRECATED: Use automated_smoke_test instead"
    - "[zero-human] This gate is skipped in zero-human mode"
    - "[migration] Add smoke_test_command to settings to replace this"
```

### 2.3 Logging
Add structured logging for gate skips:
```python
self.log_event(
    event_type="gate_skipped",
    item_id=item.id,
    supervision_mode=supervision_mode,
    reason="zero_human_mode_enabled"
)
```

---

## Phase 3: Automated Smoke Testing (2 hours)

### 3.1 Add New VERIFY Item
**File:** `workflow.yaml` and `src/default_workflow.yaml`

Insert before `manual_smoke_test`:
```yaml
- id: "automated_smoke_test"
  name: "Automated Smoke Test"
  description: "Run automated smoke test suite to verify core functionality"
  verification:
    type: "command"
    command: "{{smoke_test_command}}"
    expect_exit_code: 0
  skip_conditions: ["no_smoke_tests_defined"]
  notes:
    - "[zero-human] Replaces manual smoke test with automation"
    - "[web] Example: playwright test tests/smoke/"
    - "[cli] Example: myapp --version && myapp validate"
    - "[api] Example: curl http://localhost:8000/health"
    - "[setup] Add smoke_test_command to settings in workflow.yaml"
```

### 3.2 Create Example Smoke Tests
**File:** `tests/smoke/test_orchestrator_cli.py`

```python
"""
Smoke tests for orchestrator CLI.
Run with: pytest tests/smoke/ -v
"""
import subprocess
import pytest

def test_orchestrator_version():
    """Verify orchestrator CLI is installed and responds."""
    result = subprocess.run(
        ["orchestrator", "--version"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "workflow-orchestrator" in result.stdout.lower()

def test_orchestrator_status_no_workflow():
    """Verify status command works (even with no active workflow)."""
    result = subprocess.run(
        ["orchestrator", "status"],
        capture_output=True,
        text=True
    )
    # Exit code may be non-zero (no workflow), but should not crash
    assert "No active workflow" in result.stdout or "Phase:" in result.stdout
```

**File:** `tests/smoke/test_workflow_lifecycle.py`

```python
"""
Smoke test for basic workflow lifecycle.
"""
import subprocess
import tempfile
import os
import shutil

def test_workflow_start_and_status():
    """Test that workflows can be started and status retrieved."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create minimal workflow.yaml
        workflow_content = """
version: "1.0"
phases:
  - id: "test"
    name: "Test Phase"
    items:
      - id: "test_item"
        name: "Test Item"
        description: "Test"
"""
        workflow_path = os.path.join(tmpdir, "workflow.yaml")
        with open(workflow_path, "w") as f:
            f.write(workflow_content)

        # Start workflow
        result = subprocess.run(
            ["orchestrator", "start", "Smoke test"],
            cwd=tmpdir,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        # Check status
        result = subprocess.run(
            ["orchestrator", "status"],
            cwd=tmpdir,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "Smoke test" in result.stdout
```

### 3.3 Update Settings Example
**File:** `workflow.yaml`

Add example smoke_test_command to settings:
```yaml
settings:
  supervision_mode: "supervised"  # supervised | zero_human | hybrid
  smoke_test_command: "pytest tests/smoke/ -v --tb=short"
  test_command: "pytest tests/ -v"
  build_command: "python -m build"
```

---

## Phase 4: Visual Regression Documentation (1 hour)

### 4.1 Update VERIFY Phase Item
**File:** `workflow.yaml` and `src/default_workflow.yaml`

Update visual_regression_test with detailed Playwright guidance:
```yaml
- id: "visual_regression_test"
  name: "Visual Regression Test (Playwright)"
  description: "Automated visual regression testing using Playwright screenshots"
  verification:
    type: "command"
    command: "playwright test --grep @visual"
  skip_conditions: ["no_ui_changes", "backend_only", "api_only", "cli_only"]
  notes:
    - "[tool] Uses Playwright for screenshot capture and comparison"
    - "[install] npm install -D @playwright/test"
    - "[baseline] First run: playwright test --update-snapshots"
    - "[compare] Subsequent runs compare to baseline in tests/screenshots/"
    - "[ci] In CI mode, never update snapshots (fail on mismatch)"
    - "[threshold] Configure pixel diff threshold in playwright.config.ts"
    - "[example] See tests/visual/example.spec.ts for reference"
    - "[docs] Full guide: https://playwright.dev/docs/test-snapshots"
```

### 4.2 Create Example Visual Test
**File:** `tests/visual/example.spec.ts`

```typescript
/**
 * Example Playwright visual regression test.
 * Run with: playwright test --grep @visual
 * Update baseline: playwright test --update-snapshots
 */
import { test, expect } from '@playwright/test';

test('homepage visual regression @visual', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.waitForLoadState('networkidle');

  // Compare full page
  await expect(page).toHaveScreenshot('homepage.png', {
    maxDiffPixels: 100,  // Allow up to 100 pixel diff
  });
});

test('dashboard visual regression @visual', async ({ page }) => {
  await page.goto('http://localhost:3000/dashboard');
  await page.waitForLoadState('networkidle');

  // Compare specific element
  const dashboard = page.locator('[data-testid="dashboard"]');
  await expect(dashboard).toHaveScreenshot('dashboard-widget.png');
});
```

### 4.3 Create Visual Testing Guide
**File:** `docs/VISUAL_TESTING.md`

```markdown
# Visual Regression Testing Guide

## Overview
Visual regression tests detect unintended UI changes by comparing screenshots.

## Setup (Playwright)

1. **Install Playwright:**
   ```bash
   npm install -D @playwright/test
   npx playwright install
   ```

2. **Create test file:**
   ```typescript
   // tests/visual/homepage.spec.ts
   import { test, expect } from '@playwright/test';

   test('homepage @visual', async ({ page }) => {
     await page.goto('http://localhost:3000');
     await expect(page).toHaveScreenshot();
   });
   ```

3. **Generate baseline:**
   ```bash
   playwright test --update-snapshots
   ```

4. **Run tests:**
   ```bash
   playwright test --grep @visual
   ```

## Workflow Integration

Add to workflow.yaml:
```yaml
- id: "visual_regression_test"
  verification:
    type: "command"
    command: "playwright test --grep @visual"
```

## CI/CD Best Practices

- Never update snapshots in CI (fail on mismatch)
- Use consistent viewport sizes
- Wait for network idle before capturing
- Configure pixel diff threshold for minor differences
```

---

## Phase 5: Review Fallback System (4 hours)

### 5.1 Update Review Configuration
**File:** `src/workflow_orchestrator/review_engine.py`

Add fallback logic to review execution:
```python
async def run_review_with_fallback(
    self,
    model_key: str,
    files_changed: List[str],
    diff_content: str
) -> Optional[Dict]:
    """
    Run review with fallback chain if primary fails.

    Fallback order:
    1. Try primary model (e.g., openai/gpt-5.2-codex-max)
    2. Try OpenRouter fallback (e.g., openai/gpt-5.1)
    3. Try secondary fallback (e.g., anthropic/claude-opus-4)
    """
    settings = self.workflow.settings.reviews
    primary_model = self._get_primary_model(model_key)
    fallback_chain = settings.fallbacks.get(model_key, [])

    # Try primary
    try:
        return await self._call_review_model(primary_model, files_changed, diff_content)
    except Exception as e:
        logger.warning(f"Primary model {primary_model} failed: {e}")

    # Try fallbacks
    for fallback_model in fallback_chain:
        try:
            logger.info(f"Trying fallback model: {fallback_model}")
            result = await self._call_review_model(fallback_model, files_changed, diff_content)
            self.log_fallback_used(model_key, fallback_model)
            return result
        except Exception as e:
            logger.warning(f"Fallback model {fallback_model} failed: {e}")
            continue

    logger.error(f"All fallbacks exhausted for {model_key}")
    return None

def check_minimum_reviews(self, completed_reviews: List[str]) -> bool:
    """
    Check if minimum review threshold met.
    """
    settings = self.workflow.settings.reviews
    minimum = settings.minimum_required
    completed_count = len(completed_reviews)

    if completed_count < minimum:
        if settings.on_insufficient_reviews == "block":
            raise InsufficientReviewsError(
                f"Only {completed_count} of {minimum} required reviews completed. "
                f"Workflow blocked (on_insufficient_reviews: block)"
            )
        else:  # warn
            logger.warning(
                f"Only {completed_count} of {minimum} required reviews completed. "
                f"Proceeding with warning (on_insufficient_reviews: warn)"
            )
            return False  # Continue but flag as warning

    return True  # Minimum met
```

### 5.2 Add OpenRouter Integration
**File:** `src/workflow_orchestrator/review_providers.py`

Add OpenRouter provider:
```python
class OpenRouterProvider:
    """
    OpenRouter API integration for fallback reviews.
    https://openrouter.ai/docs
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://openrouter.ai/api/v1"

    async def call_model(
        self,
        model: str,  # e.g., "openai/gpt-5.1", "anthropic/claude-opus-4"
        prompt: str,
        max_tokens: int = 4000
    ) -> str:
        """Call OpenRouter API with model."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens
                }
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return data["choices"][0]["message"]["content"]
```

### 5.3 Update Review Logging
Log which models were used (primary vs fallback):
```python
self.log_event(
    event_type="review_completed",
    model_key=model_key,
    model_used=actual_model,  # Track if fallback was used
    is_fallback=(actual_model != primary_model),
    issues_found=len(issues)
)
```

### 5.4 Update Workflow YAML
**File:** `workflow.yaml` and `src/default_workflow.yaml`

Add review settings to settings section:
```yaml
settings:
  reviews:
    enabled: true
    minimum_required: 3  # At least 3 of 5 models must succeed

    # Fallback chain when primary models unavailable
    fallbacks:
      codex:
        - "openai/gpt-5.1"           # OpenRouter fallback
        - "anthropic/claude-opus-4"  # Secondary fallback
      gemini:
        - "google/gemini-3-pro"      # OpenRouter fallback
        - "anthropic/claude-opus-4"  # Secondary fallback
      grok:
        - "x-ai/grok-4.1"            # OpenRouter fallback
        - "anthropic/claude-opus-4"  # Secondary fallback

    # Behavior when minimum not met
    on_insufficient_reviews: "warn"  # warn | block
```

---

## Phase 6: Integration & Testing (4 hours)

### 6.1 Update Both Workflow Files
Ensure changes are applied to:
- `workflow.yaml` (project-specific)
- `src/default_workflow.yaml` (bundled template)

### 6.2 Add Unit Tests
**File:** `tests/test_supervision_mode.py`

```python
"""Tests for supervision mode and gate skipping."""
import pytest
from workflow_orchestrator.state_manager import StateManager
from workflow_orchestrator.models import WorkflowSettings

def test_supervised_mode_blocks_gates():
    """In supervised mode, manual gates should block."""
    settings = WorkflowSettings(supervision_mode="supervised")
    manager = StateManager(settings)

    item = create_manual_gate_item()
    should_skip = manager.handle_manual_gate(item)
    assert should_skip is False  # Should NOT skip

def test_zero_human_mode_skips_gates():
    """In zero_human mode, manual gates should be skipped."""
    settings = WorkflowSettings(supervision_mode="zero_human")
    manager = StateManager(settings)

    item = create_manual_gate_item()
    should_skip = manager.handle_manual_gate(item)
    assert should_skip is True  # Should skip

def test_invalid_supervision_mode():
    """Invalid supervision mode should raise validation error."""
    with pytest.raises(ValueError):
        WorkflowSettings(supervision_mode="invalid_mode")
```

**File:** `tests/test_review_fallbacks.py`

```python
"""Tests for review fallback system."""
import pytest
from workflow_orchestrator.review_engine import ReviewEngine
from workflow_orchestrator.models import ReviewSettings

@pytest.mark.asyncio
async def test_fallback_on_primary_failure():
    """When primary model fails, should try fallback."""
    settings = ReviewSettings(
        fallbacks={
            "codex": ["openai/gpt-5.1", "anthropic/claude-opus-4"]
        }
    )
    engine = ReviewEngine(settings)

    # Mock: Primary fails, fallback succeeds
    with mock_primary_failure(), mock_fallback_success():
        result = await engine.run_review_with_fallback("codex", [], "diff")
        assert result is not None
        assert result["model_used"] == "openai/gpt-5.1"  # Fallback used

@pytest.mark.asyncio
async def test_minimum_reviews_met():
    """When minimum reviews met, workflow should continue."""
    settings = ReviewSettings(minimum_required=3)
    engine = ReviewEngine(settings)

    completed = ["codex", "gemini", "grok"]  # 3 reviews
    assert engine.check_minimum_reviews(completed) is True

@pytest.mark.asyncio
async def test_insufficient_reviews_warn():
    """When insufficient reviews and mode=warn, should log warning."""
    settings = ReviewSettings(
        minimum_required=3,
        on_insufficient_reviews="warn"
    )
    engine = ReviewEngine(settings)

    completed = ["codex"]  # Only 1 review
    assert engine.check_minimum_reviews(completed) is False  # Continue with warning
```

### 6.3 Integration Test
**File:** `tests/integration/test_zero_human_workflow.py`

```python
"""
End-to-end test of zero-human workflow.
"""
import subprocess
import tempfile
import os

def test_zero_human_workflow_completes_autonomously():
    """Test that zero_human workflow runs without manual intervention."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create workflow with zero_human mode
        workflow_content = """
version: "1.0"
settings:
  supervision_mode: "zero_human"
  smoke_test_command: "echo 'smoke test passed'"
  reviews:
    enabled: false  # Disable for speed in test
phases:
  - id: "plan"
    name: "Plan"
    items:
      - id: "user_approval"
        name: "User Approval"
        verification:
          type: "manual_gate"
  - id: "verify"
    name: "Verify"
    items:
      - id: "automated_smoke_test"
        name: "Smoke Test"
        verification:
          type: "command"
          command: "{{smoke_test_command}}"
"""
        workflow_path = os.path.join(tmpdir, "workflow.yaml")
        with open(workflow_path, "w") as f:
            f.write(workflow_content)

        # Start workflow
        subprocess.run(
            ["orchestrator", "start", "Test zero-human"],
            cwd=tmpdir,
            check=True
        )

        # Verify user_approval was skipped (not blocked)
        result = subprocess.run(
            ["orchestrator", "status"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            check=True
        )

        # In zero_human mode, should see gate was skipped
        assert "user_approval" in result.stdout
        # Should not be blocked waiting for approval
        assert "Blockers:" not in result.stdout or "user_approval" not in result.stdout
```

### 6.4 Update Documentation
**File:** `CLAUDE.md`

Add section on zero-human mode:
```markdown
## Zero-Human Mode (Autonomous Workflows)

Enable fully autonomous workflows that run without manual gates:

```bash
# Start workflow in zero-human mode
orchestrator --supervision-mode zero_human start "Task"

# Or configure in workflow.yaml
settings:
  supervision_mode: "zero_human"
```

**What happens in zero-human mode:**
- Manual gates (user_approval, manual_smoke_test) are auto-skipped
- Warnings logged for each skipped gate
- Automated smoke tests run instead of manual verification
- Review fallbacks ensure minimum coverage even if models fail
- Fully autonomous operation from start to finish
```

**File:** `CHANGELOG.md`

Add entry:
```markdown
## [Unreleased]

### Added
- **Zero-Human Mode:** Enable fully autonomous workflows with `supervision_mode: "zero_human"` (WF-035)
  - Auto-skip manual gates (user_approval, manual_smoke_test) with warning logs
  - Automated smoke testing framework replaces manual verification
  - Review fallback system ensures minimum coverage (3 of 5 models)
  - OpenRouter integration for fallback models
  - Default: `supervised` mode (backward compatible)
- Automated smoke test framework with example tests in `tests/smoke/`
- Visual regression testing guide with Playwright examples
- Review fallback configuration: minimum_required, fallback chains, graceful degradation

### Changed
- Manual gates now respect `supervision_mode` setting
- Visual regression test includes detailed Playwright setup documentation
- Review system uses OpenRouter for fallback when primary models unavailable
```

---

## Testing Strategy

### Unit Tests
- ✅ `test_supervision_mode.py` - Gate skipping logic
- ✅ `test_review_fallbacks.py` - Fallback chain and minimum thresholds
- ✅ `test_smoke_tests.py` - Smoke test command execution

### Integration Tests
- ✅ `test_zero_human_workflow.py` - End-to-end autonomous workflow
- ✅ `test_review_degradation.py` - Graceful degradation with failed reviews

### Smoke Tests (Dogfooding)
- ✅ `tests/smoke/test_orchestrator_cli.py` - CLI works
- ✅ `tests/smoke/test_workflow_lifecycle.py` - Basic workflow operations

---

## Rollout Plan

### Phase 1: Ship with `supervised` Default
- No breaking changes for existing users
- New workflows default to `supervised` mode (current behavior)
- Users opt-in to `zero_human` mode explicitly

### Phase 2: Documentation & Examples
- Add zero-human examples to docs/
- Blog post explaining autonomous workflows
- Video tutorial showing zero-human mode

### Phase 3: Collect Feedback
- Monitor GitHub issues for zero-human mode bugs
- Gather feedback on fallback behavior
- Iterate on hybrid mode design (future)

---

## Success Metrics

1. **Autonomy:** Zero-human workflows complete without human intervention (0 blocked gates)
2. **Reliability:** Review fallbacks prevent workflow failures (>=3 reviews complete even with 2 model failures)
3. **Safety:** Smoke tests catch regressions before merge (0 broken deployments from skipped manual tests)
4. **Adoption:** 20% of workflows use zero-human mode within 3 months

---

## Files Changed

### Core Implementation
- `src/workflow_orchestrator/models.py` - Add supervision_mode, ReviewSettings
- `src/workflow_orchestrator/state_manager.py` - Gate skipping logic
- `src/workflow_orchestrator/review_engine.py` - Fallback system
- `src/workflow_orchestrator/review_providers.py` - OpenRouter integration
- `src/workflow_orchestrator/cli.py` - Add --supervision-mode flag

### Workflow Templates
- `workflow.yaml` - Add supervision_mode, smoke_test_command, review fallbacks
- `src/default_workflow.yaml` - Same updates (bundled template)

### Tests
- `tests/test_supervision_mode.py` - Unit tests
- `tests/test_review_fallbacks.py` - Unit tests
- `tests/integration/test_zero_human_workflow.py` - E2E test
- `tests/smoke/test_orchestrator_cli.py` - Smoke tests
- `tests/smoke/test_workflow_lifecycle.py` - Smoke tests
- `tests/visual/example.spec.ts` - Visual regression example

### Documentation
- `CLAUDE.md` - Zero-human mode guide
- `CHANGELOG.md` - Release notes
- `docs/VISUAL_TESTING.md` - Playwright guide
- `README.md` - Update features section

### Examples
- `tests/visual/example.spec.ts` - Playwright visual test
- `playwright.config.ts` - Playwright configuration (new file)

---

## Estimated Timeline

| Phase | Hours | Description |
|-------|-------|-------------|
| Phase 1 | 2 | Configuration system |
| Phase 2 | 3 | Gate skipping logic |
| Phase 3 | 2 | Automated smoke testing |
| Phase 4 | 1 | Visual regression docs |
| Phase 5 | 4 | Review fallback system |
| Phase 6 | 4 | Integration & testing |
| **Total** | **16** | **Complete implementation** |

---

## Dependencies

### External Libraries
- `aiohttp` - For OpenRouter API calls (already installed)
- `pydantic` - For settings validation (already installed)

### API Keys Required
- `OPENROUTER_API_KEY` - For review fallbacks
- (Existing review keys: OPENAI_API_KEY, GEMINI_API_KEY, XAI_API_KEY)

### Optional
- Playwright (for visual regression testing) - User installs per-project

---

## Backward Compatibility

✅ **100% Backward Compatible**

- Default `supervision_mode: "supervised"` maintains current behavior
- Existing workflows without supervision_mode setting default to `supervised`
- All new fields optional with sensible defaults
- No breaking changes to CLI or API
- Existing tests continue to pass
