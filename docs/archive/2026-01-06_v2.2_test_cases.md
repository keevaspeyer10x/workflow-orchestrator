# Test Cases: v2.2 Enhancements

## Overview

This document defines test cases for the v2.2 enhancements. Tests are organized by feature and priority.

---

## Feature 1: Provider Abstraction

### TC-P1: Provider Interface Definition
**Priority**: Critical
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Import `AgentProvider` from `src/providers/base.py` | Class is importable |
| 2 | Verify abstract methods exist | `name()`, `is_available()`, `generate_prompt()`, `execute()` defined |
| 3 | Attempt to instantiate `AgentProvider` directly | Raises `TypeError` (abstract class) |

### TC-P2: OpenRouter Provider - Availability Check
**Priority**: High
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Create OpenRouter provider without API key | `is_available()` returns `False` |
| 2 | Set `OPENROUTER_API_KEY` env var | `is_available()` returns `True` |
| 3 | Call `name()` | Returns `"openrouter"` |

### TC-P3: OpenRouter Provider - Prompt Generation
**Priority**: High
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Call `generate_prompt()` with task and context | Returns formatted markdown prompt |
| 2 | Verify prompt includes task description | Task appears in output |
| 3 | Verify prompt includes checklist items | Items appear in output |

### TC-P4: OpenRouter Provider - API Execution
**Priority**: High
**Type**: Integration Test (requires API key)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Call `execute()` with simple prompt | Returns `ExecutionResult` with `success=True` |
| 2 | Verify `output` contains response | Non-empty string |
| 3 | Verify `model_used` is populated | Contains model name |

### TC-P5: Claude Code Provider - Refactored Interface
**Priority**: High
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Import `ClaudeCodeProvider` | Class is importable |
| 2 | Verify implements `AgentProvider` interface | All abstract methods implemented |
| 3 | Call `is_available()` without Claude CLI | Returns `False` |

### TC-P6: Manual Provider - Fallback Behavior
**Priority**: Medium
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Create Manual provider | `is_available()` returns `True` (always available) |
| 2 | Call `generate_prompt()` | Returns formatted prompt for copy/paste |
| 3 | Call `execute()` | Raises `NotImplementedError` |

### TC-P7: Provider Registry - Auto-Detection
**Priority**: Critical
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Call `get_provider()` with no args, no API key | Returns Manual provider |
| 2 | Set `OPENROUTER_API_KEY` | Returns OpenRouter provider |
| 3 | Call `get_provider("manual")` | Returns Manual provider (explicit) |
| 4 | Call `list_providers()` | Returns `["openrouter", "claude_code", "manual"]` |

### TC-P8: CLI - Provider Flag
**Priority**: High
**Type**: Integration Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Run `orchestrator handoff --provider manual` | Uses Manual provider |
| 2 | Run `orchestrator handoff --provider openrouter` | Uses OpenRouter provider |
| 3 | Run `orchestrator handoff --provider invalid` | Error: unknown provider |

---

## Feature 2: Environment Detection

### TC-E1: Claude Code Detection
**Priority**: High
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Set `CLAUDE_CODE=1` env var | `detect_environment()` returns `Environment.CLAUDE_CODE` |
| 2 | Unset env var, mock parent process as `claude` | Returns `Environment.CLAUDE_CODE` |

### TC-E2: Manus Detection
**Priority**: High
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Set `MANUS_SESSION=xxx` env var | `detect_environment()` returns `Environment.MANUS` |
| 2 | Check home directory is `/home/ubuntu` | Returns `Environment.MANUS` |

### TC-E3: Standalone Fallback
**Priority**: Medium
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Clear all env vars, use non-ubuntu home | `detect_environment()` returns `Environment.STANDALONE` |

### TC-E4: Environment Override
**Priority**: Medium
**Type**: Integration Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Run `orchestrator status --env standalone` | Uses standalone behavior |
| 2 | Run `orchestrator handoff --env manus` | Uses Manus behavior |

---

## Feature 3: Operating Notes System

### TC-N1: Schema - Notes Field
**Priority**: Critical
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Create `PhaseDef` with `notes=["test"]` | Object created successfully |
| 2 | Create `PhaseDef` without notes | `notes` defaults to `[]` |
| 3 | Create `ChecklistItemDef` with notes | Object created successfully |

### TC-N2: Notes Display in Status
**Priority**: High
**Type**: Integration Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Add notes to workflow.yaml phase | Notes appear in `orchestrator status` output |
| 2 | Add `[tip]` prefixed note | Shows 💡 emoji |
| 3 | Add `[caution]` prefixed note | Shows ⚠️ emoji |

### TC-N3: Notes in Handoff Prompt
**Priority**: High
**Type**: Integration Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Add notes to current phase | Notes appear in `orchestrator handoff` output |
| 2 | Add notes to current item | Item notes appear in output |

### TC-N4: Backwards Compatibility - Notes
**Priority**: Critical
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Load workflow.yaml without notes fields | Loads successfully, notes default to `[]` |
| 2 | Load existing state file without notes | Loads successfully |

---

## Feature 4: Task Constraints

### TC-C1: Schema - Constraints Field
**Priority**: Critical
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Create `WorkflowState` with `constraints=["test"]` | Object created successfully |
| 2 | Create `WorkflowState` without constraints | `constraints` defaults to `[]` |

### TC-C2: CLI - Constraints Flag
**Priority**: High
**Type**: Integration Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Run `orchestrator start "task" --constraints "c1"` | Constraint stored in state |
| 2 | Run with multiple `--constraints` flags | All constraints stored |
| 3 | Run with `--constraints-file` | Constraints loaded from file |

### TC-C3: Constraints Display
**Priority**: High
**Type**: Integration Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Start workflow with constraints | Constraints appear in `orchestrator status` |
| 2 | Run `orchestrator handoff` | Constraints appear in handoff prompt |

### TC-C4: Backwards Compatibility - Constraints
**Priority**: Critical
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Load existing state file without constraints | Loads successfully, constraints default to `[]` |

---

## Feature 5: Checkpoint/Resume System

### TC-K1: Checkpoint Creation
**Priority**: Critical
**Type**: Integration Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Run `orchestrator checkpoint` | Creates file in `.workflow_checkpoints/` |
| 2 | Run with `--message "test"` | Message stored in checkpoint |
| 3 | Run with `--decision "d1"` | Decision stored in checkpoint |
| 4 | Run with `--file path/to/file` | File added to manifest |

### TC-K2: Checkpoint Listing
**Priority**: High
**Type**: Integration Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Create multiple checkpoints | All listed by `orchestrator checkpoints` |
| 2 | Verify listing shows phase and timestamp | Information displayed correctly |

### TC-K3: Resume from Checkpoint
**Priority**: Critical
**Type**: Integration Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Create checkpoint, modify state, run `orchestrator resume` | State restored to checkpoint |
| 2 | Run `orchestrator resume --dry-run` | Shows prompt without modifying state |
| 3 | Run `orchestrator resume --from <id>` | Resumes from specific checkpoint |

### TC-K4: Auto-Checkpoint
**Priority**: Medium
**Type**: Integration Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Set `auto_checkpoint: true` in settings | Checkpoint created on phase advance |
| 2 | Verify checkpoint contains correct phase | Phase matches pre-advance state |

### TC-K5: Context Summary Auto-Generation
**Priority**: Medium
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Create checkpoint without summary | Auto-generated summary includes task, phase, items |
| 2 | Create checkpoint with `--summary "custom"` | Custom summary used |

### TC-K6: File Manifest Auto-Detection
**Priority**: Low
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Modify files, create checkpoint | Recently modified files in manifest |
| 2 | Provide explicit `--file` flags | Explicit files added to manifest |

### TC-K7: Checkpoint Cleanup
**Priority**: Low
**Type**: Integration Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Run `orchestrator checkpoints --cleanup --max-age 0d` | Old checkpoints removed |
| 2 | Run `orchestrator checkpoints --cleanup --completed` | Completed workflow checkpoints removed |

---

## Backwards Compatibility Tests

### TC-BC1: Existing State File
**Priority**: Critical
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Copy current `.workflow_state.json` as test fixture | File preserved |
| 2 | Load with new code | Loads successfully |
| 3 | Verify all existing fields preserved | No data loss |

### TC-BC2: Existing Workflow YAML
**Priority**: Critical
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Load current `workflow.yaml` with new schema | Loads successfully |
| 2 | Verify all phases and items preserved | No data loss |

---

## Security Tests

### TC-S1: API Key Not Logged
**Priority**: Critical
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Set API key, trigger error | Key not in error message |
| 2 | Enable debug logging | Key not in log output |
| 3 | Create checkpoint | Key not in checkpoint file |

### TC-S2: Error Message Sanitization
**Priority**: High
**Type**: Unit Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Trigger API error with URL containing key | URL sanitized in error |

---

## Test Implementation Files

| Test File | Coverage |
|-----------|----------|
| `tests/test_providers.py` | TC-P1 through TC-P8 |
| `tests/test_environment.py` | TC-E1 through TC-E4 |
| `tests/test_notes.py` | TC-N1 through TC-N4 |
| `tests/test_constraints.py` | TC-C1 through TC-C4 |
| `tests/test_checkpoints.py` | TC-K1 through TC-K7 |
| `tests/test_backwards_compat.py` | TC-BC1, TC-BC2 |
| `tests/test_security.py` | TC-S1, TC-S2 |
