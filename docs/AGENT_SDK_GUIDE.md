# Agent SDK User Guide

## Overview

The Agent SDK provides a Python client library for AI agents to interact with the Workflow Orchestrator. It handles task claiming, phase transitions, tool execution, and state management.

## Installation

```bash
# From within the workflow-orchestrator project
pip install -e .
```

## Quick Start

```python
from src.agent_sdk.client import AgentClient

# Create client
with AgentClient(agent_id="my-agent-001") as client:
    # Claim a task
    task = client.claim_task(capabilities=["python", "testing"])

    # Use tools
    content = client.read_file("README.md")

    # Transition to next phase
    client.request_transition(
        target_phase="TDD",
        artifacts={
            "plan_document": {
                "title": "Implementation Plan",
                "acceptance_criteria": [
                    {"criterion": "Feature works", "how_to_verify": "Run tests"}
                ],
                "implementation_steps": ["Write tests", "Implement"],
                "scope": {"in_scope": ["Feature A"], "out_of_scope": ["Feature B"]}
            }
        }
    )
```

## Core Concepts

### Task Lifecycle

1. **Claim Task**: Agent claims a task and receives initial phase token
2. **Execute Phase**: Agent uses allowed tools for current phase
3. **Request Transition**: Agent requests to move to next phase with artifacts
4. **Repeat**: Continue through phases until workflow complete

### Phase Tokens

- JWT tokens that prove agent's authorization for current phase
- Automatically managed by SDK
- Refreshed on successful phase transitions
- Include task ID, phase, and expiration

### Tool Permissions

Tools are restricted by phase. The SDK enforces these restrictions:

- **PLAN**: read_files, grep (read-only operations)
- **TDD**: read_files, write_files, bash (write tests)
- **IMPL**: read_files, write_files, bash (implement code)
- **REVIEW**: read_files (review only)

## API Reference

### AgentClient

Main client for interacting with orchestrator.

#### Constructor

```python
AgentClient(
    agent_id: str,
    orchestrator_url: str = "http://localhost:8000"
)
```

**Parameters**:
- `agent_id`: Unique identifier for this agent
- `orchestrator_url`: URL of orchestrator API

**Example**:
```python
client = AgentClient(
    agent_id="agent-001",
    orchestrator_url="http://orchestrator:8000"
)
```

#### claim_task()

Claim a task from the orchestrator.

```python
claim_task(
    capabilities: Optional[List[str]] = None
) -> Dict[str, Any]
```

**Parameters**:
- `capabilities`: List of agent capabilities (e.g., ["python", "testing"])

**Returns**:
```python
{
    "task": {
        "id": "task-abc123",
        "agent_id": "agent-001",
        "capabilities": ["python"],
        "assigned_phase": "PLAN"
    },
    "phase_token": "eyJ0eXAiOiJKV1QiLCJhbGci...",
    "phase": "PLAN"
}
```

**Example**:
```python
result = client.claim_task(capabilities=["python", "testing"])
task_id = result["task"]["id"]
```

#### request_transition()

Request transition to next phase.

```python
request_transition(
    target_phase: str,
    artifacts: Dict[str, Any]
) -> Dict[str, Any]
```

**Parameters**:
- `target_phase`: Phase to transition to (e.g., "TDD")
- `artifacts`: Required artifacts for gate validation

**Returns**:
```python
{
    "allowed": True,
    "new_token": "eyJ0eXAiOiJKV1QiLCJhbGci...",
    "blockers": []  # Empty if allowed
}
```

**Raises**:
- `RuntimeError`: If task not claimed first
- `PermissionError`: If transition blocked by gate

**Example**:
```python
try:
    client.request_transition(
        target_phase="TDD",
        artifacts={
            "plan_document": {
                "title": "Complete Plan",
                "acceptance_criteria": [...],
                "implementation_steps": [...],
                "scope": {...}
            }
        }
    )
except PermissionError as e:
    print(f"Transition blocked: {e}")
```

#### use_tool()

Execute a tool with permission checking.

```python
use_tool(
    tool_name: str,
    **kwargs
) -> Any
```

**Parameters**:
- `tool_name`: Name of tool to execute
- `**kwargs`: Tool-specific arguments

**Returns**: Tool-specific result

**Raises**:
- `RuntimeError`: If task not claimed first
- `PermissionError`: If tool not allowed in current phase
- `ValueError`: If tool execution fails

**Example**:
```python
# Read a file
content = client.use_tool("read_files", path="/path/to/file.txt")

# Write a file (in TDD or IMPL phase)
client.use_tool("write_files", path="/path/to/output.txt", content="data")

# Run command (in TDD or IMPL phase)
result = client.use_tool("bash", command="pytest tests/", timeout=30)
```

#### get_state_snapshot()

Get current state snapshot.

```python
get_state_snapshot() -> Dict[str, Any]
```

**Returns**:
```python
{
    "task_dependencies": ["task-000"],
    "completed_tasks": ["task-000"],
    "current_phase": "PLAN",
    "blockers": []
}
```

**Example**:
```python
snapshot = client.get_state_snapshot()
if snapshot["blockers"]:
    print(f"Blockers: {snapshot['blockers']}")
```

### Convenience Methods

Simplified wrappers for common operations.

#### read_file()

Read a file.

```python
read_file(
    path: str,
    offset: int = 0,
    limit: Optional[int] = None
) -> str
```

**Example**:
```python
content = client.read_file("README.md")
```

#### write_file()

Write a file (requires TDD or IMPL phase).

```python
write_file(
    path: str,
    content: str,
    mode: str = "w"
) -> Dict[str, Any]
```

**Example**:
```python
client.write_file("output.txt", "Hello World")
```

#### run_command()

Run a shell command (requires TDD or IMPL phase).

```python
run_command(
    command: str,
    timeout: int = 30,
    cwd: Optional[str] = None
) -> Dict[str, Any]
```

**Example**:
```python
result = client.run_command("pytest tests/")
if result["exit_code"] == 0:
    print("Tests passed!")
```

#### grep()

Search files with regex.

```python
grep(
    pattern: str,
    path: str,
    context_lines: int = 0
) -> Dict[str, Any]
```

**Example**:
```python
results = client.grep(r"def.*test", "tests/")
print(f"Found {results['total']} matches")
```

## Complete Example

```python
from src.agent_sdk.client import AgentClient

def main():
    # Create client with context manager for automatic cleanup
    with AgentClient(agent_id="planning-agent-001") as client:
        # Step 1: Claim task
        print("Claiming task...")
        result = client.claim_task(capabilities=["python", "planning"])
        print(f"Claimed task: {result['task']['id']}")
        print(f"Current phase: {result['phase']}")

        # Step 2: Read requirements (PLAN phase allows read_files)
        print("\nReading requirements...")
        requirements = client.read_file("requirements.txt")
        print(f"Found {len(requirements.splitlines())} dependencies")

        # Step 3: Search codebase
        print("\nSearching codebase...")
        search_results = client.grep(r"class.*Test", "tests/")
        print(f"Found {search_results['total']} test classes")

        # Step 4: Get state snapshot
        snapshot = client.get_state_snapshot()
        print(f"\nCurrent phase: {snapshot['current_phase']}")
        print(f"Dependencies: {snapshot['task_dependencies']}")

        # Step 5: Transition to TDD phase
        print("\nRequesting transition to TDD...")
        try:
            client.request_transition(
                target_phase="TDD",
                artifacts={
                    "plan_document": {
                        "title": "Feature Implementation Plan",
                        "acceptance_criteria": [
                            {
                                "criterion": "All tests pass",
                                "how_to_verify": "Run pytest"
                            }
                        ],
                        "implementation_steps": [
                            "Write failing tests",
                            "Implement feature",
                            "Verify tests pass"
                        ],
                        "scope": {
                            "in_scope": ["User authentication"],
                            "out_of_scope": ["Password reset"]
                        }
                    }
                }
            )
            print("Transition successful!")

            # Step 6: Write tests (now in TDD phase)
            print("\nWriting tests...")
            test_content = '''
def test_authentication():
    assert True  # Placeholder
'''
            client.write_file("tests/test_auth.py", test_content)
            print("Tests written!")

            # Step 7: Run tests
            print("\nRunning tests...")
            result = client.run_command("pytest tests/test_auth.py")
            print(f"Exit code: {result['exit_code']}")

        except PermissionError as e:
            print(f"Transition blocked: {e}")
            return

if __name__ == "__main__":
    main()
```

## Error Handling

### Common Errors

#### RuntimeError: Must claim task first

**Cause**: Attempting to use SDK methods before claiming a task

**Solution**: Call `claim_task()` first

```python
client = AgentClient("agent-001")
client.claim_task()  # Required!
client.read_file("file.txt")  # Now works
```

#### PermissionError: Tool not allowed

**Cause**: Using a tool not permitted in current phase

**Solution**: Check phase permissions or transition to correct phase

```python
# In PLAN phase, write_files is forbidden
try:
    client.write_file("output.txt", "data")
except PermissionError:
    # Transition to TDD first
    client.request_transition("TDD", artifacts={...})
    client.write_file("output.txt", "data")  # Now works
```

#### PermissionError: Transition blocked

**Cause**: Artifacts don't meet requirements or gate validation fails

**Solution**: Check blockers and fix artifacts

```python
try:
    result = client.request_transition("TDD", artifacts={...})
except PermissionError as e:
    # Parse error message for blockers
    print(f"Blockers: {e}")
    # Fix artifacts and retry
```

### Retry Logic

The SDK does not include automatic retry logic. Implement your own:

```python
import time

def claim_with_retry(client, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            return client.claim_task()
        except Exception as e:
            if attempt == max_attempts - 1:
                raise
            time.sleep(2 ** attempt)  # Exponential backoff
```

## Best Practices

### 1. Use Context Manager

Always use `with` statement for automatic cleanup:

```python
# Good
with AgentClient("agent-001") as client:
    client.claim_task()
    # ... work ...

# Avoid
client = AgentClient("agent-001")
client.claim_task()
# ... work ...
client.close()  # Easy to forget
```

### 2. Check Permissions Before Tool Use

Understand phase permissions to avoid errors:

```python
# Check current phase first
snapshot = client.get_state_snapshot()
if snapshot["current_phase"] == "PLAN":
    # Only use read-only tools
    content = client.read_file("file.txt")
else:
    # Can use write tools
    client.write_file("output.txt", "data")
```

### 3. Validate Artifacts Before Transition

Ensure artifacts meet requirements:

```python
def validate_plan(plan):
    assert len(plan["title"]) >= 10
    assert len(plan["acceptance_criteria"]) > 0
    assert len(plan["implementation_steps"]) > 0
    return True

# Validate before requesting transition
artifacts = {...}
if validate_plan(artifacts["plan_document"]):
    client.request_transition("TDD", artifacts)
```

### 4. Handle State Dependencies

Check if dependencies are met:

```python
snapshot = client.get_state_snapshot()

# Check if dependencies completed
required_deps = snapshot["task_dependencies"]
completed = snapshot["completed_tasks"]

if not all(dep in completed for dep in required_deps):
    print("Waiting for dependencies...")
    # Wait or exit
```

### 5. Log Operations for Debugging

All tool executions are audited, but add your own logging:

```python
import logging

logger = logging.getLogger(__name__)

def main():
    with AgentClient("agent-001") as client:
        logger.info("Claiming task")
        client.claim_task()

        logger.info("Reading requirements")
        content = client.read_file("requirements.txt")

        logger.info(f"Found {len(content)} bytes")
```

## Advanced Usage

### Custom Orchestrator URL

Point to different orchestrator instance:

```python
client = AgentClient(
    agent_id="agent-001",
    orchestrator_url="http://production-orchestrator:8000"
)
```

### Multi-Agent Coordination

Use state snapshots for coordination:

```python
# Agent 1: Check if previous task completed
snapshot = client.get_state_snapshot()
if "task-000" in snapshot["completed_tasks"]:
    # Safe to proceed
    client.claim_task()
```

### Artifact Templates

Create reusable artifact templates:

```python
def create_plan_artifact(title, criteria, steps, scope):
    return {
        "plan_document": {
            "title": title,
            "acceptance_criteria": [
                {"criterion": c, "how_to_verify": "Manual test"}
                for c in criteria
            ],
            "implementation_steps": steps,
            "scope": scope
        }
    }

# Use template
artifacts = create_plan_artifact(
    title="Implement login",
    criteria=["User can log in"],
    steps=["Create form", "Add validation"],
    scope={"in_scope": ["Login"], "out_of_scope": ["Register"]}
)
```

## Troubleshooting

### Connection Issues

```python
import requests

# Test orchestrator connectivity
try:
    response = requests.get("http://localhost:8000/health")
    print(f"Orchestrator healthy: {response.json()}")
except requests.exceptions.ConnectionError:
    print("Cannot connect to orchestrator")
```

### Token Expiration

Tokens expire after 2 hours by default. SDK automatically handles refresh on transition.

### Phase Token Issues

If you see "Invalid phase token", the token may be expired or corrupted. Claim a new task.

## API Endpoints Used

The SDK wraps these REST endpoints:

- `POST /api/v1/tasks/claim` - Claim task
- `POST /api/v1/tasks/transition` - Request transition
- `POST /api/v1/tools/execute` - Execute tool
- `GET /api/v1/state/snapshot` - Get state snapshot

## See Also

- [Workflow YAML Specification](WORKFLOW_SPEC.md)
- [Deployment Guide](DEPLOYMENT_GUIDE.md)
- [API Documentation](http://localhost:8000/docs) (when orchestrator running)
