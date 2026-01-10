# PRD-006: Auto-Inject ApprovalGate in TmuxAdapter.spawn_agent()

## Overview
Automatically inject ApprovalGate instructions into agent prompts when spawning via TmuxAdapter, eliminating the need for manual prompt modification.

## Implementation Plan

### Step 1: Modify TmuxConfig (tmux_adapter.py)
Add configuration option to control injection:

```python
@dataclass
class TmuxConfig:
    claude_binary: str = field(default_factory=get_claude_binary)
    session_prefix: str = "wfo"
    command_timeout: int = 30
    inject_approval_gate: bool = True  # NEW: Enable/disable approval gate injection
```

### Step 2: Modify spawn_agent() (tmux_adapter.py)
Before writing prompt to file, conditionally append approval gate instructions:

```python
def spawn_agent(self, task_id: str, prompt: str, working_dir: Path, branch: str) -> SessionRecord:
    # ... existing setup code ...

    # NEW: Inject approval gate instructions if enabled
    if self.config.inject_approval_gate:
        db_path = str(working_dir / ".workflow_approvals.db")
        gate_instructions = generate_approval_gate_instructions(
            agent_id=task_id,
            db_path=db_path
        )
        prompt = prompt + "\n\n" + gate_instructions

    # Write prompt to file (existing code)
    prompt_file = prompt_dir / f"prompt_{safe_task_id}.md"
    prompt_file.write_text(prompt)
    # ... rest of method ...
```

### Step 3: Apply same pattern to SubprocessAdapter (subprocess_adapter.py)
For consistency, add the same injection logic to SubprocessAdapter:

```python
def spawn_agent(self, task_id: str, prompt: str, working_dir: Path, branch: str) -> SessionRecord:
    # NEW: Import and inject
    from .tmux_adapter import generate_approval_gate_instructions

    if self.config.inject_approval_gate:  # Assuming SubprocessConfig gets same field
        db_path = str(working_dir / ".workflow_approvals.db")
        gate_instructions = generate_approval_gate_instructions(
            agent_id=task_id,
            db_path=db_path
        )
        prompt = prompt + "\n\n" + gate_instructions

    # ... existing code ...
```

### Step 4: Add CLI flag --no-approval-gate (cli.py)
Add to `prd spawn` command:

```python
prd_spawn.add_argument('--no-approval-gate', action='store_true',
                       help='Disable automatic approval gate injection')
```

Pass through to TmuxConfig:
```python
config = TmuxConfig(inject_approval_gate=not args.no_approval_gate)
```

### Step 5: Update tests
- Test spawn_agent() with injection enabled (default)
- Test spawn_agent() with injection disabled
- Verify prompt file contains gate instructions when enabled
- Verify prompt file does NOT contain gate instructions when disabled

## Files to Modify

| File | Changes |
|------|---------|
| `src/prd/tmux_adapter.py` | Add config field, modify spawn_agent() |
| `src/prd/subprocess_adapter.py` | Add injection logic for consistency |
| `src/cli.py` | Add --no-approval-gate flag to prd spawn |
| `tests/test_tmux_adapter.py` | Add tests for injection behavior |
| `tests/test_subprocess_adapter.py` | Add tests for injection behavior |

## Scope
- ~50 lines of code changes
- Low complexity - straightforward string concatenation
- No new dependencies
- Backwards compatible (injection enabled by default)

## Out of Scope
- Changes to ApprovalGate logic (PRD-005 delivered this)
- Changes to approval queue (PRD-005 delivered this)
- New CLI commands (PRD-005 delivered this)
