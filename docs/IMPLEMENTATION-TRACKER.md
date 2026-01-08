# Multi-Agent Merge Conflict System - Implementation Tracker

**Design Document:** `docs/FINAL-merge-conflict-system-design.md`
**Started:** January 2026
**Current Phase:** 4 - Escalation System (Next)

---

## Quick Start for New Chat Sessions

When starting a new chat, read these files in order:
1. This file (`docs/IMPLEMENTATION-TRACKER.md`) - current status
2. Design doc Section 15 (`docs/FINAL-merge-conflict-system-design.md` lines 3999-4082) - phase details
3. Any files marked as "In Progress" below

**Important:** User prefers to use the orchestrator workflow system for complex coding tasks.

---

## Overall Progress

| Phase | Status | Auto-Resolve Target |
|-------|--------|---------------------|
| 1. Foundation (MVP) | **COMPLETE** | N/A (fast-path only) |
| 2. Conflict Detection | **COMPLETE** | N/A |
| 3. Basic Resolution | **COMPLETE** | ~60% |
| 4. Escalation System | Not Started | N/A |
| 5. Advanced Resolution | Not Started | ~80% |
| 6. PRD Mode & Scale | Not Started | N/A |
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

- [ ] Escalation issue creation
- [ ] Plain-English options
- [ ] Response handling
- [ ] Feature porting (winner/loser)
- [ ] Timeout handling

---

## Phase 5: Advanced Resolution

**Goal:** Resolve more conflicts automatically
**Deliverable:** System that auto-resolves ~80% of conflicts

### Checklist

- [ ] Multiple candidate strategies
- [ ] Full validation tiers
- [ ] Candidate diversity enforcement
- [ ] Self-critique (optional)
- [ ] Flaky test handling

---

## Phase 6: PRD Mode & Scale

**Goal:** Handle full PRD execution
**Deliverable:** System that executes full PRDs with many agents

### Checklist

- [ ] PRD mode configuration
- [ ] Wave-based resolution
- [ ] Integration branch management
- [ ] Checkpoint PRs
- [ ] Auto-merge configuration
- [ ] Scale to 20+ concurrent agents

---

## Phase 7: Learning & Optimization

**Goal:** System improves over time
**Deliverable:** Self-improving system

### Checklist

- [ ] Pattern memory (rerere-like)
- [ ] Strategy performance tracking
- [ ] Agent feedback loop
- [ ] Integration with orchestrator learning
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
├── resolution/        # Resolution pipeline (Phase 3) DONE
│   ├── schema.py      # Data models (ConflictContext, Intent, etc.)
│   ├── pipeline.py    # Main orchestration
│   ├── context.py     # Stage 1: Context assembly
│   ├── intent.py      # Stage 2: Intent extraction
│   ├── harmonizer.py  # Stage 3: Interface harmonization
│   ├── candidate.py   # Candidate generation
│   └── validator.py   # Build/test validation
├── escalation/        # Human escalation (Phase 4) - TODO
├── review/            # Code review (DONE)
└── git_ops/           # Git operations wrapper
```
