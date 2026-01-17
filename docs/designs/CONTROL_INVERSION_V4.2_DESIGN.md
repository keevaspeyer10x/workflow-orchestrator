# Control Inversion V4.2 Design Specification

**Issue:** #102
**Status:** Draft
**Authors:** Claude Opus 4.5 + Multi-Model Consensus (GPT-5.2, Grok 4.1, DeepSeek V3.2)
**Created:** 2026-01-17

## Executive Summary

V4.2 extends the Control Inversion architecture with five production-ready features:
1. **Chat Mode** - Interactive REPL with workflow awareness
2. **API Runner** - Alternative to subprocess for API-based LLM execution
3. **Advanced Gates** - External reviews, human approval, coverage checks
4. **Token Budgets** - Hierarchical usage tracking and enforcement
5. **Tool Security** - Capability-based allow/deny policies

This design is informed by:
- Multi-model consensus (4 frontier models)
- Production patterns from Temporal, GitHub Actions, Factory.ai, LiteLLM
- Web research on LLM security and orchestration best practices

---

## 1. Chat Mode (`orchestrator chat`)

### 1.1 Design Philosophy

**Key Insight (Multi-Model Consensus):**
> "The chat mode should be a REPL as UI over a state machine, not the orchestrator itself."

Chat mode provides an interactive interface where user/LLM messages become events in the workflow's event log, enabling:
- Full auditability and replay
- Crash recovery and session resumption
- Workflow-aware commands alongside natural language

### 1.2 Architecture

```
┌─────────────────────────────────────────────────────────┐
│ CLI / Chat REPL                                         │
├─────────────────────────────────────────────────────────┤
│ Message Router                                          │
│  ├─ Meta-commands (/status, /approve, /undo)           │
│  └─ LLM messages → Event Store                          │
├─────────────────────────────────────────────────────────┤
│ Conversation State (Event-Sourced)                      │
│  ├─ Message history                                     │
│  ├─ Checkpoints (periodic snapshots)                    │
│  └─ Workflow context                                    │
├─────────────────────────────────────────────────────────┤
│ LLM Runner (API or Subprocess)                          │
└─────────────────────────────────────────────────────────┘
```

### 1.3 Event Types

```python
class ChatEventType(Enum):
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_CALL_REQUESTED = "tool_call_requested"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    CHECKPOINT_CREATED = "checkpoint_created"
    WORKFLOW_ADVANCED = "workflow_advanced"
    GATE_TRIGGERED = "gate_triggered"
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
```

### 1.4 Meta-Commands

| Command | Description |
|---------|-------------|
| `/status` | Show current workflow state and phase |
| `/approve [gate_id]` | Approve a pending gate |
| `/checkpoint [label]` | Create a named checkpoint |
| `/restore [checkpoint_id]` | Restore to a checkpoint |
| `/undo` | Undo last action (if reversible) |
| `/budget` | Show token usage and remaining budget |
| `/tools` | List available tools and their status |
| `/workflow` | Show workflow definition |
| `/exit` | End chat session |

### 1.5 Context Management

**Problem:** LLM context windows have limits; long sessions exceed them.

**Solution (Consensus Pattern):** Sliding window + summarization
1. Keep last N messages in full
2. Summarize older messages periodically
3. Maintain "pinned" messages (system prompt, key decisions)

```python
class ContextManager:
    def __init__(self, max_tokens: int = 100_000):
        self.max_tokens = max_tokens
        self.full_window_size = 20  # Keep last 20 messages in full
        self.summary_threshold = 0.7  # Summarize at 70% capacity

    def prepare_context(self, messages: list[Message]) -> list[Message]:
        token_count = self._count_tokens(messages)

        if token_count > self.max_tokens * self.summary_threshold:
            # Summarize older messages
            old_messages = messages[:-self.full_window_size]
            summary = self._summarize(old_messages)
            return [summary] + messages[-self.full_window_size:]

        return messages
```

### 1.6 Plan → Propose → Execute Loop

**Pattern (from GPT-5.2):**
1. **Plan:** LLM analyzes task and proposes actions
2. **Propose:** Show proposed actions to user (or auto-gate based on risk)
3. **Execute:** Run approved actions, gate risky ones

```python
class ActionRisk(Enum):
    LOW = "low"       # Auto-execute (read files, run tests)
    MEDIUM = "medium" # Confirm before execute
    HIGH = "high"     # Require explicit approval

def classify_action_risk(tool_call: ToolCall) -> ActionRisk:
    if tool_call.name in ["read_file", "list_files", "run_tests"]:
        return ActionRisk.LOW
    elif tool_call.name in ["write_file", "edit_file"]:
        return ActionRisk.MEDIUM
    elif tool_call.name in ["bash", "delete_file", "git_push"]:
        return ActionRisk.HIGH
```

---

## 2. API Runner (`ClaudeAPIRunner`)

### 2.1 When to Use Each Runner

| Criteria | API Runner | Subprocess Runner |
|----------|------------|-------------------|
| Production scale | ✅ | ❌ |
| Managed retries | ✅ | Manual |
| Air-gapped environments | ❌ | ✅ |
| No API costs | ❌ | ✅ |
| Low latency | ❌ | ✅ |
| Multi-tenant | ✅ | ❌ |

### 2.2 Unified Interface

```python
class AgentRunner(ABC):
    """Unified interface for all runners."""

    @abstractmethod
    def invoke(self, phase_input: PhaseInput) -> PhaseOutput:
        """Synchronous execution."""
        pass

    @abstractmethod
    async def stream(self, phase_input: PhaseInput) -> AsyncIterator[StreamChunk]:
        """Streaming execution."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if runner is available."""
        pass
```

### 2.3 API Runner Implementation

```python
class ClaudeAPIRunner(AgentRunner):
    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_retries: int = 3,
        timeout: int = 300,
        circuit_breaker_threshold: int = 5,
    ):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout
        self.circuit_breaker = CircuitBreaker(threshold=circuit_breaker_threshold)

    def invoke(self, phase_input: PhaseInput) -> PhaseOutput:
        if not self.circuit_breaker.allow_request():
            raise RunnerUnavailable("Circuit breaker open")

        for attempt in range(self.max_retries):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    messages=self._build_messages(phase_input),
                    timeout=self.timeout,
                )
                self.circuit_breaker.record_success()
                return self._parse_response(response, phase_input)

            except anthropic.RateLimitError:
                wait_time = (2 ** attempt) + random.uniform(0, 1)  # Exponential backoff + jitter
                time.sleep(wait_time)

            except anthropic.APIError as e:
                self.circuit_breaker.record_failure()
                if attempt == self.max_retries - 1:
                    raise

        raise RunnerError("Max retries exceeded")
```

### 2.4 Hybrid Fallback

```python
class HybridRunner(AgentRunner):
    """Try API first, fall back to subprocess on failure."""

    def __init__(self, api_runner: ClaudeAPIRunner, subprocess_runner: ClaudeCodeRunner):
        self.api_runner = api_runner
        self.subprocess_runner = subprocess_runner

    def invoke(self, phase_input: PhaseInput) -> PhaseOutput:
        try:
            if self.api_runner.health_check():
                return self.api_runner.invoke(phase_input)
        except RunnerUnavailable:
            pass

        return self.subprocess_runner.invoke(phase_input)
```

---

## 3. Advanced Gate Types

### 3.1 Gate Architecture

```python
class Gate(ABC):
    """Base class for all gates."""

    id: str
    name: str
    timeout: int = 3600  # Default 1 hour

    @abstractmethod
    async def check(self, context: GateContext) -> GateResult:
        """Check if gate passes. May be async (e.g., waiting for approval)."""
        pass

    def to_audit_log(self, result: GateResult) -> dict:
        """Produce audit log entry."""
        return {
            "gate_id": self.id,
            "gate_type": self.__class__.__name__,
            "timestamp": datetime.utcnow().isoformat(),
            "result": result.status.value,
            "reason": result.reason,
            "metadata": result.metadata,
        }
```

### 3.2 External Reviews Gate

**Pattern:** Call CI/security APIs with circuit breaker; retry on 5xx.

```python
class ExternalReviewGate(Gate):
    """Gate that calls external review services."""

    def __init__(
        self,
        review_url: str,
        required_reviews: int = 1,
        timeout: int = 300,
    ):
        self.review_url = review_url
        self.required_reviews = required_reviews
        self.timeout = timeout
        self.circuit_breaker = CircuitBreaker(threshold=3)

    async def check(self, context: GateContext) -> GateResult:
        if not self.circuit_breaker.allow_request():
            return GateResult(
                status=GateStatus.FAILED,
                reason="External review service unavailable (circuit open)"
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.review_url,
                    json={"diff": context.diff, "workflow_id": context.workflow_id}
                )

                if response.status_code >= 500:
                    self.circuit_breaker.record_failure()
                    return GateResult(status=GateStatus.RETRY, reason="Server error")

                self.circuit_breaker.record_success()
                data = response.json()

                if data["approved_count"] >= self.required_reviews:
                    return GateResult(status=GateStatus.PASSED)
                else:
                    return GateResult(
                        status=GateStatus.FAILED,
                        reason=f"Need {self.required_reviews} reviews, got {data['approved_count']}"
                    )

        except httpx.TimeoutException:
            return GateResult(status=GateStatus.RETRY, reason="Request timeout")
```

### 3.3 Human Approval Gate

**Pattern (GitHub Actions):** Webhook/polling with timeout + escalation; audit trail.

```python
class HumanApprovalGate(Gate):
    """Gate requiring human approval."""

    def __init__(
        self,
        required_approvers: list[str],
        timeout: int = 86400,  # 24 hours
        escalation_after: int = 3600,  # 1 hour
        escalation_channel: str | None = None,
    ):
        self.required_approvers = required_approvers
        self.timeout = timeout
        self.escalation_after = escalation_after
        self.escalation_channel = escalation_channel

    async def check(self, context: GateContext) -> GateResult:
        # Create approval request
        request_id = await self._create_approval_request(context)

        # Notify approvers
        await self._notify_approvers(request_id)

        start_time = time.time()
        escalated = False

        while time.time() - start_time < self.timeout:
            # Check for approval
            status = await self._check_approval_status(request_id)

            if status.approved:
                return GateResult(
                    status=GateStatus.PASSED,
                    metadata={
                        "approved_by": status.approved_by,
                        "approved_at": status.approved_at.isoformat(),
                    }
                )

            if status.rejected:
                return GateResult(
                    status=GateStatus.FAILED,
                    reason=f"Rejected by {status.rejected_by}: {status.rejection_reason}",
                )

            # Escalation
            if not escalated and time.time() - start_time > self.escalation_after:
                await self._escalate(request_id)
                escalated = True

            await asyncio.sleep(30)  # Poll every 30 seconds

        return GateResult(
            status=GateStatus.FAILED,
            reason=f"Approval timeout after {self.timeout}s"
        )
```

### 3.4 Coverage Gate

**Pattern:** Deterministic artifact predicate evaluation.

```python
class MinCoverageGate(Gate):
    """Gate requiring minimum code coverage."""

    def __init__(self, min_coverage: float = 80.0, coverage_file: str = "coverage.json"):
        self.min_coverage = min_coverage
        self.coverage_file = coverage_file

    async def check(self, context: GateContext) -> GateResult:
        coverage_path = context.working_dir / self.coverage_file

        if not coverage_path.exists():
            return GateResult(
                status=GateStatus.FAILED,
                reason=f"Coverage file not found: {self.coverage_file}"
            )

        data = json.loads(coverage_path.read_text())
        actual_coverage = data.get("totals", {}).get("percent_covered", 0)

        if actual_coverage >= self.min_coverage:
            return GateResult(
                status=GateStatus.PASSED,
                metadata={"coverage": actual_coverage}
            )
        else:
            return GateResult(
                status=GateStatus.FAILED,
                reason=f"Coverage {actual_coverage:.1f}% < required {self.min_coverage}%"
            )
```

### 3.5 Budget Gate

```python
class BudgetGate(Gate):
    """Gate that blocks when budget exceeded."""

    def __init__(self, budget_tracker: BudgetTracker):
        self.budget_tracker = budget_tracker

    async def check(self, context: GateContext) -> GateResult:
        status = self.budget_tracker.get_status(context.workflow_id)

        if status.exceeded:
            return GateResult(
                status=GateStatus.FAILED,
                reason=f"Budget exceeded: {status.used}/{status.limit} tokens"
            )

        if status.warning:
            # Log warning but allow
            logger.warning(f"Budget warning: {status.percent_used:.0f}% used")

        return GateResult(status=GateStatus.PASSED)
```

---

## 4. Token Budget Tracking

### 4.1 Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Token Budget Hierarchy                                  │
├─────────────────────────────────────────────────────────┤
│ Organization Budget                                     │
│  └─ Team Budget                                         │
│      └─ User Budget                                     │
│          └─ Workflow Budget                             │
│              └─ Phase Budget                            │
│                  └─ Step Budget                         │
└─────────────────────────────────────────────────────────┘
```

### 4.2 Core Implementation

```python
from dataclasses import dataclass, field
from enum import Enum
import tiktoken

class BudgetDecision(Enum):
    OK = "ok"
    WARNING = "warning"
    BLOCKED = "blocked"
    EMERGENCY_STOP = "emergency_stop"

@dataclass
class TokenBudget:
    """Token budget with soft/hard limits."""

    limit: int
    used: int = 0
    soft_threshold: float = 0.8   # Warning at 80%
    hard_threshold: float = 1.0   # Block at 100%
    emergency_threshold: float = 1.2  # Emergency stop at 120%

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def percent_used(self) -> float:
        return (self.used / self.limit) * 100 if self.limit > 0 else 0

    def check(self, requested: int = 0) -> BudgetDecision:
        projected = self.used + requested
        ratio = projected / self.limit if self.limit > 0 else float('inf')

        if ratio >= self.emergency_threshold:
            return BudgetDecision.EMERGENCY_STOP
        elif ratio >= self.hard_threshold:
            return BudgetDecision.BLOCKED
        elif ratio >= self.soft_threshold:
            return BudgetDecision.WARNING
        return BudgetDecision.OK

    def consume(self, tokens: int) -> None:
        self.used += tokens

@dataclass
class BudgetTracker:
    """Tracks token usage across workflow hierarchy."""

    workflow_budgets: dict[str, TokenBudget] = field(default_factory=dict)
    phase_budgets: dict[str, TokenBudget] = field(default_factory=dict)
    encoder: tiktoken.Encoding = field(default_factory=lambda: tiktoken.get_encoding("cl100k_base"))

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.encoder.encode(text))

    def pre_check(self, workflow_id: str, phase_id: str, estimated_tokens: int) -> BudgetDecision:
        """Pre-flight check before LLM call."""
        workflow_budget = self.workflow_budgets.get(workflow_id)
        phase_budget = self.phase_budgets.get(f"{workflow_id}:{phase_id}")

        decisions = []
        if workflow_budget:
            decisions.append(workflow_budget.check(estimated_tokens))
        if phase_budget:
            decisions.append(phase_budget.check(estimated_tokens))

        # Return worst decision
        if BudgetDecision.EMERGENCY_STOP in decisions:
            return BudgetDecision.EMERGENCY_STOP
        if BudgetDecision.BLOCKED in decisions:
            return BudgetDecision.BLOCKED
        if BudgetDecision.WARNING in decisions:
            return BudgetDecision.WARNING
        return BudgetDecision.OK

    def record_usage(
        self,
        workflow_id: str,
        phase_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Record actual token usage after LLM call."""
        total = input_tokens + output_tokens

        if workflow_id in self.workflow_budgets:
            self.workflow_budgets[workflow_id].consume(total)

        key = f"{workflow_id}:{phase_id}"
        if key in self.phase_budgets:
            self.phase_budgets[key].consume(total)

        # Persist for billing/replay
        self._persist_usage(workflow_id, phase_id, input_tokens, output_tokens)
```

### 4.3 Integration with Executor

```python
class WorkflowExecutor:
    def __init__(self, ..., budget_tracker: BudgetTracker | None = None):
        self.budget_tracker = budget_tracker

    def _execute_phase(self, phase: PhaseSpec, state: WorkflowState) -> bool:
        # Pre-check budget
        if self.budget_tracker:
            estimated = self._estimate_tokens(phase)
            decision = self.budget_tracker.pre_check(
                state.workflow_id, phase.id, estimated
            )

            if decision == BudgetDecision.BLOCKED:
                logger.error(f"Budget exceeded for phase {phase.id}")
                return False
            elif decision == BudgetDecision.WARNING:
                logger.warning(f"Approaching budget limit for phase {phase.id}")

        # Execute phase...
        output = self.runner.run_phase(phase_input)

        # Record actual usage
        if self.budget_tracker and hasattr(output, 'token_usage'):
            self.budget_tracker.record_usage(
                state.workflow_id,
                phase.id,
                output.token_usage.input,
                output.token_usage.output,
            )

        return output.success
```

---

## 5. Tool Allow/Deny Lists

### 5.1 Security Model

**Principle (Factory.ai):** "Treat LLMs as powerful but untrusted components."

**Key Rules:**
1. Default-deny posture
2. Capability-based permissions (not just tool names)
3. Hierarchical policies (org → project → user)
4. Deny takes precedence
5. Audit everything

### 5.2 Capability Model

```python
@dataclass
class ToolCapability:
    """Capability-based tool permission."""

    namespace: str  # e.g., "fs", "net", "bash"
    action: str     # e.g., "read", "write", "run"
    pattern: str    # Glob pattern for allowed targets

    @classmethod
    def parse(cls, spec: str) -> "ToolCapability":
        """Parse spec like 'fs.read:**/*.py'"""
        parts = spec.split(":", 1)
        ns_action = parts[0].split(".")
        pattern = parts[1] if len(parts) > 1 else "*"
        return cls(
            namespace=ns_action[0],
            action=ns_action[1] if len(ns_action) > 1 else "*",
            pattern=pattern,
        )

    def matches(self, tool_call: ToolCall) -> bool:
        """Check if this capability allows the tool call."""
        # Map tool names to capabilities
        tool_capability = self._tool_to_capability(tool_call)

        if self.namespace != "*" and self.namespace != tool_capability.namespace:
            return False
        if self.action != "*" and self.action != tool_capability.action:
            return False

        return fnmatch.fnmatch(tool_call.target, self.pattern)
```

### 5.3 Policy Engine

```python
@dataclass
class ToolPolicy:
    """Tool policy with allow/deny rules."""

    default: Literal["allow", "deny"] = "deny"
    allow: list[ToolCapability] = field(default_factory=list)
    deny: list[ToolCapability] = field(default_factory=list)

    def check(self, tool_call: ToolCall) -> PolicyDecision:
        """Check if tool call is allowed."""
        # Check deny list first (deny takes precedence)
        for cap in self.deny:
            if cap.matches(tool_call):
                return PolicyDecision(
                    allowed=False,
                    reason=f"Denied by rule: {cap}",
                    matched_rule=cap,
                )

        # Check allow list
        for cap in self.allow:
            if cap.matches(tool_call):
                return PolicyDecision(
                    allowed=True,
                    reason=f"Allowed by rule: {cap}",
                    matched_rule=cap,
                )

        # Default policy
        allowed = self.default == "allow"
        return PolicyDecision(
            allowed=allowed,
            reason=f"Default policy: {self.default}",
        )

class HierarchicalPolicyEngine:
    """Policy engine with org → project → user hierarchy."""

    def __init__(
        self,
        org_policy: ToolPolicy,
        project_policy: ToolPolicy | None = None,
        user_policy: ToolPolicy | None = None,
    ):
        self.org_policy = org_policy
        self.project_policy = project_policy
        self.user_policy = user_policy

    def check(self, tool_call: ToolCall) -> PolicyDecision:
        """Check tool call against all policy levels."""
        # Org denies cannot be overridden
        org_decision = self.org_policy.check(tool_call)
        if not org_decision.allowed and any(
            cap.matches(tool_call) for cap in self.org_policy.deny
        ):
            return org_decision

        # Check project policy
        if self.project_policy:
            proj_decision = self.project_policy.check(tool_call)
            if not proj_decision.allowed:
                return proj_decision

        # Check user policy (most restrictive)
        if self.user_policy:
            user_decision = self.user_policy.check(tool_call)
            if not user_decision.allowed:
                return user_decision

        return org_decision
```

### 5.4 YAML Configuration

```yaml
# workflow.yaml
tool_policy:
  default: deny

  allow:
    # File system
    - "fs.read:**/*.py"
    - "fs.read:**/*.md"
    - "fs.read:**/*.yaml"
    - "fs.write:src/**"
    - "fs.write:tests/**"

    # Commands
    - "bash.run:pytest*"
    - "bash.run:python -m pytest*"
    - "bash.run:git status"
    - "bash.run:git diff*"
    - "bash.run:git log*"

    # Network (restricted)
    - "net.http:api.github.com/*"
    - "net.http:pypi.org/*"

  deny:
    # Dangerous commands (never allowed)
    - "bash.run:rm -rf*"
    - "bash.run:sudo*"
    - "bash.run:chmod 777*"
    - "bash.run:curl*|sh"
    - "bash.run:wget*|sh"

    # Sensitive paths
    - "fs.read:**/.env*"
    - "fs.read:**/*secret*"
    - "fs.read:**/*credential*"
    - "fs.write:**/.git/**"

    # Network restrictions
    - "net.http:*sensitive*"
    - "net.http:localhost*"
    - "net.http:127.0.0.1*"
```

### 5.5 Audit Logging

```python
@dataclass
class ToolAuditEntry:
    """Audit log entry for tool execution."""

    timestamp: datetime
    workflow_id: str
    phase_id: str
    tool_name: str
    tool_args: dict
    decision: PolicyDecision
    policy_version: str
    output_hash: str | None = None  # Hash of output for verification
    execution_time_ms: int | None = None

    def to_jsonl(self) -> str:
        return json.dumps({
            "timestamp": self.timestamp.isoformat(),
            "workflow_id": self.workflow_id,
            "phase_id": self.phase_id,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "decision": {
                "allowed": self.decision.allowed,
                "reason": self.decision.reason,
            },
            "policy_version": self.policy_version,
            "output_hash": self.output_hash,
            "execution_time_ms": self.execution_time_ms,
        })
```

---

## 6. Implementation Phases

### Phase 1: Foundation (2 weeks)
- [ ] Token budget tracking infrastructure
- [ ] Tool policy engine and YAML parsing
- [ ] Audit logging framework

### Phase 2: Gates (2 weeks)
- [ ] External reviews gate
- [ ] Human approval gate with notification
- [ ] Coverage gate
- [ ] Budget gate

### Phase 3: Runners (1 week)
- [ ] API runner implementation
- [ ] Hybrid fallback runner
- [ ] Circuit breaker pattern

### Phase 4: Chat Mode (2 weeks)
- [ ] Event-sourced conversation state
- [ ] Meta-command router
- [ ] Context management (sliding window + summarization)
- [ ] Checkpoint/restore functionality

### Phase 5: Integration (1 week)
- [ ] CLI integration (`orchestrator chat`)
- [ ] Documentation
- [ ] Testing and validation

---

## 7. Success Criteria

1. **Chat Mode:** Interactive REPL with `/status`, `/approve`, `/checkpoint` commands working
2. **API Runner:** Drop-in replacement for subprocess runner with circuit breaker
3. **Gates:** All new gate types produce deterministic results with audit logs
4. **Budgets:** Token usage tracked and enforced at workflow and phase levels
5. **Security:** Tool policies prevent execution of denied commands

---

## 8. References

### Multi-Model Consensus
- Claude Opus 4.5, GPT-5.2, Grok 4.1, DeepSeek V3.2 (January 2026)

### Production Patterns
- [Temporal Best Practices](https://docs.temporal.io/best-practices)
- [Factory LLM Safety](https://docs.factory.ai/enterprise/llm-safety-and-agent-controls)
- [LiteLLM Budgets](https://docs.litellm.ai/docs/proxy/users)
- [GitHub Environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
- [Portkey Budget Limits](https://portkey.ai/blog/budget-limits-and-alerts-in-llm-apps/)
- [Simon Willison: Prompt Injection Design Patterns](https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/)
