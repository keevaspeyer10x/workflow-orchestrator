# Issue #56: TaskProvider Interface Implementation Plan

## Overview
Implement a backend-agnostic task/issue tracking system for the orchestrator with two MVP backends: LocalTaskProvider (JSON file) and GitHubTaskProvider (gh CLI).

## Execution Strategy
**Sequential execution** - This is a single cohesive feature with dependencies between phases. Each phase builds on the previous:
1. Interface must exist before backends
2. Local backend is simpler (tests first)
3. GitHub backend builds on local patterns
4. CLI commands depend on both backends

## Architecture

```
src/task_provider/
├── __init__.py              # Factory, registry, exports
├── interface.py             # TaskProvider ABC, Task, TaskTemplate dataclasses
├── backends/
│   ├── __init__.py
│   ├── local.py             # LocalTaskProvider (JSON file)
│   └── github.py            # GitHubTaskProvider (gh CLI)
```

## Implementation Phases

### Phase 1: Core Interface & Local Backend
**Files to create:**
- `src/task_provider/__init__.py` - Registry and factory
- `src/task_provider/interface.py` - ABC and dataclasses
- `src/task_provider/backends/__init__.py` - Backend exports
- `src/task_provider/backends/local.py` - Local JSON backend

**Key decisions:**
- Use `dataclasses` for `Task`, `TaskTemplate` (matches existing patterns)
- Use `enum.Enum` for `TaskStatus`, `TaskPriority`
- Store local tasks at `~/.config/orchestrator/tasks.json`
- Auto-increment task IDs for local backend

### Phase 2: GitHub Backend
**Files to create:**
- `src/task_provider/backends/github.py` - GitHub Issues backend

**Key decisions:**
- Use `gh` CLI (not API) to match existing review patterns
- Auto-detect repo from `git remote get-url origin`
- Render TaskTemplate to issue body markdown
- Parse issue number from `gh issue create` output

### Phase 3: CLI Commands
**Modify:**
- `src/cli.py` - Add `task` subcommand group

**Commands:**
- `orchestrator task create` - Create task from prompts
- `orchestrator task list` - List tasks with filters
- `orchestrator task next` - Show highest priority open task
- `orchestrator task close <id>` - Close a task
- `orchestrator task add "title"` - Quick add (minimal prompts)

### Phase 4: Configuration Integration (Stretch)
- Add `task_provider` section to workflow.yaml schema
- Add `--from-plan` flag to create task from workflow context

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `src/task_provider/__init__.py` | Create | Factory, registry |
| `src/task_provider/interface.py` | Create | ABC, dataclasses |
| `src/task_provider/backends/__init__.py` | Create | Backend exports |
| `src/task_provider/backends/local.py` | Create | Local JSON backend |
| `src/task_provider/backends/github.py` | Create | GitHub Issues backend |
| `src/cli.py` | Modify | Add `task` subcommand |
| `tests/test_task_provider.py` | Create | Unit tests |

## Dependencies
- Existing: `dataclasses`, `json`, `subprocess`, `pathlib`
- No new dependencies required

## Success Criteria
1. `orchestrator task add "Test task"` creates local task
2. `orchestrator task list` shows tasks with status/priority
3. `orchestrator task next` returns highest priority open task
4. `orchestrator task close 1` closes task
5. GitHub backend works with gh CLI when configured
