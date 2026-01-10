"""
Agent SDK for Workflow Enforcement

This SDK must be used by all agents to interact with the orchestrator.
Direct state mutation is not allowed - all changes go through the API.
"""

__version__ = "1.0.0"

from .client import AgentClient

__all__ = ["AgentClient"]
