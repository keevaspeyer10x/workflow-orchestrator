# Claude Code Handoff: Feature 1 - Provider Abstraction Layer

## Context
You are implementing Feature 1 (Provider Abstraction) of the v2.2 enhancements for the workflow-orchestrator project. This is the foundation feature that other features depend on.

## Reference Documents
- `PRD_v2.2_ENHANCEMENTS.md` - Full specification (see Feature 1 section)
- `docs/plan_v2.2.md` - Implementation plan with acceptance criteria
- `src/claude_integration.py` - Existing code to refactor into provider

## Files to Create

### 1. `src/providers/__init__.py`
Provider registry with:
- `get_provider(name: str = None, environment: str = None) -> AgentProvider`
- `list_providers() -> list[str]`
- Auto-detection logic (explicit flag → environment → API key → manual fallback)

### 2. `src/providers/base.py`
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class ExecutionResult:
    success: bool
    output: str
    model_used: Optional[str] = None
    error: Optional[str] = None

class AgentProvider(ABC):
    @abstractmethod
    def name(self) -> str:
        """Return provider identifier (e.g., 'openrouter', 'claude_code', 'manual')"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider can be used (e.g., API key present, CLI installed)"""
        pass
    
    @abstractmethod
    def generate_prompt(self, task: str, context: dict) -> str:
        """Generate the handoff prompt for this provider"""
        pass
    
    @abstractmethod
    def execute(self, prompt: str, model: str = None) -> ExecutionResult:
        """Execute the prompt and return result. May raise NotImplementedError for manual."""
        pass
```

### 3. `src/providers/openrouter.py`
OpenRouter HTTP API provider:
- Uses `OPENROUTER_API_KEY` environment variable
- Default model: `anthropic/claude-sonnet-4`
- Endpoint: `https://openrouter.ai/api/v1/chat/completions`
- Implement retry with exponential backoff
- Timeout: 600 seconds (configurable)

### 4. `src/providers/claude_code.py`
Refactor from `src/claude_integration.py`:
- Keep existing functionality
- Implement the `AgentProvider` interface
- Check for `claude` CLI availability in `is_available()`

### 5. `src/providers/manual.py`
Fallback provider:
- `is_available()` always returns `True`
- `generate_prompt()` returns formatted prompt for copy/paste
- `execute()` raises `NotImplementedError` with helpful message

## Files to Modify

### 1. `src/cli.py`
Add to `handoff` command:
- `--provider` flag (choices: openrouter, claude_code, manual)
- `--model` flag (string, provider-specific model name)

### 2. `workflow.yaml`
Add to settings section:
```yaml
settings:
  default_provider: "openrouter"
  default_model: "anthropic/claude-sonnet-4"
  provider_config:
    openrouter:
      model: "anthropic/claude-sonnet-4"
      timeout: 600
    claude_code:
      timeout: 600
```

## Acceptance Criteria (must all pass)
- [ ] Provider interface defined in `src/providers/base.py`
- [ ] OpenRouter provider implemented and working
- [ ] Claude Code provider refactored from existing code
- [ ] Manual provider implemented as fallback
- [ ] `--provider` and `--model` flags added to CLI
- [ ] Auto-detection works correctly
- [ ] Existing `handoff --execute` still works

## Testing Requirements
Create `tests/test_providers.py` with tests for:
- Provider interface (ABC cannot be instantiated)
- OpenRouter availability check (with/without API key)
- OpenRouter prompt generation
- Claude Code availability check
- Manual provider always available
- Provider registry auto-detection
- CLI flags work correctly

## Important Notes
1. **Secrets**: OpenRouter API key is stored in `.manus/secrets.enc.yaml` (SOPS encrypted). For testing, use `OPENROUTER_API_KEY` env var.
2. **Backwards Compatibility**: Existing `handoff --execute` must continue to work (should use auto-detected provider).
3. **Error Handling**: Never log or expose API keys in error messages.
4. **Imports**: Update any imports from `claude_integration` to use new provider location.

## Output Format
After completing, provide:
```
COMPLETED_ITEMS:
- implement_code: <summary of implementation>

FILES_CREATED:
- src/providers/__init__.py
- src/providers/base.py
- src/providers/openrouter.py
- src/providers/claude_code.py
- src/providers/manual.py

FILES_MODIFIED:
- src/cli.py: Added --provider and --model flags
- workflow.yaml: Added provider settings

TESTS_CREATED:
- tests/test_providers.py

ACCEPTANCE_CRITERIA:
- [ ] or [x] for each criterion
```
