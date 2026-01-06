"""
OpenRouter provider for agent execution.

This provider uses the OpenRouter API to execute prompts through various LLM models.
Requires OPENROUTER_API_KEY environment variable to be set.
"""

import os
import time
import json
import logging
from typing import Optional
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

from .base import AgentProvider, ExecutionResult


logger = logging.getLogger(__name__)


class OpenRouterProvider(AgentProvider):
    """
    Provider that executes prompts through the OpenRouter API.
    
    OpenRouter provides unified access to multiple LLM providers through
    a single API endpoint.
    """
    
    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    DEFAULT_MODEL = "anthropic/claude-sonnet-4"
    DEFAULT_TIMEOUT = 600  # 10 minutes
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None
    ):
        """
        Initialize the OpenRouter provider.
        
        Args:
            api_key: OpenRouter API key (defaults to OPENROUTER_API_KEY env var)
            model: Default model to use (defaults to claude-sonnet-4)
            timeout: Request timeout in seconds (defaults to 600)
        """
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self._model = model or os.environ.get("OPENROUTER_MODEL", self.DEFAULT_MODEL)
        self._timeout = timeout or self.DEFAULT_TIMEOUT
    
    def name(self) -> str:
        return "openrouter"
    
    def is_available(self) -> bool:
        """Check if OpenRouter API is available (API key is set)."""
        if requests is None:
            logger.warning("requests library not available")
            return False
        return bool(self._api_key)
    
    def get_default_model(self) -> str:
        return self._model
    
    def generate_prompt(self, task: str, context: dict) -> str:
        """
        Generate a handoff prompt formatted for OpenRouter/LLM consumption.
        
        Args:
            task: The task description
            context: Workflow context dictionary
        
        Returns:
            str: Formatted prompt
        """
        lines = [
            "# Task Handoff",
            "",
            f"## Task",
            task,
            "",
        ]
        
        # Add constraints if present
        constraints = context.get("constraints", [])
        if constraints:
            lines.extend([
                "## Constraints",
                *[f"- {c}" for c in constraints],
                "",
            ])
        
        # Add phase info
        phase = context.get("phase", "Unknown")
        lines.extend([
            f"## Current Phase: {phase}",
            "",
        ])
        
        # Add checklist items
        items = context.get("items", [])
        if items:
            lines.extend([
                "## Checklist Items to Complete",
            ])
            for item in items:
                item_id = item.get("id", "unknown")
                description = item.get("description", "No description")
                lines.append(f"- [ ] **{item_id}**: {description}")
                
                # Add item notes if present
                item_notes = item.get("notes", [])
                for note in item_notes:
                    lines.append(f"  - Note: {note}")
            lines.append("")
        
        # Add phase notes if present
        notes = context.get("notes", [])
        if notes:
            lines.extend([
                "## Operating Notes",
                *[f"- {n}" for n in notes],
                "",
            ])
        
        # Add relevant files if present
        files = context.get("files", [])
        if files:
            lines.extend([
                "## Relevant Files",
                *[f"- {f}" for f in files],
                "",
            ])
        
        # Add instructions
        lines.extend([
            "## Instructions",
            "1. Complete each checklist item in order",
            "2. After completing each item, report what was done",
            "3. If you encounter blockers, document them clearly",
            "4. Run tests after implementation to verify",
            "5. Provide a summary of changes made",
            "",
            "## Output Format",
            "After completing the work, provide:",
            "```",
            "COMPLETED_ITEMS:",
            "- item_id: <notes about what was done>",
            "",
            "FILES_MODIFIED:",
            "- path/to/file.py: <description of changes>",
            "",
            "TESTS_RUN:",
            "- <test results summary>",
            "",
            "BLOCKERS (if any):",
            "- <description of any issues>",
            "```",
        ])
        
        return "\n".join(lines)
    
    def execute(self, prompt: str, model: Optional[str] = None) -> ExecutionResult:
        """
        Execute the prompt through OpenRouter API.
        
        Args:
            prompt: The prompt to execute
            model: Optional model override
        
        Returns:
            ExecutionResult: The result of execution
        """
        if not self.is_available():
            return ExecutionResult(
                success=False,
                output="",
                error="OpenRouter API key not configured. Set OPENROUTER_API_KEY environment variable."
            )
        
        model_to_use = model or self._model
        start_time = time.time()
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/workflow-orchestrator",
            "X-Title": "Workflow Orchestrator"
        }
        
        payload = {
            "model": model_to_use,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = requests.post(
                    self.API_URL,
                    headers=headers,
                    json=payload,
                    timeout=self._timeout
                )
                
                if response.status_code == 200:
                    data = response.json()
                    duration = time.time() - start_time
                    
                    # Extract response content
                    output = ""
                    if "choices" in data and len(data["choices"]) > 0:
                        message = data["choices"][0].get("message", {})
                        output = message.get("content", "")
                    
                    # Extract usage info
                    usage = data.get("usage", {})
                    tokens = usage.get("total_tokens")
                    
                    return ExecutionResult(
                        success=True,
                        output=output,
                        model_used=data.get("model", model_to_use),
                        tokens_used=tokens,
                        duration_seconds=duration,
                        metadata={
                            "provider": "openrouter",
                            "usage": usage
                        }
                    )
                
                elif response.status_code == 429:
                    # Rate limited - wait and retry
                    last_error = f"Rate limited (429). Retrying in {self.RETRY_DELAY * (attempt + 1)}s..."
                    logger.warning(last_error)
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                    continue
                
                else:
                    # Other error
                    error_msg = f"API error {response.status_code}"
                    try:
                        error_data = response.json()
                        if "error" in error_data:
                            error_detail = error_data["error"]
                            if isinstance(error_detail, dict):
                                error_msg = error_detail.get("message", error_msg)
                            else:
                                error_msg = str(error_detail)
                    except:
                        error_msg = f"{error_msg}: {response.text[:200]}"
                    
                    # Don't expose API key in error messages
                    error_msg = self._sanitize_error(error_msg)
                    last_error = error_msg
                    
                    # Retry on 5xx errors
                    if response.status_code >= 500:
                        logger.warning(f"Server error, retrying: {error_msg}")
                        time.sleep(self.RETRY_DELAY * (attempt + 1))
                        continue
                    else:
                        break
                        
            except requests.exceptions.Timeout:
                last_error = f"Request timed out after {self._timeout}s"
                logger.warning(last_error)
                time.sleep(self.RETRY_DELAY * (attempt + 1))
                continue
                
            except requests.exceptions.RequestException as e:
                last_error = self._sanitize_error(str(e))
                logger.warning(f"Request error: {last_error}")
                time.sleep(self.RETRY_DELAY * (attempt + 1))
                continue
        
        duration = time.time() - start_time
        return ExecutionResult(
            success=False,
            output="",
            error=last_error or "Unknown error",
            model_used=model_to_use,
            duration_seconds=duration
        )
    
    def _sanitize_error(self, error: str) -> str:
        """Remove any API keys from error messages."""
        if self._api_key and self._api_key in error:
            error = error.replace(self._api_key, "[REDACTED]")
        return error
