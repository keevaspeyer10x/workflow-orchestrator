# Code Review: Control Inversion V4 Implementation

## Summary
The implementation of Control Inversion V4 represents a significant architectural shift that correctly addresses the "LLM agency" problem. By moving the control loop into Python code (`WorkflowExecutor`) and treating the LLM as a sub-routine (`ClaudeCodeRunner`), reliability is guaranteed. The code structure is clean, modular, and well-typed.

## 🟢 strengths
1.  **Architecture**: The separation of `Executor` (logic), `StateStore` (persistence), `GateEngine` (validation), and `Runner` (execution) is excellent. It decouples the "brain" from the "muscle".
2.  **Reliability**: `Executor` guarantee of workflow completion (success or fail) resolves the core issue of hung workflows.
3.  **Robustness**: Atomic state writes (`temp_file.rename`) and file locking (`fcntl`) prevent corruption in concurrent scenarios (on Unix).
4.  **Feedback Loop**: The retry mechanism in `Executor._execute_phase` correctly feeds gate failure reasons back to the LLM, enabling self-correction.

## 🔴 Concerns & Risks

### 1. Security: `shell=True` & Permissions
In `src/v4/gate_engine.py`:
```python
result = subprocess.run(
    gate.cmd,
    shell=True,  # <--- Risk
    ...
)
```
And in `src/runners/claude_code.py`:
```python
"--dangerously-skip-permissions",  # <--- High trust required
```
**Risk**: While acceptable for a local dev tool where the user owns the workflow, `shell=True` opens up injection vulnerabilities if workflow YAMLs are ever shared or generated from untrusted sources.
**Recommendation**: Document this strictly. Ensure `workflow.yaml` is treated as code (reviewed).

### 2. Platform Compatibility
In `src/v4/state.py`:
```python
import fcntl  # <--- Unix only
```
**Risk**: This will crash on Windows.
**Recommendation**: Wrap the import and locking logic in a `try/except ImportError` or `os.name` check. Provide a no-op fallback for Windows (with a warning that concurrent protection is disabled).

### 3. Runner Robustness
In `src/runners/claude_code.py`, `_extract_summary` takes the last 10 lines of output.
**Risk**: If `claude` fails or outputs structured data (JSON/XML) mixed with logs, taking the "last 10 lines" might capture garbage or cut off vital context.
**Recommendation**: Consider parsing specific markers (e.g., `## Summary`) if available, or capturing `stderr` separately and surfacing it more prominently in the `PhaseOutput` if `stdout` is sparse.

## 🟡 Questions

1.  **Test Coverage**: `tests/test_executor.py` exists but is untracked. Have the acceptance tests (TC-1 to TC-4) been executed?
2.  **Path Handling**: `GateEngine._validate_no_pattern` uses `glob`. Does it protect against directory traversal (e.g., `paths: ["../../secret"]`)?

## Conclusion
**Approve with comments.** The core logic is solid and achieving the goal of control inversion. The concerns are mostly regarding platform support and security boundaries which are acceptable for an internal tool but need documentation.

**Suggested Next Steps:**
1.  Run the tests in `tests/test_executor.py`.
2.  Add a Windows compatibility fix for `fcntl`.
