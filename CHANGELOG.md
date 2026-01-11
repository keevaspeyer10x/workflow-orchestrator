# Changelog

All notable changes to the workflow-orchestrator.

## [2.8.1] - 2026-01-12

### Added
- **WF-035 Phases 3-5: Review Fallback Foundation** (Continues WF-035 zero-human mode)
  - **ReviewResult fallback tracking**: `was_fallback` and `fallback_reason` fields track when fallback models are used
  - **ReviewThresholdError exception**: Raised when insufficient reviews complete (used by `on_insufficient_reviews: block`)
  - **16 new unit tests**: `tests/test_review_fallbacks.py` covering fallback fields, threshold logic, and settings validation

### Fixed
- **Critique module attribute error**: Fixed `'ReviewResult' object has no attribute 'content'` error in `critique.py`
  - Changed `result.content` to `result.raw_output` (correct attribute name)
  - Error appeared on every phase advance since critique runs between phases

### Notes
- Phases 3 (Visual Regression) and 5 (Gate Skipping) were already implemented in previous PR
- Full fallback chain execution (try primary → fallback1 → fallback2) deferred to follow-up task
- Schema and tracking foundation now in place for graceful degradation

## [2.8.0] - 2026-01-11

### Added
- **WF-035: Zero-Human Mode - Supervision Mode Configuration** (Phases 1-2 of 6)
  - **SupervisionMode enum**: `supervised` (default), `zero_human`, `hybrid` in `src/schema.py`
  - **WorkflowSettings model**: Typed settings with `supervision_mode`, `smoke_test_command`, `test_command`, `build_command`
  - **ReviewSettings model**: Configurable review fallbacks with `minimum_required`, `fallbacks`, `on_insufficient_reviews`
  - **Gate skipping logic**: `should_skip_gate()` in `src/engine.py` auto-skips manual gates in `zero_human` mode
  - **Warning logging**: Skipped gates logged with `[ZERO-HUMAN MODE]` prefix for audit trail
  - **34 new unit tests**: Comprehensive coverage for supervision mode and gate skipping
  - **100% backward compatible**: Default `supervised` mode maintains existing behavior

### Changed
- WorkflowEngine now accepts optional `settings` parameter for typed configuration
- Manual gates respect `supervision_mode` setting when determining whether to block

### Deferred (Follow-up PR)
- WF-035 Phases 3-6: Smoke testing framework, visual regression docs, review fallbacks, integration tests

## [2.7.0] - 2026-01-11

### Added
- **WF-034 Phase 3b: Two-Tier Feedback System**: Split feedback into tool metrics (shareable) vs process context (private)
  - **Two-file architecture**: `.workflow_tool_feedback.jsonl` (anonymized) + `.workflow_process_feedback.jsonl` (full context)
  - **Anonymization with allowlist approach**: Only explicitly safe fields kept (prevents future PII leakage)
  - **Salted SHA256 hashing**: workflow_id → 16-char hash (prevents rainbow table attacks)
  - **Nested PII protection**: Phase dict keys validated (only PLAN, EXECUTE, etc. allowed)
  - **Automatic migration**: Phase 3a single-file feedback migrated to two-tier on first run
  - **Transaction-safe migration**: Atomic rename with rollback and crash recovery
  - **Sync command**: `orchestrator feedback sync` uploads anonymized tool feedback to GitHub Gist
  - **Review filters**: `orchestrator feedback review --tool` / `--process` for targeted analysis
  - **22 unit tests** covering security, atomicity, and anonymization
  - **Multi-model validation**: 5 AI models (Claude, GPT, Gemini, Grok, DeepSeek) reviewed for security

### Security
- **Salt management documentation**: Added comprehensive security guidance in CLAUDE.md
  - Default salt for single-user installations
  - Custom salt generation for teams (`openssl rand -base64 32`)
  - Warnings about salt storage, rotation, and version control
- **Allowlist-based PII filtering**: Future schema changes cannot leak PII by default
- **Deep copy protection**: Nested data structures safely handled

## [2.6.0] - 2026-01-11

### Added
- **PRD-008: Zero-Config Workflow Enforcement**: Single command workflow setup for AI agents
  - **`orchestrator enforce` command**: Auto-detects server, generates workflow, and provides agent instructions
  - **Server Auto-Discovery** (`src/orchestrator/auto_setup.py`): Checks ports 8000-8002 for running servers
  - **Server Auto-Start**: Spawns daemon process if no server found, with health check verification
  - **Repository Analysis** (`src/orchestrator/workflow_generator.py`): Detects language and test framework
    - Python (pytest), JavaScript (jest/mocha), Go (go test), Rust (cargo test)
    - Auto-detects project structure (src/, tests/, etc.)
  - **Workflow YAML Generation**: Creates `.orchestrator/agent_workflow.yaml` from template
    - 5-phase workflow (PLAN → TDD → IMPL → REVIEW → VERIFY)
    - Language-specific test commands and tool restrictions
  - **Agent Context Formatting** (`src/orchestrator/agent_context.py`): Generates SDK usage instructions
    - Markdown format with code examples
    - Sequential vs parallel execution mode support
    - Outputs to stdout for AI consumption + backup file
  - **Cross-Platform Support**: Windows and Unix daemon process management
  - **81 comprehensive unit tests** with 100% pass rate

## [2.5.0] - 2026-01-11

### Added
- **WF-029: Tradeoff Analysis in LEARN Phase**: Mandatory complexity vs benefit analysis for roadmap items
  - Added tradeoff analysis requirements to `propose_actions` workflow step
  - Requires categorization: ✅ RECOMMEND / ⚠️ DEFER / 🔍 EXPLORATORY
  - Includes YAGNI check and evidence evaluation (production data, user requests, bottlenecks)
  - Prevents roadmap bloat from low-value items without implementation evidence
  - Applied to both workflow.yaml and src/default_workflow.yaml
- **WF-030: Session Isolation** - Documented multi-workflow limitation in roadmap (planned feature)

### Changed
- **CLAUDE.md**: Added comprehensive "Automatic Updates" section explaining auto-update behavior
  - What gets auto-updated (orchestrator code) vs what doesn't (workflow.yaml)
  - How to get new workflow features in existing projects
  - Recent workflow improvements (WF-029 tradeoff analysis)
  - Verification commands for checking versions

### Added
- **PRD-007: Agent Workflow Enforcement System (Days 14-20)**: Complete orchestration server for multi-agent workflows
  - **State Management** (`src/orchestrator/state.py`): Thread-safe task tracking with JSON persistence
    - Task registration and phase tracking
    - Dependency management and completion tracking
    - Blocker recording and state snapshots
    - Concurrent operation support with lock-based protection
  - **Event Bus** (`src/orchestrator/events.py`): Pub/sub pattern for agent coordination
    - 6 standard event types (task claimed, transitioned, completed, tool executed, gate blocked/passed)
    - Event history for debugging and audit trails
    - Thread-safe subscriber management
  - **Configuration System** (`src/orchestrator/config.py`): Multi-source configuration management
    - Defaults → YAML file → Environment variables (priority order)
    - 9 configuration classes (Server, Security, State, Event, Audit, Retry, CircuitBreaker, Logging, Orchestrator)
    - Runtime updates and validation
    - Thread-safe operations
  - **Error Handling** (`src/orchestrator/error_handling.py`): Production-grade reliability
    - RetryHandler with exponential backoff and jitter
    - CircuitBreaker with 3-state pattern (CLOSED/OPEN/HALF_OPEN)
    - FallbackHandler for graceful degradation
    - ErrorHandler combining retry + circuit breaker + fallback
    - Custom exception hierarchy (RetryableError, NonRetryableError, CircuitBreakerOpenError)
  - **Agent SDK** (`src/agent_sdk/`): Simple Python client for agents
    - Automatic token management and refresh
    - Convenience methods (claim_task, advance_phase, execute_tool)
    - Context manager support
    - Comprehensive error handling
  - **API Integration**: StateManager and EventBus integrated into FastAPI endpoints
    - Task claim tracking
    - Phase transition events
    - Tool execution events
    - State snapshots
  - **Testing**: 102 new tests (100% pass rate)
    - 13 StateManager tests (registration, phases, completion, dependencies, persistence, thread safety)
    - 12 EventBus tests (subscribers, publishing, history, error handling, thread safety)
    - 28 integration tests (state + events coordination)
    - 11 E2E workflow tests (complete workflows, multi-agent, gates, permissions)
    - 32 configuration tests (loading, overrides, validation, priority)
    - 31 error handling tests (retry, circuit breaker, fallback, thread safety)
    - 21 Agent SDK tests
  - **Documentation** (125+ pages total):
    - `docs/AGENT_SDK_GUIDE.md` (40+ pages): Complete SDK user guide with API reference, examples, best practices
    - `docs/WORKFLOW_SPEC.md` (35+ pages): Workflow YAML specification with schema, validation, examples
    - `docs/DEPLOYMENT_GUIDE.md` (50+ pages): Production deployment (systemd, Docker, Kubernetes, monitoring, security)
    - Implementation summaries: `docs/DAYS_13_20_SUMMARY.md`, `docs/DAYS_14_16_SUMMARY.md`, `docs/DAYS_17_20_SUMMARY.md`
  - **Production Ready**:
    - Security: JWT authentication, permission enforcement, audit logging
    - Reliability: Retry logic, circuit breakers, graceful degradation
    - Scalability: Stateless API, horizontal scaling, thread-safe operations
    - Observability: Comprehensive logging, health checks, event tracking
    - Deployment: Systemd, Docker, Kubernetes manifests provided

### Changed
- API endpoints now publish events and track state through StateManager and EventBus

## [2.4.0] - 2026-01-10

### Added
- **CORE-023-P1: Conflict Resolution - Core**: Fast conflict detection and resolution without LLM
  - `orchestrator resolve` command with preview and `--apply` modes
  - Conflict detection for merge and rebase operations
  - 3-way merge via `git merge-file`
  - Git `rerere` integration for resolution caching
  - Interactive escalation with ours/theirs/both/editor options
  - Status integration with conflict warnings
  - Files: `src/git_conflict_resolver.py`, CLI in `src/cli.py`

- **CORE-023-P2: Conflict Resolution - LLM Integration**: Intelligent resolution for complex conflicts
  - `--use-llm` flag for `orchestrator resolve` command
  - Intent extraction with structured JSON output
  - Multi-provider support: OpenAI, Gemini, OpenRouter
  - Confidence-based escalation (HIGH=auto, MEDIUM=ask, LOW=escalate)
  - Tiered validation: conflict markers, syntax, JSON, YAML
  - Sensitive file protection (skips .env, secrets, keys)
  - Context-aware with CLAUDE.md conventions and token budgets
  - 36 unit tests covering all functionality
  - Files: `src/resolution/llm_resolver.py`

- **WF-027: Workflow Finish Summary Archival**: Automatic persistence of completion summaries
  - Saves full `orchestrator finish` output to `docs/archive/YYYY-MM-DD_<task-slug>_summary.md`
  - Includes phase summaries, skipped items, external reviews, learnings
  - Solves terminal truncation and enables later reference
  - Displays save location confirmation

- **PRD-005: ApprovalGate + TmuxAdapter Integration**: Human-in-the-loop for parallel agents
  - Automatic pause at workflow gates for human approval
  - `ApprovalGate.get_decision_log()` tracks decisions with rationale
  - `ApprovalQueue.decision_summary()` groups by auto/human decisions
  - `orchestrator approval watch` with tmux bell notifications
  - `orchestrator approval summary` for decision analysis
  - 50 new tests; 21 in `tests/test_approval_gate.py`
  - Files: `src/approval_gate.py`, `src/approval_queue.py`, `src/prd/tmux_adapter.py`

- **PRD-006: Auto-Inject ApprovalGate in spawn_agent()**: Zero-config approval system
  - Automatic injection of approval gate instructions during agent spawning
  - Added `inject_approval_gate: bool = True` to TmuxConfig/SubprocessConfig
  - `--no-approval-gate` CLI flag for opt-out
  - 13 new tests (8 TmuxAdapter, 5 SubprocessAdapter)
  - Maintains backward compatibility

- **Parallel Agent Approval System**: Coordinate multiple Claude Code agents with approval gates
  - `ApprovalQueue`: SQLite-backed queue with WAL mode for concurrent agent access
  - `ApprovalGate`: Agent-side interface with exponential backoff polling (2s → 10s → 30s)
  - State machine: PENDING → APPROVED/REJECTED → CONSUMED (consume-once semantics)
  - Risk-based auto-approval: LOW auto-approves, CRITICAL always requires human
  - Heartbeat tracking + TTL expiration for stuck agent detection
  - CLI commands: `approval pending`, `approve`, `reject`, `approve-all`, `stats`, `cleanup`
  - 29 new tests covering queue operations, concurrency, and maintenance

### Changed
- **CLAUDE.md**: Added documentation for approval commands in Key Commands table

## [2.3.0] - 2026-01-10

### Added
- **PRD-001: Claude Squad Integration Phase 1**: Architecture simplification for agent spawning
  - Replaced complex multi-backend spawning with Claude Squad integration
  - New files: `src/prd/squad_adapter.py`, `src/prd/squad_capabilities.py`, `src/prd/session_registry.py`
  - CLI commands: `prd check-squad`, `prd spawn`, `prd sessions`, `prd attach`, `prd done`
  - Persistent session state registry
  - Capability-aware agent selection
  - Removed: Modal/Render/local subprocess backends (`worker_pool.py`, `backends/local.py`, `backends/modal_worker.py`, `backends/render.py`)
  - Retained: GitHub Actions batch execution, branch management, conflict resolution

- **PRD-004: Direct tmux Agent Management**: Replaced broken Claude Squad integration with direct tmux session management
  - `TmuxAdapter`: Spawns Claude Code agents in tmux windows for interactive sessions
  - `SubprocessAdapter`: Fire-and-forget fallback when tmux unavailable
  - `BackendSelector`: Auto-detects tmux, falls back to subprocess
  - Happy integration via `CLAUDE_BINARY=happy` config
  - 57 new tests covering both adapters

### Changed
- **CLI prd commands**: Now use new adapters instead of broken ClaudeSquadAdapter
  - `prd sessions`: Lists active agent sessions
  - `prd attach`: Attaches to tmux session (tmux only)
  - `prd done`: Marks task complete and terminates session
  - `prd cleanup`: Cleans up all sessions
- **ExecutionMode**: Added `SUBPROCESS` mode for non-tmux environments

### Fixed
- **Stale learnings in finish summary**: `orchestrator finish` now generates learning report BEFORE displaying summary, so current workflow learnings are shown instead of previous workflow's content

### Deprecated
- `ClaudeSquadAdapter` and `squad_capabilities.py` - kept for reference but no longer used

## [2.2.2] - 2026-01-10

### Fixed
- **Smarter API Key Check**: Now warns only when NO review API keys are set (was warning if ANY key missing)
  - At least one key (GEMINI, OPENAI, OPENROUTER, or XAI) enables reviews
  - Empty strings treated as missing
  - Less noisy UX for vibe coders
- **default_test Bug**: Fixed `check_project_mismatch` using wrong default (`npm run build` → `npm test`)
- **sops Command Syntax**: Fixed invalid bash syntax in API key loading instructions (now uses `yq`)

### Changed
- **Skip Summary Enhancement**: Now shows `item_id: description` format for better traceability
- **Gate Bypass Highlighting**: Force-skipped gate items now show `⚠️ GATE BYPASSED:` prefix in finish summary

### Added
- 4 new tests for API key check behavior (`TestAPIKeyCheck` class)

## [2.2.1] - 2026-01-08

### Added
- **Auto-Run Third-Party Reviews (WF-010)**: Automatically runs third-party model reviews when completing REVIEW phase items
  - `security_review` → runs security review via Codex
  - `quality_review` → runs quality review via Codex
  - `architecture_review` → runs holistic review via Gemini
  - Blocks completion if review fails or finds blocking issues
  - Captures review results in completion notes
  - `--skip-auto-review` flag available (not recommended)
  - Guides users to `skip --reason` if review infrastructure unavailable

## [2.2.0] - 2026-01-07

### Added
- **OpenRouter Streaming Support (CORE-012)**: Real-time response streaming
  - `execute_streaming()` method yields chunks as they arrive
  - `stream_to_console()` convenience method for interactive use
  - Handles stream interruption gracefully

- **Visual Verification Enhancements (VV-001 through VV-006)**:
  - **VV-001**: Auto-load style guide - `style_guide_path` parameter auto-loads and includes style guide in all verifications
  - **VV-002**: Workflow step integration - `run_all_visual_tests()` wires into workflow's `visual_regression_test` item
  - **VV-003**: Visual test discovery - `discover_visual_tests()` scans `tests/visual/*.md` files with YAML frontmatter
  - **VV-004**: Baseline management - `save_baseline()`, `get_baseline()`, `compare_with_baseline()` with hash-based comparison
  - **VV-006**: Cost tracking - `UsageInfo` dataclass with token counts and estimated cost from service

- **Model Selection Guidance (WF-003)**: `get_latest_model(category)` in model registry
  - Categories: `codex`, `gemini`, `claude` and aliases (`security`, `quality`, `consistency`, `holistic`)
  - Returns latest available model for review routing

- **Changelog/Roadmap Automation**: New `update_changelog_roadmap` item in LEARN phase
  - Prompts to move completed roadmap items to changelog
  - Configurable `roadmap_file` and `changelog_file` settings in workflow.yaml

- **CLI Enhancements**:
  - `visual-verify-all` command for running all visual tests in a directory
  - `--device` flag for device presets (e.g., `iphone-14`, `desktop`)
  - `--show-cost` flag for cost/token display
  - `--save-baseline` flag for baseline screenshot management

### Changed
- Visual verification client now returns `VerificationResult` dataclass instead of dict
- Mobile viewport updated to iPhone 14 dimensions (390x844)
- API key is now optional for visual verification (for unprotected services)

### Integration
- Updated `visual-verification-service` with cost tracking (`usage` field in response)

## [2.1.0] - 2026-01-06

### Added
- **Global Installation (CORE-018)**: pip-installable package with bundled default workflow
  - `pip install git+https://github.com/keevaspeyer10x/workflow-orchestrator.git`
  - `orchestrator init` command to create local workflow.yaml
  - Config discovery: local workflow.yaml > bundled default
  - Works in Claude Code Web, Manus, and local environments

- **TDD-Enforced Test Ordering (WF-005)**: EXECUTE phase now enforces tests-first
  - `write_tests` (RED) before `implement_code` (GREEN)
  - Operating notes explain TDD rationale

- **Improved LEARN Phase (WF-006)**: Explicit action approval before applying
  - `propose_actions` → `approve_actions` → `apply_approved_actions`
  - User must approve specific changes before they're embedded

- **Commit and Sync Step (WF-007)**: Final workflow item prompts to commit
  - Auto-generates commit message from task description and changes
  - Prompts user before committing and pushing to main

- **Auto-Setup Hook Commands (CORE-019)**: Easy setup for Claude Code sessions
  - `orchestrator install-hook` - Installs SessionStart hook for auto-setup
  - `orchestrator uninstall-hook` - Removes the hook
  - Always gets latest version with `--upgrade`
  - Works in Claude Code CLI and Claude Code Web

### Changed
- EXECUTE phase item order: write_tests now comes before implement_code
- LEARN phase restructured for explicit action approval
- Version bumped to 2.0.0 in CLI

## [2.0.0] - 2026-01-06

### Added
- **Multi-Model Review Routing (CORE-016)**: Route reviews to different AI models
  - Security/Quality → Codex
  - Consistency/Holistic → Gemini
  - CLI mode (Codex/Gemini CLIs) or API mode (OpenRouter)
  - `setup-reviews` command for GitHub Actions bootstrap

- **Provider Abstraction (CORE-001)**: Generic provider interface
  - OpenRouter, Claude Code, Manual providers
  - `--provider` and `--model` CLI flags

- **Environment Detection (CORE-002)**: Auto-detect Claude Code, Manus, Standalone

- **Operating Notes (CORE-003)**: `notes` field on phases and items
  - Categories: `[tip]`, `[caution]`, `[learning]`, `[context]`

- **Task Constraints (CORE-004)**: `--constraints` flag on start command

- **Checkpoint/Resume (CORE-005)**: Save and restore workflow state
  - `orchestrator checkpoint`, `orchestrator resume`
  - Auto-checkpoint on phase transitions

- **Visual Verification**: AI-powered UAT testing
  - `visual-verify`, `visual-template` commands
  - Desktop and mobile viewport testing
  - Style guide integration

- **SOPS Secrets Management**: Backported from quiet-ping-v6

## [1.0.0] - 2026-01-05

### Added
- Core workflow engine with phase/item state machine
- YAML-based workflow definitions
- Active verification (file_exists, command, manual_gate)
- Claude Code CLI integration
- Analytics and learning engine
- Web dashboard
- Security hardening (injection protection, path traversal)
- Version-locked workflow definitions in state
- Template variable substitution
