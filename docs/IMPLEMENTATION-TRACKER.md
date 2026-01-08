# Multi-Agent Merge Conflict System - Implementation Tracker

**Design Document:** `docs/FINAL-merge-conflict-system-design.md`
**Started:** January 2026
**Current Phase:** 6 - PRD Mode & Scale (In Progress)

---

## Quick Start for New Chat Sessions

When starting a new chat, read these files in order:
1. This file (`docs/IMPLEMENTATION-TRACKER.md`) - current status
2. Design doc Section 15 (`docs/FINAL-merge-conflict-system-design.md` lines 3999-4082) - phase details
3. Any files marked as "In Progress" below

**CRITICAL PROCESS REQUIREMENT:**
Always use the orchestrator workflow system for ALL code changes (unless trivially simple).
This includes: PLAN → EXECUTE → REVIEW → VERIFY → LEARN phases.
This reminder exists because context compaction can cause Claude to forget workflow requirements.

**MANDATORY PRE-COMMIT REVIEW:**
Before ANY commit, run: `python scripts/pre_commit_review.py`
This invokes external model reviews (GPT-5.2 Max, Gemini, Grok, Codex).
Commits with blocking issues will be REJECTED. Internal Claude review alone is NOT sufficient.

**SECRETS ACCESS (for AI agents):**
API keys are stored encrypted in `secrets.enc.yaml` using SOPS + age encryption.
To access secrets:
1. The age private key is stored at `~/.config/sops/age/keys.txt`
2. Decrypt with: `sops -d secrets.enc.yaml`
3. Or use `.envrc` with direnv which auto-loads secrets into environment
Available keys: GEMINI_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY, XAI_API_KEY (Grok)

**MODEL VERSIONS (IMPORTANT - read this!):**
The current date is January 2026. Do NOT downgrade to older models based on training data!
- OpenAI: GPT-5.2 Max, GPT-5.1 Codex Max (NOT GPT-4o)
- Google: Gemini 3 Pro (NOT Gemini 1.5)
- xAI: Grok 4.1 (NOT Grok beta)
- Anthropic: Claude Opus 4.5, Claude Sonnet 4
Canonical config: `.claude/review-config.yaml` - always check this for current models.

---

## Overall Progress

| Phase | Status | Auto-Resolve Target |
|-------|--------|---------------------|
| 1. Foundation (MVP) | **COMPLETE** | N/A (fast-path only) |
| 2. Conflict Detection | **COMPLETE** | N/A |
| 3. Basic Resolution | **COMPLETE** | ~60% |
| 4. Escalation System | **COMPLETE** | N/A |
| 5. Advanced Resolution | **COMPLETE** | ~80% |
| 6. PRD Mode & Scale | **IN PROGRESS** | N/A |
| 7. Learning & Optimization | Not Started | N/A |

---

## Phase 1: Foundation (MVP)

**Goal:** Basic coordination without intelligent resolution
**Deliverable:** System that auto-merges non-conflicting agent work

### Checklist

- [x] Agent manifest schema (`src/coordinator/schema.py`)
- [x] Manifest storage - GitHub artifacts (`src/coordinator/manifest_store.py`)
- [x] Agent discovery - find claude/* branches (`src/coordinator/discovery.py`)
- [x] Basic conflict detection - git merge-tree (`src/conflict/detector.py`)
- [x] Fast-path merge - no conflicts → create PR (`src/coordinator/fast_path.py`)
- [x] GitHub Actions workflows (`.github/workflows/`)
  - [x] `claude-branch-ping.yml` (untrusted, minimal)
  - [x] `claude-coordinator.yml` (trusted, full access)
- [x] CLI entry point (`src/coordinator/__main__.py`)
- [x] Simple notifications (built into coordinator via GitHubActionsFormatter)

### Files Created

| File | Status | Description |
|------|--------|-------------|
| `src/coordinator/__init__.py` | **DONE** | Package init with all exports |
| `src/coordinator/schema.py` | **DONE** | AgentManifest, DerivedManifest, enums |
| `src/coordinator/discovery.py` | **DONE** | AgentDiscovery, find claude/* branches |
| `src/coordinator/manifest_store.py` | **DONE** | Local + GitHub artifact storage |
| `src/coordinator/fast_path.py` | **DONE** | FastPathMerger, PR creation |
| `src/conflict/__init__.py` | **DONE** | Package init |
| `src/conflict/detector.py` | **DONE** | ConflictDetector, git merge-tree |
| `src/coordinator/__main__.py` | **DONE** | CLI entry point for GitHub Actions |
| `.github/workflows/claude-branch-ping.yml` | **DONE** | Untrusted ping workflow |
| `.github/workflows/claude-coordinator.yml` | **DONE** | Trusted coordinator workflow |

### Decisions Made

1. **Local storage fallback**: ManifestStore uses local `.claude/manifests/` when not in GitHub Actions
2. **Session ID extraction**: Extract from branch name suffix (last segment after dash)
3. **Conflict severity**: Based on file patterns (auth/security = critical, api/core = high)

### Blockers

(None yet)

---

## Supporting Systems

### Multi-Model Code Review System

**Status:** OPERATIONAL
**Location:** `src/review/`

The review system uses multiple AI models to review code changes before merge.

| Component | Status | Description |
|-----------|--------|-------------|
| `src/review/orchestrator.py` | **DONE** | ReviewOrchestrator with tier selection |
| `src/review/models.py` | **DONE** | LiteLLM-based adapters for all providers |
| `src/review/schema.py` | **DONE** | ReviewConfig, ModelSpec, ReviewIssue |

**Configured Models:**

| Provider | Model | Focus Areas | Status |
|----------|-------|-------------|--------|
| OpenAI | gpt-5.2-max | Security, Correctness | Working |
| Google | gemini-2.5-pro | Architecture, Design | Working |
| xAI | grok-4.1 | Operations, Edge Cases | Working |
| OpenAI | codex → gpt-5.2-max | Correctness, Performance | Working |

**API Keys:** Managed via SOPS (`secrets.enc.yaml`)

### Third-Party Design Reviews

Design reviews were conducted by multiple AI models:

| Round | Reviewers | Key Findings |
|-------|-----------|--------------|
| Round 1 | Claude Opus, Gemini, Grok, ChatGPT | Initial architecture validation |
| Round 2 | Codex, Grok, Gemini, ChatGPT | Security (split workflows), "derive don't trust" |
| Round 3 | Codex | O(n²) scaling, existing code security issues |

**Key Validated Decisions:**
- Split workflows (untrusted ping + trusted coordinator)
- Manifest-as-artifact (not in git)
- "Derive, don't trust" philosophy
- Tiered validation approach

**Outstanding Recommendations (from reviews):**
- [x] Fix existing orchestrator security issues (path traversal, CSRF, manual gates)
- [ ] Add artifact signing/attestation
- [ ] Add CODEOWNERS integration for intent conflicts
- [x] Design pattern lifecycle for learning system (see below)

### Roadmap / Future Enhancements

| Item | Priority | Description |
|------|----------|-------------|
| ~~Review Types Single Source of Truth~~ | ~~**CRITICAL**~~ | **COMPLETE** - See "Review Types Consolidation" section below |
| Orchestrator Context Persistence | HIGH | Build mechanism to ensure Claude remembers to use orchestrator after context compaction. Options: (1) Add to system prompt, (2) Hook into context restore, (3) Automated prompt injection |
| Background Parallel Reviews | HIGH | Run external model reviews in background during workflow, not just at commit. Trigger on file save, cache results, notify when complete. Reviews should run continuously as code is written. |
| Fix OpenAI Model Configuration | HIGH | OpenAI models (gpt-5.2-max, codex) fail in litellm due to model naming format. Need to update `src/review/models.py` to use correct litellm format (e.g., `openai/gpt-4` not `gpt-5.2-max`). |
| Use CLI Tools for Reviews | HIGH | Use Gemini CLI (aistudio) and Codex CLI for reviews instead of API - they have better repo context because they can browse files directly. Update ReviewOrchestrator to shell out to CLI tools. |
| ~~Fix Phase 3 Security Issues~~ | ~~HIGH~~ | **COMPLETE** - See "Phase 3 Security Remediation" section below |
| Write spec-driven tests for Phase 3 | MEDIUM | Existing tests were written post-implementation; add TDD-style tests from spec |
| Artifact signing/attestation | MEDIUM | Prevent manifest tampering |
| CODEOWNERS integration | LOW | Use CODEOWNERS for intent conflict escalation |

### Review Types Consolidation (CRITICAL Priority)

**Status:** COMPLETE (Session 9)
**Priority:** CRITICAL - Prevented configuration drift bugs

**Problem:** Review types were defined in 3 places:
1. `workflow.yaml` settings.reviews.types
2. `prompts.py` REVIEW_TOOLS dict
3. `model_registry.py` category_mapping

This caused a bug when adding `vibe_coding_review` - one location was forgotten.

**Solution:** Made `workflow.yaml` the single source of truth.

| File | Change |
|------|--------|
| `src/review/config.py` | **NEW** - ReviewTypeConfig reads from workflow.yaml |
| `src/review/prompts.py` | Removed hardcoded REVIEW_TOOLS, `get_tool()` now uses config |
| `src/model_registry.py` | Added `_resolve_category()` that uses config |
| `src/default_workflow.yaml` | Added `vibe_coding_review: grok` |
| `tests/review/test_config.py` | **NEW** - 15 tests for config module |

**Adding a new review type now requires changes in ONLY 2 places:**
1. `workflow.yaml` - add type → tool mapping
2. `prompts.py` - add the prompt template

**Verification:**
- All 15 config tests pass
- All existing tests pass (494/496, 2 pre-existing failures)
- Imports and functions verified working

---

### Phase 3 Security Remediation (from Third-Party Review)

**Status:** COMPLETE - All 4 critical issues fixed (Session 6)
**Priority:** HIGH - Fixed before production use

| Issue | File | Severity | Status | Fix Description |
|-------|------|----------|--------|-----------------|
| Command injection | `src/resolution/validator.py` | **CRITICAL** | **FIXED** | Changed to `shell=False` with `shlex.split()`, added `_validate_branch_name()` |
| Path traversal | `src/resolution/context.py` | **CRITICAL** | **FIXED** | Added `_sanitize_filepath()` and `_validate_repo_path()` functions |
| Branch name injection | `src/resolution/candidate.py` | **CRITICAL** | **FIXED** | Added `_validate_branch_name()` with regex validation |
| Missing exception handling | `src/resolution/pipeline.py` | **HIGH** | **FIXED** | Wrapped all 6 stages in try/except, return escalation Resolution on failure |

**Verification:**
- All 21 resolution tests pass
- All 22 escalation tests pass
- 59/61 total tests pass (2 pre-existing failures in conflict module)

### Learning System - Pattern Lifecycle Design

**Philosophy:** Autonomous improvement without human review queues.

**Pattern States:**
```
ACTIVE (high confidence) → Used frequently, validated
SUGGESTING (medium confidence) → Suggest but don't auto-apply
DORMANT (low confidence) → Not matched recently, may be stale
DEPRECATED → Failed validation, kept for reference only
```

**Lifecycle Rules:**

| Event | Action |
|-------|--------|
| Pattern matched + validation passes | Refresh timestamp, boost confidence |
| Pattern matched + validation fails | Decrease confidence, flag for analysis |
| Pattern unused for N days | Decay confidence by X% |
| Confidence drops below threshold | Move to SUGGESTING (human sees suggestion) |
| Confidence drops to minimum | Move to DORMANT (not applied) |
| Pattern causes repeated failures | Move to DEPRECATED |

**Auto-Improvement Mechanisms:**
1. **Success tracking**: Patterns that lead to passing builds strengthen
2. **Failure learning**: Failed patterns generate "anti-patterns" to avoid
3. **Context binding**: Patterns tagged with (language, framework, conflict_type)
4. **Version awareness**: Patterns can be tied to framework versions, auto-expire when versions change

**No Human Review Required:**
- Patterns self-manage based on validation outcomes
- System improves through use, not manual curation
- Failed patterns are deprecated, not deleted (forensics)

See: `docs/design-review-round3-synthesis.md` for full details.

---

## Phase 2: Conflict Detection

**Goal:** Accurate conflict classification
**Deliverable:** System that accurately identifies and classifies conflicts

### Checklist

- [x] Stage 0: Full detection pipeline (`src/conflict/pipeline.py`)
- [x] Build/test merged result (`src/conflict/build_tester.py`)
- [x] Semantic conflict detection (`src/conflict/semantic.py`)
- [x] Dependency conflict detection (`src/conflict/dependency.py`)
- [x] Conflict clustering (`src/conflict/clusterer.py`)
- [x] Risk flag detection (enhanced `src/conflict/detector.py`)

### Files Created

| File | Status | Description |
|------|--------|-------------|
| `src/conflict/pipeline.py` | **DONE** | DetectionPipeline orchestrating all steps |
| `src/conflict/build_tester.py` | **DONE** | BuildTester for merged code testing |
| `src/conflict/dependency.py` | **DONE** | DependencyAnalyzer for package conflicts |
| `src/conflict/semantic.py` | **DONE** | SemanticAnalyzer for symbol/domain overlap |
| `src/conflict/clusterer.py` | **DONE** | ConflictClusterer for wave-based resolution |
| `tests/conflict/test_pipeline.py` | **DONE** | Tests for Phase 2 components |

---

## Phase 3: Basic Resolution

**Goal:** Resolve simple conflicts automatically
**Deliverable:** System that auto-resolves ~60% of conflicts

### Checklist

- [x] Stage 1: Context assembly (`src/resolution/context.py`)
- [x] Stage 2: Intent extraction (basic) (`src/resolution/intent.py`)
- [x] Stage 3: Interface harmonization (`src/resolution/harmonizer.py`)
- [x] Single candidate generation (`src/resolution/candidate.py`)
- [x] Basic validation (build + targeted tests) (`src/resolution/validator.py`)
- [x] Resolution pipeline orchestrator (`src/resolution/pipeline.py`)

### Files Created

| File | Status | Description |
|------|--------|-------------|
| `src/resolution/__init__.py` | **DONE** | Package init with all exports |
| `src/resolution/schema.py` | **DONE** | Data models (ConflictContext, ExtractedIntent, etc.) |
| `src/resolution/context.py` | **DONE** | Stage 1: Context assembly from manifests and git |
| `src/resolution/intent.py` | **DONE** | Stage 2: Intent extraction and comparison |
| `src/resolution/harmonizer.py` | **DONE** | Stage 3: Interface harmonization |
| `src/resolution/candidate.py` | **DONE** | Candidate generation with strategy selection |
| `src/resolution/validator.py` | **DONE** | Build/test validation and scoring |
| `src/resolution/pipeline.py` | **DONE** | Main ResolutionPipeline orchestrator |
| `tests/resolution/test_resolution.py` | **DONE** | Tests for Phase 3 components |

### Key Design Decisions

1. **Heuristic-based intent extraction** for Phase 3 (LLM-based in Phase 5)
2. **Single candidate generation** - select best strategy, generate one candidate
3. **Auto-escalate on low confidence** - don't guess when unsure
4. **Strategy selection** based on intent confidence and harmonization success

---

## Phase 4: Escalation System

**Goal:** Handle complex conflicts gracefully
**Deliverable:** Complete escalation workflow for complex conflicts

### Checklist

- [x] Escalation schema and data models (`src/escalation/schema.py`)
- [x] Escalation issue creation (`src/escalation/issue_creator.py`)
- [x] Plain-English options (integrated in IssueCreator)
- [x] Response handling (`src/escalation/response_handler.py`)
- [x] Feature porting (winner/loser) (`src/escalation/feature_porter.py`)
- [x] Timeout handling with SLA policies (`src/escalation/timeout_handler.py`)
- [x] Main orchestrator (`src/escalation/manager.py`)
- [x] Tests (`tests/escalation/test_escalation.py`)

### Files Created

| File | Status | Description |
|------|--------|-------------|
| `src/escalation/__init__.py` | **DONE** | Package init with all exports |
| `src/escalation/schema.py` | **DONE** | EscalationTrigger, Priority, Status, TimeoutPolicy, etc. |
| `src/escalation/issue_creator.py` | **DONE** | GitHub issue creation with plain-English options |
| `src/escalation/response_handler.py` | **DONE** | Parse and process user responses (A/B/C, explain, custom:) |
| `src/escalation/feature_porter.py` | **DONE** | Port unique features from losing to winning option |
| `src/escalation/timeout_handler.py` | **DONE** | SLA-based reminders and auto-selection |
| `src/escalation/manager.py` | **DONE** | Main EscalationManager orchestrator |
| `tests/escalation/__init__.py` | **DONE** | Test package init |
| `tests/escalation/test_escalation.py` | **DONE** | 22 tests covering all components |

### Key Design Decisions

1. **Policy-based timeouts**: Different SLAs by priority (critical 24h no-auto, standard 72h with auto-select)
2. **Never auto-select critical/high**: Security, auth, DB migrations always require human decision
3. **Feature porting**: Unique features from losing options are ported to winning architecture
4. **Multi-channel notifications**: GitHub, Slack, email (when configured)
5. **Priority emojis**: 🚨 critical, ⚠️ high, 🤔 standard for visual distinction

---

## Phase 5: Advanced Resolution

**Goal:** Resolve more conflicts automatically
**Deliverable:** System that auto-resolves ~80% of conflicts

### Checklist

- [x] Multiple candidate strategies (`src/resolution/multi_candidate.py`)
- [x] Full validation tiers (`src/resolution/validation_tiers.py`)
- [x] Candidate diversity enforcement (`src/resolution/diversity.py`)
- [x] Self-critique (optional) (`src/resolution/self_critic.py`)
- [x] Flaky test handling (`src/resolution/flaky_handler.py`)

### Files Created

| File | Status | Description |
|------|--------|-------------|
| `src/resolution/multi_candidate.py` | **DONE** | MultiCandidateGenerator - generates 3 candidates with distinct strategies |
| `src/resolution/diversity.py` | **DONE** | DiversityChecker - ensures candidates are meaningfully different |
| `src/resolution/validation_tiers.py` | **DONE** | TieredValidator - smoke/lint/targeted/comprehensive tiers |
| `src/resolution/flaky_handler.py` | **DONE** | FlakyTestHandler - tracks flakiness, retries, adjusts scoring |
| `src/resolution/self_critic.py` | **DONE** | SelfCritic - LLM-based critique via LiteLLM (optional) |
| `src/resolution/schema.py` | **UPDATED** | Added ValidationTier, FlakyTestRecord, CritiqueResult, DiversityResult, TieredValidationResult |
| `tests/resolution/test_phase5.py` | **DONE** | 32 tests covering all Phase 5 components |

### Key Design Decisions

1. **3 strategies by default**: agent1_primary, agent2_primary, convention_primary (fresh_synthesis optional)
2. **Diversity threshold**: min 0.3 Jaccard distance between candidates
3. **Tiered validation**: Smoke → Lint → Targeted → Comprehensive (high-risk only)
4. **Flaky handling**: Track history, retry up to 3x, downweight flaky failures
5. **Self-critique**: Optional LLM review for security/bugs (disabled by default)

### Security Fixes Applied

1. **Command validation whitelist** in `validation_tiers.py` - only allows known-safe commands
2. **Prompt sanitization** in `self_critic.py` - prevents prompt injection via agent data

---

## Phase 6: PRD Mode & Scale

**Goal:** Handle full PRD execution
**Deliverable:** System that executes full PRDs with many agents

### Checklist

- [x] PRD mode configuration (`src/prd/schema.py`)
- [x] Wave-based resolution (`src/prd/wave_resolver.py`)
- [x] Integration branch management (`src/prd/integration.py`)
- [x] Checkpoint PRs (in IntegrationBranchManager)
- [x] Multi-backend worker pool (`src/prd/worker_pool.py`)
- [x] File-based job queue (`src/prd/queue.py`)
- [x] Backend implementations:
  - [x] LocalBackend (Claude Code CLI)
  - [x] ManualBackend (Claude Web prompts)
  - [x] ModalBackend (serverless)
  - [x] RenderBackend (containers)
  - [x] GitHubActionsBackend
- [x] PRD Executor orchestrator (`src/prd/executor.py`)
- [x] Scale to 20+ concurrent agents (configurable)
- [x] CLI integration with orchestrator (`orchestrator prd` command)
- [ ] End-to-end testing with real PRD

### Files Created

| File | Status | Description |
|------|--------|-------------|
| `src/prd/__init__.py` | **DONE** | Package init with all exports |
| `src/prd/schema.py` | **DONE** | PRDConfig, PRDTask, PRDDocument, JobMessage, WorkerBackend enum |
| `src/prd/queue.py` | **DONE** | FileJobQueue (pending/processing/completed/failed) |
| `src/prd/worker_pool.py` | **DONE** | WorkerPool with auto-scaling backend selection |
| `src/prd/integration.py` | **DONE** | IntegrationBranchManager, MergeRecord, CheckpointPR |
| `src/prd/wave_resolver.py` | **DONE** | WaveResolver, WaveResult, WaveResolutionResult |
| `src/prd/executor.py` | **DONE** | PRDExecutor, PRDExecutionResult |
| `src/prd/backends/__init__.py` | **DONE** | Backend package exports |
| `src/prd/backends/base.py` | **DONE** | WorkerBackendBase abstract class |
| `src/prd/backends/local.py` | **DONE** | LocalBackend (Claude Code CLI) |
| `src/prd/backends/manual.py` | **DONE** | ManualBackend (prompts for Claude Web) |
| `src/prd/backends/modal_worker.py` | **DONE** | ModalBackend (serverless functions) |
| `src/prd/backends/render.py` | **DONE** | RenderBackend (containers) |
| `src/prd/backends/github_actions.py` | **DONE** | GitHubActionsBackend |
| `tests/prd/__init__.py` | **DONE** | Test package init |
| `tests/prd/test_schema.py` | **DONE** | Schema tests |
| `tests/prd/test_queue.py` | **DONE** | Job queue tests |
| `tests/prd/test_workers.py` | **DONE** | Worker pool and backend tests |

### Key Design Decisions

1. **Provider-agnostic architecture**: WorkerBackend enum with auto-selection based on task count and credentials
2. **Auto-scaling**: Local for ≤4 tasks, cloud backends for larger scale
3. **File-based job queue**: Simple, reliable, no external dependencies (pending/processing/completed/failed dirs)
4. **Integration branch strategy**: `integration/{prd_id}` accumulates work, checkpoint PRs to main
5. **Wave-based resolution**: Merge non-conflicting first, then resolve conflicts in waves
6. **Manual backend for Claude Web**: Generates copy/paste prompts when no API available

### Backend Selection Logic

```
task_count ≤ 4: LOCAL (Claude Code CLI)
task_count > 4:
  1. MODAL (if credentials available) - serverless, fastest
  2. RENDER (if credentials available) - containers
  3. GITHUB_ACTIONS (if authenticated) - built-in
  4. MANUAL - generate prompts for Claude Web
```

### Secrets Configured

| Secret | Location | Purpose |
|--------|----------|---------|
| `render_api_key` | secrets.enc.yaml | Render container backend |
| `modal_token_id` | secrets.enc.yaml | Modal serverless auth |
| `modal_token_secret` | secrets.enc.yaml | Modal serverless auth |

---

## Phase 7: Learning & Optimization

**Goal:** System improves over time
**Deliverable:** Self-improving system

**EXECUTION PLAN:** Phase 7 will be implemented using the PRD system itself (dogfooding).
This serves as both the Phase 7 implementation AND the end-to-end test for Phase 6.

```bash
# In a new chat session with fresh context:
orchestrator prd start examples/phase7_prd.yaml --backend local
```

The PRD file (`examples/phase7_prd.yaml`) contains 10 tasks with proper dependencies.

### Checklist

- [ ] Pattern memory schema (`src/learning/pattern_schema.py`)
- [ ] Pattern database (`src/learning/pattern_database.py`)
- [ ] Pattern hasher (`src/learning/pattern_hasher.py`)
- [ ] Pattern memory integration (`src/learning/pattern_memory.py`)
- [ ] Strategy tracker schema (`src/learning/strategy_schema.py`)
- [ ] Strategy tracker (`src/learning/strategy_tracker.py`)
- [ ] Agent feedback schema (`src/learning/feedback_schema.py`)
- [ ] Feedback loop (`src/learning/feedback_loop.py`)
- [ ] Learning engine integration
- [ ] Performance optimization

---

## Session Log

### Session 1 (Current)
**Date:** January 2026
**Context:** Continued from previous session (context compacted once)
**Work Done:**
- Created design document with multi-AI review integration
- Implemented SOPS secrets infrastructure
- Implemented multi-model code review system (`src/review/`)
- Created this implementation tracker
- Implemented Phase 1 core modules:
  - `src/coordinator/schema.py` - AgentManifest, DerivedManifest, status enums
  - `src/coordinator/discovery.py` - AgentDiscovery for finding claude/* branches
  - `src/coordinator/manifest_store.py` - Local + GitHub artifact storage
  - `src/coordinator/fast_path.py` - FastPathMerger for PR creation
  - `src/conflict/detector.py` - ConflictDetector using git merge-tree

**Next:** Simple notifications, then Phase 1 complete

### Session 2
**Date:** January 2026
**Work Done:**
- Created GitHub Actions workflows:
  - `claude-branch-ping.yml` - untrusted workflow that pings coordinator on claude/* branch push
  - `claude-coordinator.yml` - trusted workflow that runs coordination on main branch
- Created `src/coordinator/__main__.py` - CLI entry point for running coordinator from GitHub Actions
- Updated this tracker

**Status:** Phase 1 COMPLETE - ready to commit and begin Phase 2

### Session 3
**Date:** January 2026
**Work Done:**
- Completed Phase 2: Conflict Detection
  - `pipeline.py` - 6-step detection orchestrator
  - `build_tester.py` - Tests merged code (catches "clean but broken")
  - `dependency.py` - Detects version conflicts in package files
  - `semantic.py` - Symbol overlap, domain overlap, API changes
  - `clusterer.py` - Groups conflicts for wave-based resolution
  - Enhanced `detector.py` with risk flag detection
- Added tests in `tests/conflict/test_pipeline.py`
- Used orchestrator workflow system for implementation

**Status:** Phase 2 COMPLETE - ready to commit and begin Phase 3

### Session 4
**Date:** January 2026
**Work Done:**
- Fixed security vulnerabilities from Codex review:
  - Path traversal prevention in `src/engine.py`
  - Manual gates bypass prevention in `src/schema.py`
  - CSRF token protection in `src/dashboard.py`
- Designed autonomous pattern lifecycle for learning system
- Completed Phase 3: Basic Resolution
  - `src/resolution/schema.py` - Data models for resolution pipeline
  - `src/resolution/context.py` - Stage 1: Context assembly
  - `src/resolution/intent.py` - Stage 2: Intent extraction and comparison
  - `src/resolution/harmonizer.py` - Stage 3: Interface harmonization
  - `src/resolution/candidate.py` - Candidate generation with strategy selection
  - `src/resolution/validator.py` - Build/test validation and scoring
  - `src/resolution/pipeline.py` - Main ResolutionPipeline orchestrator
  - `tests/resolution/test_resolution.py` - Comprehensive tests

**Status:** Phase 3 COMPLETE - ready to commit and begin Phase 4

### Session 5
**Date:** January 2026
**Work Done:**
- Completed Phase 4: Escalation System
  - `src/escalation/schema.py` - EscalationTrigger, Priority, Status, TimeoutPolicy, ALWAYS_ESCALATE_TRIGGERS
  - `src/escalation/issue_creator.py` - GitHub issue creation with priority emojis and plain-English options
  - `src/escalation/response_handler.py` - Parse user responses (A/B/C selection, explain, custom:)
  - `src/escalation/feature_porter.py` - Port unique features from losing to winning architecture
  - `src/escalation/timeout_handler.py` - SLA-based reminders and auto-selection (policy-driven)
  - `src/escalation/manager.py` - Main EscalationManager orchestrating the full lifecycle
  - `tests/escalation/test_escalation.py` - 22 tests covering all components (all passing)
- Ran third-party review of Phase 3 code
  - Found 4 critical security issues (see Phase 3 Security Remediation above)
- Added orchestrator reminder mechanism to Quick Start section

**Important Process Notes:**
- User emphasized: ALWAYS use orchestrator for code changes (not trivial documentation updates)
- Phase 3 tests were written post-implementation (not TDD) - noted for future phases
- Third-party reviews should be run BEFORE committing phases

**Status:** Phase 4 COMPLETE - ready to commit. Phase 3 security issues pending remediation.

### Session 6
**Date:** January 2026
**Work Done:**
- Fixed all 4 Phase 3 security vulnerabilities:
  - `validator.py`: Changed subprocess to `shell=False` with `shlex.split()`, added branch validation
  - `context.py`: Added `_sanitize_filepath()` and `_validate_repo_path()` functions
  - `candidate.py`: Added `_validate_branch_name()` function with regex validation
  - `pipeline.py`: Added try/except blocks around all 6 stages with proper error escalation
- Created `scripts/pre_commit_review.py` enforcement script for mandatory external model reviews
- Updated IMPLEMENTATION-TRACKER.md with mandatory review process
- All tests pass (21 resolution + 22 escalation = 43; 59/61 total with 2 pre-existing failures)

**Important Process Notes:**
- Identified gap: Phase 3 was reviewed by Claude sub-agent, NOT by ReviewOrchestrator with external models
- Created enforcement mechanism: pre_commit_review.py must be run before any commit
- External models (GPT-5.2 Max, Gemini, Grok, Codex) are required for code reviews, not just internal Claude

**Status:** Phase 3 Security Remediation COMPLETE. Ready for external model review and commit.

### Session 7
**Date:** January 2026
**Work Done:**
- Completed Phase 5: Advanced Resolution
  - `src/resolution/multi_candidate.py` - MultiCandidateGenerator (3 strategies, configurable)
  - `src/resolution/diversity.py` - DiversityChecker (Jaccard distance, min 0.3 threshold)
  - `src/resolution/validation_tiers.py` - TieredValidator (smoke/lint/targeted/comprehensive)
  - `src/resolution/flaky_handler.py` - FlakyTestHandler (history tracking, retries, score adjustment)
  - `src/resolution/self_critic.py` - SelfCritic (LLM-based review via LiteLLM, optional)
  - `src/resolution/schema.py` - Added ValidationTier, FlakyTestRecord, CritiqueResult, etc.
  - `tests/resolution/test_phase5.py` - 32 new tests (TDD approach)
- Fixed 2 security issues found in Phase 5 review:
  - Added command validation whitelist in `validation_tiers.py`
  - Added prompt sanitization in `self_critic.py`
- All 53 resolution tests pass (21 Phase 3 + 32 Phase 5)
- Used orchestrator workflow system throughout

**Process Notes:**
- Followed TDD: wrote tests first, then implementation
- Security review caught issues before commit
- Third-party reviews (external models) ran during REVIEW phase

**Status:** Phase 5 COMPLETE. Ready to commit.

### Session 8
**Date:** January 2026
**Work Done:**
- Gold-plated the review system for vibe coding (zero human review):
  - Added 5th review: `vibe_coding_review` using Grok 4.1 for AI-specific issues
  - Fixed root cause: REVIEW phase items now include all 5 reviews (was missing consistency + holistic)
  - All reviews run in background for parallel execution
- Fixed model versioning:
  - CLI executor now uses `model_registry.get_latest_model()` instead of hardcoding
  - Added Grok to model_registry with correct OpenRouter IDs (`x-ai/grok-4.1-fast`)
  - Updated workflow.yaml and default_workflow.yaml with all models
- Improved visibility:
  - `cmd_finish` now shows which external models performed reviews
  - Added API key checks to `install.sh` with SOPS instructions
  - Added review event types to schema.py

**Root Causes Fixed:**
1. Gemini reviews skipped: workflow phase items didn't match configured review types
2. Used outdated Grok model: hardcoded instead of using model_registry framework
3. Wrong model ID format: `grok-4-1-fast-reasoning` vs actual `grok-4.1-fast`

**Architectural Issue Identified:**
Review types defined in 3 places (workflow.yaml, prompts.py, model_registry.py) - added to roadmap as CRITICAL priority to consolidate to single source of truth.

**Status:** Review system improvements committed. Ready for Phase 6 or architectural cleanup.

### Session 9
**Date:** January 2026
**Work Done:**
- Fixed CRITICAL roadmap item: Review Types Single Source of Truth
  - Created `src/review/config.py` - ReviewTypeConfig reads from workflow.yaml
  - Updated `src/review/prompts.py` - removed hardcoded REVIEW_TOOLS, uses config
  - Updated `src/model_registry.py` - `_resolve_category()` uses config
  - Updated `src/default_workflow.yaml` - added `vibe_coding_review: grok`
  - Created `tests/review/test_config.py` - 15 tests for config module
- Used orchestrator workflow system throughout (PLAN → EXECUTE → REVIEW → VERIFY → LEARN)

**Key Changes:**
- Adding a new review type now requires changes in ONLY 2 places:
  1. `workflow.yaml` - add type → tool mapping
  2. `prompts.py` - add the prompt template
- Backward compatibility maintained via `_ReviewToolsProxy` class

**Status:** Architectural cleanup COMPLETE. Ready to continue with Phase 6.

### Session 9 (Continued)
**Date:** January 2026
**Work Done:**
- Implemented Phase 6: PRD Mode & Scale core infrastructure
  - `src/prd/schema.py` - PRDConfig, PRDTask, PRDDocument, JobMessage, WorkerBackend enum, backend configs
  - `src/prd/queue.py` - FileJobQueue with pending/processing/completed/failed directories
  - `src/prd/worker_pool.py` - WorkerPool with auto-scaling backend selection
  - `src/prd/integration.py` - IntegrationBranchManager, MergeRecord, CheckpointPR
  - `src/prd/wave_resolver.py` - WaveResolver for wave-based conflict resolution
  - `src/prd/executor.py` - PRDExecutor main orchestrator
  - 5 backend implementations (Local, Manual, Modal, Render, GitHub Actions)
  - 51 tests passing
- Added Render and Modal credentials to encrypted secrets
- User provided:
  - Render API key: `rnd_VxSWOndcqHxRCamT0KEnycgHRWFz`
  - Modal token: `ak-YjLWQg7WOslrl4rUsT8j7T` / `as-UhDItFATIrLFSjDw8JzBpZ`

**Key Design Decisions:**
- Provider-agnostic: all 5 backends supported with auto-selection
- Auto-scaling: Local for ≤4 tasks, cloud for larger scale
- ManualBackend for Claude Web users (generates copy/paste prompts)
- Integration branch pattern: `integration/{prd_id}` accumulates work

**Status:** Phase 6 core infrastructure COMPLETE. Pending: CLI integration, end-to-end tests, external reviews.

---

## Context Switch Guidelines

**Start a new chat when:**
1. Completing a phase (natural breakpoint)
2. After 3-4 major implementation sessions
3. Context feels slow/repetitive
4. Before starting complex multi-file implementation

**Before switching:**
1. Update this tracker with current status
2. Commit all work with descriptive message
3. Note any in-progress work or decisions needed

**After switching (new chat prompt):**
```
I'm implementing a multi-agent merge conflict system. Please read:
1. docs/IMPLEMENTATION-TRACKER.md (current status)
2. The relevant phase section in docs/FINAL-merge-conflict-system-design.md

Continue from where we left off. I'm multi-tasking so guide me through it.
Use the orchestrator workflow system for complex coding tasks.
```

---

## Architecture Reference

```
src/
├── coordinator/       # Multi-agent coordination (Phase 1)
│   ├── schema.py      # Agent manifest, status enums
│   ├── discovery.py   # Find agent branches
│   ├── manifest_store.py  # GitHub artifact storage
│   └── fast_path.py   # Non-conflict merge
├── conflict/          # Conflict detection (Phase 1-2)
│   ├── detector.py    # Basic detection (merge-tree)
│   ├── pipeline.py    # 6-step detection orchestrator
│   ├── build_tester.py # Build/test validation
│   ├── semantic.py    # Symbol/domain analysis
│   ├── dependency.py  # Package version conflicts
│   └── clusterer.py   # Graph clustering
├── resolution/        # Resolution pipeline (Phase 3 + 5) DONE
│   ├── schema.py      # Data models (ConflictContext, Intent, ValidationTier, etc.)
│   ├── pipeline.py    # Main orchestration
│   ├── context.py     # Stage 1: Context assembly
│   ├── intent.py      # Stage 2: Intent extraction
│   ├── harmonizer.py  # Stage 3: Interface harmonization
│   ├── candidate.py   # Single candidate generation (Phase 3)
│   ├── validator.py   # Build/test validation (Phase 3)
│   ├── multi_candidate.py  # Multi-candidate generation (Phase 5)
│   ├── diversity.py   # Candidate diversity checking (Phase 5)
│   ├── validation_tiers.py # Tiered validation (Phase 5)
│   ├── flaky_handler.py    # Flaky test handling (Phase 5)
│   └── self_critic.py      # LLM self-critique (Phase 5)
├── escalation/        # Human escalation (Phase 4) DONE
│   ├── schema.py      # EscalationTrigger, Priority, Status, TimeoutPolicy
│   ├── issue_creator.py # GitHub issue creation
│   ├── response_handler.py # Parse user responses
│   ├── feature_porter.py # Port features from loser to winner
│   ├── timeout_handler.py # SLA-based reminders/auto-select
│   └── manager.py     # Main EscalationManager
├── review/            # Code review (DONE)
├── prd/               # PRD execution (Phase 6) IN PROGRESS
│   ├── schema.py      # PRDConfig, PRDTask, PRDDocument, JobMessage
│   ├── queue.py       # FileJobQueue (file-based job queue)
│   ├── worker_pool.py # WorkerPool with auto-scaling
│   ├── integration.py # Integration branch management
│   ├── wave_resolver.py # Wave-based conflict resolution
│   ├── executor.py    # PRDExecutor main orchestrator
│   └── backends/      # Worker backend implementations
│       ├── base.py        # WorkerBackendBase abstract class
│       ├── local.py       # LocalBackend (Claude Code CLI)
│       ├── manual.py      # ManualBackend (Claude Web prompts)
│       ├── modal_worker.py # ModalBackend (serverless)
│       ├── render.py      # RenderBackend (containers)
│       └── github_actions.py # GitHubActionsBackend
└── git_ops/           # Git operations wrapper
```
