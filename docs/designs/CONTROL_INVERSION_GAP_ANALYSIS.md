# Control Inversion Gap Analysis

## Executive Summary

This document analyzes the gap between the designed hybrid orchestration architecture and what was actually implemented in V3. **The core control inversion was never implemented.**

## What Was Designed (hybrid_orchestration_design.md)

### Core Architecture - DESIGNED BUT NOT IMPLEMENTED

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (Control Layer)                  │
│  • Owns workflow state machine                                   │
│  • Enforces phase order and gates                                │
│  • CALLS LLM for phase work (not vice versa)     ← KEY MISSING   │
│  • Validates artifacts before transitions                        │
└─────────────────────────────────────────────────────────────────┘
```

### The Critical Missing Piece: `run_workflow()` Loop

```python
# DESIGNED (hybrid_orchestration_design.md lines 82-103)
def run_workflow(self, task: str):
    """Main loop - orchestrator drives, LLM executes."""
    self.state = self.load_checkpoint() or self.init_state(task)

    while self.state.phase != 'DONE':
        phase_config = self.PHASES[self.state.phase]

        # Orchestrator calls LLM with scoped context
        result = self.execute_phase(...)

        # Validate gates before transition
        if not self.validate_gates(...):
            self.handle_gate_failure(result)
            continue  # Retry phase, don't advance

        # Checkpoint and advance
        self.save_checkpoint()
        self.state.phase = self.next_phase()
```

**This was NEVER implemented.** Instead, we have passive CLI commands that the LLM must remember to call.

### Designed CLI (Never Implemented)

```bash
# DESIGNED - Orchestrator-driven
orchestrator run --task "Fix bug"        # ← NOT IMPLEMENTED
orchestrator run --until REVIEW          # ← NOT IMPLEMENTED
orchestrator resume <checkpoint>         # ← Partially implemented

# DESIGNED - LLM-facing (scoped)
orchestrator llm-status                  # ← NOT IMPLEMENTED
orchestrator llm-report <artifact>       # ← NOT IMPLEMENTED
orchestrator llm-request-approval        # ← NOT IMPLEMENTED
orchestrator llm-report-blocker <issue>  # ← NOT IMPLEMENTED

# DESIGNED - Admin-only (with audit)
orchestrator admin-skip <item>           # ← NOT IMPLEMENTED
orchestrator admin-force-advance         # ← NOT IMPLEMENTED
```

### What We Have Instead (Current Reality)

```bash
# CURRENT - LLM has full control (no enforcement)
orchestrator start "Task"        # LLM must remember to call
orchestrator complete <item>     # LLM must remember to call
orchestrator advance             # LLM must remember to call
orchestrator finish              # LLM must remember to call ← I FORGOT THIS TODAY
```

## Detailed Gap Analysis

### 1. Control Flow

| Aspect | Designed | Implemented | Gap |
|--------|----------|-------------|-----|
| Main loop owner | Orchestrator | LLM | **CRITICAL** |
| Phase transitions | Programmatic | LLM discretion | **CRITICAL** |
| Gate enforcement | Automatic | LLM must call | **CRITICAL** |
| Workflow completion | Guaranteed | LLM must remember | **CRITICAL** |

### 2. CLI Commands

| Designed Command | Purpose | Implemented |
|------------------|---------|-------------|
| `orchestrator run --task` | Orchestrator-driven execution | ❌ NO |
| `orchestrator run --until PHASE` | Run to specific phase | ❌ NO |
| `orchestrator llm-status` | Read-only status for LLM | ❌ NO |
| `orchestrator llm-report` | LLM reports work products | ❌ NO |
| `orchestrator llm-request-approval` | LLM requests gate approval | ❌ NO |
| `orchestrator llm-report-blocker` | LLM reports blockers | ❌ NO |
| `orchestrator admin-skip` | Human-only skip with audit | ❌ NO |
| `orchestrator admin-force-advance` | Human-only force with audit | ❌ NO |

### 3. Migration Path (Was Defined But Not Followed)

```
Phase 1: Immediate (Low effort)           → ✅ DONE
  - Add ORCHESTRATOR_MODE env var         → ✅ Implemented
  - Disable --force/--skip in LLM mode    → ⚠️ Partial (skip still works)
  - Add artifact validation               → ✅ Implemented

Phase 2: Short-term (Medium effort)       → ❌ NOT DONE
  - Implement checkpointing              → ✅ Done
  - Add `orchestrator run` command       → ❌ NOT DONE ← CRITICAL
  - Create scoped llm-* commands         → ❌ NOT DONE

Phase 3: Long-term (High effort)          → ❌ NOT DONE
  - Full inversion of control            → ❌ NOT DONE ← CRITICAL
  - Dynamic tool injection per phase     → ❌ NOT DONE
  - Supervisor process for audit         → ❌ NOT DONE
```

### 4. From orchestrator_platform_design_v2.md

| Layer | Designed | Implemented |
|-------|----------|-------------|
| Task Ingestion | Full task parser | ❌ None (just string description) |
| Workflow Generation | Dynamic from task | ❌ Static YAML only |
| Execution Engine | `ExecutionEngine.run()` | ❌ Passive CLI only |
| Environment Adapters | Interface + adapters | ⚠️ Partial (tmux adapter) |
| Learning Store | ML-based learning | ⚠️ Partial (feedback capture) |
| Self-Improvement | Governance system | ❌ None |
| Web UI | Dashboard | ❌ None |
| Plugin System | Domain extensibility | ❌ None |

## Root Cause: Why Wasn't It Implemented?

### Hypothesis 1: Scope Creep to Lower-Risk Items
V3 implementation focused on:
- Mode detection (easy, low risk)
- State integrity/checksums (important but not control inversion)
- Checkpointing (useful but not the core problem)
- Gates (implemented but not enforced automatically)

These are all **infrastructure** for control inversion but not control inversion itself.

### Hypothesis 2: Acknowledged Limitation Not Addressed
From V3 implementation plan:
> "Tool scoping is theater" - Claude Code controls tool access, not orchestrator.

This was noted as a limitation but then used as justification to not implement true enforcement:
> We acknowledge this limitation. `intended_tools` is documentation to guide the LLM, not a security boundary.

### Hypothesis 3: No Test for the Core Requirement
The V3 tests validated:
- Mode detection works
- Checksums detect tampering
- Gates validate artifacts

But there was **no test that verified**: "LLM cannot complete workflow without going through all required steps"

### Hypothesis 4: Incremental Approach Lost the Goal
The migration path was:
1. Phase 1: Foundation ← This is what got implemented
2. Phase 2: `orchestrator run` ← This is where control inversion lives
3. Phase 3: Full inversion ← Never reached

The incremental approach meant Phase 1 was "good enough" and Phase 2 never happened.

## Impact: Today's Failure

Today I (Claude) implemented code changes and then **forgot to run `orchestrator finish`**. The user had to prompt me.

This happened because:
1. The orchestrator is passive - it waits for me to call it
2. There's no enforcement that I must call `orchestrator finish`
3. The YAML says "required: true" but nothing enforces it
4. I have full discretion to ignore the workflow

With true control inversion:
1. `orchestrator run` would be driving the workflow
2. I would be called to do work, not calling the orchestrator
3. The orchestrator would automatically advance when gates pass
4. Workflow completion would be guaranteed, not discretionary

## What Needs to Happen

### Option A: True Control Inversion (Recommended)

The orchestrator becomes the main process:

```
┌─────────────────────────────────────────┐
│           ORCHESTRATOR                   │
│                                          │
│  1. Parse task                           │
│  2. Load/generate workflow               │
│  3. For each phase:                      │
│     a. CALL Claude Code to do work       │
│     b. Validate gates                    │
│     c. Checkpoint                        │
│     d. Advance (automatic)               │
│  4. Complete workflow (guaranteed)       │
│                                          │
└─────────────────────────────────────────┘
```

### Option B: Enforcement Layer (Fallback)

If true inversion isn't feasible in Claude Code's execution model:

```
┌─────────────────────────────────────────┐
│     ENFORCEMENT LAYER                    │
│                                          │
│  - Block `orchestrator start` if         │
│    previous workflow incomplete          │
│  - Block session end if workflow active  │
│  - Programmatically call `finish`        │
│    when gates pass                       │
│                                          │
└─────────────────────────────────────────┘
```

### Option C: Hybrid with YAML Control

Specify in YAML what is programmatic vs LLM discretion:

```yaml
enforcement:
  mode: strict  # strict | guided | permissive

  # These MUST happen - code enforces
  programmatic:
    - workflow_completion    # orchestrator finish always called
    - gate_validation        # can't advance without passing gates
    - required_reviews       # reviews must complete before VERIFY

  # These are LLM discretion
  llm_controlled:
    - item_ordering          # LLM decides order within phase
    - implementation_approach # LLM decides how to code
    - skip_optional_items    # LLM can skip if justified
```

## Recommendation

Implement **Option A (True Control Inversion)** with **Option C (YAML Control)** for flexibility.

The architecture exists in the design docs. It just needs to be built.
