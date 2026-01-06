# Workflow Orchestrator Roadmap

This document tracks **planned** improvements, deferred features, and audit recommendations.

For completed features, see [CHANGELOG.md](CHANGELOG.md).

---

## Planned Improvements

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
**Status:** ✅ Completed (2026-01-06)
**Complexity:** Low
**Priority:** Medium
**Description:** Add deprecation warning to `claude_integration.py` and update documentation to use new provider system.

**Implementation:**
- Added deprecation warning at module import with `stacklevel=2`
- Warning points users to `src.providers.claude_code`

**Files:** `src/claude_integration.py`

---

#### CORE-008: Input Length Limits
**Status:** ✅ Completed (2026-01-06)
**Complexity:** Low
**Priority:** Medium
**Source:** Security Review v2.2
**Description:** Add length limits to user-provided constraints and notes to prevent DoS via extremely long strings.

**Implementation:**
- Created `src/validation.py` with `validate_constraint()` and `validate_note()` functions
- Added validation calls to CLI commands: `start`, `complete`, `approve-item`, `finish`
- 14 tests in `tests/test_validation.py`

**Files:** `src/validation.py`, `src/cli.py`, `tests/test_validation.py`

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

#### CORE-010: Enhanced Skip Visibility
**Status:** Planned
**Complexity:** Low
**Priority:** High
**Source:** Learnings from roadmap items implementation (2026-01-06)
**Description:** Make skipped items more visible to force deliberate consideration and prevent lazy skipping.

**Problem Solved:**
When AI agents skip workflow items, the skip reason is stored but not prominently displayed. This allows:
1. **Lazy skipping** - Agent skips items without fully considering implications
2. **Silent accumulation** - Multiple skips go unnoticed until workflow ends
3. **Lost context** - User doesn't see what was skipped or why

The act of articulating rationale forces deeper consideration - it's harder to be lazy when you have to explain yourself out loud.

**Desired Behavior:**

1. **At skip time** - Enhanced output that forces consideration:
```
============================================================
⊘ SKIPPING: visual_regression_test
============================================================
Reason: Not applicable - CLI tool with no visual UI

Implications:
  • No visual regression testing will be performed
  • UI changes (if any) will not be automatically verified

This skip is acceptable because:
  • This is a CLI-only tool with no visual components
  • Visual testing would have no meaningful assertions
============================================================
```

2. **At phase advance** - Show skipped items for the completed phase:
```
Phase VERIFY completed with 1 skipped item(s):
  ⊘ visual_regression_test - "Not applicable - CLI tool with no visual UI"
```

3. **At workflow finish** - Summary of all skipped items:
```
============================================================
SKIPPED ITEMS SUMMARY
============================================================
Review these skips - were they all justified?

Phase PLAN:
  ⊘ clarifying_questions - "Roadmap items well-specified"

Phase VERIFY:
  ⊘ visual_regression_test - "CLI tool with no visual UI"

Phase LEARN:
  ⊘ backport_improvements - "No universal improvements to backport"
  ⊘ update_knowledge_base - "Handled via ROADMAP.md updates"

Total: 4 items skipped across 3 phases
============================================================
```

**Implementation Notes:**

```python
# In cmd_skip() - src/cli.py
def cmd_skip(args):
    # ... existing validation ...

    # Enhanced skip output
    print("=" * 60)
    print(f"⊘ SKIPPING: {args.item}")
    print("=" * 60)
    print(f"Reason: {args.reason}")
    print()

    # Get item definition for context
    item_def = engine.get_item_definition(args.item)
    if item_def and item_def.description:
        print("What this item does:")
        print(f"  {item_def.description}")
        print()

    print("Implications:")
    print(f"  • {item_def.name} will not be performed")
    print()
    print("=" * 60)

    # Proceed with skip
    success, message = engine.skip_item(args.item, args.reason)
    # ...

# In cmd_advance() - show skipped items for completed phase
def cmd_advance(args):
    # ... existing logic ...

    # After successful advance, show skipped items from previous phase
    skipped = engine.get_skipped_items(previous_phase_id)
    if skipped:
        print(f"\nPhase {previous_phase_id} completed with {len(skipped)} skipped item(s):")
        for item_id, reason in skipped:
            print(f"  ⊘ {item_id} - \"{reason}\"")

# In cmd_finish() - full summary
def cmd_finish(args):
    # ... existing logic ...

    # Before completing, show all skipped items
    all_skipped = engine.get_all_skipped_items()
    if all_skipped:
        print("\n" + "=" * 60)
        print("SKIPPED ITEMS SUMMARY")
        print("=" * 60)
        print("Review these skips - were they all justified?\n")

        for phase_id, items in all_skipped.items():
            print(f"Phase {phase_id}:")
            for item_id, reason in items:
                print(f"  ⊘ {item_id} - \"{reason}\"")
            print()

        total = sum(len(items) for items in all_skipped.values())
        print(f"Total: {total} items skipped across {len(all_skipped)} phases")
        print("=" * 60)
```

**Engine Methods to Add:**

```python
# In WorkflowEngine - src/engine.py

def get_skipped_items(self, phase_id: str) -> list[tuple[str, str]]:
    """Get list of (item_id, skip_reason) for skipped items in a phase."""
    if not self.state:
        return []
    phase = self.state.phases.get(phase_id)
    if not phase:
        return []
    return [
        (item_id, item.skip_reason or "No reason provided")
        for item_id, item in phase.items.items()
        if item.status == ItemStatus.SKIPPED
    ]

def get_all_skipped_items(self) -> dict[str, list[tuple[str, str]]]:
    """Get all skipped items grouped by phase."""
    if not self.state:
        return {}
    result = {}
    for phase_id, phase in self.state.phases.items():
        skipped = self.get_skipped_items(phase_id)
        if skipped:
            result[phase_id] = skipped
    return result

def get_item_definition(self, item_id: str) -> Optional[ChecklistItemDef]:
    """Get the workflow definition for an item."""
    if not self.workflow_def:
        return None
    for phase in self.workflow_def.phases:
        for item in phase.items:
            if item.id == item_id:
                return item
    return None
```

**Tasks:**
- [ ] Add `get_skipped_items()` method to WorkflowEngine
- [ ] Add `get_all_skipped_items()` method to WorkflowEngine
- [ ] Add `get_item_definition()` method to WorkflowEngine
- [ ] Update `cmd_skip()` to show enhanced output with implications
- [ ] Update `cmd_advance()` to show skipped items from completed phase
- [ ] Update `cmd_finish()` to show full skipped items summary
- [ ] Add tests for new engine methods
- [ ] Add tests for CLI output changes
- [ ] Update documentation

**Why This Matters for AI Agents:**
When an AI agent must articulate *why* something is being skipped and see the implications displayed, it:
1. Forces genuine consideration of whether skipping is appropriate
2. Makes lazy skipping visible and uncomfortable
3. Creates accountability in the conversation/logs
4. Gives the human user visibility into agent decision-making

This is particularly important for "vibe coding" workflows where AI operates with high autonomy.

---

#### CORE-011: Workflow Completion Summary & Next Steps
**Status:** Planned
**Complexity:** Low
**Priority:** High
**Source:** Learnings from roadmap items implementation (2026-01-06)
**Description:** Show comprehensive completion summary and prompt for next steps when workflow finishes, preventing conversations from "tailing off" without proper closure.

**Problem Solved:**
When `orchestrator finish` runs, it just outputs "✓ Workflow completed" and stops. This allows:
1. **Premature closure** - Agent assumes work is done when user may have more steps
2. **Missing handoff** - No prompt to create PR, merge, or continue discussion
3. **Lost context** - No summary of what was accomplished or skipped
4. **Conversation drift** - Discussion gets sidetracked and workflow silently ends

The workflow completion is a critical moment - the agent should explicitly check with the user about next steps rather than assuming the conversation is over.

**Desired Behavior:**

When `orchestrator finish` runs, show:

```
============================================================
✓ WORKFLOW COMPLETED
============================================================
Task: Implement roadmap items: CORE-007, CORE-008, ARCH-001, WF-004
Started: 2026-01-06 10:30 UTC
Finished: 2026-01-06 12:45 UTC
Duration: 2h 15m

PHASE SUMMARY
─────────────────────────────────────────────────────────────
  PLAN:     6 items (5 completed, 1 skipped)
  EXECUTE:  4 items (4 completed)
  REVIEW:   4 items (3 completed, 1 skipped)
  VERIFY:   3 items (2 completed, 1 skipped)
  LEARN:    6 items (4 completed, 2 skipped)
─────────────────────────────────────────────────────────────
  Total:    23 items (18 completed, 5 skipped)

SKIPPED ITEMS (review for justification)
─────────────────────────────────────────────────────────────
  • clarifying_questions: "Roadmap items well-specified"
  • visual_regression_test: "CLI tool with no visual UI"
  • refactoring_assessment: "Small focused changes"
  • backport_improvements: "No universal improvements"
  • update_knowledge_base: "Handled via ROADMAP.md"

============================================================
⚠️  WORKFLOW COMPLETE - WHAT'S NEXT?
============================================================

The workflow is finished, but you may still need to:

  □ Create a PR:
    gh pr create --title "feat: Implement CORE-007, CORE-008, ARCH-001, WF-004"

  □ Merge to main (if approved):
    git checkout main && git merge <branch> && git push

  □ Continue discussion with user about:
    • Any follow-up tasks?
    • Questions about the implementation?
    • Ready to close this session?

Reply to confirm next steps or start a new workflow.
============================================================
```

**Implementation Notes:**

```python
# In cmd_finish() - src/cli.py

def cmd_finish(args):
    engine = get_engine(args)

    if not engine.state:
        print("Error: No active workflow")
        sys.exit(1)

    # Capture summary before completing
    summary = engine.get_workflow_summary()
    skipped = engine.get_all_skipped_items()

    # Complete the workflow
    if args.abandon:
        engine.abandon_workflow(args.reason)
        print("✓ Workflow abandoned")
    else:
        engine.complete_workflow(notes=args.notes)

        # Show comprehensive completion summary
        print_completion_summary(summary, skipped, engine.state)

        # Prompt for next steps
        print_next_steps_prompt(engine.state)

def print_completion_summary(summary, skipped, state):
    """Print detailed completion summary."""
    print("=" * 60)
    print("✓ WORKFLOW COMPLETED")
    print("=" * 60)
    print(f"Task: {state.task_description}")

    if state.started_at and state.completed_at:
        duration = state.completed_at - state.started_at
        print(f"Duration: {format_duration(duration)}")
    print()

    # Phase summary table
    print("PHASE SUMMARY")
    print("-" * 60)
    for phase_id, phase_summary in summary.items():
        completed = phase_summary['completed']
        skipped = phase_summary['skipped']
        total = phase_summary['total']
        print(f"  {phase_id:12} {total} items ({completed} completed, {skipped} skipped)")
    print("-" * 60)

    # Skipped items
    if skipped:
        print("\nSKIPPED ITEMS (review for justification)")
        print("-" * 60)
        for phase_id, items in skipped.items():
            for item_id, reason in items:
                # Truncate long reasons
                short_reason = reason[:50] + "..." if len(reason) > 50 else reason
                print(f"  • {item_id}: \"{short_reason}\"")
    print()

def print_next_steps_prompt(state):
    """Prompt user/agent about next steps."""
    print("=" * 60)
    print("⚠️  WORKFLOW COMPLETE - WHAT'S NEXT?")
    print("=" * 60)
    print()
    print("The workflow is finished, but you may still need to:")
    print()
    print("  □ Create a PR:")
    print(f"    gh pr create --title \"{get_pr_title(state)}\"")
    print()
    print("  □ Merge to main (if approved)")
    print()
    print("  □ Continue discussion with user about:")
    print("    • Any follow-up tasks?")
    print("    • Questions about the implementation?")
    print("    • Ready to close this session?")
    print()
    print("Reply to confirm next steps or start a new workflow.")
    print("=" * 60)
```

**Engine Methods to Add:**

```python
# In WorkflowEngine - src/engine.py

def get_workflow_summary(self) -> dict:
    """Get summary of items per phase."""
    if not self.state:
        return {}

    summary = {}
    for phase_id, phase in self.state.phases.items():
        completed = sum(1 for i in phase.items.values()
                       if i.status == ItemStatus.COMPLETED)
        skipped = sum(1 for i in phase.items.values()
                     if i.status == ItemStatus.SKIPPED)
        total = len(phase.items)
        summary[phase_id] = {
            'completed': completed,
            'skipped': skipped,
            'total': total
        }
    return summary
```

**Tasks:**
- [ ] Add `get_workflow_summary()` method to WorkflowEngine
- [ ] Add `print_completion_summary()` function to CLI
- [ ] Add `print_next_steps_prompt()` function to CLI
- [ ] Update `cmd_finish()` to call both functions
- [ ] Add helper to generate suggested PR title from task description
- [ ] Add duration calculation and formatting
- [ ] Include skipped items summary (integrate with CORE-010)
- [ ] Add tests for summary generation
- [ ] Add tests for CLI output

**Why This Matters for AI Agents:**
AI agents can lose track of where they are in a conversation, especially after completing a complex multi-phase workflow. By explicitly prompting "what's next?" the orchestrator:
1. Prevents the agent from assuming work is done prematurely
2. Reminds the agent to check with the user before ending
3. Provides concrete next step suggestions (PR, merge, etc.)
4. Keeps the conversation focused on completing the full task

This is critical for "vibe coding" where the human may be minimally engaged - the agent needs explicit prompts to stay on track rather than silently stopping.

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
**Status:** ✅ Completed (2026-01-06)
**Complexity:** Low
**Priority:** Medium
**Source:** Current workflow
**Description:** Automatically archive workflow documents (plan.md, risk_analysis.md) when starting a new workflow.

**Implementation:**
- Added `archive_existing_docs()` method to `WorkflowEngine`
- Archives `docs/plan.md`, `docs/risk_analysis.md`, `tests/test_cases.md`
- Added `--no-archive` flag to skip archiving
- Uses `slugify()` utility for filename generation
- Handles duplicate filenames with counter suffix
- 10 tests in `tests/test_roadmap_features.py`

**Files:** `src/engine.py`, `src/cli.py`, `src/utils.py`, `tests/test_roadmap_features.py`

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
**Status:** ✅ Completed (2026-01-06)
**Complexity:** Low
**Source:** Architecture Review (Score: 7/10)
**Description:** Extract retry logic with exponential backoff into a reusable utility.

**Implementation:**
- Created `src/utils.py` with `@retry_with_backoff` decorator
- Configurable: `max_retries`, `base_delay`, `max_delay`, `exceptions`
- Also added `slugify()` utility for filename generation
- 15 tests in `tests/test_utils.py`

**Files:** `src/utils.py`, `tests/test_utils.py`

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

See [CHANGELOG.md](CHANGELOG.md) for completed features and their details.

---

## Contributing

When adding items to this roadmap:
1. Use the appropriate prefix (CORE-, VV-, SEC-, ARCH-, WF-, DEF-)
2. Include: Status, Complexity, Description, Implementation Notes
3. For audit items, include Source reference
4. When completed, move to CHANGELOG.md and remove from this file
