"""
Base provider interface for agent execution.

This module defines the abstract base class that all agent providers must implement,
as well as the ExecutionResult dataclass for standardized return values.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime


@dataclass
class ExecutionResult:
    """Result of executing a prompt through a provider."""
    
    success: bool
    output: str
    model_used: Optional[str] = None
    error: Optional[str] = None
    tokens_used: Optional[int] = None
    duration_seconds: Optional[float] = None
    metadata: dict = field(default_factory=dict)
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class AgentProvider(ABC):
    """
    Abstract base class for agent providers.
    
    All providers must implement these four methods to be usable
    by the workflow orchestrator's handoff system.
    """
    
    @abstractmethod
    def name(self) -> str:
        """
        Return the provider identifier.
        
        Returns:
            str: Provider name (e.g., 'openrouter', 'claude_code', 'manual')
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this provider can be used.
        
        This should verify that all required dependencies are present,
        such as API keys, CLI tools, or network connectivity.
        
        Returns:
            bool: True if the provider is ready to use
        """
        pass
    
    @abstractmethod
    def generate_prompt(self, task: str, context: dict) -> str:
        """
        Generate the handoff prompt for this provider.
        
        Args:
            task: The task description
            context: Dictionary containing workflow context including:
                - phase: Current phase name
                - items: List of checklist items to complete
                - notes: Any operating notes for the phase/items
                - constraints: Task-specific constraints
                - files: Relevant file paths
        
        Returns:
            str: Formatted prompt ready for the provider
        """
        pass
    
    @abstractmethod
    def execute(self, prompt: str, model: Optional[str] = None) -> ExecutionResult:
        """
        Execute the prompt and return the result.
        
        Args:
            prompt: The prompt to execute
            model: Optional model override (provider-specific)
        
        Returns:
            ExecutionResult: The result of execution
        
        Raises:
            NotImplementedError: For providers that don't support execution (e.g., manual)
        """
        pass
    
    def get_default_model(self) -> Optional[str]:
        """
        Get the default model for this provider.
        
        Returns:
            Optional[str]: Default model name, or None if not applicable
        """
        return None
    
    def supports_execution(self) -> bool:
        """
        Check if this provider supports direct execution.
        
        Returns:
            bool: True if execute() can be called, False for manual providers
        """
        return True
