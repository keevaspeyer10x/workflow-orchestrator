# Fix PRD LocalBackend for Claude Code Environment

## Problem

The LocalBackend at `src/prd/backends/local.py` spawns `claude --print -p <prompt>` subprocesses. This doesn't work when already running inside Claude Code because:

1. The spawned processes run in non-interactive mode
2. They can't actually create branches, edit files, or commit changes
3. Creates a recursive Claude-in-Claude situation that doesn't function

## Solution: Sequential Execution Mode

When running inside Claude Code, the backend should switch to **sequential execution mode** where:

1. Tasks are yielded one at a time as prompts
2. The current Claude session executes each task
3. Execution is tracked via the file-based queue

## Implementation

### 1. Add environment detection

```python
def is_inside_claude_code() -> bool:
    """Detect if we're running inside Claude Code."""
    # Check for Claude Code environment indicators
    return os.environ.get('CLAUDE_CODE') == '1' or
           'claude' in os.environ.get('_', '').lower()
```

### 2. Create SequentialBackend

New backend that doesn't spawn processes but instead:
- Generates task prompts
- Tracks tasks via queue
- Allows current session to mark tasks complete

```python
class SequentialBackend(WorkerBackendBase):
    """Backend for sequential execution by current Claude session."""

    def spawn(self, job: JobMessage) -> WorkerHandle:
        # Don't actually spawn - just queue the task
        # Return handle with prompt for current session
```

### 3. Update PRDExecutor

Modify executor to detect sequential mode and yield tasks:

```python
async def execute_prd_sequential(self, prd: PRDDocument):
    """Execute PRD sequentially, yielding tasks for current session."""
    for task in self._get_ready_tasks():
        yield TaskPrompt(task_id=task.id, prompt=self._generate_prompt(task))
        # Wait for task to be marked complete
        await self._wait_for_task_complete(task.id)
```

### 4. Update CLI

Add interactive mode for sequential execution:

```python
def cmd_prd_start(args):
    if is_inside_claude_code():
        # Interactive sequential mode
        for task_prompt in executor.execute_prd_sequential(prd):
            print(f"\n=== TASK: {task_prompt.task_id} ===")
            print(task_prompt.prompt)
            print("\nExecute this task, then run: orchestrator prd task-done")
```

## Files to Modify

- `src/prd/backends/local.py` - Add environment detection
- `src/prd/backends/sequential.py` (NEW) - Sequential execution backend
- `src/prd/executor.py` - Add sequential execution mode
- `src/cli.py` - Update prd command for sequential mode

## Testing

1. Run `orchestrator prd start examples/phase7_prd.yaml --backend local`
2. Should detect Claude Code environment
3. Should yield tasks one at a time
4. Execute task, mark done, get next task
