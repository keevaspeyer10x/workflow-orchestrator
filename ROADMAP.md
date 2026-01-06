# Workflow Orchestrator Roadmap

This document tracks planned improvements, deferred features, and audit recommendations for the workflow orchestrator.

---

## v2.2 Enhancements (COMPLETED)

> See `PRD_v2.2_ENHANCEMENTS.md` for full specification

### CORE-001: Provider Abstraction & OpenRouter Integration
**Status:** ✅ Completed (2026-01-06)
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
**Status:** ✅ Completed (2026-01-06)
**Complexity:** Low
**Description:** Auto-detect execution environment and adapt behavior accordingly.

**Features:**
- Detect Claude Code, Manus, Standalone CLI environments
- Environment-specific provider defaults
- Adapted output format per environment
- `--env` override flag

---

### CORE-003: Operating Notes System
**Status:** ✅ Completed (2026-01-06)
**Complexity:** Low
**Description:** Add `notes` field to phases and items for embedding operational wisdom.

**Features:**
- `notes: list[str]` on PhaseDef and ChecklistItemDef
- Optional categorization: `[tip]`, `[caution]`, `[learning]`, `[context]`
- Display in status recitation and handoff prompts
- Learning engine suggests note additions

---

### CORE-004: Task Constraints Flag
**Status:** ✅ Completed (2026-01-06)
**Complexity:** Low
**Description:** Allow task-specific guidance without modifying workflow.yaml.

**Features:**
- `--constraints` flag on `orchestrator start`
- Stored in workflow state
- Included in all recitation and handoff output

---

### CORE-005: Checkpoint/Resume System
**Status:** ✅ Completed (2026-01-06)
**Complexity:** Medium
**Description:** Enable saving workflow state with context summaries for resumption in fresh context.

**Features:**
- `orchestrator checkpoint` - Save state with context summary
- `orchestrator resume` - Restore and generate handoff prompt
- `orchestrator checkpoints` - List available checkpoints
- Auto-checkpoint on phase transitions (configurable)
- Context recovery data: decisions, file manifest, summary

---

## v2.3 Recommendations (From v2.2 Implementation)

> Items identified during v2.2 implementation for future work

### Short-term (Low Effort)

#### CORE-006: Automatic Connector Detection with User Fallback
**Status:** Planned  
**Complexity:** Medium  
**Priority:** High  
**Source:** v2.2 Implementation Learning  
**Description:** Automatically detect available agent connectors and ask user before defaulting to manual implementation when preferred agent is unavailable.

**Problem Solved:**
During v2.2 implementation, Claude Code CLI was unavailable in Manus sandbox. Instead of asking the user about alternative connection methods (Manus direct connector), the agent defaulted to manual implementation. This missed an opportunity to use a specialized coding AI.

**Desired Behavior:**
1. Check for Claude Code CLI (`which claude`)
2. Check for Manus direct connector (environment detection)
3. Check for OpenRouter API key
4. If primary agent unavailable, **ASK USER** before proceeding:
   - "Claude Code CLI is not available. Would you like me to:
     a) Use Manus direct connector (detected)
     b) Use OpenRouter API
     c) Proceed with manual implementation
     d) Help me install Claude Code CLI"

**Implementation Notes:**
```python
def get_available_providers() -> List[str]:
    """Return list of available providers in priority order."""
    available = []
    if shutil.which('claude'):
        available.append('claude_code')
    if detect_manus_connector():
        available.append('manus_direct')
    if os.environ.get('OPENROUTER_API_KEY'):
        available.append('openrouter')
    available.append('manual')  # Always available
    return available

def prompt_user_for_provider(preferred: str, available: List[str]) -> str:
    """Ask user which provider to use when preferred is unavailable."""
    if preferred in available:
        return preferred
    # Generate user prompt with available options
    ...
```

**Tasks:**
- [ ] Add `detect_manus_connector()` function to environment.py
- [ ] Add `get_available_providers()` to providers/__init__.py
- [ ] Add `prompt_user_for_provider()` interactive function
- [ ] Update `handoff` command to use interactive selection when needed
- [ ] Add `--interactive` flag to force user prompt
- [ ] Document Manus direct connector access method

---

#### CORE-007: Deprecate Legacy Claude Integration
**Status:** Planned  
**Complexity:** Low  
**Priority:** Medium  
**Description:** Add deprecation warning to `claude_integration.py` and update documentation to use new provider system.

**Implementation:**
```python
# In claude_integration.py
import warnings
warnings.warn(
    "claude_integration module is deprecated. Use src.providers.claude_code instead.",
    DeprecationWarning,
    stacklevel=2
)
```

**Tasks:**
- [ ] Add deprecation warning to module import
- [ ] Update README to reference new provider system
- [ ] Remove in v3.0

---

#### CORE-008: Input Length Limits
**Status:** Planned  
**Complexity:** Low  
**Priority:** Medium  
**Source:** Security Review v2.2  
**Description:** Add length limits to user-provided constraints and notes to prevent DoS via extremely long strings.

**Implementation:**
```python
MAX_CONSTRAINT_LENGTH = 1000
MAX_NOTE_LENGTH = 500

def validate_constraint(constraint: str) -> str:
    if len(constraint) > MAX_CONSTRAINT_LENGTH:
        raise ValueError(f"Constraint exceeds {MAX_CONSTRAINT_LENGTH} characters")
    return constraint
```

**Tasks:**
- [ ] Add `MAX_CONSTRAINT_LENGTH` constant (1000 chars)
- [ ] Add `MAX_NOTE_LENGTH` constant (500 chars)
- [ ] Validate in CLI before storing
- [ ] Add tests for validation

---

#### CORE-009: Constraints File Flag
**Status:** Planned  
**Complexity:** Low  
**Priority:** Low  
**Description:** Add `--constraints-file` flag to load constraints from a file for complex multi-line constraints.

**Implementation:**
```bash
# Usage
orchestrator start "My task" --constraints-file constraints.txt

# constraints.txt
Do not modify database schema
All changes must be backwards compatible
Follow PEP 8 style guide
```

**Tasks:**
- [ ] Add `--constraints-file` argument to start command
- [ ] Read file and split by newlines
- [ ] Combine with inline `--constraints` flags
- [ ] Add documentation

---

#### CORE-016: Multi-Model Review Routing
**Status:** ✅ Completed (2026-01-06)
**Complexity:** Medium
**Priority:** High
**Source:** Current workflow
**Description:** Route REVIEW phase items to different AI models to prevent self-review blind spots.

**Problem Solved:**
The same model that writes code shouldn't review it. Different models have different blind spots and perspectives.

**Hybrid Model Strategy:**
- `security_review` + `quality_review` → Codex (code-specialized)
- `consistency_review` + `holistic_review` → Gemini (long context)

**Implementation:**
- Context collector gathers git diff, changed files, related files
- Review router with auto-detection: CLI mode (Codex/Gemini CLIs) or API mode (OpenRouter)
- Four review types: security, consistency, quality, holistic
- `setup-reviews` command to bootstrap GitHub Actions workflow
- 27 tests covering all components

**Files:** `src/review/` module (8 files)

---

#### WF-004: Auto-Archive Workflow Documents
**Status:** Planned
**Complexity:** Low
**Priority:** Medium
**Source:** Current workflow
**Description:** Automatically archive workflow documents (plan.md, risk_analysis.md) when starting a new workflow.

**Problem Solved:**
Multiple plan/risk files accumulate, making the repo messy.

**Desired Behavior:**
1. On `orchestrator start`, check for existing `docs/plan.md`
2. If exists, move to `docs/archive/YYYY-MM-DD_<task_slug>_plan.md`
3. Same for `docs/risk_analysis.md` and `tests/test_cases.md`
4. Log archive action

**Implementation Notes:**
```python
def archive_existing_docs(self):
    """Archive existing workflow docs before starting new workflow."""
    docs_to_archive = [
        ("docs/plan.md", "plan"),
        ("docs/risk_analysis.md", "risk"),
        ("tests/test_cases.md", "test_cases"),
    ]
    archive_dir = self.working_dir / "docs" / "archive"
    archive_dir.mkdir(exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    for doc_path, suffix in docs_to_archive:
        src = self.working_dir / doc_path
        if src.exists():
            task_slug = slugify(self.state.task_description[:30])
            dst = archive_dir / f"{date_str}_{task_slug}_{suffix}.md"
            src.rename(dst)
```

**Tasks:**
- [ ] Add `archive_existing_docs()` method to engine
- [ ] Call in `start_workflow()` before creating new state
- [ ] Add `--no-archive` flag to skip
- [ ] Log archived files

---

#### CORE-017: Auto-Update Review Models
**Status:** Planned
**Complexity:** Low
**Priority:** Medium
**Source:** Current workflow
**Description:** Automatically detect and use latest available AI models for reviews.

**Problem Solved:**
Model versions in config become stale as new models are released. Currently requires manual updates.

**Desired Behavior:**
1. `./orchestrator update-models` - Query OpenRouter API for latest models
2. Auto-suggest updates when newer models detected
3. Optional "latest" alias that resolves dynamically

**Implementation Notes:**
```python
def get_latest_models():
    """Query OpenRouter for latest available models."""
    response = requests.get("https://openrouter.ai/api/v1/models")
    models = response.json()["data"]

    # Find latest OpenAI and Gemini models
    latest_openai = max([m for m in models if m["id"].startswith("openai/gpt-5")],
                        key=lambda m: m["created"])
    latest_gemini = max([m for m in models if "gemini-3" in m["id"]],
                        key=lambda m: m["created"])
    return {"codex": latest_openai["id"], "gemini": latest_gemini["id"]}
```

**Tasks:**
- [ ] Add `update-models` CLI command
- [ ] Query OpenRouter API for model list
- [ ] Update workflow.yaml models section
- [ ] Add `--check-models` flag to review command
- [ ] Warn when using outdated models

---

### Medium-term (Medium Effort)

#### CORE-010: Checkpoint Database Backend
**Status:** Planned  
**Complexity:** Medium  
**Priority:** Medium  
**Description:** Add optional database backend for checkpoints to support multi-node deployments and better querying.

**Current State:**
- Checkpoints stored as JSON files in `.workflow_checkpoints/`
- Works well for single-node, local development

**Desired State:**
- Optional SQLite backend (default for local)
- Optional PostgreSQL backend (for teams/production)
- Configurable via `CHECKPOINT_BACKEND` env var

**Implementation Notes:**
```python
class CheckpointBackend(ABC):
    @abstractmethod
    def save(self, checkpoint: CheckpointData) -> None: ...
    @abstractmethod
    def load(self, checkpoint_id: str) -> Optional[CheckpointData]: ...
    @abstractmethod
    def list(self, workflow_id: Optional[str] = None) -> List[CheckpointData]: ...

class FileBackend(CheckpointBackend): ...  # Current implementation
class SQLiteBackend(CheckpointBackend): ...  # New
class PostgresBackend(CheckpointBackend): ...  # New
```

**Tasks:**
- [ ] Create `CheckpointBackend` abstract base class
- [ ] Refactor current file-based storage to `FileBackend`
- [ ] Implement `SQLiteBackend`
- [ ] Implement `PostgresBackend`
- [ ] Add `CHECKPOINT_BACKEND` configuration
- [ ] Add migration utility for existing checkpoints

---

#### CORE-011: Provider Caching
**Status:** Planned  
**Complexity:** Medium  
**Priority:** Low  
**Description:** Cache provider availability checks to avoid repeated subprocess calls and API pings.

**Current State:**
- `is_available()` called on each provider selection
- Claude Code check spawns subprocess each time
- OpenRouter check may make HTTP request

**Desired State:**
- Cache availability for configurable duration (default: 5 minutes)
- Invalidate cache on explicit request
- Thread-safe caching

**Implementation Notes:**
```python
from functools import lru_cache
from datetime import datetime, timedelta

class CachedProvider:
    _availability_cache: dict[str, tuple[bool, datetime]] = {}
    _cache_ttl = timedelta(minutes=5)
    
    def is_available(self) -> bool:
        cached = self._availability_cache.get(self.name)
        if cached and datetime.now() - cached[1] < self._cache_ttl:
            return cached[0]
        result = self._check_availability()
        self._availability_cache[self.name] = (result, datetime.now())
        return result
```

**Tasks:**
- [ ] Add caching to `AgentProvider` base class
- [ ] Make TTL configurable
- [ ] Add `--no-cache` flag to force fresh check
- [ ] Add cache invalidation method

---

#### CORE-012: OpenRouter Streaming Support
**Status:** Planned  
**Complexity:** Medium  
**Priority:** Low  
**Description:** Add streaming support to OpenRouter provider for real-time output display.

**Current State:**
- OpenRouter provider waits for full response
- No progress indication during long generations

**Desired State:**
- Optional streaming mode with `--stream` flag
- Real-time token output to terminal
- Progress indicator for non-streaming mode

**Implementation Notes:**
```python
def execute_streaming(self, prompt: str) -> Generator[str, None, ExecutionResult]:
    response = requests.post(
        f"{self._base_url}/chat/completions",
        json={...},
        stream=True
    )
    for line in response.iter_lines():
        if line.startswith(b'data: '):
            chunk = json.loads(line[6:])
            yield chunk['choices'][0]['delta'].get('content', '')
```

**Tasks:**
- [ ] Add `execute_streaming()` method to OpenRouter provider
- [ ] Add `--stream` flag to handoff command
- [ ] Handle stream interruption gracefully
- [ ] Add progress spinner for non-streaming mode

---

### Long-term (High Effort)

#### CORE-013: Provider Plugin System
**Status:** Planned  
**Complexity:** High  
**Priority:** Low  
**Description:** Allow external packages to register custom providers without modifying core code.

**Desired State:**
- Providers discoverable via entry points
- Install custom provider: `pip install orchestrator-provider-anthropic`
- Auto-registered on import

**Implementation Notes:**
```toml
# In external package's pyproject.toml
[project.entry-points."orchestrator.providers"]
anthropic = "orchestrator_anthropic:AnthropicProvider"
```

```python
# In orchestrator startup
import importlib.metadata

for ep in importlib.metadata.entry_points(group='orchestrator.providers'):
    provider_class = ep.load()
    register_provider(ep.name, provider_class)
```

**Tasks:**
- [ ] Define entry point group `orchestrator.providers`
- [ ] Add provider discovery on startup
- [ ] Create provider development guide
- [ ] Create example provider package
- [ ] Add provider validation on registration

---

#### CORE-014: Checkpoint Encryption
**Status:** Planned  
**Complexity:** High  
**Priority:** Low  
**Description:** Encrypt checkpoint data for sensitive workflows containing secrets or proprietary information.

**Desired State:**
- Optional encryption via `--encrypt` flag
- Use age encryption (consistent with SOPS)
- Decrypt on resume with key from env var

**Implementation Notes:**
```python
class EncryptedCheckpointBackend(CheckpointBackend):
    def __init__(self, key: str):
        self._key = key
    
    def save(self, checkpoint: CheckpointData) -> None:
        data = json.dumps(checkpoint.to_dict())
        encrypted = age_encrypt(data, self._key)
        # Save encrypted blob
    
    def load(self, checkpoint_id: str) -> Optional[CheckpointData]:
        encrypted = # Load encrypted blob
        data = age_decrypt(encrypted, self._key)
        return CheckpointData.from_dict(json.loads(data))
```

**Tasks:**
- [ ] Add `pyage` or similar library dependency
- [ ] Create `EncryptedCheckpointBackend`
- [ ] Add `--encrypt` flag to checkpoint command
- [ ] Add `CHECKPOINT_ENCRYPTION_KEY` env var
- [ ] Document encryption setup

---

#### CORE-015: Distributed Workflow Execution
**Status:** Planned  
**Complexity:** High  
**Priority:** Low  
**Description:** Support multiple agents working on the same workflow with item locking and claiming.

**Desired State:**
- Central workflow state (database-backed)
- Item claiming/locking mechanism
- Conflict resolution for concurrent updates
- Agent identification and tracking

**Implementation Notes:**
- Requires CORE-009 (database backend) first
- Add `claimed_by`, `claimed_at` fields to item state
- Add `orchestrator claim <item_id>` command
- Add heartbeat mechanism for stale claim detection

**Tasks:**
- [ ] Design distributed state schema
- [ ] Implement item locking mechanism
- [ ] Add agent identification
- [ ] Add claim/release commands
- [ ] Add conflict resolution strategy
- [ ] Add heartbeat and stale claim cleanup

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
| CORE-001 | Provider Abstraction & OpenRouter Integration | 2026-01-06 |
| CORE-002 | Environment Detection & Adaptation | 2026-01-06 |
| CORE-003 | Operating Notes System | 2026-01-06 |
| CORE-004 | Task Constraints Flag | 2026-01-06 |
| CORE-005 | Checkpoint/Resume System | 2026-01-06 |
| CORE-000 | SOPS Secrets Management (backported) | 2026-01-06 |
| CORE-016 | Multi-Model Review Routing | 2026-01-06 |
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
