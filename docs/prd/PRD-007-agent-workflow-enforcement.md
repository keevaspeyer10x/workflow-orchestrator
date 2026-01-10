# PRD-007: Agent Workflow Enforcement System

## Problem Statement

Parallel agents currently bypass workflow gates, leading to:
- TDD violations (code without tests)
- Skipped plan approval
- Missing reviews
- No completion verification
- Untracked state changes

**Root Cause:** Agents operate independently with no orchestrator oversight.

## Solution

Implement a **contract-based enforcement system** where:
1. `agent_workflow.yaml` defines the workflow contract
2. Orchestrator enforces the contract via API + cryptographic tokens
3. Agent SDK makes compliance mandatory (non-compliance is impossible)
4. Tool access is capability-scoped by phase

## Dependencies

- PRD-006 (completed): Approval gate infrastructure exists
- Existing orchestrator state machine
- Tmux/subprocess adapters for spawning

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR                             │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         Workflow Enforcement Engine                   │   │
│  │  • Reads agent_workflow.yaml                          │   │
│  │  • Validates phase transitions                        │   │
│  │  • Issues phase tokens (JWT)                          │   │
│  │  • Enforces tool access controls                      │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │             Orchestrator REST API                     │   │
│  │  POST /api/v1/tasks/claim                             │   │
│  │  POST /api/v1/tasks/transition                        │   │
│  │  POST /api/v1/tools/execute                           │   │
│  │  GET  /api/v1/state/snapshot                          │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ HTTPS + JWT
                          │
┌─────────────────────────┴───────────────────────────────────┐
│                     AGENT (via SDK)                          │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Agent SDK                                │   │
│  │  • claim_task() → get phase token                     │   │
│  │  • request_transition() → validate artifacts          │   │
│  │  • use_tool() → check permissions                     │   │
│  │  • get_state_snapshot() → read-only view             │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         Agent Implementation                          │   │
│  │  Uses SDK for ALL orchestrator interactions           │   │
│  │  Cannot bypass - SDK is the only API                  │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### Phase Token Flow

```
1. Agent spawned
   └─> Orchestrator injects: workflow contract + SDK import + initial phase token

2. Agent claims task via SDK
   └─> SDK sends: claim_task(agent_id)
   └─> Orchestrator returns: {task, phase_token for "PLAN"}

3. Agent works in PLAN phase
   └─> Can only use tools allowed in PLAN (enforced by orchestrator)
   └─> Creates plan artifacts

4. Agent requests transition to TDD
   └─> SDK sends: request_transition(target="TDD", artifacts={plan, scope})
   └─> Orchestrator validates:
       - Phase token is valid
       - Artifacts match schema
       - Gate blockers passed
   └─> If valid: returns new phase token for "TDD"
   └─> If invalid: returns blockers

5. Repeat for TDD → IMPL → REVIEW → COMPLETE
```

### Enforcement Mechanisms

#### 1. Phase Tokens (Cryptographic Proof)

```python
# Orchestrator generates JWT
token = jwt.encode(
    {
        "task_id": "task-123",
        "phase": "TDD",
        "allowed_tools": ["read_files", "write_files", "bash"],
        "exp": datetime.utcnow() + timedelta(hours=2)
    },
    secret=os.environ["ORCHESTRATOR_JWT_SECRET"],
    algorithm="HS256"
)
```

Agents must include token in every API call. Invalid/missing token = rejection.

#### 2. Tool Access Control

```python
# Orchestrator checks on EVERY tool call
def can_use_tool(phase: str, tool: str, phase_token: str) -> bool:
    # Verify token
    if not verify_token(phase_token):
        return False

    # Check YAML
    workflow = load_agent_workflow()
    phase_def = workflow["phases"][phase]

    if tool in phase_def["forbidden_tools"]:
        return False

    if tool not in phase_def["allowed_tools"]:
        return False

    return True
```

#### 3. Artifact Validation

```python
# Before allowing phase transition
def validate_artifacts(artifacts: dict, required: list) -> ValidationResult:
    for req in required:
        if req["type"] not in artifacts:
            return ValidationResult(passed=False, error=f"Missing {req['type']}")

        # Validate against JSON schema
        schema = load_schema(req["schema"])
        try:
            jsonschema.validate(artifacts[req["type"]], schema)
        except ValidationError as e:
            return ValidationResult(passed=False, error=str(e))

    return ValidationResult(passed=True)
```

#### 4. Gate Validation

```python
# Check gate blockers from YAML
def check_gate(gate_id: str, artifacts: dict) -> GateResult:
    gate = workflow["gates"][gate_id]

    blockers = []
    for check in gate["blockers"]:
        if check["check"] == "tests_are_failing":
            # Run actual validation
            test_result = artifacts.get("test_run_result", {})
            if test_result.get("failed", 0) == 0:
                blockers.append(check["message"])

        # ... other checks ...

    return GateResult(
        passed=len(blockers) == 0,
        blockers=blockers
    )
```

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)
- Create `src/orchestrator/enforcement.py` - Workflow enforcement engine
- Create `src/orchestrator/api.py` - REST API for agents
- Create `src/agent_sdk/client.py` - Agent SDK
- Load and validate `agent_workflow.yaml` on startup

### Phase 2: Tool Enforcement (Week 1-2)
- Intercept all tool calls through API
- Check phase tokens
- Validate tool permissions
- Log all tool usage to audit trail

### Phase 3: Phase Transitions (Week 2)
- Implement `/api/v1/tasks/transition` endpoint
- Artifact validation against schemas
- Gate checking logic
- Phase token generation/verification

### Phase 4: Agent Integration (Week 2-3)
- Update `spawn_agent()` to inject SDK usage
- Inject workflow contract into prompts
- Generate initial phase tokens
- Test with real agents

### Phase 5: State Coordination (Week 3)
- Implement read-only state snapshots
- Event bus for coordination
- Completion tracking
- PRD state updates

## Success Metrics

### Must-Have (Blocking)
- [ ] 100% of phase transitions validated by orchestrator
- [ ] 0 tool calls bypass permission checks
- [ ] All agents use SDK (enforced - non-SDK calls rejected)
- [ ] Phase tokens cryptographically secure

### Should-Have (Important)
- [ ] <100ms latency for tool permission checks
- [ ] <500ms latency for phase transitions
- [ ] Audit log captures all agent actions
- [ ] State snapshots stay <100KB

### Nice-to-Have (Enhancing)
- [ ] Real-time dashboard of agent activity
- [ ] Automatic gate timeout alerts
- [ ] Gate pass rate >90%

## Risks

### Risk 1: SDK Adoption
**Concern:** Agents might try to bypass SDK

**Mitigation:**
- Make SDK the ONLY way to interact with orchestrator
- No direct file/git access from agents
- All tools proxied through orchestrator API

### Risk 2: Performance Overhead
**Concern:** API calls add latency

**Mitigation:**
- Local SQLite for state (fast)
- In-memory token cache
- Batch tool calls where possible
- Optimize hot paths

### Risk 3: Token Security
**Concern:** Stolen tokens allow bypassing gates

**Mitigation:**
- Short expiry (2 hours)
- Bind tokens to task_id + phase
- Rotate secret regularly
- Audit log for forensics

### Risk 4: YAML Complexity
**Concern:** YAML becomes hard to maintain

**Mitigation:**
- Schema validation on load
- Clear documentation
- Examples for each phase
- Validation tooling

## Testing Strategy

### Unit Tests
- Enforcement engine logic
- Phase token generation/verification
- Artifact schema validation
- Gate checking logic

### Integration Tests
- Full workflow: PLAN → TDD → IMPL → REVIEW → COMPLETE
- Tool enforcement (allowed vs forbidden)
- Phase transition with artifacts
- Error cases (invalid token, missing artifacts, gate blockers)

### End-to-End Tests
- Spawn real agent
- Agent uses SDK to complete workflow
- Verify all gates enforced
- Verify state correctly updated

## Migration Strategy

### For Existing Agents
1. Update spawn prompts to include SDK
2. Provide migration guide
3. Deprecation period (optional bypass mode)
4. Full enforcement (no bypass)

### Rollout Plan
1. Deploy API + enforcement engine
2. Test with synthetic agents
3. Enable for 1 real task
4. Monitor metrics
5. Enable for all tasks

## Open Questions

1. Should we support "advisory" mode for testing? (Answer: Yes, via `enforcement.mode: permissive`)
2. How to handle agent crashes mid-phase? (Answer: Orchestrator resumes from last checkpoint)
3. Should phase tokens be revocable? (Answer: Not in v1, rely on expiry)

## Acceptance Criteria

- [ ] `agent_workflow.yaml` loaded and validated on orchestrator startup
- [ ] Orchestrator API running at `http://localhost:8000/api/v1`
- [ ] Agent SDK pip-installable: `pip install orchestrator-agent-sdk`
- [ ] Phase transitions require valid artifacts
- [ ] Tool calls require valid phase tokens
- [ ] All 5 phases enforced (PLAN, TDD, IMPL, REVIEW, COMPLETE)
- [ ] Tests pass for enforcement engine
- [ ] Documentation: "Agent Development Guide"

## Documentation Deliverables

1. **Agent Developer Guide** - How to use SDK, understand workflow
2. **Workflow YAML Reference** - All fields, schemas, examples
3. **API Reference** - All endpoints, request/response formats
4. **Architecture Diagram** - Component interaction

## Future Enhancements (Out of Scope for PRD-007)

- [ ] PRD-008: Visual workflow dashboard
- [ ] PRD-009: A/B testing different workflows
- [ ] PRD-010: Machine learning for gate optimization
- [ ] PRD-011: Distributed orchestrator (multi-node)
