# Implementation Plan: OpenRouter Function Calling for Interactive Repo Context

## Overview

Add function calling support to the OpenRouter provider, enabling AI models to interactively request repo context during execution. This gives API-based models (via Claude Code Web) similar context access capabilities to CLI-based tools, without requiring a local proxy like claudish.

## Problem Statement

When workflow-orchestrator uses OpenRouter to execute tasks with non-Claude models:
- Models receive a text prompt but cannot explore the codebase
- Context must be pre-collected and injected into prompts
- Models can't ask for more context mid-execution
- This limits effectiveness compared to tools with native file access

## Solution

Implement OpenRouter function calling to expose these tools:
- `read_file` - Read file contents
- `list_files` - List files matching a glob pattern
- `search_code` - Search for code/text patterns (grep-like)

Models can call these tools during execution, and the orchestrator executes them locally and feeds results back.

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Tools included | read_file, list_files, search_code | Core exploration needs; no shell for security |
| Limits | Soft warnings only | Future-proof as models improve; 2MB file warning, 50 call warning |
| Fallback | Context injection | Graceful degradation for models without function calling |
| Integration | New method + auto-detect | Backwards compatible; existing code unchanged |

---

## Implementation Steps

### Phase 1: Tool Definitions

**1.1 Create `src/providers/tools.py`**
- Define tool schemas in OpenAI function calling format
- `READ_FILE_TOOL` - path parameter, returns file content
- `LIST_FILES_TOOL` - pattern parameter, returns matching paths
- `SEARCH_CODE_TOOL` - pattern + optional path parameters, returns matches

**1.2 Implement tool execution functions**
- `execute_read_file(path, working_dir)` - Read file, warn if >2MB
- `execute_list_files(pattern, working_dir)` - Glob match files
- `execute_search_code(pattern, path, working_dir)` - Grep-like search
- All functions return structured results with success/error status

### Phase 2: Function Calling Loop

**2.1 Add `execute_with_tools()` to `OpenRouterProvider`**
```python
def execute_with_tools(self, prompt: str, model: str = None) -> ExecutionResult:
    """Execute prompt with function calling support."""
    messages = [{"role": "user", "content": prompt}]
    tools = get_tool_definitions()
    call_count = 0

    while True:
        response = self._call_api(messages, tools, model)

        if response.has_tool_calls:
            call_count += 1
            if call_count > 50:
                logger.warning("⚠️ 50+ tool calls - consider optimizing")

            for tool_call in response.tool_calls:
                result = execute_tool(tool_call, self.working_dir)
                messages.append(tool_result_message(tool_call.id, result))
        else:
            # Model finished, return final response
            return ExecutionResult(success=True, output=response.content, ...)
```

**2.2 Implement `_call_api()` with tools support**
- Add `tools` parameter to OpenRouter API call
- Handle streaming responses with tool calls
- Parse tool call responses correctly

### Phase 3: Model Detection & Auto-Selection

**3.1 Add function calling capability detection**
- Maintain list of models known to support function calling
- Query OpenRouter model metadata if available
- Default to assuming support for major models (GPT-4+, Claude, Gemini)

**3.2 Update `execute()` to auto-detect**
```python
def execute(self, prompt: str, model: str = None) -> ExecutionResult:
    model = model or self._model

    if self._supports_function_calling(model):
        return self.execute_with_tools(prompt, model)
    else:
        # Fall back to context injection (existing behavior)
        return self._execute_basic(prompt, model)
```

### Phase 4: Context Injection Fallback

**4.1 Integrate with existing `ReviewContextCollector`**
- Reuse `src/review/context.py` for gathering context
- When function calling unavailable, pre-collect and inject
- Keep existing behavior as fallback path

**4.2 Add working_dir support to provider**
- Provider needs to know the working directory for tool execution
- Add `working_dir` parameter to `__init__` or `execute()`

### Phase 5: Testing

**5.1 Unit tests for tools**
- Test each tool function independently
- Test edge cases (large files, no matches, invalid paths)
- Test warning thresholds

**5.2 Integration tests**
- Test full execute_with_tools loop with mock API
- Test fallback behavior
- Test model detection

**5.3 Manual testing**
- Test with real OpenRouter API
- Verify with GPT-4, Claude, Gemini models

---

## File Changes Summary

### New Files
- `src/providers/tools.py` - Tool definitions and execution functions

### Modified Files
- `src/providers/openrouter.py` - Add execute_with_tools(), model detection
- `src/providers/base.py` - Add working_dir to interface (optional)

### Test Files
- `tests/test_provider_tools.py` - New tests for tools module
- `tests/test_providers.py` - Update with function calling tests

---

## Success Criteria

1. Models with function calling can read files on-demand during execution
2. Models without function calling fall back to context injection seamlessly
3. Soft warnings logged for large files (>2MB) and high call counts (>50)
4. All existing tests pass
5. New functionality covered by tests
6. Works in Claude Code Web environment

---

## Execution Approach

Will implement directly (not Claude Code handoff) since:
- Changes are focused on the provider module
- Straightforward Python implementation
- Good test coverage needed throughout

---

## Open Questions (Resolved)

| Question | Resolution |
|----------|------------|
| Include run_command? | No - security risk, not needed for context |
| Hard limits? | No - soft warnings only, future-proof |
| Total context cap? | No - let model's context window be the limit |
