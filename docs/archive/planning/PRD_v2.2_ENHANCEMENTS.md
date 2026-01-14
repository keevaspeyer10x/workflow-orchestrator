# PRD: Workflow Orchestrator v2.2 Enhancements

## Overview

This document specifies enhancements to the workflow orchestrator based on best practices from AI agent workflow research. The goal is to make the orchestrator more flexible, environment-agnostic, and capable of handling long-running workflows across context limits.

### Goals
1. **Model flexibility** - Support multiple LLM providers (OpenRouter as default)
2. **Environment agnostic** - Run from Claude Code, Manus, or standalone CLI
3. **Accumulated wisdom** - Operating notes system for embedding learnings
4. **Long workflow support** - Checkpoint/resume for workflows that exceed context limits
5. **Task-specific guidance** - Constraints flag for per-task customization

### Non-Goals
- Direct LLM API calls from the orchestrator (providers generate prompts, external tools execute)
- Sub-agent type hints (deferred)
- Slack/GitHub integrations (deferred, see ROADMAP.md)

---

## Feature 1: Provider Abstraction

### Description
Abstract the current Claude Code integration into a generic provider interface. This enables multiple LLM backends and execution environments.

### Requirements

#### 1.1 Provider Interface
Create `src/providers/base.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class ExecutionResult:
    success: bool
    output: str
    error: Optional[str] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None

class AgentProvider(ABC):
    """Base class for agent providers."""

    @abstractmethod
    def name(self) -> str:
        """Provider name for display."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is available in current environment."""
        pass

    @abstractmethod
    def generate_prompt(self, task: str, context: dict) -> str:
        """Generate a prompt for the agent."""
        pass

    @abstractmethod
    def execute(self, prompt: str, config: dict) -> ExecutionResult:
        """Execute the prompt and return results."""
        pass
```

#### 1.2 Provider Implementations

**OpenRouter Provider** (`src/providers/openrouter.py`):
- Default provider
- Requires `OPENROUTER_API_KEY` environment variable
- Configurable model via `OPENROUTER_MODEL` env var (default: `anthropic/claude-sonnet-4`)
- HTTP API calls to `https://openrouter.ai/api/v1/chat/completions`
- Support for model override per-call

**Claude Code Provider** (`src/providers/claude_code.py`):
- Refactor existing `claude_integration.py` into this interface
- Auto-detected when running inside Claude Code environment
- Uses `claude --print` CLI

**Manual Provider** (`src/providers/manual.py`):
- Generates prompts for human copy/paste
- No execution capability (`execute()` raises NotImplementedError)
- Fallback when no API keys configured

#### 1.3 Provider Registry
Create `src/providers/__init__.py`:

```python
def get_provider(name: Optional[str] = None) -> AgentProvider:
    """Get provider by name, or auto-detect best available."""
    pass

def list_providers() -> list[str]:
    """List available provider names."""
    pass
```

Auto-detection priority:
1. Explicit `--provider` flag
2. Environment detection (Claude Code env → claude_code provider)
3. API key presence (OPENROUTER_API_KEY → openrouter)
4. Fallback to manual

#### 1.4 CLI Integration
Update `handoff` command:

```bash
# Use auto-detected provider
orchestrator handoff

# Specify provider
orchestrator handoff --provider openrouter
orchestrator handoff --provider claude_code
orchestrator handoff --provider manual

# Specify model (for providers that support it)
orchestrator handoff --provider openrouter --model anthropic/claude-opus-4

# Execute with provider
orchestrator handoff --execute --provider openrouter
```

#### 1.5 Configuration
Add to workflow.yaml settings (optional):

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

### Acceptance Criteria
- [ ] Provider interface defined in `src/providers/base.py`
- [ ] OpenRouter provider implemented and working
- [ ] Claude Code provider refactored from existing code
- [ ] Manual provider implemented as fallback
- [ ] `--provider` and `--model` flags added to CLI
- [ ] Auto-detection works correctly
- [ ] Existing `handoff --execute` still works

---

## Feature 2: Environment Detection

### Description
Detect the execution environment and adapt behavior accordingly.

### Requirements

#### 2.1 Environment Detection Module
Create `src/environment.py`:

```python
from enum import Enum

class Environment(Enum):
    CLAUDE_CODE = "claude_code"
    MANUS = "manus"
    STANDALONE = "standalone"

def detect_environment() -> Environment:
    """Detect current execution environment."""
    # Check for Claude Code indicators
    # Check for Manus indicators
    # Default to standalone
    pass

def get_environment_config(env: Environment) -> dict:
    """Get environment-specific configuration."""
    pass
```

#### 2.2 Detection Heuristics

**Claude Code**:
- Environment variable `CLAUDE_CODE` is set
- Or parent process is `claude`
- Or `.claude` directory exists in ancestors

**Manus**:
- Environment variable `MANUS_SESSION` is set
- Or running inside Manus sandbox indicators

**Standalone**:
- Default fallback

#### 2.3 Environment-Specific Behavior

| Behavior | Claude Code | Manus | Standalone |
|----------|-------------|-------|------------|
| Default provider | claude_code | openrouter | openrouter |
| Output format | Markdown optimized | Markdown | Plain text option |
| Handoff style | Task tool hint | File-based | Copy/paste prompt |
| Status verbosity | Concise | Full | Full |

#### 2.4 CLI Flag
```bash
# Override auto-detection
orchestrator status --env standalone
orchestrator handoff --env manus
```

### Acceptance Criteria
- [ ] Environment detection module created
- [ ] Claude Code environment detected correctly
- [ ] Manus environment detected correctly
- [ ] Standalone fallback works
- [ ] `--env` override flag works
- [ ] Provider auto-selection adapts to environment

---

## Feature 3: Operating Notes System

### Description
Add a `notes` field to phases and items for embedding operational wisdom, tips, cautions, and learnings.

### Requirements

#### 3.1 Schema Changes
Update `src/schema.py`:

```python
class ChecklistItemDef(BaseModel):
    id: str
    name: str
    description: str = ""
    required: bool = True
    skippable: bool = True
    verification: Optional[VerificationConfig] = None
    notes: list[str] = []  # NEW: Operating notes for this item

class PhaseDef(BaseModel):
    id: str
    name: str
    description: str = ""
    items: list[ChecklistItemDef]
    notes: list[str] = []  # NEW: Operating notes for this phase
```

#### 3.2 Note Conventions
Notes are freeform strings. Optional bracket prefixes for categorization:

- `[tip]` - Helpful suggestion
- `[caution]` - Something to watch out for
- `[learning]` - Insight from previous workflows
- `[context]` - Background information
- `[learning:YYYY-MM-DD]` - Learning with date
- `[from:workflow-id]` - Learning with source

Examples:
```yaml
phases:
  - id: "IMPLEMENT"
    notes:
      - "This codebase uses barrel exports - follow that pattern"
      - "[caution] utils/ has circular dependency issues"
      - "[learning:2024-01-03] Large refactors work better as multiple PRs"
    items:
      - id: "write_tests"
        notes:
          - "[tip] Integration tests catch issues unit tests miss"
          - "[caution] Over-mocking hides bugs"
```

#### 3.3 Display in Recitation
Update `status` command output to include notes:

```
CURRENT PHASE: IMPLEMENT
Phase Notes:
  • This codebase uses barrel exports - follow that pattern
  • ⚠️ [caution] utils/ has circular dependency issues
  • 💡 [learning] Large refactors work better as multiple PRs

CURRENT ITEM: write_tests
Item Notes:
  • 💡 [tip] Integration tests catch issues unit tests miss
  • ⚠️ [caution] Over-mocking hides bugs
```

#### 3.4 Display in Handoff Prompts
Include notes in generated handoff prompts:

```markdown
## Operating Notes

### Phase: IMPLEMENT
- This codebase uses barrel exports - follow that pattern
- ⚠️ utils/ has circular dependency issues
- 💡 Large refactors work better as multiple PRs

### Current Items
**write_tests**:
- 💡 Integration tests catch issues unit tests miss
- ⚠️ Over-mocking hides bugs
```

#### 3.5 Learning Integration
Update `src/learning.py` to suggest notes:

```
Suggested operating notes for future workflows:

For IMPLEMENT phase:
  - "[learning] Security review caught 3 issues"

For item 'write_tests':
  - "[learning] Spent 2h on mock issues - prefer integration tests"

Add to workflow.yaml? [y/n/edit]
```

### Acceptance Criteria
- [ ] `notes` field added to PhaseDef schema
- [ ] `notes` field added to ChecklistItemDef schema
- [ ] Notes displayed in `status` command
- [ ] Notes included in handoff prompts
- [ ] Optional emoji rendering for categorized notes
- [ ] Learning engine suggests note additions
- [ ] Example workflows updated with notes

---

## Feature 4: Task Constraints Flag

### Description
Add a `--constraints` flag to `orchestrator start` for task-specific guidance without modifying workflow.yaml.

### Requirements

#### 4.1 CLI Change
```bash
orchestrator start "Fix the login bug" \
  --constraints "Minimal changes only" \
  --constraints "Do not refactor surrounding code" \
  --constraints "Must maintain backwards compatibility"
```

Or multiline:
```bash
orchestrator start "Refactor auth module" --constraints "$(cat <<EOF
This is a large refactor - multiple PRs are acceptable
Must maintain backwards compatibility for /api/v1 endpoints
Database schema changes require migration scripts
EOF
)"
```

#### 4.2 State Storage
Add to WorkflowState:

```python
class WorkflowState(BaseModel):
    # ... existing fields ...
    constraints: list[str] = []  # NEW: Task-specific constraints
```

#### 4.3 Display in Recitation
```
CURRENT TASK: Fix the login bug

CONSTRAINTS:
  • Minimal changes only
  • Do not refactor surrounding code
  • Must maintain backwards compatibility

CURRENT PHASE: IMPLEMENT
...
```

#### 4.4 Display in Handoff
```markdown
## Task
Fix the login bug

## Constraints
- Minimal changes only
- Do not refactor surrounding code
- Must maintain backwards compatibility

## Current Phase
...
```

### Acceptance Criteria
- [ ] `--constraints` flag added to `start` command
- [ ] Constraints stored in workflow state
- [ ] Constraints displayed in `status` output
- [ ] Constraints included in handoff prompts
- [ ] Multiple `--constraints` flags accumulate

---

## Feature 5: Checkpoint/Resume System

### Description
Enable saving workflow state with context summaries and resuming in fresh context. Critical for long workflows that exceed context limits.

### Requirements

#### 5.1 Checkpoint Data Model
Add to `src/schema.py`:

```python
@dataclass
class Checkpoint:
    id: str  # e.g., "checkpoint_2024-01-05_PLAN_complete"
    workflow_state: WorkflowState
    created_at: datetime
    phase_at_checkpoint: str

    # Context recovery data
    decisions: list[str]  # Key decisions made so far
    file_manifest: list[str]  # Important files to read on resume
    context_summary: str  # Human or LLM-generated summary
    accumulated_learnings: list[str]  # Learnings so far

    # Optional metadata
    message: Optional[str] = None  # User-provided checkpoint message
    context_tokens_estimate: Optional[int] = None
```

#### 5.2 Checkpoint Storage
Store checkpoints in `.workflow_checkpoints/` directory:
```
.workflow_checkpoints/
  checkpoint_2024-01-05_PLAN_complete.json
  checkpoint_2024-01-05_IMPLEMENT_item3.json
```

#### 5.3 CLI Commands

**Create checkpoint:**
```bash
# Manual checkpoint
orchestrator checkpoint
orchestrator checkpoint --message "Completed auth design, ready for implementation"

# Include specific decisions
orchestrator checkpoint --decision "Using JWT not sessions" --decision "Tokens in httpOnly cookies"

# Include files to read on resume
orchestrator checkpoint --file src/auth/design.md --file src/types/auth.ts
```

**List checkpoints:**
```bash
orchestrator checkpoints
# Output:
# Available checkpoints:
#   1. checkpoint_2024-01-05_PLAN_complete (2 hours ago)
#      Phase: PLAN → IMPLEMENT
#      Message: "Completed auth design"
#   2. checkpoint_2024-01-05_IMPLEMENT_item3 (30 min ago)
#      Phase: IMPLEMENT (3/6 items)
```

**Resume from checkpoint:**
```bash
# Resume from latest
orchestrator resume

# Resume from specific checkpoint
orchestrator resume --from checkpoint_2024-01-05_PLAN_complete

# Just show handoff prompt without modifying state
orchestrator resume --dry-run
```

#### 5.4 Auto-Checkpoint
Add setting for automatic checkpointing:

```yaml
settings:
  auto_checkpoint: true  # Checkpoint after each phase completes
  checkpoint_on_phase_complete: true
```

When `orchestrator advance` completes a phase, automatically create checkpoint.

#### 5.5 Resume Handoff Prompt
When resuming, generate a handoff prompt optimized for fresh context:

```markdown
# Workflow Handoff: [Task Description]

## Context Recovery
This is a continuation of an in-progress workflow. Read the following to restore context:

### Key Decisions Made
1. Using JWT tokens (not sessions) - need stateless scaling
2. Refresh tokens stored in httpOnly cookies
3. Access token expiry: 15 minutes

### Files to Read
Before proceeding, read these files:
- docs/AUTH_DESIGN.md - Full design document
- src/types/auth.ts - Type definitions
- src/middleware/auth.ts - Current implementation (partial)

### Summary
[Context summary here - what was done, what's next]

## Current Status
Task: Implement user authentication system
Phase: IMPLEMENT (3/6 items complete)
Constraints:
- Must work with existing User model
- No breaking changes to /api/users

### Completed Items
- [x] JWT signing utilities (src/utils/jwt.ts)
- [x] Login endpoint (src/routes/auth/login.ts)
- [x] Token refresh endpoint

### Remaining Items
- [ ] Auth middleware
- [ ] Logout endpoint
- [ ] Password reset flow

## Operating Notes
- [caution] Watch for circular imports in utils/
- [tip] Run type-check frequently

## Next Action
Continue with item: auth_middleware
```

#### 5.6 Checkpoint Cleanup
```bash
# Remove old checkpoints
orchestrator checkpoints --cleanup --max-age 7d

# Remove all checkpoints for completed workflows
orchestrator checkpoints --cleanup --completed
```

### Acceptance Criteria
- [ ] Checkpoint data model defined
- [ ] `checkpoint` command creates checkpoint files
- [ ] `checkpoints` command lists available checkpoints
- [ ] `resume` command restores state and generates handoff
- [ ] Auto-checkpoint on phase completion works
- [ ] Handoff prompt includes all context recovery data
- [ ] `--dry-run` flag shows prompt without modifying state
- [ ] Checkpoint cleanup works

---

## Implementation Notes

### File Changes Summary

| File | Changes |
|------|---------|
| `src/schema.py` | Add `notes` to PhaseDef/ChecklistItemDef, add `constraints` to WorkflowState, add Checkpoint model |
| `src/engine.py` | Add checkpoint/resume methods, integrate constraints |
| `src/cli.py` | Add `--provider`, `--model`, `--env`, `--constraints` flags, add `checkpoint`, `checkpoints`, `resume` commands |
| `src/providers/` | New directory with base.py, openrouter.py, claude_code.py, manual.py |
| `src/environment.py` | New file for environment detection |
| `src/claude_integration.py` | Refactor into `src/providers/claude_code.py` |

### Testing Considerations

1. **Provider tests**: Mock HTTP calls for OpenRouter, test provider selection logic
2. **Environment tests**: Test detection with various env var combinations
3. **Notes tests**: Verify notes appear in status and handoff output
4. **Checkpoint tests**: Create checkpoint, resume, verify state matches
5. **Integration tests**: Full workflow with checkpoints across "sessions"

### Migration

- Existing workflows without `notes` fields should work (empty list default)
- Existing state files without `constraints` should work (empty list default)
- `claude_integration.py` can be deprecated with import redirect to new location

---

## Success Metrics

1. **Provider flexibility**: Can execute handoffs with OpenRouter API
2. **Environment adaptation**: Correctly detects and adapts to Claude Code, Manus, standalone
3. **Operating notes**: Notes appear in status and handoff output
4. **Checkpoint/resume**: Can checkpoint mid-workflow, resume in new session, continue successfully
5. **Backwards compatible**: Existing workflows and state files continue to work
