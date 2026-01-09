# Implementation Plan: Full Integration of Step Enforcement

## Overview

Integrate the step enforcement system (StepType, evidence validation, skip reasoning validation, HardGateExecutor) into the core engine and CLI for full functionality.

## Changes Required

### 1. engine.py Updates

**Add imports:**
```python
from .schema import StepType
from .enforcement import (
    HardGateExecutor,
    validate_skip_reasoning,
    validate_evidence_depth,
    get_evidence_schema
)
```

**Add gate executor instance to WorkflowEngine.__init__:**
```python
self.gate_executor = HardGateExecutor()
```

**Modify complete_item() to:**
- Check step_type before completing
- For `gate` steps: run HardGateExecutor, store result in gate_result
- For `documented` steps: validate evidence if provided, store in evidence field
- For `required` steps: allow completion without evidence
- For `flexible` steps: allow completion without evidence

**Modify skip_item() to:**
- Check step_type - reject skip for `gate` and `required` types
- Use validate_skip_reasoning() for stricter validation on `documented` and `flexible` steps
- Store skip_context_considered if provided

**Add new method execute_gate():**
- Runs gate command with retry logic (max 3 retries)
- Feeds error back for potential fix attempts
- Logs GATE_EXECUTED, GATE_PASSED, GATE_FAILED, GATE_RETRY events

### 2. cli.py Updates

**Add --evidence option to complete command:**
```python
@click.option('--evidence', type=str, help='JSON evidence artifact for documented steps')
```

**Add --context option to skip command:**
```python
@click.option('--context', type=str, help='Context considered before skipping (comma-separated)')
```

**Update complete command handler:**
- Parse evidence JSON if provided
- Pass to engine.complete_item()

**Update skip command handler:**
- Parse context list if provided
- Pass to engine.skip_item()

### 3. default_workflow.yaml Updates

Update key items with appropriate step_type:
- `run_tests` → step_type: gate
- `initial_plan` → step_type: required
- `clarifying_questions` → step_type: documented, evidence_schema: SpecReviewEvidence
- Other items → step_type: flexible (default)

## Implementation Order

1. Update engine.py imports and __init__
2. Add execute_gate() method
3. Modify complete_item() for step enforcement
4. Modify skip_item() for step enforcement
5. Update cli.py with new options
6. Update default_workflow.yaml
7. Add integration tests
8. Run full test suite
