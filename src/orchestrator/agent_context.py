"""
Agent context and instruction generation.

Generates markdown instructions and formatted prompts for AI agents.
"""

from pathlib import Path


class AgentContextError(Exception):
    """Raised when agent context operations fail."""
    pass


def generate_agent_instructions(
    task: str,
    server_url: str,
    workflow_path: Path,
    mode: str
) -> str:
    """
    Generate agent instructions in markdown format.

    Args:
        task: Task description
        server_url: Orchestrator server URL
        workflow_path: Path to agent_workflow.yaml
        mode: Execution mode ("sequential" or "parallel")

    Returns:
        Markdown-formatted instructions
    """
    mode_desc = "sequential mode (single agent)" if mode == "sequential" else "parallel mode (multiple agents with coordination)"

    instructions = f"""# Agent Workflow Instructions

## Task
{task}

## Setup Complete
✓ Orchestrator running on {server_url}
✓ Workflow defined in {workflow_path}
✓ Agent SDK available
✓ Execution mode: {mode_desc}

## How to Start

Use the Agent SDK to work through the enforced workflow:

```python
from src.agent_sdk.client import AgentClient

# Initialize client
client = AgentClient(
    agent_id="agent-001",
    orchestrator_url="{server_url}"
)

# Claim the task
task = client.claim_task(capabilities=["read_files", "write_files", "testing"])
print(f"Claimed task: {{task['task']['description']}}")
print(f"Current phase: {{task['phase']}}")

# Example: Request transition to next phase
# When you've completed PLAN phase artifacts:
transition = client.request_transition(
    target_phase="TDD",
    artifacts={{
        "plan_document": "docs/plan.md",
        "scope_definition": "docs/scope.md"
    }}
)
print(f"Transition allowed: {{transition['allowed']}}")
```

## Workflow Phases

The workflow has 5 phases you must complete in order:

### 1. PLAN - Planning & Approval
**Current Phase** ← You start here

**Allowed tools:**
- `read_files` - Read existing code and documentation
- `search_codebase` - Search for patterns in code
- `grep` - Search file contents
- `glob` - Find files by pattern
- `ask_user_question` - Ask clarifying questions
- `web_fetch` - Research external documentation

**Forbidden tools:**
- `write_files`, `edit_files` - No implementation yet!
- `git_commit` - No commits in planning phase
- `bash` - No arbitrary commands during planning

**Required artifacts:**
- Plan document with acceptance criteria
- Scope definition (in-scope vs out-of-scope)

**Next:** Submit plan for approval, then transition to TDD

### 2. TDD - Write Tests (RED phase)
Write failing tests BEFORE implementation.

**Required artifacts:**
- Test files covering acceptance criteria
- Test run showing tests FAIL (RED phase)

### 3. IMPL - Implementation (GREEN phase)
Implement code to make tests pass.

**Required artifacts:**
- Implementation code
- Test run showing tests PASS (GREEN phase)

### 4. REVIEW - Code Review & Quality
Automated security and quality checks.

**Required artifacts:**
- Review report showing no critical issues

### 5. VERIFY - Final Verification
Final checks before completion.

**Required artifacts:**
- Verification that all acceptance criteria met
- Final test run (all passing)

## Agent SDK Reference

### Claim Task
```python
task = client.claim_task(capabilities=["python", "testing"])
```

### Request Phase Transition
```python
result = client.request_transition(
    target_phase="TDD",
    artifacts={{"plan_document": "docs/plan.md"}}
)
```

### Execute Tool (with permission check)
```python
result = client.use_tool("read_files", file_path="src/main.py")
```

### Get State Snapshot
```python
state = client.get_state_snapshot()
print(f"Current phase: {{state['current_phase']}}")
```

## Full Documentation

For complete SDK documentation, see:
- `~/workflow-orchestrator/docs/AGENT_SDK_GUIDE.md`
- Workflow spec: {workflow_path}

## Important Notes

- **Phase tokens are cryptographic proof** - You can only transition when gates pass
- **Tools are enforced** - Forbidden tools will be rejected by orchestrator
- **All state goes through orchestrator** - No direct file mutation of workflow state
- **Gates may require approval** - Some transitions need human approval

---

**Ready to start!** Begin by exploring the codebase in PLAN phase, then create your plan artifacts.
"""

    return instructions


def format_agent_prompt(
    instructions: str,
    server_url: str,
    mode: str
) -> str:
    """
    Format instructions as rich terminal prompt.

    Args:
        instructions: Markdown instructions
        server_url: Orchestrator server URL
        mode: Execution mode

    Returns:
        Formatted prompt with headers and structure
    """
    mode_display = "Sequential (single agent)" if mode == "sequential" else "Parallel (multiple agents)"

    prompt = f"""
============================================================
✓ AGENT WORKFLOW READY
============================================================

Server: {server_url} (running)
Mode: {mode_display}
Workflow: .orchestrator/agent_workflow.yaml (generated)

------------------------------------------------------------
AGENT CONTEXT - USE THIS TO START WORKING
------------------------------------------------------------

{instructions}

------------------------------------------------------------
START WORKING - The orchestrator is watching your progress
============================================================
"""

    return prompt


def save_agent_instructions(content: str, repo_path: Path) -> Path:
    """
    Save agent instructions to .orchestrator directory.

    Args:
        content: Instruction markdown content
        repo_path: Repository root path

    Returns:
        Path to saved instructions file

    Raises:
        AgentContextError: If save fails
    """
    # Create .orchestrator directory
    orchestrator_dir = repo_path / ".orchestrator"

    try:
        orchestrator_dir.mkdir(exist_ok=True)
    except PermissionError:
        raise AgentContextError(
            f"Permission denied: Cannot create {orchestrator_dir}"
        )

    # Save instructions
    instructions_path = orchestrator_dir / "agent_instructions.md"

    try:
        instructions_path.write_text(content)
    except PermissionError:
        raise AgentContextError(
            f"Permission denied: Cannot write to {instructions_path}"
        )

    return instructions_path
