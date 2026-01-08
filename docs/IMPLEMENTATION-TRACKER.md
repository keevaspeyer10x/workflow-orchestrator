# Multi-Agent Merge Conflict System - Implementation Tracker

**Design Document:** `docs/FINAL-merge-conflict-system-design.md`
**Started:** January 2026
**Current Phase:** 1 - Foundation (MVP)

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
| 2. Conflict Detection | Not Started | N/A |
| 3. Basic Resolution | Not Started | ~60% |
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

## Phase 2: Conflict Detection

**Goal:** Accurate conflict classification
**Deliverable:** System that accurately identifies and classifies conflicts

### Checklist

- [ ] Stage 0: Full detection pipeline
- [ ] Build/test merged result
- [ ] Semantic conflict detection
- [ ] Dependency conflict detection
- [ ] Conflict clustering
- [ ] Risk flag detection

---

## Phase 3: Basic Resolution

**Goal:** Resolve simple conflicts automatically
**Deliverable:** System that auto-resolves ~60% of conflicts

### Checklist

- [ ] Stage 1: Context assembly
- [ ] Stage 2: Intent extraction (basic)
- [ ] Stage 3: Interface harmonization
- [ ] Single candidate generation
- [ ] Basic validation (build + targeted tests)
- [ ] Auto-resolve low-risk conflicts

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
│   ├── classifier.py  # Type/severity (Phase 2)
│   └── clusterer.py   # Graph clustering (Phase 2)
├── resolution/        # Resolution pipeline (Phase 3-5)
│   ├── pipeline.py    # Orchestration
│   ├── context.py     # Stage 1
│   ├── intent.py      # Stage 2
│   └── ...
├── escalation/        # Human escalation (Phase 4)
├── review/            # Code review (DONE)
└── git_ops/           # Git operations wrapper
```
