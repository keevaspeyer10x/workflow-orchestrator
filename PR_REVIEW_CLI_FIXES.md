# Code Review: V3 Pre-Implementation & CLI Changes

## Summary
This PR sets the stage for the **V3 Hybrid Orchestration** refactor. It introduces foundational helper functions in `src/cli.py` for environment detection ("LLM Mode" vs. Human) and emergency overrides. It also completely replaces the project plan and test cases documentation to focus on the V3 pre-implementation checklist.

## 🔍 Findings

### 1. New CLI Helpers (`src/cli.py`)
- **`is_llm_mode()`**: Added to detect if the CLI is being driven by an LLM (specifically Claude Code or piped input).
  - **Observation**: It considers `not sys.stdin.isatty()` as "LLM Mode". This means any piped command (e.g., `echo "yes" | orchestrator ...`) will be classified as LLM mode.
  - **Status**: Defined but **unused** in this diff.
- **`_emergency_override_active()`**: Added to bypass mode detection via `ORCHESTRATOR_EMERGENCY_OVERRIDE`.
  - **Status**: Defined but **unused** in this diff.

### 2. Documentation Pivot (`docs/plan.md`, `tests/test_cases.md`)
- **Complete Rewrite**: The previous content regarding "Issue #58: Model Fallback" has been replaced with the "V3 Pre-Implementation Checklist".
- **Verification**: `src/review/retry.py` and `tests/test_review_fallback.py` exist, so the previous feature (fallback) seems implemented. Replacing the planning docs is acceptable if they are considered ephemeral "current focus" documents.

### 3. Testing
- **Missing Tests**: `src/cli.py` has excellent coverage in `tests/test_cli_noninteractive.py`, but the new `is_llm_mode` and override functions are not yet tested.

## 🛠️ Recommendations

### A. Add Unit Tests for New Helpers
Even if unused, verify the logic to prevent regressions when they are eventually wired up. Add this to `tests/test_cli_noninteractive.py`:

```python
from src.cli import is_llm_mode, _emergency_override_active

class TestIsLLMMode:
    def test_returns_true_with_claudecode_env(self):
        with patch.dict(os.environ, {'CLAUDECODE': '1'}):
             assert is_llm_mode() is True

    def test_returns_true_when_not_tty(self):
        with patch.object(sys.stdin, 'isatty', return_value=False):
             # Ensure CLAUDECODE is unset for this test
             with patch.dict(os.environ, {}, clear=True):
                 assert is_llm_mode() is True

    def test_emergency_override(self):
        with patch.dict(os.environ, {'ORCHESTRATOR_EMERGENCY_OVERRIDE': 'human-override-v3'}):
            assert _emergency_override_active() is True
```

### B. Clarify "LLM Mode" Definition
If `is_llm_mode()` returns `True` for any piped input (`!isatty`), it might be too broad if you intend to distinguish "Automated Script" from "LLM Agent".
- If the intent is "Non-Interactive", you already have `is_interactive()`.
- If the intent is "Agent Context", consider if a standard CI script should trigger "LLM Mode".

## ❓ Questions

1. **Usage Plan**: When will `is_llm_mode` be wired up? Is it intended to restrict actions (like `orchestrator resolve`) or change output formatting?
2. **Standardization**: Is `CLAUDECODE=1` the standard env var we are relying on, or should we support others (e.g., `ODIN_MODE`, `OPENAI_AGENT`)?

## Conclusion
**Approve with nits.** The changes are safe (unused code) and clearly part of a larger plan. Adding the unit tests now is recommended to maintain the high testing standard of `src/cli.py`.
