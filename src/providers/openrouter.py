"""
OpenRouter provider for agent execution.

This provider uses the OpenRouter API to execute prompts through various LLM models.
Requires OPENROUTER_API_KEY environment variable to be set.

Supports function calling for models that have this capability, allowing
interactive repo context exploration during execution.
"""

import os
import time
import json
import logging
from pathlib import Path
from typing import Optional, Any, Generator, Iterator

try:
    import requests
except ImportError:
    requests = None

from .base import AgentProvider, ExecutionResult
from .tools import (
    get_tool_definitions,
    execute_tool,
    TOOL_CALL_WARNING_COUNT,
    TOOL_CALL_HARD_LIMIT,
)


logger = logging.getLogger(__name__)

# Models known to support function calling
# This is a conservative list - models not listed will fall back to basic execution
# See CORE-017 in ROADMAP.md for planned `update-models` command to keep this current
FUNCTION_CALLING_MODELS = {
    # OpenAI models (including Codex)
    "openai/gpt-4",
    "openai/gpt-4-turbo",
    "openai/gpt-4-turbo-preview",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/gpt-4.1",
    "openai/gpt-4.1-mini",
    "openai/gpt-4.1-nano",
    "openai/gpt-5",
    "openai/gpt-5.1",
    "openai/gpt-5.1-codex",
    "openai/gpt-5.1-codex-max",
    "openai/codex",  # Codex family prefix
    # Anthropic models
    "anthropic/claude-3-opus",
    "anthropic/claude-3-sonnet",
    "anthropic/claude-3-haiku",
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3.5-haiku",
    "anthropic/claude-sonnet-4",
    "anthropic/claude-opus-4",
    # Google models
    "google/gemini-pro",
    "google/gemini-pro-1.5",
    "google/gemini-2.0-flash",
    "google/gemini-2.5-pro",
    "google/gemini-3-pro",
    "google/gemini-3-pro-preview",
}


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
        timeout: Optional[int] = None,
        working_dir: Optional[Path] = None,
        enable_tools: bool = True
    ):
        """
        Initialize the OpenRouter provider.

        Args:
            api_key: OpenRouter API key (defaults to OPENROUTER_API_KEY env var)
            model: Default model to use (defaults to claude-sonnet-4)
            timeout: Request timeout in seconds (defaults to 600)
            working_dir: Working directory for tool execution (defaults to cwd)
            enable_tools: Whether to enable function calling for supported models
        """
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self._model = model or os.environ.get("OPENROUTER_MODEL", self.DEFAULT_MODEL)
        self._timeout = timeout or self.DEFAULT_TIMEOUT
        self._working_dir = Path(working_dir) if working_dir else Path.cwd()
        self._enable_tools = enable_tools and not os.environ.get("ORCHESTRATOR_DISABLE_TOOLS")
    
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

        Automatically uses function calling for models that support it,
        falling back to basic execution for other models.

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

        # Check if we should use function calling
        if self._enable_tools and self._supports_function_calling(model_to_use):
            logger.info(f"Using function calling with {model_to_use}")
            return self.execute_with_tools(prompt, model_to_use)
        else:
            logger.info(f"Using basic execution with {model_to_use}")
            return self._execute_basic(prompt, model_to_use)
    
    def _sanitize_error(self, error: str) -> str:
        """Remove any API keys from error messages."""
        if self._api_key and self._api_key in error:
            error = error.replace(self._api_key, "[REDACTED]")
        return error

    def _supports_function_calling(self, model: str) -> bool:
        """
        Check if a model supports function calling.

        Args:
            model: The model identifier (e.g., "openai/gpt-4")

        Returns:
            True if the model is known to support function calling
        """
        # Check exact match first
        if model in FUNCTION_CALLING_MODELS:
            return True

        # Check prefix matches for model families
        # This handles versioned models like "openai/gpt-4-0613"
        for known_model in FUNCTION_CALLING_MODELS:
            if model.startswith(known_model):
                return True

        # Conservative default: don't assume function calling support
        return False

    def execute_with_tools(
        self,
        prompt: str,
        model: Optional[str] = None,
        working_dir: Optional[Path] = None
    ) -> ExecutionResult:
        """
        Execute a prompt with function calling support.

        This method enables the model to interactively explore repository
        context by calling tools (read_file, list_files, search_code).

        Args:
            prompt: The prompt to execute
            model: Optional model override
            working_dir: Optional working directory override

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
        work_dir = Path(working_dir) if working_dir else self._working_dir
        start_time = time.time()
        total_tokens = 0
        tool_call_count = 0

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/workflow-orchestrator",
            "X-Title": "Workflow Orchestrator"
        }

        # Initialize conversation with user prompt
        messages = [{"role": "user", "content": prompt}]
        tools = get_tool_definitions()

        while tool_call_count < TOOL_CALL_HARD_LIMIT:
            payload = {
                "model": model_to_use,
                "messages": messages,
                "tools": tools,
            }

            try:
                response = requests.post(
                    self.API_URL,
                    headers=headers,
                    json=payload,
                    timeout=self._timeout
                )

                if response.status_code != 200:
                    error_msg = self._parse_error_response(response)
                    # On API error, try falling back to basic execution
                    logger.warning(f"Tool execution failed: {error_msg}. Falling back to basic execution.")
                    return self._execute_basic(prompt, model_to_use, start_time)

                data = response.json()

                # Track token usage
                usage = data.get("usage", {})
                total_tokens += usage.get("total_tokens", 0)

                # Get the assistant's response
                if "choices" not in data or len(data["choices"]) == 0:
                    return ExecutionResult(
                        success=False,
                        output="",
                        error="No response from API",
                        model_used=model_to_use,
                        duration_seconds=time.time() - start_time
                    )

                choice = data["choices"][0]
                message = choice.get("message", {})
                finish_reason = choice.get("finish_reason", "")

                # Check if the model wants to call tools
                tool_calls = message.get("tool_calls", [])

                if tool_calls:
                    # Add assistant's message with tool calls to conversation
                    messages.append(message)

                    # Process each tool call
                    for tool_call in tool_calls:
                        tool_call_count += 1

                        if tool_call_count == TOOL_CALL_WARNING_COUNT:
                            logger.warning(
                                f"High tool call count ({TOOL_CALL_WARNING_COUNT}+) - "
                                "consider optimizing the prompt"
                            )

                        tool_id = tool_call.get("id", "")
                        function = tool_call.get("function", {})
                        tool_name = function.get("name", "")

                        # Parse arguments
                        try:
                            arguments = json.loads(function.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            arguments = {}

                        logger.debug(f"Tool call: {tool_name}({arguments})")

                        # Execute the tool
                        result = execute_tool(tool_name, arguments, work_dir)

                        # Add tool result to conversation
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": json.dumps(result)
                        })

                else:
                    # Model finished - return the final response
                    output = message.get("content", "")
                    duration = time.time() - start_time

                    return ExecutionResult(
                        success=True,
                        output=output,
                        model_used=data.get("model", model_to_use),
                        tokens_used=total_tokens,
                        duration_seconds=duration,
                        metadata={
                            "provider": "openrouter",
                            "tool_calls": tool_call_count,
                            "usage": usage,
                            "used_function_calling": True
                        }
                    )

            except requests.exceptions.Timeout:
                logger.warning(f"Request timed out after {self._timeout}s during tool execution")
                return self._execute_basic(prompt, model_to_use, start_time)

            except requests.exceptions.RequestException as e:
                logger.warning(f"Request error during tool execution: {self._sanitize_error(str(e))}")
                return self._execute_basic(prompt, model_to_use, start_time)

        # Hit the hard limit
        duration = time.time() - start_time
        return ExecutionResult(
            success=False,
            output="",
            error=f"Exceeded maximum tool calls ({TOOL_CALL_HARD_LIMIT})",
            model_used=model_to_use,
            tokens_used=total_tokens,
            duration_seconds=duration,
            metadata={
                "provider": "openrouter",
                "tool_calls": tool_call_count
            }
        )

    def _execute_basic(
        self,
        prompt: str,
        model: str,
        start_time: Optional[float] = None
    ) -> ExecutionResult:
        """
        Execute a prompt without function calling (basic mode).

        This is the fallback for models that don't support function calling
        or when tool execution fails.

        Args:
            prompt: The prompt to execute
            model: The model to use
            start_time: Optional start time for duration calculation

        Returns:
            ExecutionResult: The result of execution
        """
        if start_time is None:
            start_time = time.time()

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/workflow-orchestrator",
            "X-Title": "Workflow Orchestrator"
        }

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}]
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

                    output = ""
                    if "choices" in data and len(data["choices"]) > 0:
                        message = data["choices"][0].get("message", {})
                        output = message.get("content", "")

                    usage = data.get("usage", {})
                    tokens = usage.get("total_tokens")

                    return ExecutionResult(
                        success=True,
                        output=output,
                        model_used=data.get("model", model),
                        tokens_used=tokens,
                        duration_seconds=duration,
                        metadata={
                            "provider": "openrouter",
                            "usage": usage,
                            "used_function_calling": False
                        }
                    )

                elif response.status_code == 429:
                    last_error = f"Rate limited (429). Retrying..."
                    logger.warning(last_error)
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                    continue

                else:
                    last_error = self._parse_error_response(response)
                    if response.status_code >= 500:
                        logger.warning(f"Server error, retrying: {last_error}")
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
            model_used=model,
            duration_seconds=duration
        )

    def _parse_error_response(self, response: requests.Response) -> str:
        """Parse error message from API response."""
        error_msg = f"API error {response.status_code}"
        try:
            error_data = response.json()
            if "error" in error_data:
                error_detail = error_data["error"]
                if isinstance(error_detail, dict):
                    error_msg = error_detail.get("message", error_msg)
                else:
                    error_msg = str(error_detail)
        except Exception:
            error_msg = f"{error_msg}: {response.text[:200]}"

        return self._sanitize_error(error_msg)

    def execute_streaming(
        self,
        prompt: str,
        model: Optional[str] = None,
        on_chunk: Optional[callable] = None
    ) -> Generator[str, None, ExecutionResult]:
        """
        Execute the prompt with streaming response (CORE-012).

        Yields text chunks as they arrive, enabling real-time display.
        Note: Streaming is incompatible with function calling - tools are disabled.

        Args:
            prompt: The prompt to execute
            model: Optional model override
            on_chunk: Optional callback called with each chunk

        Yields:
            str: Text chunks as they arrive

        Returns:
            ExecutionResult: Final result after streaming completes
        """
        if not self.is_available():
            yield ""
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
            "messages": [{"role": "user", "content": prompt}],
            "stream": True
        }

        try:
            response = requests.post(
                self.API_URL,
                headers=headers,
                json=payload,
                timeout=self._timeout,
                stream=True
            )

            if response.status_code != 200:
                error_msg = self._parse_error_response(response)
                yield ""
                return ExecutionResult(
                    success=False,
                    output="",
                    error=error_msg,
                    model_used=model_to_use,
                    duration_seconds=time.time() - start_time
                )

            full_output = []
            total_tokens = 0

            for line in response.iter_lines():
                if not line:
                    continue

                # SSE format: "data: {...}"
                line_str = line.decode('utf-8') if isinstance(line, bytes) else line

                if not line_str.startswith('data: '):
                    continue

                data_str = line_str[6:]  # Remove "data: " prefix

                if data_str.strip() == '[DONE]':
                    break

                try:
                    data = json.loads(data_str)

                    # Track usage if present
                    if 'usage' in data:
                        total_tokens = data['usage'].get('total_tokens', total_tokens)

                    # Extract content delta
                    if 'choices' in data and len(data['choices']) > 0:
                        delta = data['choices'][0].get('delta', {})
                        content = delta.get('content', '')

                        if content:
                            full_output.append(content)
                            if on_chunk:
                                on_chunk(content)
                            yield content

                except json.JSONDecodeError:
                    logger.debug(f"Failed to parse SSE data: {data_str[:100]}")
                    continue

            duration = time.time() - start_time
            complete_output = ''.join(full_output)

            return ExecutionResult(
                success=True,
                output=complete_output,
                model_used=model_to_use,
                tokens_used=total_tokens if total_tokens > 0 else None,
                duration_seconds=duration,
                metadata={
                    "provider": "openrouter",
                    "streaming": True,
                    "used_function_calling": False
                }
            )

        except requests.exceptions.Timeout:
            duration = time.time() - start_time
            yield ""
            return ExecutionResult(
                success=False,
                output="",
                error=f"Request timed out after {self._timeout}s",
                model_used=model_to_use,
                duration_seconds=duration
            )

        except requests.exceptions.RequestException as e:
            duration = time.time() - start_time
            yield ""
            return ExecutionResult(
                success=False,
                output="",
                error=self._sanitize_error(str(e)),
                model_used=model_to_use,
                duration_seconds=duration
            )

    def stream_to_console(
        self,
        prompt: str,
        model: Optional[str] = None
    ) -> ExecutionResult:
        """
        Execute with streaming and print chunks to console in real-time.

        Convenience method for interactive use.

        Args:
            prompt: The prompt to execute
            model: Optional model override

        Returns:
            ExecutionResult: Final result after streaming completes
        """
        import sys

        result = None
        for chunk in self.execute_streaming(prompt, model):
            sys.stdout.write(chunk)
            sys.stdout.flush()

        # Get the final result (returned from generator)
        # This is a bit awkward but necessary for generator return values
        try:
            gen = self.execute_streaming(prompt, model)
            for _ in gen:
                pass
            result = gen.send(None)
        except StopIteration as e:
            result = e.value

        print()  # Newline after streaming
        return result
