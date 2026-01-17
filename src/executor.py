"""
Core workflow executor - implements control inversion.
The orchestrator DRIVES; Claude Code EXECUTES within bounds.
"""
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .v4.models import (
    WorkflowSpec, WorkflowState, WorkflowStatus, WorkflowResult,
    PhaseSpec, PhaseInput, PhaseOutput, PhaseExecution, GateResult
)
from .v4.state import StateStore
from .v4.gate_engine import GateEngine
from .v4.parser import parse_workflow
from .runners.base import AgentRunner, RunnerError


class ExecutorError(Exception):
    """Error during workflow execution"""
    pass


class WorkflowExecutor:
    """
    The deterministic workflow executor.

    This is where CONTROL INVERSION happens:
    - Orchestrator owns the loop
    - Orchestrator calls Claude Code for each phase
    - Orchestrator validates gates
    - Orchestrator guarantees completion

    LLM cannot:
    - Skip phases
    - Self-declare completion
    - Bypass gate validation
    """

    def __init__(
        self,
        workflow_spec: WorkflowSpec,
        runner: AgentRunner,
        state_store: StateStore,
        gate_engine: GateEngine
    ):
        self.spec = workflow_spec
        self.runner = runner
        self.state_store = state_store
        self.gate_engine = gate_engine

    def run(self, task_description: str) -> WorkflowResult:
        """
        Execute the workflow to completion.

        This is THE MAIN LOOP - deterministic and guaranteed to complete.

        Args:
            task_description: What the workflow should accomplish

        Returns:
            WorkflowResult with final status
        """
        start_time = time.time()

        # Initialize state
        state = self.state_store.initialize(
            workflow_name=self.spec.name,
            task_description=task_description
        )

        print(f"\n{'='*60}")
        print(f"ORCHESTRATOR: Starting workflow '{self.spec.name}'")
        print(f"Workflow ID: {state.workflow_id}")
        print(f"Task: {task_description}")
        print(f"{'='*60}\n")

        try:
            # Start with first phase
            current_phase = self.spec.get_first_phase()

            # THE MAIN LOOP
            while current_phase is not None:
                phase_result = self._execute_phase(current_phase, state)

                if phase_result:
                    # Phase passed - advance
                    self.state_store.complete_phase(current_phase.id)
                    current_phase = self.spec.get_next_phase(current_phase.id)
                else:
                    # Phase failed after max attempts
                    self.state_store.mark_complete(success=False)
                    return WorkflowResult(
                        workflow_id=state.workflow_id,
                        status=WorkflowStatus.FAILED,
                        phases_completed=state.phases_completed,
                        total_duration_seconds=time.time() - start_time,
                        error_message=f"Phase '{current_phase.id}' failed after max attempts"
                    )

            # All phases complete - SUCCESS
            self.state_store.mark_complete(success=True)

            print(f"\n{'='*60}")
            print("ORCHESTRATOR: Workflow COMPLETED successfully")
            print(f"Phases completed: {', '.join(state.phases_completed)}")
            print(f"Duration: {time.time() - start_time:.1f}s")
            print(f"{'='*60}\n")

            return WorkflowResult(
                workflow_id=state.workflow_id,
                status=WorkflowStatus.COMPLETED,
                phases_completed=state.phases_completed,
                total_duration_seconds=time.time() - start_time,
                summary=f"Successfully completed {len(state.phases_completed)} phases"
            )

        except Exception as e:
            # Unexpected error - save state and fail
            self.state_store.mark_complete(success=False)
            return WorkflowResult(
                workflow_id=state.workflow_id,
                status=WorkflowStatus.FAILED,
                phases_completed=state.phases_completed,
                total_duration_seconds=time.time() - start_time,
                error_message=f"Unexpected error: {str(e)}"
            )
        finally:
            self.state_store.cleanup()

    def _execute_phase(self, phase: PhaseSpec, state: WorkflowState) -> bool:
        """
        Execute a single phase with retry logic.

        Returns:
            True if phase completed successfully, False if failed after max attempts
        """
        print(f"\n{'-'*40}")
        print(f"PHASE: {phase.id} - {phase.name}")
        print(f"Max attempts: {phase.max_attempts}")
        print(f"{'-'*40}")

        for attempt in range(1, phase.max_attempts + 1):
            print(f"\n  Attempt {attempt}/{phase.max_attempts}")

            # Update state
            self.state_store.update_phase(phase.id, attempt)

            # Record execution start
            execution = PhaseExecution(
                phase_id=phase.id,
                attempt=attempt,
                started_at=datetime.now()
            )
            state.phase_executions.append(execution)

            # Build phase input
            is_retry = attempt > 1
            retry_feedback = ""
            if is_retry and state.phase_executions:
                # Get feedback from previous attempt's gate failures
                prev_exec = state.phase_executions[-2] if len(state.phase_executions) > 1 else None
                if prev_exec and prev_exec.gate_results:
                    failed_gates = [g for g in prev_exec.gate_results if not g.passed]
                    retry_feedback = "\n".join([
                        f"- {g.gate_type}: {g.reason}" for g in failed_gates
                    ])

            phase_input = PhaseInput(
                phase_id=phase.id,
                phase_name=phase.name,
                task_description=state.task_description,
                phase_description=phase.description,
                constraints=[],  # Could be populated from YAML
                context={
                    "phases_completed": state.phases_completed,
                    "workflow_name": self.spec.name,
                    "attempt": attempt
                },
                is_retry=is_retry,
                retry_feedback=retry_feedback
            )

            # Execute via runner
            print(f"  Running Claude Code...")
            try:
                output = self.runner.run_phase(phase_input)
            except RunnerError as e:
                print(f"  ERROR: Runner failed: {e}")
                execution.status = "failed"
                execution.completed_at = datetime.now()
                continue

            execution.output_summary = output.summary

            if not output.success:
                print(f"  Phase execution failed: {output.error_message}")
                execution.status = "failed"
                execution.completed_at = datetime.now()
                continue

            # Validate gates
            print(f"  Validating gates...")
            gate_results = self.gate_engine.validate_all(phase.gates)
            execution.gate_results = gate_results

            # Check if all gates passed
            if self.gate_engine.all_passed(gate_results):
                print(f"  All gates PASSED")
                execution.status = "passed"
                execution.completed_at = datetime.now()
                self.state_store.save()
                return True
            else:
                # Report failed gates
                failed = [g for g in gate_results if not g.passed]
                print(f"  {len(failed)} gate(s) FAILED:")
                for g in failed:
                    print(f"    - {g.gate_type}: {g.reason}")
                execution.status = "failed"
                execution.completed_at = datetime.now()
                self.state_store.save()

        # Max attempts exhausted
        print(f"\n  Phase FAILED after {phase.max_attempts} attempts")
        return False

    def resume(self, workflow_id: str) -> WorkflowResult:
        """
        Resume a paused or interrupted workflow.

        Args:
            workflow_id: ID of workflow to resume

        Returns:
            WorkflowResult with final status
        """
        start_time = time.time()

        # Load existing state
        state = self.state_store.load(workflow_id)

        if state.is_complete():
            return WorkflowResult(
                workflow_id=workflow_id,
                status=state.status,
                phases_completed=state.phases_completed,
                total_duration_seconds=0,
                summary="Workflow already complete"
            )

        print(f"\n{'='*60}")
        print(f"ORCHESTRATOR: Resuming workflow '{state.workflow_name}'")
        print(f"Workflow ID: {workflow_id}")
        print(f"Resuming from phase: {state.current_phase_id}")
        print(f"{'='*60}\n")

        try:
            # Resume from current phase
            current_phase = self.spec.get_phase(state.current_phase_id)

            # Continue the loop
            while current_phase is not None:
                phase_result = self._execute_phase(current_phase, state)

                if phase_result:
                    self.state_store.complete_phase(current_phase.id)
                    current_phase = self.spec.get_next_phase(current_phase.id)
                else:
                    self.state_store.mark_complete(success=False)
                    return WorkflowResult(
                        workflow_id=workflow_id,
                        status=WorkflowStatus.FAILED,
                        phases_completed=state.phases_completed,
                        total_duration_seconds=time.time() - start_time,
                        error_message=f"Phase '{current_phase.id}' failed after max attempts"
                    )

            self.state_store.mark_complete(success=True)

            return WorkflowResult(
                workflow_id=workflow_id,
                status=WorkflowStatus.COMPLETED,
                phases_completed=state.phases_completed,
                total_duration_seconds=time.time() - start_time,
                summary=f"Successfully completed {len(state.phases_completed)} phases"
            )

        finally:
            self.state_store.cleanup()
