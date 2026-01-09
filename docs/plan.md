# Implementation Plan: Step Enforcement with Hard Gates and Evidence Validation

## Overview

Add a step enforcement system that ensures workflow compliance through three mechanisms:
1. **Hard Gates**: Commands run by orchestrator (not LLM), cannot be skipped
2. **Evidence Requirements**: Structured output proving engagement with the step
3. **Skip Reasoning Validation**: Substantive justification required when skipping

## Problem Statement

Claude Code sometimes skips steps or executes them superficially when working autonomously. The current system relies on the LLM to self-enforce, which is unreliable. We need external enforcement.

## Design Principles

1. **Trust for judgment, verify for compliance** - Let Claude exercise judgment on substantive work, but enforce procedural steps externally
2. **Hard gates for verifiable steps** - If a bash script can verify it, the orchestrator should run it
3. **Evidence for soft steps** - Require structured artifacts that prove thinking happened
4. **Conscious skipping** - Allow skips but require substantive reasoning

## Architecture Changes

### 1. New Step Type Enum (`schema.py`)

```python
class StepType(str, Enum):
    """Type of step determining enforcement mechanism."""
    LLM_WORK = "llm_work"           # Full latitude, no structure required
    EVIDENCE_REQUIRED = "evidence"   # Must produce structured evidence artifact
    HARD_GATE = "hard_gate"          # Orchestrator runs command, cannot skip
```

### 2. Evidence Schema Support (`schema.py`)

Add to `ChecklistItemDef`:
```python
class ChecklistItemDef(BaseModel):
    # ... existing fields ...
    step_type: StepType = StepType.LLM_WORK
    evidence_schema: Optional[str] = None  # Name of Pydantic model for evidence
    evidence_prompt: Optional[str] = None  # Prompt for generating evidence
```

### 3. Evidence Models (`src/enforcement/evidence.py`)

New module with Pydantic models for common evidence types:
```python
class CodeAnalysisEvidence(BaseModel):
    files_reviewed: list[str]
    patterns_identified: list[str]
    concerns_raised: list[str]
    approach_decision: str

class EdgeCaseEvidence(BaseModel):
    cases_considered: list[str]
    how_handled: dict[str, str]
    cases_deferred: list[str]

class SpecReviewEvidence(BaseModel):
    requirements_extracted: list[str]
    ambiguities_found: list[str]
    assumptions_made: list[str]
```

### 4. Skip Decision Model (`src/enforcement/skip.py`)

```python
class SkipDecision(BaseModel):
    action: Literal["completed", "skipped"]
    evidence: Optional[dict] = None  # Required if completed
    skip_reasoning: Optional[str] = None  # Required if skipped
    context_considered: Optional[list[str]] = None

    @model_validator(mode='after')
    def validate_decision(self):
        if self.action == "skipped":
            if not self.skip_reasoning:
                raise ValueError("Must explain why step was skipped")
            if len(self.skip_reasoning) < 50:
                raise ValueError("Skip reasoning too shallow - minimum 50 chars")
            # Check for shallow patterns
            shallow = ["not needed", "not applicable", "n/a", "obvious", "already done"]
            if self.skip_reasoning.lower().strip() in shallow:
                raise ValueError(f"Skip reasoning too shallow: '{self.skip_reasoning}'")
        return self
```

### 5. Hard Gate Executor (`src/enforcement/gates.py`)

```python
class HardGateExecutor:
    """Executes hard gate commands directly via subprocess."""

    def execute(self, command: str, working_dir: Path) -> GateResult:
        """Run command and return result. Cannot be skipped."""
        result = subprocess.run(
            shlex.split(command),
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=300
        )
        return GateResult(
            success=result.returncode == 0,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr
        )
```

### 6. Engine Integration (`engine.py`)

Modify `complete_item` to check step type:
```python
def complete_item(self, item_id: str, evidence: Optional[dict] = None, ...):
    item_def = self.get_item_def(item_id)

    if item_def.step_type == StepType.HARD_GATE:
        # Run command directly - this is NOT an LLM call
        result = self.gate_executor.execute(item_def.verification.command)
        if not result.success:
            # Feed error back for potential LLM fix
            return False, f"Gate failed: {result.stderr}"
        # Auto-complete on success
        ...

    elif item_def.step_type == StepType.EVIDENCE_REQUIRED:
        if not evidence:
            return False, "This step requires evidence artifact"
        # Validate against schema
        validated = self.validate_evidence(item_def.evidence_schema, evidence)
        # Check for shallow evidence
        self.check_evidence_depth(validated)
        ...
```

### 7. Audit Trail Enhancement (`schema.py`)

Add new event types and enhanced logging:
```python
class EventType(str, Enum):
    # ... existing ...
    GATE_EXECUTED = "gate_executed"
    EVIDENCE_VALIDATED = "evidence_validated"
    SKIP_VALIDATED = "skip_validated"
    SHALLOW_RESPONSE_REJECTED = "shallow_response_rejected"
```

## File Changes Summary

| File | Change |
|------|--------|
| `src/schema.py` | Add `StepType` enum, evidence fields to `ChecklistItemDef` |
| `src/enforcement/__init__.py` | New module |
| `src/enforcement/evidence.py` | Evidence Pydantic models |
| `src/enforcement/skip.py` | Skip decision validation |
| `src/enforcement/gates.py` | Hard gate executor |
| `src/engine.py` | Integrate enforcement in `complete_item`, `skip_item` |
| `src/cli.py` | Add evidence parameter to complete command |
| `src/default_workflow.yaml` | Update items to use new step types |

## Workflow YAML Changes

Example of updated item definitions:
```yaml
- id: "analyze_code"
  name: "Analyze existing code"
  step_type: "evidence"
  evidence_schema: "CodeAnalysisEvidence"
  skippable: false

- id: "run_tests"
  name: "Run tests"
  step_type: "hard_gate"
  verification:
    type: "command"
    command: "{{test_command}}"
  # Note: hard gates are never skippable

- id: "implement_feature"
  name: "Implement the feature"
  step_type: "llm_work"
  # Full latitude, no evidence required
```

## Migration Strategy

1. New fields have sensible defaults (`step_type: llm_work`)
2. Existing workflows continue to work unchanged
3. Gradually update `default_workflow.yaml` to use new types
4. Add step_type to items that should be gates/evidence

## Testing Plan

1. Unit tests for evidence validation
2. Unit tests for skip reasoning validation
3. Unit tests for hard gate execution
4. Integration test: workflow with mixed step types
5. Test shallow response rejection

## Questions for User

1. **Evidence storage**: Should evidence artifacts be stored in a separate file (e.g., `.workflow_evidence.json`) or in the main state file?

2. **Gate retry behavior**: When a hard gate fails, should we:
   - a) Feed error to Claude and let it fix, then retry gate
   - b) Block workflow until manually resolved
   - c) Configurable per-gate

3. **Skip threshold**: Should there be a maximum number of skips per phase before escalation?

4. **Evidence schemas**: Should users be able to define custom evidence schemas in their workflow YAML, or use predefined ones only?

## Implementation Order

1. Add `StepType` enum and fields to schema (non-breaking)
2. Create enforcement module with evidence/skip validation
3. Add hard gate executor
4. Integrate into engine
5. Update CLI with evidence parameter
6. Update default_workflow.yaml with step types
7. Add tests
