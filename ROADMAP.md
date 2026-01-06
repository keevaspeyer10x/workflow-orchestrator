# Workflow Orchestrator Roadmap

This document tracks planned improvements, deferred features, and audit recommendations for the workflow orchestrator.

---

## Visual Verification Improvements

### High Priority

#### VV-001: Auto-load Style Guide in Visual Verification
**Status:** Planned  
**Complexity:** Low  
**Description:** When `style_guide_path` is configured in workflow.yaml, automatically include the style guide content in all visual verification evaluations without requiring explicit calls to `verify_with_style_guide()`.

**Current Behavior:**
- Must explicitly call `verify_with_style_guide()` method
- Or manually pass style guide content to `verify()`

**Desired Behavior:**
- If `style_guide_path` is set and file exists, automatically load and include in all `verify()` calls
- Add `include_style_guide: true/false` parameter to override

**Implementation Notes:**
- Modify `VisualVerificationClient.__init__()` to load style guide if path provided
- Update `verify()` to automatically append style guide content to specification
- Add setting `auto_include_style_guide: true` (default) to workflow.yaml

---

#### VV-002: Workflow Step Integration for Visual Tests
**Status:** Planned  
**Complexity:** Medium  
**Description:** Wire the visual verification into the `visual_regression_test` workflow step so tests run automatically during the VERIFY phase.

**Current Behavior:**
- CLI commands exist (`visual-verify`, `visual-template`)
- `visual_regression_test` step exists but doesn't auto-run tests

**Desired Behavior:**
- During `visual_regression_test` step, automatically:
  1. Find all test files in `tests/visual/` directory
  2. Parse each test file for URL and specification
  3. Run verification against configured `app_url` setting
  4. Report results and fail workflow if any test fails

**Implementation Notes:**
- Add `app_url` setting to workflow.yaml (the deployed URL to test against)
- Create `run_all_visual_tests()` function in visual_verification.py
- Parse markdown test files for structured test data
- Integrate with orchestrator's item completion logic

**Dependencies:**
- Requires deployed application URL to be known
- Requires test files in `tests/visual/` directory

---

#### VV-003: Visual Test Discovery
**Status:** Planned  
**Complexity:** Low  
**Description:** Automatically discover and run all visual test files in the `tests/visual/` directory.

**Current Behavior:**
- Must specify each test file/URL manually via CLI

**Desired Behavior:**
- `./orchestrator visual-verify-all` scans `tests/visual/*.md`
- Each file contains URL, specification, and expected behavior
- Runs all tests and reports aggregate results

**Implementation Notes:**
- Define test file format (YAML frontmatter + markdown body)
- Add `visual-verify-all` CLI command
- Support filtering by tag/feature

---

### Medium Priority

#### VV-004: Baseline Screenshot Management
**Status:** Planned  
**Complexity:** Medium  
**Description:** Store baseline screenshots and compare against them for regression detection.

**Current Behavior:**
- Each verification is independent, no comparison to previous state

**Desired Behavior:**
- Option to save screenshots as baselines
- Compare new screenshots against baselines
- Flag visual differences for review

**Implementation Notes:**
- Store baselines in `tests/visual/baselines/` directory
- Add `--save-baseline` flag to CLI
- Consider image diff library for pixel comparison
- AI evaluation for semantic comparison

---

#### VV-005: CI/CD Integration
**Status:** Planned  
**Complexity:** Medium  
**Description:** GitHub Actions workflow for running visual tests on PR/push.

**Implementation Notes:**
- Create `.github/workflows/visual-tests.yml`
- Run against preview/staging deployment
- Post results as PR comment
- Block merge on failure

---

### Low Priority

#### VV-006: Cost Tracking for Visual Tests
**Status:** Planned  
**Complexity:** Low  
**Description:** Track Claude API usage and costs for visual verification calls.

**Implementation Notes:**
- Log token usage from API responses
- Aggregate per-test and per-run costs
- Add `--show-cost` flag to CLI

---

## Security Improvements

### SEC-001: HTTPS Enforcement
**Status:** Planned  
**Complexity:** Low  
**Source:** Security Review (Score: 7/10)  
**Description:** Validate that `visual_verification_url` uses HTTPS to prevent API key transmission over insecure connections.

**Implementation:**
```python
if not service_url.startswith('https://'):
    raise VisualVerificationError("Service URL must use HTTPS")
```

---

### SEC-002: Input Validation
**Status:** Planned  
**Complexity:** Low  
**Source:** Security Review  
**Description:** Add validation for URLs, viewport dimensions, and action parameters.

**Implementation Notes:**
- Validate URL format using `urllib.parse`
- Validate viewport width/height are positive integers within reasonable bounds
- Validate action types against allowed list

---

### SEC-003: Exception Message Sanitization
**Status:** Planned  
**Complexity:** Low  
**Source:** Security Review  
**Description:** Sanitize exception messages to avoid leaking sensitive information like URLs or headers.

**Implementation Notes:**
- Create wrapper that strips sensitive data from exception messages
- Log full details internally, return sanitized message to caller

---

## Architecture Improvements

### ARCH-001: Extract Retry Logic
**Status:** Planned  
**Complexity:** Low  
**Source:** Architecture Review (Score: 7/10)  
**Description:** Extract retry logic with exponential backoff into a reusable utility.

**Current State:**
- Retry logic duplicated in `verify()` method

**Desired State:**
- Reusable `@retry_with_backoff` decorator or utility function
- Configurable retry count, base delay, max delay

---

### ARCH-002: HTTP Client Dependency Injection
**Status:** Planned  
**Complexity:** Medium  
**Source:** Architecture Review  
**Description:** Allow injection of HTTP client for better testability.

**Implementation Notes:**
- Accept optional `session` parameter in `__init__`
- Default to `requests.Session()` if not provided
- Enables mocking without patching

---

## Workflow Improvements

### WF-001: Claude Code CLI Installation Check
**Status:** Planned  
**Complexity:** Low  
**Source:** Visual Verification Service task  
**Description:** Add setup phase that checks for Claude Code CLI and installs if missing.

**Implementation Notes:**
- Add `setup_requirements` section to workflow.yaml
- Check for `claude` command availability
- Provide installation instructions if missing

---

### WF-002: Available Secrets Documentation
**Status:** Planned  
**Complexity:** Low  
**Source:** Visual Verification Service task  
**Description:** Document available environment variables and secrets in workflow initialization.

**Implementation Notes:**
- Add `available_secrets` section to workflow.yaml
- Display during `orchestrator start`
- Include in generated plan template

---

### WF-003: Model Selection Guidance
**Status:** Planned  
**Complexity:** Low  
**Source:** Visual Verification Service task  
**Description:** Use "latest generation available" principle for model selection instead of hardcoding specific model names.

**Implementation Notes:**
- Add `model_preference: latest` setting
- Maintain mapping of "latest" to current best model
- Update mapping when new models released

---

## Deferred Features

These features were considered but deferred for future consideration:

### DEF-001: Video Recording of Visual Tests
**Complexity:** Medium-High  
**Reason Deferred:** Nice-to-have, not core functionality. Adds ffmpeg dependency and storage requirements.

### DEF-002: Response Caching
**Complexity:** Medium  
**Reason Deferred:** Optimization that adds complexity. Evaluate need based on actual usage patterns.

### DEF-003: Network Interception
**Complexity:** High  
**Reason Deferred:** Significant scope creep. Would change service architecture substantially.

---

## Completed Items

| ID | Description | Completed |
|----|-------------|-----------|
| - | Visual verification client implementation | 2026-01-06 |
| - | CLI commands (visual-verify, visual-template) | 2026-01-06 |
| - | Mobile viewport testing by default | 2026-01-06 |
| - | Style guide integration method | 2026-01-06 |
| - | Unit test suite (19 tests) | 2026-01-06 |
| - | Documentation (VISUAL_VERIFICATION.md) | 2026-01-06 |

---

## Contributing

When adding items to this roadmap:
1. Use the appropriate prefix (VV-, SEC-, ARCH-, WF-, DEF-)
2. Include: Status, Complexity, Description, Implementation Notes
3. For audit items, include Source reference
4. Move completed items to the Completed Items table
