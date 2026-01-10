# PRD-007 Implementation Guide

## Quick Start for Sequential Implementation

This guide breaks down PRD-007 into manageable sequential tasks for a single implementer.

## Week 1: Core Infrastructure

### Day 1: Foundation
- [ ] Create directory structure:
  ```
  src/orchestrator/
    __init__.py
    enforcement.py
    api.py
  src/agent_sdk/
    __init__.py
    client.py
  .orchestrator/
    schemas/
  ```
- [ ] Set up FastAPI server skeleton in `api.py`
- [ ] Create `WorkflowEnforcement` class skeleton in `enforcement.py`
- [ ] Add pytest fixtures for orchestrator testing

### Day 2: YAML Loading & Validation
- [ ] Implement `load_agent_workflow()` - parse agent_workflow.yaml
- [ ] Add schema validation for workflow YAML structure
- [ ] Create helper methods: `_get_phase()`, `_get_gate()`, `_find_transition()`
- [ ] Write tests for YAML loading (valid, invalid, missing fields)

### Day 3: Phase Token System
- [ ] Install PyJWT: `pip install pyjwt`
- [ ] Implement `generate_phase_token(task_id, phase)`
- [ ] Implement `_verify_phase_token(token, task_id, phase)`
- [ ] Add environment variable: `ORCHESTRATOR_JWT_SECRET`
- [ ] Write tests for token generation/verification (valid, expired, tampered)

### Day 4: Artifact Validation
- [ ] Create JSON schemas in `.orchestrator/schemas/`:
  - `plan.schema.json`
  - `scope.schema.json`
  - `tests.schema.json`
  - `test_result.schema.json`
  - `implementation.schema.json`
  - `review.schema.json`
  - `completion.schema.json`
- [ ] Implement `_validate_artifacts(artifacts, required)` using jsonschema
- [ ] Write tests for artifact validation (missing, invalid, valid)

### Day 5: Gate Validation
- [ ] Implement gate checkers:
  - `_check_plan_has_acceptance_criteria()`
  - `_check_tests_are_failing()`
  - `_check_all_tests_pass()`
  - `_check_no_blocking_issues()`
- [ ] Implement `_validate_gate(gate, artifacts)`
- [ ] Write tests for each gate checker

## Week 2: API + Tool Enforcement

### Day 6: FastAPI Endpoints - Task Management
- [ ] Implement `POST /api/v1/tasks/claim`
  - Input: `{agent_id, capabilities}`
  - Output: `{task, phase_token}`
- [ ] Implement `GET /api/v1/state/snapshot`
  - Input: `{phase_token}`
  - Output: `{task_dependencies, completed_tasks, blockers}`
- [ ] Add authentication middleware (verify phase tokens)
- [ ] Write API tests using `httpx.AsyncClient`

### Day 7: FastAPI Endpoints - Phase Transitions
- [ ] Implement `POST /api/v1/tasks/transition`
  - Input: `{current_phase, target_phase, phase_token, artifacts}`
  - Output: `{allowed, new_token?, blockers?}`
- [ ] Connect to `WorkflowEnforcement.validate_phase_transition()`
- [ ] Handle transition triggers (e.g., spawn review agents)
- [ ] Write tests for successful and blocked transitions

### Day 8: Tool Enforcement
- [ ] Implement `POST /api/v1/tools/execute`
  - Input: `{phase_token, tool_name, args}`
  - Output: `{result}` or `403 Forbidden`
- [ ] Implement `get_allowed_tools(phase)` and `is_tool_forbidden(phase, tool)`
- [ ] Add tool constraint checking (e.g., write_files only to test dirs in TDD)
- [ ] Write tests for allowed/forbidden tool calls

### Day 9: Tool Audit Logging
- [ ] Create `.orchestrator/tool_audit.jsonl`
- [ ] Log every tool call: `{timestamp, agent_id, phase, tool, args, result}`
- [ ] Add log rotation (max 100MB)
- [ ] Write tests for audit log creation and format

### Day 10: Agent SDK - Basic Client
- [ ] Create `AgentClient` class in `src/agent_sdk/client.py`
- [ ] Implement `__init__(agent_id, orchestrator_url)`
- [ ] Implement `claim_task()` - calls `/api/v1/tasks/claim`
- [ ] Implement `get_state_snapshot()` - calls `/api/v1/state/snapshot`
- [ ] Write SDK tests (mock HTTP responses)

## Week 3: Agent Integration + State

### Day 11: Agent SDK - Phase Transitions
- [ ] Implement `request_transition(target_phase, artifacts)`
  - Calls `/api/v1/tasks/transition`
  - Updates `self.phase_token` on success
  - Returns result with blockers if failed
- [ ] Write tests for transition success and failure paths

### Day 12: Agent SDK - Tool Execution
- [ ] Implement `use_tool(tool_name, **kwargs)`
  - Calls `/api/v1/tools/execute`
  - Includes phase_token
  - Raises `PermissionError` on 403
- [ ] Add convenience methods: `read_file()`, `write_file()`, etc.
- [ ] Write tests for tool calls (allowed, forbidden)

### Day 13: Inject SDK into Agent Prompts
- [ ] Update `spawn_agent()` to inject SDK usage instructions
- [ ] Generate workflow contract text from agent_workflow.yaml
- [ ] Include initial phase token in prompt
- [ ] Test with real agent spawn (manual verification)

### Day 14: Event Bus for Coordination
- [ ] Create SQLite database: `.orchestrator/events.db`
- [ ] Schema: `{id, timestamp, event_type, task_id, data}`
- [ ] Implement `publish_event(event_type, task_id, data)`
- [ ] Implement `subscribe_to_events(event_types)` (polling)
- [ ] Write tests for publish/subscribe

### Day 15: State Snapshots
- [ ] Implement state snapshot generation:
  - Read `.workflow_state.json`
  - Read `prd_state.json`
  - Filter by task dependencies
- [ ] Add caching (refresh every 5 seconds)
- [ ] Write tests for snapshot content

## Week 4: Testing + Documentation

### Day 16: End-to-End Test
- [ ] Write full workflow test:
  1. Spawn agent (via TmuxAdapter)
  2. Agent uses SDK to claim task
  3. Agent transitions PLAN → TDD → IMPL → REVIEW → COMPLETE
  4. Verify gates enforced at each step
  5. Verify state updated correctly

### Day 17: Error Handling
- [ ] Add error handling for all API endpoints
- [ ] Return proper HTTP status codes (400, 401, 403, 500)
- [ ] Clear error messages for common issues
- [ ] Write tests for error cases

### Day 18: Configuration
- [ ] Add orchestrator config file: `.orchestrator/config.yaml`
  ```yaml
  api:
    host: localhost
    port: 8000
  enforcement:
    mode: strict
  jwt:
    expiry_seconds: 7200
  ```
- [ ] Load config on startup
- [ ] Allow environment variable overrides

### Day 19: Documentation
- [ ] Write "Agent Developer Guide"
  - How to use SDK
  - Workflow phases explained
  - Tool permissions per phase
  - Example agent implementation
- [ ] Write "Workflow YAML Reference"
  - All fields documented
  - Schema specifications
  - Examples for each phase
- [ ] Write "API Reference"
  - All endpoints documented
  - Request/response examples
  - Error codes

### Day 20: Integration + Polish
- [ ] Run full test suite
- [ ] Fix any integration issues
- [ ] Add logging throughout
- [ ] Performance profiling (ensure <100ms tool checks)
- [ ] Update ROADMAP.md (mark PRD-007 complete)

## Testing Strategy

### Unit Tests (pytest)
```bash
# Test structure
tests/orchestrator/
  test_enforcement.py      # Gate validation, artifact checking
  test_api.py              # API endpoint behavior
  test_phase_tokens.py     # Token generation/verification

tests/agent_sdk/
  test_client.py           # SDK methods

# Run tests
pytest tests/orchestrator/ -v
pytest tests/agent_sdk/ -v
```

### Integration Tests
```bash
# Full workflow tests
pytest tests/integration/test_agent_workflow.py -v --slow
```

### Manual Testing Checklist
- [ ] Start orchestrator: `python -m src.orchestrator.api`
- [ ] Spawn agent with SDK
- [ ] Agent claims task successfully
- [ ] Agent blocked trying to write code in PLAN phase
- [ ] Agent transitions PLAN → TDD successfully
- [ ] Agent writes test, transitions TDD → IMPL
- [ ] Agent writes code, tests pass, transitions IMPL → REVIEW
- [ ] Reviews auto-spawn
- [ ] Agent blocked until reviews complete
- [ ] Agent transitions REVIEW → COMPLETE
- [ ] State correctly updated

## Common Pitfalls

### 1. Token Expiry
**Issue:** Agents timeout waiting for human approval, token expires.

**Solution:** Add token refresh endpoint: `POST /api/v1/tokens/refresh`

### 2. Circular Imports
**Issue:** `enforcement.py` imports `api.py`, `api.py` imports `enforcement.py`

**Solution:** Use lazy imports or dependency injection

### 3. SQLite Locking
**Issue:** Multiple API requests hit SQLite concurrently, locks occur

**Solution:** Use connection pooling with timeout, or switch to file-based queue

### 4. Tool Constraints Complex
**Issue:** `tool_constraints` in YAML is hard to validate (glob patterns)

**Solution:** Start simple (just allowed/forbidden), add constraints in v2

### 5. Agent Doesn't Use SDK
**Issue:** Agent tries to directly write files

**Solution:** Make sure `spawn_agent()` makes SDK usage crystal clear in prompt

## Rollout Plan

### Phase 1: Soft Launch (Advisory Mode)
- Set `enforcement.mode: permissive` in agent_workflow.yaml
- Agents get warnings for violations, but not blocked
- Monitor metrics: gate block rate, tool violation rate

### Phase 2: Staged Rollout
- Enable strict enforcement for 1 test task
- Monitor for issues
- Enable for 5 tasks
- Enable for all tasks

### Phase 3: Full Enforcement
- Set `enforcement.mode: strict`
- All agents MUST use SDK
- Tool violations = immediate rejection

## Success Criteria

- [ ] `agent_workflow.yaml` loaded on startup, no validation errors
- [ ] Orchestrator API running at http://localhost:8000
- [ ] Agent SDK pip-installable: `pip install -e src/agent_sdk`
- [ ] 100% of phase transitions validated
- [ ] 0 tool calls bypass permission checks
- [ ] All tests pass (unit + integration)
- [ ] Documentation complete and published

## Next Steps After PRD-007

Once enforcement is working:
- **PRD-008:** Visual dashboard to see agent workflow states
- **PRD-009:** Experiment with different workflow definitions
- **PRD-010:** ML-based optimization of gates (which gates block most?)

## Questions? Issues?

- Check `docs/prd/PRD-007-agent-workflow-enforcement.md` for full details
- Review `agent_workflow.yaml` for contract definition
- Look at `/minds` output for multi-model perspectives
