# Control Inversion V4 Implementation Plan

**Issue:** #100
**Date:** 2026-01-17
**Status:** PLANNING

## Overview

Implement full control inversion so the orchestrator **drives** workflow execution rather than relying on LLM to remember commands.

### Key Principle
> The orchestrator DRIVES; Claude Code EXECUTES within bounds.

## Scope

### IN SCOPE (V4.1):
- `orchestrator run` command (core executor)
- `ClaudeCodeRunner` (subprocess-based, NOT API)
- Basic gates: `file_exists`, `command`, `no_pattern`, `json_valid`
- One complete workflow: `workflows/default_v4.yaml`
- State management in `.orchestrator/v4/`

### OUT OF SCOPE (V4.2 - Issue #101):
- `orchestrator chat` command
- `ClaudeAPIRunner` (API mode)
- `external_reviews` gate
- `human_approval` gate
- `min_coverage` gate
- Token budget tracking
- Tool allow/deny enforcement

## File Structure

```
workflow-orchestrator/
├── src/
│   ├── cli.py                         # EXISTING - ADD run command
│   ├── executor.py                    # NEW - Core executor
│   ├── runners/                       # NEW directory
│   │   ├── __init__.py
│   │   ├── base.py                   # Runner interface
│   │   └── claude_code.py            # Subprocess runner
│   └── v4/                            # NEW directory
│       ├── __init__.py
│       ├── models.py                 # All dataclasses
│       ├── state.py                  # State management
│       ├── parser.py                 # YAML parsing
│       └── gate_engine.py            # Gate validation
├── workflows/                         # NEW directory
│   └── default_v4.yaml               # Migrated workflow
└── tests/
    └── test_executor.py              # Executor tests
```

## Implementation Steps

### Step 1: Create src/v4/ directory structure
1. Create `src/v4/__init__.py`
2. Create `src/v4/models.py` - All dataclasses (PhaseType, GateType, WorkflowStatus, etc.)
3. Create `src/v4/state.py` - StateStore with file locking
4. Create `src/v4/parser.py` - YAML parser with validation
5. Create `src/v4/gate_engine.py` - Programmatic gate validation

### Step 2: Create src/runners/ directory
1. Create `src/runners/__init__.py`
2. Create `src/runners/base.py` - AgentRunner interface
3. Create `src/runners/claude_code.py` - ClaudeCodeRunner (subprocess)

### Step 3: Implement Core Executor
1. Create `src/executor.py` - WorkflowExecutor class with main control loop

### Step 4: CLI Integration
1. Add `cmd_run` function to `src/cli.py`
2. Add `setup_run_parser` to register the command
3. Add appropriate imports

### Step 5: Create Default Workflow
1. Create `workflows/` directory
2. Create `workflows/default_v4.yaml`

### Step 6: Create Tests
1. Create `tests/test_executor.py` with acceptance tests

### Step 7: Verification
1. Run pytest to verify tests pass
2. Manual test: `orchestrator run workflows/default_v4.yaml --task "Test task"`

## Execution Strategy

**Decision: SEQUENTIAL execution**

**Reason:** The components have dependencies:
- models.py must exist before state.py, parser.py, gate_engine.py
- base.py must exist before claude_code.py
- All v4/ and runners/ modules must exist before executor.py
- All modules must exist before CLI integration

The spec provides complete code for each module, so sequential creation following the dependency order is most reliable.

## Acceptance Criteria

From the spec - these tests MUST pass:

1. **test_workflow_completes_even_if_llm_doesnt_call_finish** - Orchestrator guarantees completion
2. **test_llm_cannot_skip_phases** - Phase order is enforced programmatically
3. **test_gates_validated_by_code_not_llm** - Gate validation done by code
4. **test_finalize_always_called** - mark_complete() always called

## Risks

| Risk | Mitigation |
|------|------------|
| CLI integration conflicts | Add new command without modifying existing |
| State file conflicts with existing .orchestrator/ | Use separate `.orchestrator/v4/` directory |
| Import errors | Follow dependency order, test imports |
| Test failures | Follow spec exactly, debug incrementally |

## Dependencies

No new dependencies required. Uses stdlib:
- `subprocess` - Running Claude Code
- `json` - State serialization
- `fcntl` - File locking (Unix)
- `re` - Pattern matching
- `pathlib` - Path handling
- `pyyaml` - Already in project for YAML parsing
