# Control Inversion V4 - Test Cases

## Acceptance Tests

These tests MUST pass before the feature is complete. They verify the core control inversion requirements.

### 1. test_workflow_completes_even_if_llm_doesnt_call_finish

**Purpose:** Core requirement - orchestrator guarantees completion.

**Setup:**
- Mock LLM runner that doesn't call any completion commands
- Simple workflow with one phase (no gates)

**Verification:**
- Workflow completes successfully
- State is marked as COMPLETED
- LLM never called "finish" but workflow still finished

**Code:**
```python
def test_workflow_completes_even_if_llm_doesnt_call_finish():
    runner = MockRunner()  # Returns success but no orchestrator calls
    executor = WorkflowExecutor(spec, runner, state_store, gate_engine)
    result = executor.run("Test task")

    assert result.status == WorkflowStatus.COMPLETED
    assert "phase1" in result.phases_completed
```

### 2. test_llm_cannot_skip_phases

**Purpose:** Phase order is enforced programmatically.

**Setup:**
- Workflow with 3 phases: phase1 → phase2 → phase3
- Mock runner that executes each phase

**Verification:**
- All phases executed in order
- No phases skipped
- Runner called exactly 3 times

**Code:**
```python
def test_llm_cannot_skip_phases():
    runner = MockRunner()
    executor = WorkflowExecutor(spec, runner, state_store, gate_engine)
    result = executor.run("Test task")

    assert result.phases_completed == ["phase1", "phase2", "phase3"]
    assert runner.call_count == 3
```

### 3. test_gates_validated_by_code_not_llm

**Purpose:** Gate validation is done by code, not LLM self-report.

**Setup:**
- Workflow with file_exists gate
- Mock runner that claims success but doesn't create the file
- Max attempts = 1 (fail immediately)

**Verification:**
- Workflow fails because gate check (by code) fails
- LLM's success claim is irrelevant

**Code:**
```python
def test_gates_validated_by_code_not_llm():
    runner = MockRunner()  # Claims success
    # But file doesn't exist
    executor = WorkflowExecutor(spec, runner, state_store, gate_engine)
    result = executor.run("Test task")

    assert result.status == WorkflowStatus.FAILED
```

### 4. test_finalize_always_called

**Purpose:** mark_complete() is always called, even on failure.

**Setup:**
- Workflow with command gate that always fails (exit 1)
- Max attempts = 1

**Verification:**
- Workflow fails
- State is marked as FAILED (not stuck in RUNNING)
- completed_at timestamp is set

**Code:**
```python
def test_finalize_always_called():
    runner = MockRunner()
    executor = WorkflowExecutor(spec, runner, state_store, gate_engine)
    result = executor.run("Test task")

    assert result.status == WorkflowStatus.FAILED
    state = state_store.load(result.workflow_id)
    assert state.status == WorkflowStatus.FAILED
    assert state.completed_at is not None
```

## Unit Tests

### Gate Engine Tests

1. `test_file_exists_gate_passes` - File exists → pass
2. `test_file_exists_gate_fails` - File missing → fail
3. `test_command_gate_passes` - Exit 0 → pass
4. `test_command_gate_fails_exit_code` - Exit 1 → fail
5. `test_command_gate_timeout` - Timeout → fail
6. `test_no_pattern_gate_passes` - Pattern not found → pass
7. `test_no_pattern_gate_fails` - Pattern found → fail
8. `test_json_valid_gate_passes` - Valid JSON → pass
9. `test_json_valid_gate_fails` - Invalid JSON → fail

### State Store Tests

1. `test_state_initialize` - Creates new state
2. `test_state_save_load` - Persistence works
3. `test_state_locking` - Concurrent access blocked
4. `test_state_atomic_write` - Crash-safe writes

### Parser Tests

1. `test_parse_simple_workflow` - Basic YAML parses
2. `test_parse_with_gates` - Gates are parsed correctly
3. `test_parse_invalid_yaml` - Error on invalid YAML
4. `test_parse_missing_required` - Error on missing fields

## Integration Tests

1. `test_full_workflow_execution` - End-to-end with real runner (manual)
2. `test_resume_interrupted_workflow` - Resume after crash
3. `test_concurrent_workflows` - Multiple workflows in same directory fail
