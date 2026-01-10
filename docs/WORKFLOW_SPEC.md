# Workflow YAML Specification

## Overview

The workflow YAML file defines the phases, transitions, gates, and enforcement rules for the orchestrator. It provides a declarative way to specify workflow constraints.

## File Location

Default: `agent_workflow.yaml` in the current directory

Can be overridden via:
- API startup parameter
- Environment variable: `ORCHESTRATOR_WORKFLOW_FILE`

## Schema

### Top-Level Structure

```yaml
name: string              # Workflow name
version: string           # Workflow version
phases: []               # List of phases
transitions: []          # List of allowed transitions
enforcement:             # Enforcement configuration
  mode: string
  phase_tokens: {}
```

## Phases

Phases define workflow stages with tool permissions and required artifacts.

### Phase Structure

```yaml
phases:
  - id: string                    # Unique phase identifier
    name: string                  # Human-readable name
    allowed_tools: []            # Tools allowed in this phase
    forbidden_tools: []          # Explicitly forbidden tools
    required_artifacts: []       # Artifacts required to exit phase
    gates: []                    # Gate validation for transitions
```

### Example Phase

```yaml
- id: PLAN
  name: Planning
  allowed_tools:
    - read_files
    - grep
  forbidden_tools:
    - write_files
    - git_commit
  required_artifacts:
    - type: plan_document
      schema: schemas/plan.json
  gates:
    - id: plan_approval
      type: approval
      blockers:
        - check: plan_has_acceptance_criteria
          severity: blocking
          message: "Plan must have acceptance criteria"
```

### Tool Permissions

#### allowed_tools

List of tools permitted in this phase:

```yaml
allowed_tools:
  - read_files    # Read file contents
  - write_files   # Write file contents
  - bash          # Execute shell commands
  - grep          # Search files
  - git_commit    # Commit changes
```

#### forbidden_tools

Explicitly forbidden tools (overrides allowed_tools):

```yaml
forbidden_tools:
  - git_commit    # Cannot commit in this phase
  - write_files   # Read-only phase
```

**Tool Permission Logic**:
1. If tool in `forbidden_tools`: **DENY**
2. If tool in `allowed_tools`: **ALLOW**
3. Otherwise: **DENY**

### Required Artifacts

Artifacts that must be provided for phase transitions:

```yaml
required_artifacts:
  - type: plan_document         # Artifact type
    schema: schemas/plan.json   # JSON Schema file for validation
```

#### Standard Artifact Types

- `plan_document`: Planning phase output
- `test_files`: Test suite
- `implementation`: Code implementation
- `review_results`: Code review results

#### Artifact Schema Example

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["title", "acceptance_criteria", "implementation_steps", "scope"],
  "properties": {
    "title": {
      "type": "string",
      "minLength": 10
    },
    "acceptance_criteria": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["criterion", "how_to_verify"],
        "properties": {
          "criterion": {"type": "string"},
          "how_to_verify": {"type": "string"}
        }
      }
    },
    "implementation_steps": {
      "type": "array",
      "minItems": 1,
      "items": {"type": "string"}
    },
    "scope": {
      "type": "object",
      "required": ["in_scope", "out_of_scope"],
      "properties": {
        "in_scope": {
          "type": "array",
          "items": {"type": "string"}
        },
        "out_of_scope": {
          "type": "array",
          "items": {"type": "string"}
        }
      }
    }
  }
}
```

### Gates

Gates perform validation before allowing phase transitions.

#### Gate Structure

```yaml
gates:
  - id: string              # Unique gate identifier
    type: string            # Gate type (approval, validation, etc.)
    blockers: []           # List of blocking conditions
```

#### Gate Types

- `approval`: Requires explicit approval
- `validation`: Automated validation checks
- `review`: Code review gate

#### Blocker Structure

```yaml
blockers:
  - check: string          # Check identifier
    severity: string       # blocking, warning, info
    message: string        # Error message if blocked
```

**Severity Levels**:
- `blocking`: Must be resolved to proceed
- `warning`: Can proceed with warning
- `info`: Informational only

#### Gate Example

```yaml
gates:
  - id: tests_passing
    type: validation
    blockers:
      - check: all_tests_pass
        severity: blocking
        message: "All tests must pass before implementation"
      - check: coverage_above_80
        severity: warning
        message: "Test coverage below 80%"
```

## Transitions

Transitions define allowed phase changes.

### Transition Structure

```yaml
transitions:
  - from: string           # Source phase ID
    to: string             # Target phase ID
    gate: string           # Gate ID that must pass
    requires_token: bool   # Whether phase token required
```

### Example Transitions

```yaml
transitions:
  - from: PLAN
    to: TDD
    gate: plan_approval
    requires_token: true

  - from: TDD
    to: IMPL
    gate: tests_written
    requires_token: true

  - from: IMPL
    to: REVIEW
    gate: tests_passing
    requires_token: true

  - from: REVIEW
    to: VERIFY
    gate: review_approved
    requires_token: true
```

### Transition Validation

When requesting a transition:
1. Check `from` phase matches current phase
2. Verify transition exists in configuration
3. Validate phase token if `requires_token: true`
4. Check required artifacts provided
5. Evaluate gate blockers
6. If all pass, generate new phase token

## Enforcement

Configuration for enforcement mode and security.

### Enforcement Structure

```yaml
enforcement:
  mode: string              # strict, permissive, audit
  phase_tokens:
    enabled: bool           # Whether phase tokens required
    algorithm: string       # JWT algorithm (HS256, RS256)
    secret_env_var: string  # Environment variable with secret
    expiry_seconds: int     # Token expiration time
```

### Enforcement Modes

#### strict (Recommended)

Strictly enforces all rules. Blocks non-compliant operations.

```yaml
enforcement:
  mode: strict
```

**Behavior**:
- Tool permissions enforced
- Phase tokens required
- Artifact validation mandatory
- Gates must pass

**Use when**: Production workflows, critical systems

#### permissive

Allows operations with warnings.

```yaml
enforcement:
  mode: permissive
```

**Behavior**:
- Tool permissions warned but not blocked
- Phase tokens optional
- Artifact validation warned
- Gates provide warnings

**Use when**: Development, testing new workflows

#### audit

Logs all operations but doesn't block.

```yaml
enforcement:
  mode: audit
```

**Behavior**:
- All operations allowed
- Everything logged to audit log
- No blocking

**Use when**: Monitoring existing workflows, migration

### Phase Token Configuration

```yaml
phase_tokens:
  enabled: true
  algorithm: HS256
  secret_env_var: ORCHESTRATOR_JWT_SECRET
  expiry_seconds: 7200  # 2 hours
```

**Parameters**:
- `enabled`: Whether to use phase tokens
- `algorithm`: JWT signing algorithm
  - `HS256`: HMAC with SHA-256 (recommended)
  - `RS256`: RSA with SHA-256 (for distributed systems)
- `secret_env_var`: Environment variable containing secret
- `expiry_seconds`: Token lifetime

**Security Best Practices**:
1. Always enable phase tokens in production
2. Use strong secrets (32+ characters)
3. Rotate secrets regularly
4. Use `RS256` for multi-service deployments
5. Set appropriate expiry (2-8 hours typical)

## Complete Example

```yaml
name: "Standard Development Workflow"
version: "1.0"

phases:
  - id: PLAN
    name: "Planning"
    allowed_tools:
      - read_files
      - grep
    forbidden_tools:
      - write_files
      - git_commit
    required_artifacts:
      - type: plan_document
        schema: schemas/plan.json
    gates:
      - id: plan_approval
        type: approval
        blockers:
          - check: plan_has_acceptance_criteria
            severity: blocking
            message: "Plan must have at least one acceptance criterion"
          - check: plan_has_implementation_steps
            severity: blocking
            message: "Plan must have implementation steps"

  - id: TDD
    name: "Test-Driven Development"
    allowed_tools:
      - read_files
      - write_files
      - bash
    forbidden_tools:
      - git_commit
    required_artifacts:
      - type: test_files
        schema: schemas/tests.json
    gates:
      - id: tests_written
        type: validation
        blockers:
          - check: tests_are_failing
            severity: blocking
            message: "Tests must be failing (TDD RED phase)"

  - id: IMPL
    name: "Implementation"
    allowed_tools:
      - read_files
      - write_files
      - bash
    forbidden_tools: []
    required_artifacts:
      - type: implementation
        schema: schemas/implementation.json
    gates:
      - id: tests_passing
        type: validation
        blockers:
          - check: all_tests_pass
            severity: blocking
            message: "All tests must pass"
          - check: coverage_threshold
            severity: warning
            message: "Test coverage below threshold"

  - id: REVIEW
    name: "Code Review"
    allowed_tools:
      - read_files
    forbidden_tools:
      - write_files
      - bash
    required_artifacts:
      - type: review_results
        schema: schemas/review.json
    gates:
      - id: review_approved
        type: approval
        blockers:
          - check: no_blocking_issues
            severity: blocking
            message: "Review found blocking issues"

transitions:
  - from: PLAN
    to: TDD
    gate: plan_approval
    requires_token: true

  - from: TDD
    to: IMPL
    gate: tests_written
    requires_token: true

  - from: IMPL
    to: REVIEW
    gate: tests_passing
    requires_token: true

enforcement:
  mode: strict
  phase_tokens:
    enabled: true
    algorithm: HS256
    secret_env_var: ORCHESTRATOR_JWT_SECRET
    expiry_seconds: 7200
```

## Custom Tools

To add custom tools, modify the tool registry:

```python
# src/orchestrator/tools.py
from .tools import tool_registry

@tool_registry.register("custom_tool")
def my_custom_tool(arg1: str, arg2: int) -> dict:
    """Custom tool implementation"""
    return {"result": "success"}
```

Then use in workflow:

```yaml
allowed_tools:
  - custom_tool
```

## Validation

Validate workflow YAML before deployment:

```python
from src.orchestrator.enforcement import WorkflowEnforcement

# Validate workflow
try:
    enforcement = WorkflowEnforcement("workflow.yaml")
    print("Workflow valid!")
except Exception as e:
    print(f"Validation failed: {e}")
```

## Best Practices

### 1. Start Strict

Begin with strict enforcement mode:

```yaml
enforcement:
  mode: strict
```

This catches issues early. Relax only if needed.

### 2. Minimal Tool Permissions

Grant only necessary tools per phase:

```yaml
# Good: Minimal permissions
allowed_tools:
  - read_files

# Avoid: Too permissive
allowed_tools:
  - read_files
  - write_files
  - bash
  - git_commit
```

### 3. Clear Gate Messages

Write helpful blocker messages:

```yaml
# Good: Clear action
message: "Plan must have at least 3 acceptance criteria"

# Avoid: Vague
message: "Invalid plan"
```

### 4. Version Your Workflow

Track workflow changes:

```yaml
name: "Development Workflow"
version: "2.1"
```

### 5. Document Custom Checks

If implementing custom gate checks, document them:

```yaml
gates:
  - id: custom_gate
    type: validation
    blockers:
      - check: custom_security_scan  # See docs/security_scan.md
        severity: blocking
        message: "Security scan failed"
```

## Troubleshooting

### Workflow Fails to Load

**Error**: `WorkflowEnforcement failed to initialize`

**Solutions**:
1. Check YAML syntax: `yamllint workflow.yaml`
2. Verify all schema files exist
3. Check file permissions
4. Validate against JSON Schema

### Tool Permission Denied

**Error**: `Tool 'write_files' not allowed in phase 'PLAN'`

**Solutions**:
1. Check phase `allowed_tools`
2. Verify not in `forbidden_tools`
3. Consider if tool needed in this phase
4. Transition to appropriate phase first

### Gate Blocking Transition

**Error**: `Transition blocked: Plan must have acceptance criteria`

**Solutions**:
1. Check required artifact structure
2. Validate against schema
3. Review gate blocker conditions
4. Fix artifacts and retry

### Invalid Phase Token

**Error**: `Invalid or expired phase token`

**Solutions**:
1. Check `ORCHESTRATOR_JWT_SECRET` set
2. Verify token not expired
3. Ensure using latest token from transition
4. Claim new task if needed

## See Also

- [Agent SDK Guide](AGENT_SDK_GUIDE.md)
- [Deployment Guide](DEPLOYMENT_GUIDE.md)
- [API Documentation](http://localhost:8000/docs)
