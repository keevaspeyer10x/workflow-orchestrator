# Workflow Orchestrator Roadmap

This document tracks planned improvements, deferred features, and audit recommendations for the workflow orchestrator.

---

## v2.2 Enhancements (Currently Implementing)

> See `PRD_v2.2_ENHANCEMENTS.md` for full specification

### CORE-001: Provider Abstraction & OpenRouter Integration
**Status:** In Progress
**Complexity:** Medium
**Description:** Abstract the Claude Code integration into a generic provider interface to support multiple LLM backends.

**Features:**
- Generic HTTP API provider interface
- OpenRouter as default provider (requires `OPENROUTER_API_KEY`)
- Claude Code provider (refactored from existing)
- Manual provider (fallback for copy/paste)
- `--provider` and `--model` CLI flags
- Per-phase/item model selection support

---

### CORE-002: Environment Detection & Adaptation
**Status:** In Progress
**Complexity:** Low
**Description:** Auto-detect execution environment and adapt behavior accordingly.

**Features:**
- Detect Claude Code, Manus, Standalone CLI environments
- Environment-specific provider defaults
- Adapted output format per environment
- `--env` override flag

---

### CORE-003: Operating Notes System
**Status:** In Progress
**Complexity:** Low
**Description:** Add `notes` field to phases and items for embedding operational wisdom.

**Features:**
- `notes: list[str]` on PhaseDef and ChecklistItemDef
- Optional categorization: `[tip]`, `[caution]`, `[learning]`, `[context]`
- Display in status recitation and handoff prompts
- Learning engine suggests note additions

---

### CORE-004: Task Constraints Flag
**Status:** In Progress
**Complexity:** Low
**Description:** Allow task-specific guidance without modifying workflow.yaml.

**Features:**
- `--constraints` flag on `orchestrator start`
- Stored in workflow state
- Included in all recitation and handoff output

---

### CORE-005: Checkpoint/Resume System
**Status:** In Progress
**Complexity:** Medium
**Description:** Enable saving workflow state with context summaries for resumption in fresh context.

**Features:**
- `orchestrator checkpoint` - Save state with context summary
- `orchestrator resume` - Restore and generate handoff prompt
- `orchestrator checkpoints` - List available checkpoints
- Auto-checkpoint on phase transitions (configurable)
- Context recovery data: decisions, file manifest, summary

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

### DEF-004: Sub-Agent Type Hints
**Complexity:** Low
**Reason Deferred:** `agent_hint` field on items (explore, plan, execute). Deferred until provider abstraction settles.

### DEF-005: Tool Result Compression
**Complexity:** Low
**Reason Deferred:** Change handoff prompts to reference files rather than include content. Optimize later if needed.

### DEF-006: Slack Integration
**Complexity:** Medium
**Reason Deferred:** Slack bot/channel for workflow notifications, approval requests, status updates. Future consideration.

### DEF-007: GitHub Integration
**Complexity:** Medium
**Reason Deferred:** Create issues from workflow items, link PRs to phases, auto-complete on merge. Future consideration.

### DEF-008: VS Code Extension
**Complexity:** High
**Reason Deferred:** Sidebar showing workflow status, click to complete/skip. Future consideration.

### DEF-009: Workflow Templates Library
**Complexity:** Medium
**Reason Deferred:** Pre-built workflows for common tasks. `orchestrator init --template bugfix`. Future consideration.

### DEF-010: Distributed/Team Workflows
**Complexity:** High
**Reason Deferred:** Multiple agents on same workflow, locking/claiming items. Complex, long-term.

### DEF-011: LLM-Assisted Workflow Generation
**Complexity:** Medium
**Reason Deferred:** Describe task, LLM generates workflow.yaml. Experimental idea.

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
| - | Core workflow engine with phase/item state machine | 2026-01-05 |
| - | YAML-based workflow definitions | 2026-01-05 |
| - | Active verification (file_exists, command, manual_gate) | 2026-01-05 |
| - | Claude Code CLI integration | 2026-01-05 |
| - | Analytics and learning engine | 2026-01-05 |
| - | Web dashboard | 2026-01-05 |
| - | Security hardening (injection protection, path traversal) | 2026-01-05 |
| - | Version-locked workflow definitions in state | 2026-01-05 |
| - | Template variable substitution | 2026-01-05 |

---

## Contributing

When adding items to this roadmap:
1. Use the appropriate prefix (CORE-, VV-, SEC-, ARCH-, WF-, DEF-)
2. Include: Status, Complexity, Description, Implementation Notes
3. For audit items, include Source reference
4. Move completed items to the Completed Items table
