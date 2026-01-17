# Control Inversion Design V4: Full Programmatic Workflow Enforcement

**Author:** Claude (synthesizing multi-model consensus)
**Date:** 2026-01-17
**Status:** DESIGN REVIEW
**Supersedes:** hybrid_orchestration_design.md (partially implemented)

## Executive Summary

This document defines the architecture for **full control inversion** in the workflow orchestrator. The core principle: **the orchestrator DRIVES the workflow; LLMs EXECUTE within bounds**. This is not optional behavior controlled by prompts—it is programmatically enforced.

### Core Insight (Multi-Model Consensus)

> "LLMs should not own process control. The solution is a Supervisor Pattern where the orchestrator becomes the deterministic driver, with Claude operating within orchestrator-defined scopes."

## Problem Statement

### Today's Failure

On 2026-01-17, Claude completed implementation work but **forgot to run `orchestrator finish`**. The user had to prompt Claude to do it.

This happened because:
1. The orchestrator is passive—it waits for the LLM to call it
2. The YAML says "required: true" but nothing enforces it
3. The LLM has full discretion to ignore the workflow

### The Fundamental Issue

```
CURRENT (Passive Mode):
┌─────────────────────────────────────────────────────────────┐
│  User → Claude Code → (maybe calls orchestrator?)           │
│                       (maybe forgets?)                      │
│                       (maybe skips phases?)                 │
└─────────────────────────────────────────────────────────────┘

REQUIRED (Active Mode):
┌─────────────────────────────────────────────────────────────┐
│  User → orchestrator run → Claude Code (scoped tasks)       │
│              ↓                                              │
│         [Enforced gates, guaranteed completion]             │
└─────────────────────────────────────────────────────────────┘
```

## Design Principles

### P1: Deterministic Backbone + Autonomous Islands

The orchestrator owns:
- Workflow state machine (deterministic)
- Phase transitions (programmatic)
- Gate validation (code-executed)
- Workflow completion (guaranteed)

The LLM owns:
- Task execution within a phase (autonomous)
- Implementation approach (discretionary)
- Sub-task ordering (flexible)

### P2: YAML Compiles to Executable State Machine

The workflow YAML is not documentation—it compiles to:
1. A state machine with defined transitions
2. Programmatic gate validators
3. Agent prompt templates

### P3: Structured Contracts

All LLM outputs must be structured (JSON) with defined schemas. Non-structured outputs allow the LLM to regain control via ambiguity.

### P4: Entry Point Shift for Guarantees

True completion guarantees require the orchestrator to be the entry point:
- `orchestrator run <workflow.yaml>` (fully automated)
- `orchestrator chat <workflow.yaml>` (interactive with enforcement)

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR ENGINE                           │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  YAML Parser → Executable State Machine                    │  │
│  │  - Phases as nodes                                         │  │
│  │  - Transitions as edges                                    │  │
│  │  - Gates as validators                                     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                           │                                      │
│                           ▼                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Executor Loop (DETERMINISTIC)                             │  │
│  │                                                            │  │
│  │  while not complete:                                       │  │
│  │    1. Load current state                                   │  │
│  │    2. Build scoped prompt for current phase                │  │
│  │    3. CALL agent (API or subprocess)                       │  │
│  │    4. Parse structured output                              │  │
│  │    5. Validate gates (PROGRAMMATIC)                        │  │
│  │    6. Checkpoint state                                     │  │
│  │    7. Advance or retry                                     │  │
│  │                                                            │  │
│  │  finalize()  ← GUARANTEED TO HAPPEN                        │  │
│  └───────────────────────────────────────────────────────────┘  │
│                           │                                      │
│                           ▼                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Agent Interface                                           │  │
│  │  - ClaudeAPIRunner (primary)                               │  │
│  │  - ClaudeCodeSubprocessRunner (fallback)                   │  │
│  │  - ManualRunner (copy-paste mode)                          │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LLM AGENT (Claude)                            │
│                                                                  │
│  - Receives scoped task + constraints                           │
│  - Has bounded autonomy within phase                            │
│  - Returns structured output (JSON)                             │
│  - CANNOT skip phases                                           │
│  - CANNOT self-declare completion                               │
│  - CANNOT access state directly                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### YAML Schema (Enhanced)

```yaml
workflow:
  version: "4.0"
  name: "Development Workflow"

  # Control mode: strict (enforced) vs permissive (advisory)
  enforcement:
    mode: strict

    # These are ALWAYS enforced by code
    programmatic:
      - phase_order          # Cannot skip phases
      - gate_validation      # Gates checked by code
      - workflow_completion  # finish() always called
      - max_attempts         # Retry limits enforced

    # These are LLM discretion within bounds
    discretionary:
      - item_ordering        # Order within phase
      - implementation_approach
      - skip_optional_items  # With justification

  phases:
    - id: plan
      name: "Planning Phase"
      phase_type: strict     # No skipping allowed

      # What the LLM should do
      agent:
        prompt_template: prompts/plan.md
        output_schema: schemas/plan_output.json
        max_attempts: 3
        timeout: 3600  # 1 hour

      # What the orchestrator validates (PROGRAMMATIC)
      gates:
        - type: file_exists
          path: docs/plan.md

        - type: json_schema
          file: .orchestrator/plan_output.json
          schema: schemas/plan_output.json

        - type: command
          cmd: "python -m pytest tests/test_plan.py"
          exit_code: 0

      # Phase transitions
      next: implement
      on_gate_failure: retry  # or escalate

    - id: implement
      name: "Implementation Phase"
      phase_type: guided

      agent:
        prompt_template: prompts/implement.md
        output_schema: schemas/implement_output.json
        # Can specify tools available in this phase
        allowed_tools:
          - read_file
          - write_file
          - run_tests
        forbidden_tools:
          - delete_file  # Safety constraint

      gates:
        - type: command
          cmd: "npm test"

        - type: no_pattern
          pattern: "TODO|FIXME|HACK"
          paths: ["src/**/*.py"]

        - type: min_coverage
          threshold: 80

      next: review

    - id: review
      name: "Review Phase"
      phase_type: strict

      gates:
        - type: external_reviews
          required:
            - security
            - quality

        - type: human_approval
          approvers: ["@owner"]
          timeout: 86400  # 24 hours

      next: complete

    - id: complete
      name: "Completion"
      phase_type: strict

      gates:
        - type: command
          cmd: "git status --porcelain"
          expect_empty: true
          message: "All changes must be committed"
```

### Agent Runner Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any
import json

@dataclass
class PhaseInput:
    """What the agent receives"""
    phase_id: str
    phase_name: str
    task_description: str
    constraints: list[str]
    allowed_tools: list[str]
    forbidden_tools: list[str]
    output_schema: Dict[str, Any]
    context: Dict[str, Any]  # Previous outputs, state
    max_tokens: int = 8192

@dataclass
class PhaseOutput:
    """What the agent must return (structured)"""
    phase_id: str
    deliverables: list[Dict[str, str]]  # [{name, path, description}]
    decisions: list[str]
    open_questions: list[str]
    self_assessment: str
    raw_output: str

class AgentRunner(ABC):
    """Interface for running agent phases"""

    @abstractmethod
    async def run_phase(self, input: PhaseInput) -> PhaseOutput:
        """Execute a phase and return structured output"""
        pass

class ClaudeAPIRunner(AgentRunner):
    """Primary runner - direct Anthropic API"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    async def run_phase(self, input: PhaseInput) -> PhaseOutput:
        system_prompt = self._build_system_prompt(input)
        user_prompt = self._build_user_prompt(input)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=input.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        return self._parse_output(response.content[0].text, input)

    def _build_system_prompt(self, input: PhaseInput) -> str:
        return f"""You are executing phase '{input.phase_name}' of a workflow.

CONSTRAINTS (MUST follow):
{chr(10).join(f'- {c}' for c in input.constraints)}

ALLOWED TOOLS: {', '.join(input.allowed_tools) or 'Standard tools only'}
FORBIDDEN TOOLS: {', '.join(input.forbidden_tools) or 'None'}

OUTPUT FORMAT:
You MUST respond with valid JSON matching this schema:
{json.dumps(input.output_schema, indent=2)}

Do not include any text outside the JSON response.
"""

    def _build_user_prompt(self, input: PhaseInput) -> str:
        return f"""## Task

{input.task_description}

## Context

{json.dumps(input.context, indent=2)}

## Required Output

Complete this phase and return a JSON object with:
- deliverables: List of files/artifacts created
- decisions: Key decisions made
- open_questions: Any unresolved questions
- self_assessment: Brief assessment of completion quality
"""

class ClaudeCodeSubprocessRunner(AgentRunner):
    """Fallback runner - subprocess with Claude Code CLI"""

    async def run_phase(self, input: PhaseInput) -> PhaseOutput:
        import subprocess
        import tempfile

        # Write prompt to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(self._build_full_prompt(input))
            prompt_file = f.name

        # Run Claude Code with prompt
        result = subprocess.run(
            ['claude', '--print', '--file', prompt_file],
            capture_output=True,
            text=True,
            timeout=input.max_tokens  # Rough timeout
        )

        return self._parse_output(result.stdout, input)
```

### Executor Loop (Core)

```python
class WorkflowExecutor:
    """The deterministic executor - this is where control inversion happens"""

    def __init__(
        self,
        workflow_spec: WorkflowSpec,
        agent_runner: AgentRunner,
        state_store: StateStore
    ):
        self.spec = workflow_spec
        self.runner = agent_runner
        self.state = state_store
        self.gate_engine = GateEngine()

    async def run(self, task_description: str) -> WorkflowResult:
        """
        THE MAIN LOOP - Orchestrator drives, LLM executes.
        This loop GUARANTEES completion (success or max-attempts failure).
        """
        # Initialize
        self.state.initialize(task_description)
        self.state.save()

        while not self.state.is_complete():
            phase = self.spec.get_phase(self.state.current_phase)

            print(f"\n{'='*60}")
            print(f"ORCHESTRATOR: Phase {phase.id} - {phase.name}")
            print(f"{'='*60}")

            # Build scoped input for agent
            phase_input = self._build_phase_input(phase)

            # Execute with retry
            success = False
            for attempt in range(phase.agent.max_attempts):
                print(f"Attempt {attempt + 1}/{phase.agent.max_attempts}")

                # CALL AGENT (this is the key inversion)
                try:
                    output = await self.runner.run_phase(phase_input)
                except Exception as e:
                    print(f"Agent execution failed: {e}")
                    continue

                # VALIDATE GATES (programmatic, not LLM-controlled)
                gate_result = await self.gate_engine.validate(
                    phase.gates,
                    output,
                    self.state
                )

                if gate_result.passed:
                    success = True
                    self.state.record_phase_completion(phase.id, output)
                    self.state.advance_to(phase.next)
                    break
                else:
                    print(f"Gate failed: {gate_result.reason}")
                    phase_input = self._build_retry_input(
                        phase, output, gate_result
                    )

            if not success:
                # Max attempts exceeded
                if phase.on_gate_failure == "escalate":
                    return WorkflowResult(
                        status="escalated",
                        phase=phase.id,
                        reason="Max attempts exceeded"
                    )
                else:
                    # Record failure and continue (if policy allows)
                    self.state.record_phase_failure(phase.id)

            # CHECKPOINT (always, regardless of success)
            self.state.save()

        # FINALIZE (GUARANTEED)
        return self._finalize()

    def _finalize(self) -> WorkflowResult:
        """
        Called when workflow is complete.
        This is GUARANTEED to happen - the LLM cannot forget it.
        """
        print(f"\n{'='*60}")
        print("ORCHESTRATOR: Workflow Complete")
        print(f"{'='*60}")

        # Commit, sync, cleanup - all programmatic
        self.state.mark_complete()
        self.state.save()

        return WorkflowResult(
            status="completed",
            summary=self.state.get_summary()
        )
```

### Gate Engine (Programmatic Validation)

```python
class GateEngine:
    """Programmatic gate validation - LLM cannot bypass this"""

    def __init__(self):
        self.validators = {
            'file_exists': self._validate_file_exists,
            'json_schema': self._validate_json_schema,
            'command': self._validate_command,
            'no_pattern': self._validate_no_pattern,
            'min_coverage': self._validate_min_coverage,
            'external_reviews': self._validate_external_reviews,
            'human_approval': self._validate_human_approval,
        }

    async def validate(
        self,
        gates: list[GateSpec],
        output: PhaseOutput,
        state: WorkflowState
    ) -> GateResult:
        """
        Validate all gates for a phase.
        Returns GateResult with passed=True only if ALL gates pass.
        """
        results = []

        for gate in gates:
            validator = self.validators.get(gate.type)
            if not validator:
                raise ValueError(f"Unknown gate type: {gate.type}")

            result = await validator(gate, output, state)
            results.append(result)

            if not result.passed:
                return GateResult(
                    passed=False,
                    reason=f"Gate '{gate.type}' failed: {result.reason}",
                    details=result.details
                )

        return GateResult(passed=True)

    async def _validate_file_exists(
        self, gate: GateSpec, output: PhaseOutput, state: WorkflowState
    ) -> GateResult:
        path = Path(gate.path)
        if not path.exists():
            return GateResult(passed=False, reason=f"File not found: {gate.path}")
        return GateResult(passed=True)

    async def _validate_command(
        self, gate: GateSpec, output: PhaseOutput, state: WorkflowState
    ) -> GateResult:
        result = subprocess.run(
            gate.cmd,
            shell=True,
            capture_output=True,
            timeout=gate.timeout or 300
        )

        expected = gate.exit_code if gate.exit_code is not None else 0
        if result.returncode != expected:
            return GateResult(
                passed=False,
                reason=f"Command failed with exit code {result.returncode}",
                details={"stderr": result.stderr.decode()}
            )

        if gate.expect_empty and result.stdout.strip():
            return GateResult(
                passed=False,
                reason=f"Expected empty output: {result.stdout.decode()}"
            )

        return GateResult(passed=True)

    async def _validate_no_pattern(
        self, gate: GateSpec, output: PhaseOutput, state: WorkflowState
    ) -> GateResult:
        import re
        pattern = re.compile(gate.pattern)

        for glob_pattern in gate.paths:
            for path in Path('.').glob(glob_pattern):
                if path.is_file():
                    content = path.read_text()
                    matches = pattern.findall(content)
                    if matches:
                        return GateResult(
                            passed=False,
                            reason=f"Pattern '{gate.pattern}' found in {path}",
                            details={"matches": matches[:5]}
                        )

        return GateResult(passed=True)
```

## CLI Interface

### New Commands

```bash
# Orchestrator-driven execution (TRUE CONTROL INVERSION)
orchestrator run workflow.yaml --task "Build authentication system"
orchestrator run workflow.yaml --resume <checkpoint-id>

# Interactive mode (with enforcement)
orchestrator chat workflow.yaml --task "Build authentication system"

# Check status
orchestrator status
orchestrator status --verbose

# Manual approval for human gates
orchestrator approve <gate-id>
orchestrator reject <gate-id> --reason "..."
```

### Deprecated Commands (Compatibility Mode)

```bash
# These still work but emit deprecation warnings
orchestrator start "task"    # → Warns: Use 'orchestrator run' instead
orchestrator complete <id>   # → Warns: Orchestrator now manages completion
orchestrator finish          # → No-op in run mode (finalize is automatic)
```

## Backward Compatibility

### Dual Mode Support

```yaml
# In workflow.yaml
workflow:
  control_mode: driven   # NEW: orchestrator drives (default in v4)
  # OR
  control_mode: passive  # LEGACY: LLM drives (deprecated)
```

### Migration Path

1. **Phase 1 (Immediate)**: Ship `orchestrator run` command
2. **Phase 2 (1 month)**: Default new workflows to `control_mode: driven`
3. **Phase 3 (3 months)**: Deprecate passive mode
4. **Phase 4 (6 months)**: Remove passive mode

## Acceptance Criteria

These tests MUST pass before the feature is complete:

```python
def test_workflow_completes_even_if_llm_forgets():
    """
    Core requirement: Orchestrator guarantees completion.
    LLM cannot prevent workflow from finishing.
    """
    # Setup: Mock LLM that doesn't call any completion commands
    runner = MockRunner(outputs=["Here's the implementation..."])
    executor = WorkflowExecutor(spec, runner, state)

    result = await executor.run("Build feature")

    # Even though LLM didn't call finish, workflow completes
    assert result.status == "completed"
    assert state.is_complete()

def test_llm_cannot_skip_phases():
    """
    Phase order is enforced programmatically.
    LLM cannot skip from PLAN to VERIFY.
    """
    # LLM tries to report completion of VERIFY while in PLAN
    runner = MockRunner(outputs=[{"phase": "verify", "complete": True}])
    executor = WorkflowExecutor(spec, runner, state)

    result = await executor.run("Build feature")

    # Orchestrator ignores the skip attempt, processes PLAN first
    assert state.phases_completed == ["plan"]

def test_gates_validated_programmatically():
    """
    Gate validation is done by code, not LLM self-report.
    """
    # LLM claims tests pass, but they actually don't
    runner = MockRunner(outputs=[{
        "self_assessment": "All tests pass!",
        "deliverables": []
    }])

    # But the test command actually fails
    with patch('subprocess.run') as mock_run:
        mock_run.return_value.returncode = 1

        result = await executor.run_phase(plan_phase)

        # Gate fails based on actual command, not LLM claim
        assert result.gate_result.passed == False

def test_structured_output_required():
    """
    LLM must return structured JSON output.
    Non-structured output is rejected.
    """
    runner = MockRunner(outputs=["Here's some prose without JSON..."])
    executor = WorkflowExecutor(spec, runner, state)

    result = await executor.run_phase(plan_phase)

    # Output rejected, retry triggered
    assert result.needs_retry
    assert "JSON" in result.retry_reason
```

## Implementation Plan

### Phase 1: Core Executor (Week 1)

1. Create `src/executor.py` with:
   - `WorkflowExecutor` class
   - State machine logic
   - Basic gate validation

2. Create `src/runners/base.py` with:
   - `AgentRunner` interface
   - `PhaseInput`/`PhaseOutput` contracts

3. Create `src/runners/api.py` with:
   - `ClaudeAPIRunner` implementation

4. Add `orchestrator run` command

### Phase 2: Gate Engine (Week 2)

1. Extend `src/gates.py` with:
   - `GateEngine` class
   - All gate types from spec

2. Add structured output validation

3. Add retry logic with feedback

### Phase 3: CLI & Compatibility (Week 3)

1. Add `orchestrator chat` command
2. Add deprecation warnings to old commands
3. Add `control_mode` to workflow spec
4. Migration tooling

### Phase 4: Testing & Hardening (Week 4)

1. All acceptance tests
2. Integration tests
3. Performance testing
4. Documentation

## Open Questions

1. **Timeout handling**: What happens when a phase times out?
   - Recommendation: Checkpoint state, allow resume

2. **Cost management**: API calls add up. How to limit?
   - Recommendation: Token budgets per phase, warn before exceeding

3. **Interactive mode UX**: How to make `orchestrator chat` feel natural?
   - Recommendation: Stream output, show phase transitions clearly

4. **Human gates**: How to notify approvers?
   - Recommendation: Webhook/email integration, polling with bell

## References

- [Gap Analysis](./CONTROL_INVERSION_GAP_ANALYSIS.md)
- [Industry Research](./CONTROL_INVERSION_RESEARCH.md)
- [Process Failure Analysis](./CONTROL_INVERSION_PROCESS_FAILURE_ANALYSIS.md)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [CrewAI Flows](https://www.crewai.com/crewai-flows)
- [Temporal Durable Execution](https://temporal.io/how-it-works)
- [Blueprint First, Model Second (2025)](https://www.arxiv.org/pdf/2508.02721)
