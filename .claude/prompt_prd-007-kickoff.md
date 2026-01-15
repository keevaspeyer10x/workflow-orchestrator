# PRD-007: Agent Workflow Enforcement System - Implementation

## Context

I need you to implement PRD-007, which adds workflow enforcement for spawned parallel agents. Currently, agents bypass workflow gates (no tests, no reviews, no approvals), leading to quality issues.

## What PRD-007 Does

Creates a **contract-based enforcement system** where:
- `agent_workflow.yaml` defines the workflow contract (PLAN → TDD → IMPL → REVIEW → COMPLETE)
- Orchestrator enforces the contract via REST API + cryptographic JWT tokens
- Agent SDK makes compliance mandatory (agents cannot bypass)
- Tool access is capability-scoped by phase (PLAN can't write code, TDD can only write tests, etc.)

**Key Insight:** YAML provides flexibility, code enforcement makes it unbreakable.

## Documentation Available

All PRD-007 documentation is already written:

1. **agent_workflow.yaml** - The workflow contract (phases, gates, tool permissions, schemas)
2. **docs/prd/PRD-007-agent-workflow-enforcement.md** - Full PRD with architecture, risks, metrics
3. **docs/prd/PRD-007-implementation-guide.md** - **START HERE** - Day-by-day implementation guide (20 days)
4. **ROADMAP.md** - PRD-007 entry with success criteria

## Your Task

Implement PRD-007 following the sequential implementation guide. Use the orchestrator workflow system:

### Step 1: Start the Workflow

```bash
orchestrator start "PRD-007: Agent Workflow Enforcement System"
```

### Step 2: Read the Implementation Guide

The guide breaks PRD-007 into 4 weeks:
- **Week 1:** Core infrastructure (YAML loading, phase tokens, artifact validation)
- **Week 2:** API + tool enforcement (FastAPI endpoints, tool ACLs)
- **Week 3:** Agent integration (SDK, event bus, state snapshots)
- **Week 4:** Testing + documentation

**READ:** `docs/prd/PRD-007-implementation-guide.md` - This is your roadmap.

### Step 3: Follow the Guide

Start with **Day 1: Foundation**:
- Create directory structure (`src/orchestrator/`, `src/agent_sdk/`, `.orchestrator/schemas/`)
- Set up FastAPI server skeleton
- Create `WorkflowEnforcement` class skeleton
- Add pytest fixtures

Each day has specific tasks with checkboxes. Follow them sequentially.

### Step 4: Use the Workflow

As you complete each day's tasks:

```bash
# Mark tasks complete
orchestrator complete <item_id> --notes "What you accomplished"

# Advance phases
orchestrator advance

# Run reviews
orchestrator review all

# Finish workflow
orchestrator finish
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR                             │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Workflow Enforcement Engine (enforcement.py)         │   │
│  │  • Reads agent_workflow.yaml                          │   │
│  │  • Validates phase transitions                        │   │
│  │  • Issues JWT phase tokens                            │   │
│  │  • Enforces tool ACLs                                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Orchestrator REST API (api.py)                       │   │
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
│  │  Agent SDK (client.py)                                │   │
│  │  • claim_task() → get phase token                     │   │
│  │  • request_transition() → validate artifacts          │   │
│  │  • use_tool() → check permissions                     │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

## Key Components to Build

### 1. WorkflowEnforcement (enforcement.py)
```python
class WorkflowEnforcement:
    def __init__(self, workflow_path: Path):
        self.workflow = yaml.safe_load(workflow_path)

    def validate_phase_transition(
        self, task_id, current_phase, target_phase,
        phase_token, artifacts
    ) -> tuple[bool, list[str]]:
        # Verify token, validate artifacts, check gate
        pass

    def get_allowed_tools(self, phase: str) -> list[str]:
        pass

    def generate_phase_token(self, task_id: str, phase: str) -> str:
        # JWT with task_id, phase, allowed_tools, exp
        pass
```

### 2. Orchestrator API (api.py)
```python
from fastapi import FastAPI, HTTPException

app = FastAPI()

@app.post("/api/v1/tasks/claim")
async def claim_task(agent_id: str):
    # Assign task, return phase token
    pass

@app.post("/api/v1/tasks/transition")
async def request_transition(request: TransitionRequest):
    # Validate and transition
    pass

@app.post("/api/v1/tools/execute")
async def execute_tool(request: ToolRequest):
    # Check permissions, execute tool
    pass
```

### 3. Agent SDK (client.py)
```python
class AgentClient:
    def __init__(self, agent_id: str, orchestrator_url: str):
        self.agent_id = agent_id
        self.orchestrator_url = orchestrator_url
        self.phase_token = None

    def claim_task(self) -> Optional[dict]:
        # POST to /api/v1/tasks/claim
        pass

    def request_transition(self, target_phase, artifacts) -> dict:
        # POST to /api/v1/tasks/transition
        pass

    def use_tool(self, tool_name, **kwargs):
        # POST to /api/v1/tools/execute
        pass
```

## Dependencies

Install these as needed:
```bash
pip install fastapi uvicorn pyjwt jsonschema pyyaml httpx
```

## Testing Strategy

Test as you build:

```bash
# Unit tests
pytest tests/orchestrator/test_enforcement.py -v
pytest tests/orchestrator/test_api.py -v
pytest tests/agent_sdk/test_client.py -v

# Integration test (end-to-end)
pytest tests/integration/test_agent_workflow.py -v --slow
```

## Success Criteria

You're done when:
- [ ] `agent_workflow.yaml` loads without errors
- [ ] Orchestrator API running at http://localhost:8000
- [ ] Agent SDK can claim tasks and transition phases
- [ ] Phase tokens are cryptographically validated
- [ ] Tool calls are permission-checked
- [ ] 100% of phase transitions go through orchestrator
- [ ] All tests pass
- [ ] Documentation complete

## Important Notes

1. **Follow the guide sequentially** - Don't skip days. Each builds on the previous.

2. **Test as you go** - Each day has specific tests. Don't accumulate technical debt.

3. **Read agent_workflow.yaml** - It's the source of truth for what to enforce.

4. **Phase tokens are JWTs** - Use PyJWT. Include: task_id, phase, allowed_tools, exp.

5. **Start simple** - Day 1-5 is just loading YAML and generating tokens. Don't overcomplicate.

6. **Use the workflow** - This is a dogfooding opportunity. Use `orchestrator` commands throughout.

## If You Get Stuck

1. Read the full PRD: `docs/prd/PRD-007-agent-workflow-enforcement.md`
2. Check the implementation guide: `docs/prd/PRD-007-implementation-guide.md`
3. Look at `agent_workflow.yaml` - it shows what needs to be enforced
4. Check ROADMAP.md for context on why this matters

## Multi-Model Perspective Available

The previous session consulted 5 AI models (Claude Opus, Gemini 3 Pro, GPT-5.2, Grok 4.1, DeepSeek V3.2) on this architecture. All agreed on:
- Invert control (orchestrator owns state)
- Phase tokens (cryptographic proof)
- SDK mandatory (only way to interact)
- Tool ACLs (capability-scoped by phase)

Their full responses are in the previous session logs if you need architectural guidance.

## Ready to Start?

1. Run: `orchestrator start "PRD-007: Agent Workflow Enforcement System"`
2. Read: `docs/prd/PRD-007-implementation-guide.md`
3. Begin: Day 1 tasks (create directories, FastAPI skeleton, WorkflowEnforcement class)

Let's build a robust workflow enforcement system that makes non-compliance impossible!
