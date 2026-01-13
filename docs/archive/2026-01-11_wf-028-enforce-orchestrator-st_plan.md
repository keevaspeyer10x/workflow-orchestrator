# PRD-007 Implementation Plan

## Overview

Implement a contract-based workflow enforcement system for parallel agents using:
- `agent_workflow.yaml` (declarative contract)
- Orchestrator REST API (validation engine)
- Agent SDK (mandatory client library)
- Cryptographic phase tokens (unforgeable proof)

## Implementation Approach

Follow the 20-day sequential guide in `docs/prd/PRD-007-implementation-guide.md`, building from core infrastructure to full integration.

## Phase 1: Core Infrastructure (Week 1)

### Day 1: Foundation
- Create directory structure (`src/orchestrator/`, `src/agent_sdk/`, `.orchestrator/schemas/`)
- Set up FastAPI server skeleton
- Create WorkflowEnforcement class skeleton
- Add pytest fixtures

### Day 2: YAML Loading & Validation
- Implement `load_agent_workflow()` - parse agent_workflow.yaml
- Add schema validation for workflow structure
- Helper methods: `_get_phase()`, `_get_gate()`, `_find_transition()`
- Tests for YAML loading (valid, invalid, missing)

### Day 3: Phase Token System
- Install PyJWT: `pip install pyjwt`
- Implement `generate_phase_token(task_id, phase)`
- Implement `_verify_phase_token(token, task_id, phase)`
- Environment variable: `ORCHESTRATOR_JWT_SECRET`
- Tests for token generation/verification

### Day 4: Artifact Validation
- Create JSON schemas in `.orchestrator/schemas/`
  - plan.schema.json, scope.schema.json, tests.schema.json
  - test_result.schema.json, implementation.schema.json
  - review.schema.json, completion.schema.json
- Implement `_validate_artifacts(artifacts, required)` using jsonschema
- Tests for artifact validation

### Day 5: Gate Validation
- Implement gate checkers:
  - `_check_plan_has_acceptance_criteria()`
  - `_check_tests_are_failing()`
  - `_check_all_tests_pass()`
  - `_check_no_blocking_issues()`
- Implement `_validate_gate(gate, artifacts)`
- Tests for each gate checker

## Phase 2: API + Tool Enforcement (Week 2)

### Day 6: FastAPI Endpoints - Task Management
- Implement `POST /api/v1/tasks/claim`
- Implement `GET /api/v1/state/snapshot`
- Add authentication middleware (verify phase tokens)
- API tests using httpx.AsyncClient

### Day 7: FastAPI Endpoints - Phase Transitions
- Implement `POST /api/v1/tasks/transition`
- Connect to WorkflowEnforcement.validate_phase_transition()
- Handle transition triggers (spawn review agents)
- Tests for successful/blocked transitions

### Day 8: Tool Enforcement
- Implement `POST /api/v1/tools/execute`
- Implement `get_allowed_tools(phase)` and `is_tool_forbidden(phase, tool)`
- Tool constraint checking (write_files only to test dirs in TDD)
- Tests for allowed/forbidden tool calls

### Day 9: Tool Audit Logging
- Create `.orchestrator/tool_audit.jsonl`
- Log every tool call: `{timestamp, agent_id, phase, tool, args, result}`
- Add log rotation (max 100MB)
- Tests for audit log

### Day 10: Agent SDK - Basic Client
- Create `AgentClient` class in `src/agent_sdk/client.py`
- Implement `__init__(agent_id, orchestrator_url)`
- Implement `claim_task()` and `get_state_snapshot()`
- SDK tests (mock HTTP responses)

## Phase 3: Agent Integration + State (Week 3)

### Day 11: Agent SDK - Phase Transitions
- Implement `request_transition(target_phase, artifacts)`
- Updates `self.phase_token` on success
- Tests for transition success/failure paths

### Day 12: Agent SDK - Tool Execution
- Implement `use_tool(tool_name, **kwargs)`
- Convenience methods: `read_file()`, `write_file()`
- Tests for tool calls (allowed, forbidden)

### Day 13: Inject SDK into Agent Prompts
- Update `spawn_agent()` to inject SDK usage instructions
- Generate workflow contract text from agent_workflow.yaml
- Include initial phase token in prompt
- Manual verification with real agent spawn

### Day 14: Event Bus for Coordination
- Create SQLite database: `.orchestrator/events.db`
- Schema: `{id, timestamp, event_type, task_id, data}`
- Implement `publish_event()` and `subscribe_to_events()` (polling)
- Tests for publish/subscribe

### Day 15: State Snapshots
- Implement state snapshot generation (read workflow state, PRD state)
- Filter by task dependencies
- Add caching (refresh every 5 seconds)
- Tests for snapshot content

## Phase 4: Testing + Documentation (Week 4)

### Day 16: End-to-End Test
- Full workflow test: spawn agent, claim task, PLAN → TDD → IMPL → REVIEW → COMPLETE
- Verify gates enforced at each step
- Verify state updated correctly

### Day 17: Error Handling
- Error handling for all API endpoints
- Proper HTTP status codes (400, 401, 403, 500)
- Clear error messages
- Tests for error cases

### Day 18: Configuration
- Add `.orchestrator/config.yaml`
- Load config on startup
- Allow environment variable overrides

### Day 19: Documentation
- Write "Agent Developer Guide" (SDK usage, workflow phases, tool permissions)
- Write "Workflow YAML Reference" (all fields, schemas, examples)
- Write "API Reference" (endpoints, request/response, error codes)

### Day 20: Integration + Polish
- Run full test suite
- Fix integration issues
- Add logging throughout
- Performance profiling (<100ms tool checks)
- Update ROADMAP.md (mark PRD-007 complete)

## Acceptance Criteria

- [ ] `agent_workflow.yaml` loaded and validated on startup
- [ ] Orchestrator API running at http://localhost:8000
- [ ] Agent SDK pip-installable
- [ ] 100% of phase transitions validated
- [ ] 0 tool calls bypass permission checks
- [ ] All 5 phases enforced (PLAN, TDD, IMPL, REVIEW, COMPLETE)
- [ ] Phase tokens cryptographically secure
- [ ] Tests pass (unit + integration)
- [ ] Documentation complete

## Testing Strategy

### Unit Tests
- `tests/orchestrator/test_enforcement.py` - Gate validation, artifact checking
- `tests/orchestrator/test_api.py` - API endpoint behavior
- `tests/orchestrator/test_phase_tokens.py` - Token generation/verification
- `tests/agent_sdk/test_client.py` - SDK methods

### Integration Tests
- `tests/integration/test_agent_workflow.py` - Full workflow end-to-end

### Manual Testing
- Start orchestrator, spawn agent with SDK
- Verify tool blocking in wrong phases
- Verify successful transitions through all phases
- Verify reviews auto-spawn
- Verify state correctly updated

## Dependencies

To be installed as needed:
- fastapi - REST API framework
- uvicorn - ASGI server for FastAPI
- pyjwt - JWT token generation/verification
- jsonschema - Artifact schema validation
- httpx - Agent SDK HTTP client
- pyyaml - YAML loading (already installed)

## Rollout Strategy

### Phase 1: Soft Launch (Advisory Mode)
- Set `enforcement.mode: permissive` in agent_workflow.yaml
- Agents get warnings, not blocked
- Monitor: gate block rate, tool violation rate

### Phase 2: Staged Rollout
- Enable strict enforcement for 1 test task
- Enable for 5 tasks
- Enable for all tasks

### Phase 3: Full Enforcement
- Set `enforcement.mode: strict`
- All agents MUST use SDK
- Tool violations = immediate rejection

## Key Design Decisions

1. **YAML for Contract** - Declarative, versioned, readable
2. **JWT for Tokens** - Cryptographic proof, standard, widely supported
3. **REST API** - Simple, language-agnostic, testable
4. **SQLite for Events** - No external dependencies, easy to deploy
5. **SDK Mandatory** - Only way to interact, prevents bypass

## Out of Scope

- Visual dashboard (PRD-008)
- A/B testing workflows (PRD-009)
- ML-based gate optimization (PRD-010)
- Distributed orchestrator (PRD-011)
