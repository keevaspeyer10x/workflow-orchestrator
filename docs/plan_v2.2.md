# Implementation Plan: v2.2 Enhancements

## Overview

This plan details the implementation of five major enhancements to the workflow orchestrator as specified in `PRD_v2.2_ENHANCEMENTS.md`, plus a backported SOPS secrets management feature. The implementation will be done using Claude Code for the core coding work, with Manus orchestrating the workflow.

## Implementation Order

The features will be implemented in dependency order:

1. **Feature 0: SOPS Secrets Management** (Backport from quiet-ping-v6) ✅ COMPLETE
2. **Feature 1: Provider Abstraction** (Foundation - required by Feature 2)
3. **Feature 2: Environment Detection** (Uses providers)
4. **Feature 3: Operating Notes System** (Independent, schema changes)
5. **Feature 4: Task Constraints Flag** (Independent, schema changes)
6. **Feature 5: Checkpoint/Resume System** (Depends on schema changes from 3 & 4)

---

## Feature 0: SOPS Secrets Management (Backport)

**Status:** ✅ COMPLETE

### Files Created
| File | Purpose |
|------|---------|
| `.sops.yaml` | SOPS configuration with age encryption rules |
| `.manus/secrets.enc.yaml` | Encrypted secrets file (safe to commit) |
| `.manus/decrypt-secrets.sh` | Helper script to decrypt secrets |
| `.manus/README.md` | Documentation for secrets management |

### Key Information
- **Public Key:** `age1g30eu0w5xsudt5pg0dt28xm2d82dwmvvyznxu60acsm8vv9x4q6se6dkvq`
- **Secret Key:** Must be stored in Manus project secrets as `SOPS_AGE_KEY`
- **Secret Key Value:** `AGE-SECRET-KEY-10N6AF3D5J0V2RHCQFY26PUK704VVMMA4M4FRTFQK90YUF488THFQ4GP9Z8`

### Stored Secrets
- `workflow_orchestrator.api_keys.openrouter` - OpenRouter API key

---

## Feature 1: Provider Abstraction

### Files to Create
| File | Purpose |
|------|---------|
| `src/providers/__init__.py` | Provider registry with `get_provider()` and `list_providers()` |
| `src/providers/base.py` | `AgentProvider` ABC and `ExecutionResult` dataclass |
| `src/providers/openrouter.py` | OpenRouter HTTP API provider |
| `src/providers/claude_code.py` | Refactored from `claude_integration.py` |
| `src/providers/manual.py` | Fallback provider for copy/paste |

### Files to Modify
| File | Changes |
|------|---------|
| `src/cli.py` | Add `--provider` and `--model` flags to `handoff` command |
| `workflow.yaml` | Add `settings.default_provider` and `settings.provider_config` |

### PRD Acceptance Criteria
- [ ] Provider interface defined in `src/providers/base.py`
- [ ] OpenRouter provider implemented and working
- [ ] Claude Code provider refactored from existing code
- [ ] Manual provider implemented as fallback
- [ ] `--provider` and `--model` flags added to CLI
- [ ] Auto-detection works correctly
- [ ] Existing `handoff --execute` still works

### Implementation Details

The provider interface will define four abstract methods:
- `name() -> str` - Provider identifier
- `is_available() -> bool` - Check if provider can be used
- `generate_prompt(task, context) -> str` - Generate handoff prompt
- `execute(prompt) -> ExecutionResult` - Execute the prompt

Auto-detection priority:
1. Explicit `--provider` flag
2. Environment detection (Claude Code → claude_code provider)
3. API key presence (OPENROUTER_API_KEY → openrouter)
4. Fallback to manual

---

## Feature 2: Environment Detection

### Files to Create
| File | Purpose |
|------|---------|
| `src/environment.py` | `Environment` enum and detection functions |

### Files to Modify
| File | Changes |
|------|---------|
| `src/cli.py` | Add `--env` flag to relevant commands |
| `src/providers/__init__.py` | Use environment for provider auto-selection |

### PRD Acceptance Criteria
- [ ] Environment detection module created
- [ ] Claude Code environment detected correctly
- [ ] Manus environment detected correctly
- [ ] Standalone fallback works
- [ ] `--env` override flag works
- [ ] Provider auto-selection adapts to environment

### Detection Heuristics

| Environment | Detection Method |
|-------------|------------------|
| Claude Code | `CLAUDE_CODE` env var, or parent process is `claude`, or `.claude` directory exists |
| Manus | `MANUS_SESSION` env var, or `/home/ubuntu` home directory pattern |
| Standalone | Default fallback |

---

## Feature 3: Operating Notes System

### Files to Modify
| File | Changes |
|------|---------|
| `src/schema.py` | Add `notes: list[str] = []` to `PhaseDef` and `ChecklistItemDef` |
| `src/engine.py` | Include notes in status output and handoff prompts |
| `src/cli.py` | Display notes with emoji rendering in status command |
| `src/learning.py` | Suggest note additions based on learnings |
| `workflow.yaml` | Add example notes to demonstrate feature |

### PRD Acceptance Criteria
- [ ] `notes` field added to PhaseDef schema
- [ ] `notes` field added to ChecklistItemDef schema
- [ ] Notes displayed in `status` command
- [ ] Notes included in handoff prompts
- [ ] Optional emoji rendering for categorized notes
- [ ] Learning engine suggests note additions
- [ ] Example workflows updated with notes

### Note Categories
Notes support optional bracket prefixes for categorization with emoji rendering:
- `[tip]` → 💡
- `[caution]` → ⚠️
- `[learning]` → 📚
- `[context]` → 📋

---

## Feature 4: Task Constraints Flag

### Files to Modify
| File | Changes |
|------|---------|
| `src/schema.py` | Add `constraints: list[str] = []` to `WorkflowState` |
| `src/cli.py` | Add `--constraints` flag to `start` command (multiple allowed) |
| `src/engine.py` | Store constraints in state, include in recitation and handoff |

### PRD Acceptance Criteria
- [ ] `--constraints` flag added to `start` command
- [ ] Constraints stored in workflow state
- [ ] Constraints displayed in `status` output
- [ ] Constraints included in handoff prompts
- [ ] Multiple `--constraints` flags accumulate

### CLI Usage (per PRD)
```bash
orchestrator start "Fix the login bug" \
  --constraints "Minimal changes only" \
  --constraints "Do not refactor surrounding code" \
  --constraints "Must maintain backwards compatibility"
```

---

## Feature 5: Checkpoint/Resume System

### Files to Create
| File | Purpose |
|------|---------|
| `.workflow_checkpoints/` | Directory for checkpoint files |

### Files to Modify
| File | Changes |
|------|---------|
| `src/schema.py` | Add `Checkpoint` dataclass |
| `src/engine.py` | Add `create_checkpoint()`, `list_checkpoints()`, `resume_from_checkpoint()` methods |
| `src/cli.py` | Add `checkpoint`, `checkpoints`, `resume` commands |
| `workflow.yaml` | Add `settings.auto_checkpoint` option |

### PRD Acceptance Criteria
- [ ] Checkpoint data model defined
- [ ] `checkpoint` command creates checkpoint files
- [ ] `checkpoints` command lists available checkpoints
- [ ] `resume` command restores state and generates handoff
- [ ] Auto-checkpoint on phase completion works
- [ ] Handoff prompt includes all context recovery data
- [ ] `--dry-run` flag shows prompt without modifying state
- [ ] Checkpoint cleanup works

### CLI Commands (per PRD)

**Create checkpoint:**
```bash
orchestrator checkpoint
orchestrator checkpoint --message "Completed auth design"
orchestrator checkpoint --decision "Using JWT not sessions" --decision "Tokens in httpOnly cookies"
orchestrator checkpoint --file src/auth/design.md --file src/types/auth.ts
```

**List checkpoints:**
```bash
orchestrator checkpoints
```

**Resume from checkpoint:**
```bash
orchestrator resume
orchestrator resume --from checkpoint_2024-01-05_PLAN_complete
orchestrator resume --dry-run
```

**Cleanup checkpoints:**
```bash
orchestrator checkpoints --cleanup --max-age 7d
orchestrator checkpoints --cleanup --completed
```

### Checkpoint Data Model
```python
@dataclass
class Checkpoint:
    id: str
    workflow_state: WorkflowState
    created_at: datetime
    phase_at_checkpoint: str
    decisions: list[str]
    file_manifest: list[str]
    context_summary: str
    accumulated_learnings: list[str]
    message: Optional[str] = None
```

### Auto-Detection Features
- **Context Summary**: Auto-generated from workflow state (task, phase, completed items)
- **File Manifest**: Auto-detect recently modified files in project directory

---

## Testing Strategy

### Unit Tests
Each feature will have dedicated unit tests in `tests/`:
- `tests/test_providers.py` - Provider interface and implementations
- `tests/test_environment.py` - Environment detection
- `tests/test_notes.py` - Notes parsing and display
- `tests/test_constraints.py` - Constraints storage and display
- `tests/test_checkpoints.py` - Checkpoint creation and resume

### Integration Tests
- `tests/test_integration.py` - End-to-end workflow with all features

---

## Backwards Compatibility

All changes maintain backwards compatibility:
- New schema fields have default values (empty lists)
- Existing `.workflow_state.json` files will work without migration
- New CLI flags are optional
- Existing `handoff --execute` behavior preserved

---

## Estimated Effort

| Feature | Complexity | Estimated Time |
|---------|------------|----------------|
| SOPS Secrets (F0) | Low | ✅ Complete |
| Provider Abstraction (F1) | Medium | 2-3 hours |
| Environment Detection (F2) | Low | 1 hour |
| Operating Notes (F3) | Low | 1-2 hours |
| Task Constraints (F4) | Low | 1 hour |
| Checkpoint/Resume (F5) | Medium | 2-3 hours |
| Testing | Medium | 2-3 hours |
| **Total** | | **9-13 hours** |

---

## Execution Approach

Implementation will be delegated to Claude Code for the core coding work. Each feature will be implemented as a separate handoff to ensure focused, testable increments. The workflow orchestrator will track progress through the EXECUTE phase items.
