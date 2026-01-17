"""
Base interface for agent runners.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..v4.models import PhaseInput, PhaseOutput


class RunnerError(Exception):
    """Base error for runner failures"""
    pass


class AgentRunner(ABC):
    """
    Interface for running agent phases.
    Implementations execute phases and return structured output.
    """

    @abstractmethod
    def run_phase(self, phase_input: PhaseInput) -> PhaseOutput:
        """
        Execute a workflow phase.

        Args:
            phase_input: Input context for the phase

        Returns:
            PhaseOutput with execution results

        Raises:
            RunnerError: If execution fails unrecoverably
        """
        pass
