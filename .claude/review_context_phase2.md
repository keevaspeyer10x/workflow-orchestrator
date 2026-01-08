# Design Review Request: PRD-001 Phase 2 - Claude Squad Integration

## Context for Reviewers

You are reviewing a design plan for Phase 2 of integrating Claude Squad into a Workflow Orchestrator system. Please provide critical feedback on the approach, identify risks, and suggest improvements.

---

## 1. What is This System?

**Workflow Orchestrator** is a tool for executing Product Requirement Documents (PRDs) using multiple AI agents (Claude Code instances) working in parallel.

**Claude Squad** is an external tool that manages multiple Claude Code sessions in tmux terminals. Each session is a full interactive Claude Code instance the user can attach to and monitor.

**Goal**: Enable a user to spawn 10+ Claude Code agents working on different tasks simultaneously, then merge their work together with automatic conflict resolution.

**Key constraint**: This is a "zero human code review" / "vibe coding" system. The system must handle conflicts automatically with minimal user intervention.

---

## 2. What Phase 1 Accomplished (Already Implemented)

Created 4 new modules with 66 tests:

1. **SessionRegistry** (`src/prd/session_registry.py`)
   - Persists task↔session mappings to `.claude/squad_sessions.json`
   - Thread-safe via file locking
   - Survives orchestrator restarts
   - Auto-reconciliation with Claude Squad state

2. **SquadCapabilities** (`src/prd/squad_capabilities.py`)
   - Detects Claude Squad CLI capabilities via --version and --help parsing
   - Validates minimum version and required flags
   - Fails fast if incompatible

3. **ClaudeSquadAdapter** (`src/prd/squad_adapter.py`)
   - Spawns Claude Squad sessions for tasks
   - Idempotent spawning (returns existing if already spawned)
   - Robust output parsing with fallbacks
   - Session lifecycle management

4. **BackendSelector** (`src/prd/backend_selector.py`)
   - Selects execution mode: INTERACTIVE (Claude Squad) or MANUAL (prompts)
   - Previously included BATCH (GitHub Actions) but user wants to remove this

5. **CLI Commands**
   - `prd check-squad` - verify Claude Squad compatibility
   - `prd spawn` - spawn sessions
   - `prd sessions` - list active sessions
   - `prd attach` - attach to session terminal
   - `prd done` - mark task complete
   - `prd cleanup` - clean orphaned sessions

---

## 3. What Phase 2 Proposes

### 3.1 Workflow Model Change

**Old model** (complex):
- Executor runs async loop
- Spawns tasks, polls for completion
- Wave resolver merges N branches at once optimally
- Complex orchestration

**New model** (simple, CLI-driven):
```bash
orchestrator prd spawn      # Spawn next wave of ready tasks
# User works on sessions...
orchestrator prd merge task-1   # Merge ONE task into integration branch
orchestrator prd merge task-2   # Merge next task
orchestrator prd sync           # Merge all done + spawn next wave
```

Key changes:
- **Parallel execution**: 10+ agents work simultaneously in Claude Squad sessions
- **Sequential merging**: User merges one task at a time when ready
- **No polling**: User controls when to merge
- **Simpler conflicts**: Each merge is one branch vs integration (not N-way)

### 3.2 Smart Spawning (Flipped Wave Resolver)

**Problem**: If two tasks modify the same files, they'll conflict when merging.

**Solution**: Don't spawn them together. Use the wave resolver logic BEFORE spawning to predict which tasks will conflict, and schedule them in different waves.

```
Ready tasks: task-1 (auth), task-2 (api), task-3 (auth), task-4 (docs)

File overlap prediction:
  task-1 (auth) → likely touches src/auth/*
  task-3 (auth) → likely touches src/auth/* → overlaps with task-1!
  task-2 (api)  → likely touches src/api/*  → no overlap
  task-4 (docs) → likely touches docs/*     → no overlap

Wave 1: spawn task-1, task-2, task-4 (no overlap)
Wave 2: spawn task-3 (after task-1 merged)
```

**SpawnScheduler** (new, refactored from wave_resolver):
- Predicts file overlap from task descriptions (keywords, patterns)
- Clusters non-conflicting tasks
- Returns waves to spawn sequentially
- Can learn from historical data (which files each task type touched)

### 3.3 Files to Remove

| File | Reason |
|------|--------|
| `worker_pool.py` | Replaced by ClaudeSquadAdapter |
| `backends/local.py` | Claude Squad replaces subprocess spawning |
| `backends/modal_worker.py` | Cloud backend, not compatible with interactive model |
| `backends/render.py` | Cloud backend, not compatible |
| `backends/sequential.py` | Claude Squad handles this |
| `backends/github_actions.py` | User can't monitor, unnecessary |
| `wave_resolver.py` | Logic moves to spawn_scheduler.py |

### 3.4 Files to Keep

| File | Reason |
|------|--------|
| `backends/manual.py` | For Claude Code Web users |
| `src/resolution/*` | Resolution pipeline for auto-resolving conflicts |
| `src/conflict/clusterer.py` | Logic reused in SpawnScheduler |

### 3.5 New/Updated Components

1. **SpawnScheduler** (`src/prd/spawn_scheduler.py`)
   - `predict_files(task)` - predict files from description
   - `schedule_waves(tasks)` - group into non-conflicting waves
   - `get_next_wave()` - return tasks safe to spawn now

2. **Simplified Executor** (`src/prd/executor.py`)
   - `spawn()` - spawn next wave via ClaudeSquadAdapter
   - `merge(task_id)` - merge one task via resolution pipeline
   - `sync()` - merge all completed + spawn next wave
   - No async loop, no polling, CLI-driven

3. **Updated CLI**
   - `prd spawn` - spawn next wave
   - `prd merge <task>` - merge one task (auto-resolve conflicts)
   - `prd sync` - merge done + spawn next

---

## 4. Key Design Decisions to Review

### Decision 1: Sequential Merging vs Batch Merging
**Choice**: Merge one task at a time instead of N tasks at once.
**Rationale**: Smaller conflicts, simpler resolution, user controls timing.
**Risk**: Slower than batch merge? But user wanted control.

### Decision 2: Smart Spawning
**Choice**: Predict file overlap and avoid spawning conflicting tasks together.
**Rationale**: Prevention > Resolution. In zero-review system, every conflict resolved is a potential bug.
**Risk**: Predictions may be inaccurate. Mitigation: conservative clustering, learn over time.

### Decision 3: Remove GitHub Actions Backend
**Choice**: Remove GHA, keep only Claude Squad + Manual.
**Rationale**: User can't monitor GHA execution (no terminal), unnecessary code.
**Risk**: Lose remote/batch execution capability.

### Decision 4: Remove Wave Resolver, Keep Logic
**Choice**: Delete wave_resolver.py, move clustering logic to spawn_scheduler.py.
**Rationale**: Wave resolver was for merging N branches. Now we merge one at a time. But the clustering logic is valuable for spawn scheduling.

### Decision 5: CLI-Driven Instead of Daemon
**Choice**: No background process. User runs commands when ready.
**Rationale**: Simpler, user controls timing, no polling.
**Risk**: User must remember to run commands.

---

## 5. Questions for Reviewers

1. Is the sequential merging approach sound, or does it introduce risks?
2. Is smart spawning (predicting file overlap) worth the complexity?
3. Are there risks in removing 6 backend files?
4. Is the CLI-driven model appropriate for a "vibe coding" workflow?
5. What edge cases or failure modes should we handle?
6. Any architectural concerns with this approach?

---

## 6. Success Criteria

1. 10 parallel Claude Squad sessions spawn with one command
2. Smart spawning groups non-conflicting tasks into waves
3. One-at-a-time merge with auto-resolution works
4. 6 deprecated backend files removed
5. All tests pass
6. CLI workflow: spawn → work → merge → sync
