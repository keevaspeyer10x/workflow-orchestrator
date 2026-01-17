# Control Inversion Research: Industry Patterns

## Executive Summary

Researched how leading agent orchestration frameworks (LangGraph, CrewAI, Microsoft Agent Framework, OpenAI Agents SDK, Temporal) handle control flow, workflow enforcement, and the "agent must complete workflow" requirement.

**Key Finding**: The industry has converged on a clear pattern - **deterministic orchestration backbone with autonomous execution islands**. The orchestrator DRIVES the workflow; agents EXECUTE within phases.

## Framework Analysis

### 1. LangGraph (LangChain)

**Architecture**: Graph-based state machine with explicit checkpointing

**Control Model**:
- Graph structure defines allowed transitions (deterministic backbone)
- Nodes are agent execution points (autonomous islands)
- Edges can be static or conditional
- State is persisted after every step

**Key Mechanisms**:
```python
# Interrupt function - pauses execution
interrupt(value)  # Persists state, returns control

# Resume with Command
graph.invoke(Command(resume="user input"), thread)
```

**Enforcement**:
- Agent cannot transition between nodes without graph allowing it
- Checkpointing ensures no state loss
- `interrupt_before` and `interrupt_after` for mandatory human gates
- Thread status tracks interrupted vs running vs completed

**Source**: [LangGraph Human-in-the-Loop Docs](https://langchain-ai.github.io/langgraphjs/concepts/human_in_the_loop/)

### 2. CrewAI Flows

**Architecture**: Dual approach - Crews (autonomous) + Flows (deterministic)

**Control Model**:
- **Flows**: Deterministic, event-driven orchestration
- **Crews**: Autonomous collaboration within flow steps
- "Flows give you step-level visibility, testing, and governance"

**Key Insight**:
> "You choose where autonomy is applied and where execution stays deterministic."

**Enforcement**:
- Flow steps execute in defined order
- Conditional logic for branching
- State management between steps
- 12M+ executions/day in production

**Source**: [CrewAI Flows](https://www.crewai.com/crewai-flows)

### 3. Microsoft Agent Framework (AutoGen + Semantic Kernel)

**Architecture**: Workflow abstraction with data-flow routing

**Control Model**:
- Workflows are data-flow based (messages routed through edges)
- Executors activated by edges
- Support for concurrent execution
- Group chat, debate, reflection patterns

**Key Features**:
- Fine-grained workflow control
- Robust state management
- Human-in-the-loop controls
- Enterprise governance (role-based access, auditability)

**Enforcement**:
- Workflow defines execution paths
- Agents cannot bypass workflow structure
- Persistent state for long-running scenarios

**Source**: [Microsoft Agent Framework Overview](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview)

### 4. OpenAI Agents SDK

**Architecture**: Lightweight with handoffs and guardrails

**Control Model**:
- Agents with instructions and tools
- Handoffs for delegation (one-way transfer)
- Guardrails for validation
- Sessions for conversation history

**Key Mechanisms**:
```python
# Handoff - transfers to another agent
handoff(agent_b)  # Immediate transfer with state

# Guardrails - validation
@guardrail
def check_input(input): ...
```

**Enforcement**:
- Guardrails can stop generation
- Handoffs enforce agent transitions
- Simpler model, less explicit orchestration

**Source**: [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)

### 5. Temporal (Durable Execution)

**Architecture**: Workflow-as-code with guaranteed completion

**Control Model**:
- **Workflows**: Deterministic orchestration (survives crashes)
- **Activities**: Non-deterministic work (LLM calls, tools)
- Full execution history persisted
- Replay for recovery

**Key Guarantee**:
> "Durable execution guarantees that your code runs to completion no matter what."

**Enforcement**:
- Workflow code MUST be deterministic
- Same input = same decision sequence
- Activities can fail/retry, workflow continues
- State never lost (99.999% uptime case studies)

**Source**: [Temporal Durable Execution](https://temporal.io/how-it-works)

## Common Patterns

### Pattern 1: Deterministic Backbone + Autonomous Islands

```
┌─────────────────────────────────────────────────────┐
│          DETERMINISTIC BACKBONE                      │
│  (Orchestrator-controlled, cannot be bypassed)       │
│                                                      │
│   ┌─────┐    ┌─────┐    ┌─────┐    ┌─────┐         │
│   │PLAN │───▶│EXEC │───▶│REVIEW──▶│VERIFY│         │
│   └──┬──┘    └──┬──┘    └──┬──┘    └──┬──┘         │
│      │          │          │          │             │
│      ▼          ▼          ▼          ▼             │
│   ┌─────┐    ┌─────┐    ┌─────┐    ┌─────┐         │
│   │ LLM │    │ LLM │    │ LLM │    │ LLM │         │
│   │ has │    │ has │    │ has │    │ has │         │
│   │auton│    │auton│    │auton│    │auton│         │
│   └─────┘    └─────┘    └─────┘    └─────┘         │
│  (Autonomous Islands - can work freely within)      │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### Pattern 2: State Machine with Mandatory Transitions

All frameworks implement some form of:
1. **State persistence** - Cannot lose progress
2. **Defined transitions** - Cannot skip states
3. **Gate validation** - Cannot proceed without passing
4. **Interrupt/resume** - Can pause without losing state

### Pattern 3: Separation of Concerns

| Concern | Owner | Determinism |
|---------|-------|-------------|
| Workflow structure | Orchestrator | Deterministic |
| State transitions | Orchestrator | Deterministic |
| Gate validation | Orchestrator | Deterministic |
| Task execution | Agent/LLM | Non-deterministic |
| Problem solving | Agent/LLM | Non-deterministic |

### Pattern 4: The "Blueprint First" Model

From recent research paper:
> "An expert-defined operational procedure is first codified into a machine-readable Execution Blueprint. A deterministic engine then executes this code-defined blueprint, navigating its states with complete fidelity. The role of the Foundation Model is strategically reframed: it is no longer the central decision-maker but is invoked as a specialized tool at specific nodes."

**Source**: [Blueprint First, Model Second (2025)](https://www.arxiv.org/pdf/2508.02721)

## What Our Orchestrator Is Missing

| Industry Pattern | Our Status |
|------------------|------------|
| Deterministic backbone | ❌ LLM controls flow |
| State machine transitions | ❌ LLM calls `advance` |
| Mandatory gates | ❌ LLM can skip with justification |
| Guaranteed completion | ❌ LLM must remember to `finish` |
| Interrupt/resume | ⚠️ Checkpoints exist but not integrated |
| Durable execution | ❌ No crash recovery guarantee |

## Recommended Architecture

Based on research, the ideal architecture for our orchestrator:

```
┌─────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR ENGINE                       │
│                                                              │
│  1. Load workflow.yaml (defines deterministic structure)     │
│  2. Initialize state machine                                 │
│  3. For each phase:                                          │
│     a. CALL Claude Code with phase prompt + tools            │
│     b. Claude works autonomously within phase               │
│     c. VALIDATE gates (orchestrator checks, not Claude)      │
│     d. CHECKPOINT state                                      │
│     e. ADVANCE to next phase (orchestrator decides)          │
│  4. Complete workflow (guaranteed by engine)                 │
│                                                              │
│  Crash Recovery: Resume from last checkpoint                 │
│  Human Gates: interrupt() → resume with input                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Key Design Decisions Needed

1. **How does orchestrator "call" Claude Code?**
   - MCP tool server?
   - Subprocess with prompt injection?
   - Claude Code extension/hook?

2. **How are phase tools scoped?**
   - Dynamic system prompt per phase?
   - Tool filtering in MCP?
   - Honor system (current approach)?

3. **How is state persisted?**
   - Local JSON (current)
   - SQLite for durability
   - Remote for multi-machine

4. **How are gates validated?**
   - Artifact existence (current, weak)
   - Command execution (current, better)
   - Semantic validation (LLM-based, risky)

## References

- [LangGraph Multi-Agent Orchestration Guide 2025](https://latenode.com/blog/ai-frameworks-technical-infrastructure/langgraph-multi-agent-orchestration/)
- [CrewAI Flows](https://www.crewai.com/crewai-flows)
- [Microsoft Agent Framework Overview](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [Temporal Durable Execution](https://temporal.io/how-it-works)
- [Blueprint First, Model Second (2025)](https://www.arxiv.org/pdf/2508.02721)
- [AI Agent Framework Landscape 2025](https://medium.com/@hieutrantrung.it/the-ai-agent-framework-landscape-in-2025-what-changed-and-what-matters-3cd9b07ef2c3)
