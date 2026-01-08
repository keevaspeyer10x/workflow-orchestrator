# PRD-001 Phase 2: Claude Squad Integration - Smart Spawning Model

## Overview

Complete the Claude Squad integration with a simplified, CLI-driven workflow:
- **Parallel execution** via Claude Squad (10+ agents in tmux sessions)
- **Sequential merging** (user controls when to merge each task)
- **Smart spawning** (schedule tasks to minimize conflicts)
- **Zero human review** (system auto-resolves conflicts)

## External AI Reviews (2026-01-09)

Reviewed by: Gemini 2.0, GPT-4o, Grok 3

| Reviewer | Assessment | Key Concern |
|----------|------------|-------------|
| Gemini | Sound | Prediction accuracy, learning mechanism unclear |
| GPT-4o | Needs Work | Sequential bottleneck, loss of batch capability |
| Grok | Needs Work | User friction, backend flexibility |

### Improvements Added Based on Reviews

1. **Transparency flags**: `--explain` and `--dry-run` for spawn/merge
2. **Manual override**: `--force` flag to bypass scheduler predictions
3. **Preserve backends**: Move to `_deprecated/` instead of deleting
4. **Idle warnings**: Show task idle time in `prd status`
5. **Fallback mechanism**: When predictions fail, allow manual control

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Commands                             │
│  spawn → sessions → attach → merge → sync                       │
├─────────────────────────────────────────────────────────────────┤
│                     SpawnScheduler                               │
│  - Predict file overlap from task descriptions                  │
│  - Cluster non-conflicting tasks into waves                     │
│  - Spawn wave 1 first, wave 2 after wave 1 merges               │
├─────────────────────────────────────────────────────────────────┤
│                   ClaudeSquadAdapter                             │
│  - Spawn tmux sessions (one per task)                           │
│  - SessionRegistry (persistent state)                            │
│  - Capability detection                                          │
├─────────────────────────────────────────────────────────────────┤
│                   BackendSelector                                │
│  - INTERACTIVE: Claude Squad                                     │
│  - MANUAL: Generate prompts for Claude Code Web                  │
├─────────────────────────────────────────────────────────────────┤
│                  Resolution Pipeline                             │
│  - Auto-resolve conflicts on merge                               │
│  - Ask minimal questions when uncertain                          │
└─────────────────────────────────────────────────────────────────┘
```

## Workflow

```bash
# 1. Spawn ready tasks (respects dependencies + smart overlap scheduling)
orchestrator prd spawn

# 2. Work on sessions (attach to any, work in parallel)
orchestrator prd sessions          # List all
orchestrator prd attach task-1     # Jump into terminal

# 3. Merge when ready (one at a time, auto-resolve conflicts)
orchestrator prd merge task-1      # Merge into integration branch

# 4. Sync: merge completed, spawn next wave
orchestrator prd sync              # Convenience: merge all done + spawn next
```

## Implementation Tasks

### Task 1: Create SpawnScheduler
Refactor wave_resolver.py → spawn_scheduler.py

**Preserve from clusterer.py:**
- `_build_file_adjacency()` - detect file overlap
- `_build_domain_adjacency()` - detect domain overlap
- `_infer_domains()` - keyword-based domain detection
- `_find_connected_components()` - cluster non-conflicting tasks
- `order_by_dependency()` - topological sort

**New logic:**
- `predict_files(task)` - predict files from task description
- `schedule_waves(tasks)` - group tasks into spawn waves
- `get_next_wave()` - return tasks safe to spawn now

### Task 2: Update executor.py
Simplify to CLI-driven model:

**Remove:**
- Async execution loop
- WorkerPool integration
- Automatic completion detection

**Add:**
- `spawn()` - spawn next wave via ClaudeSquadAdapter
- `merge(task_id)` - merge one task via resolution pipeline
- `sync()` - merge all completed + spawn next wave

### Task 3: Deprecate old backends (preserve, don't delete)

| File | Action |
|------|--------|
| `src/prd/worker_pool.py` | Move to `_deprecated/` |
| `src/prd/backends/local.py` | Move to `_deprecated/` |
| `src/prd/backends/modal_worker.py` | Move to `_deprecated/` |
| `src/prd/backends/render.py` | Move to `_deprecated/` |
| `src/prd/backends/sequential.py` | Move to `_deprecated/` |
| `src/prd/backends/github_actions.py` | Move to `_deprecated/` |
| `src/prd/wave_resolver.py` | Refactor to spawn_scheduler.py |

**Keep active:**
- `src/prd/backends/manual.py` - for Claude Code Web
- `src/prd/backends/base.py` - base class still needed

### Task 4: Update CLI commands

| Command | Description |
|---------|-------------|
| `prd spawn` | Spawn next wave of tasks |
| `prd spawn --explain` | Show wave groupings without spawning |
| `prd spawn --force <task>` | Bypass scheduler, spawn specific task |
| `prd sessions` | List active sessions |
| `prd attach <task>` | Attach to session terminal |
| `prd merge <task>` | Merge one task into integration |
| `prd merge --dry-run <task>` | Show what would be merged/resolved |
| `prd sync` | Merge completed + spawn next |
| `prd status` | Show PRD progress with idle times |

### Task 5: Update tests
- Add tests for SpawnScheduler
- Update executor tests
- Remove tests for deprecated backends

### Task 6: Update documentation
- Update IMPLEMENTATION-TRACKER.md (Phase 7 complete, Phase 6 updated)
- Update ROADMAP.md
- Update CLAUDE.md with new commands

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| File prediction inaccurate | Medium | Low | Conservative clustering, learn over time |
| Merge conflicts unresolvable | Low | Medium | Resolution pipeline + ask user |
| Session state lost | Low | Medium | Persistent SessionRegistry |
| Claude Squad not installed | Medium | Low | Clear error, manual fallback |

## Success Criteria

1. [ ] 10 parallel Claude Squad sessions spawn with one command
2. [ ] Smart spawning groups non-conflicting tasks
3. [ ] One-at-a-time merge with auto-resolution works
4. [ ] 6 deprecated backend files removed
5. [ ] All tests pass
6. [ ] CLI workflow: spawn → work → merge → sync
