# Control Inversion V4.2 Implementation Plan

**Issue:** #102
**Status:** Ready for Implementation (All blocking issues resolved)
**Created:** 2026-01-17
**Reviewed By:** Multi-model consensus (Claude Opus 4.5, GPT-5.2, Grok 4.1, DeepSeek V3.2)

## Review Summary

### Second Review (Implementation Plan)

The implementation plan was rated **7.5-9/10** with 4 blocking issues identified and now fixed:

| Issue | Status | Fix |
|-------|--------|-----|
| Sandbox not enforced in execute_secure() | ✅ FIXED | Added `_execute_in_container()` and conditional sandbox enforcement |
| Argument validation incomplete | ✅ FIXED | Added `_validate_arguments()` with full YAML rules enforcement |
| Event store race condition | ✅ FIXED | Uses `BEGIN IMMEDIATE` to acquire write lock before read |
| SQLite FOR UPDATE doesn't exist | ✅ FIXED | Added `DatabaseAdapter` pattern for SQLite/PostgreSQL compatibility |

### First Review (Design Spec)

The initial design spec was rated **7/10** with the following critical gaps:

| Issue | Severity | Consensus |
|-------|----------|-----------|
| No persistence strategy | Critical | 4/4 |
| Tool security broken (shell injection) | Critical | 4/4 |
| Path traversal vulnerability | Critical | 4/4 |
| No authentication for approvals | Critical | 4/4 |
| Wrong token counting (GPT tokenizer for Claude) | High | 4/4 |
| Polling-based gates don't scale | Medium | 4/4 |
| Concurrency/race conditions | High | 4/4 |

This implementation plan reorganizes work to **fix critical issues first**.

---

## Phase 0: Security Hardening (BLOCKING)

**Must complete before ANY other implementation.**

### 0.1 Tool Execution Security

**Problem:** `bash.run:pytest*` pattern matching is bypassable via `pytest; rm -rf /`

**Solution:** Replace glob patterns with argv-based sandboxed execution.

```python
# BEFORE (INSECURE)
class CommandGate:
    cmd: str  # Raw string passed to shell=True

# AFTER (SECURE)
@dataclass
class SecureCommand:
    """Sandboxed command execution."""
    executable: str  # Must be in allowlist
    args: list[str]  # Parsed, validated arguments
    working_dir: Path
    timeout: int = 300
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)

@dataclass
class SandboxConfig:
    """Sandbox configuration."""
    use_container: bool = True  # Docker/Podman
    read_only_rootfs: bool = True
    network_mode: str = "none"  # No network by default
    allowed_paths: list[Path] = field(default_factory=list)
    max_memory_mb: int = 512
    max_cpu_seconds: int = 60

def execute_secure(cmd: SecureCommand, config: ToolSecurityConfig) -> CommandResult:
    """Execute command in sandbox with shell=False."""
    # Validate executable is in allowlist
    if cmd.executable not in config.allowed_executables:
        raise SecurityError(f"Executable not allowed: {cmd.executable}")

    # Validate arguments against per-executable rules
    exe_name = Path(cmd.executable).name
    if exe_name in config.argument_rules:
        rules = config.argument_rules[exe_name]
        _validate_arguments(cmd.args, rules)

    # Validate arguments don't contain shell metacharacters
    for arg in cmd.args:
        if any(c in arg for c in [';', '|', '&', '$', '`', '\n']):
            raise SecurityError(f"Invalid argument: {arg}")

    # ENFORCE SANDBOX if configured
    if cmd.sandbox.use_container:
        return _execute_in_container(cmd)
    else:
        # Direct execution (only for trusted environments)
        result = subprocess.run(
            [cmd.executable] + cmd.args,
            shell=False,  # CRITICAL: Never shell=True
            cwd=cmd.working_dir,
            capture_output=True,
            timeout=cmd.timeout,
        )
        return CommandResult(...)

def _validate_arguments(args: list[str], rules: ArgumentRules) -> None:
    """Validate arguments against per-executable rules."""
    for arg in args:
        # Check denied flags
        if arg in rules.denied_flags:
            raise SecurityError(f"Denied flag: {arg}")
        # Check denied patterns
        for pattern in rules.denied_patterns:
            if re.match(pattern, arg):
                raise SecurityError(f"Argument matches denied pattern: {arg}")
        # If allowed_flags specified, argument must be in list or be a value
        if rules.allowed_flags and arg.startswith('-'):
            if arg not in rules.allowed_flags:
                raise SecurityError(f"Flag not in allowlist: {arg}")
    # Check subcommands (first non-flag argument)
    if rules.allowed_subcommands:
        subcommand = next((a for a in args if not a.startswith('-')), None)
        if subcommand and subcommand not in rules.allowed_subcommands:
            raise SecurityError(f"Subcommand not allowed: {subcommand}")

def _execute_in_container(cmd: SecureCommand) -> CommandResult:
    """Execute command inside container sandbox."""
    sandbox = cmd.sandbox

    # Build container command
    container_cmd = [
        "docker", "run", "--rm",
        "--read-only" if sandbox.read_only_rootfs else "",
        f"--network={sandbox.network_mode}",
        f"--memory={sandbox.max_memory_mb}m",
        f"--cpus={sandbox.max_cpu_seconds / 60}",  # Approximate
    ]

    # Mount allowed paths
    for path in sandbox.allowed_paths:
        container_cmd.extend(["-v", f"{path}:{path}"])

    # Add working directory mount
    container_cmd.extend(["-v", f"{cmd.working_dir}:{cmd.working_dir}", "-w", str(cmd.working_dir)])

    # Add image and command
    container_cmd.extend([
        "sandbox-runner:latest",  # Minimal image with common tools
        cmd.executable, *cmd.args
    ])

    # Filter empty strings
    container_cmd = [c for c in container_cmd if c]

    result = subprocess.run(
        container_cmd,
        shell=False,
        capture_output=True,
        timeout=cmd.timeout,
    )
    return CommandResult(...)
```

**Allowlist approach:**
```yaml
# Executable allowlist (not pattern matching)
tool_security:
  allowed_executables:
    - /usr/bin/python
    - /usr/bin/pytest
    - /usr/bin/git
    - /usr/bin/npm
    - /usr/bin/go

  # Arguments validated per-executable
  argument_rules:
    git:
      allowed_subcommands: [status, diff, log, add, commit]
      denied_flags: [--force, -f, --hard]
    pytest:
      allowed_flags: [-v, -x, --tb=short, -k]
      denied_patterns: []
```

### 0.2 Path Traversal Prevention

**Problem:** `src/../../../etc/passwd` may match `src/**`

**Solution:** Canonicalize all paths and validate containment.

```python
from pathlib import Path
import os

def safe_path(base_dir: Path, user_path: str) -> Path:
    """
    Resolve user path safely within base directory.

    Prevents:
    - Path traversal (../)
    - Symlink escapes
    - Absolute path injection
    """
    # Resolve base directory to absolute, canonical form
    base = base_dir.resolve()

    # Join and resolve user path
    target = (base / user_path).resolve()

    # Verify target is within base
    try:
        target.relative_to(base)
    except ValueError:
        raise SecurityError(f"Path escapes base directory: {user_path}")

    # Check for symlink escapes
    if target.is_symlink():
        real_target = target.resolve()
        try:
            real_target.relative_to(base)
        except ValueError:
            raise SecurityError(f"Symlink escapes base directory: {user_path}")

    return target

def validate_glob_pattern(pattern: str) -> bool:
    """Validate glob pattern doesn't allow traversal."""
    # Deny patterns with ..
    if '..' in pattern:
        return False
    # Deny absolute paths
    if pattern.startswith('/'):
        return False
    # Deny patterns starting with glob that could match parent
    if pattern.startswith('**/..'):
        return False
    return True
```

### 0.3 Authentication for Approvals

**Problem:** No RBAC - anyone can `/approve`.

**Solution:** Signed approvals with identity binding.

```python
from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac

@dataclass
class ApprovalRequest:
    """Request for human approval."""
    id: str
    workflow_id: str
    gate_id: str
    artifact_hash: str  # Hash of what's being approved
    required_approvers: list[str]
    created_at: datetime
    expires_at: datetime

@dataclass
class Approval:
    """Signed approval record."""
    request_id: str
    approved_by: str  # Identity (e.g., GitHub username)
    approved_at: datetime
    artifact_hash: str  # Must match request
    signature: str  # HMAC signature

    @classmethod
    def create(
        cls,
        request: ApprovalRequest,
        approver: str,
        signing_key: bytes,
    ) -> "Approval":
        """Create signed approval."""
        approval = cls(
            request_id=request.id,
            approved_by=approver,
            approved_at=datetime.utcnow(),
            artifact_hash=request.artifact_hash,
            signature="",  # Computed below
        )

        # Sign the approval
        payload = f"{approval.request_id}:{approval.approved_by}:{approval.artifact_hash}"
        approval.signature = hmac.new(
            signing_key,
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        return approval

    def verify(self, signing_key: bytes) -> bool:
        """Verify approval signature."""
        payload = f"{self.request_id}:{self.approved_by}:{self.artifact_hash}"
        expected = hmac.new(
            signing_key,
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(self.signature, expected)

class ApprovalAuthenticator:
    """Authenticate approvers via GitHub/OAuth."""

    async def authenticate(self, token: str) -> str | None:
        """Verify token and return identity."""
        # GitHub token verification
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {token}"}
            )
            if resp.status_code == 200:
                return resp.json()["login"]
        return None

    def is_authorized(self, identity: str, required_approvers: list[str]) -> bool:
        """Check if identity is in required approvers list."""
        return identity in required_approvers
```

### 0.4 Acceptance Criteria (Phase 0)

- [ ] All command execution uses `shell=False`
- [ ] Executable allowlist enforced
- [ ] Path traversal tests pass (10+ edge cases)
- [ ] Symlink escape tests pass
- [ ] Approval signatures verified
- [ ] Unauthorized approval attempts rejected
- [ ] Security audit by external reviewer

---

## Phase 1: Persistence Layer

**Prerequisite:** Phase 0 complete

### 1.1 Event Store

**Technology Choice:** SQLite for single-node, PostgreSQL for distributed.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator
import json

@dataclass
class Event:
    """Canonical event envelope (per GPT recommendation)."""
    id: str
    stream_id: str  # workflow_id or chat_session_id
    type: str
    version: int  # For schema evolution
    timestamp: datetime
    correlation_id: str  # Links related events
    causation_id: str | None  # Event that caused this one
    data: dict
    metadata: dict

class EventStore(ABC):
    """Abstract event store interface."""

    @abstractmethod
    async def append(self, stream_id: str, events: list[Event]) -> None:
        """Append events to stream (atomic)."""
        pass

    @abstractmethod
    async def read(
        self,
        stream_id: str,
        from_version: int = 0,
    ) -> AsyncIterator[Event]:
        """Read events from stream."""
        pass

    @abstractmethod
    async def read_all(
        self,
        from_position: int = 0,
        event_types: list[str] | None = None,
    ) -> AsyncIterator[Event]:
        """Read all events (for projections)."""
        pass

class SQLiteEventStore(EventStore):
    """SQLite-based event store for single-node deployment."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    stream_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    causation_id TEXT,
                    data TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    global_position INTEGER AUTOINCREMENT,
                    UNIQUE(stream_id, version)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_stream_id
                ON events(stream_id, version)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_type
                ON events(type)
            """)

    async def append(self, stream_id: str, events: list[Event]) -> None:
        """
        Append with optimistic concurrency control.

        Uses BEGIN IMMEDIATE to acquire write lock before reading,
        preventing race conditions between version check and insert.
        The UNIQUE(stream_id, version) constraint provides final safety.
        """
        async with aiosqlite.connect(self.db_path) as conn:
            # BEGIN IMMEDIATE acquires write lock immediately, preventing
            # race conditions between SELECT and INSERT
            await conn.execute("BEGIN IMMEDIATE")

            try:
                # Get current max version (now safe - we hold the write lock)
                cursor = await conn.execute(
                    "SELECT MAX(version) FROM events WHERE stream_id = ?",
                    (stream_id,)
                )
                row = await cursor.fetchone()
                current_version = row[0] or 0

                # Verify expected version
                if events[0].version != current_version + 1:
                    raise ConcurrencyError(
                        f"Expected version {events[0].version}, "
                        f"but stream is at {current_version}"
                    )

                # Insert events (UNIQUE constraint is backup protection)
                for event in events:
                    await conn.execute(
                        """
                        INSERT INTO events
                        (id, stream_id, type, version, timestamp,
                         correlation_id, causation_id, data, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.id,
                            stream_id,
                            event.type,
                            event.version,
                            event.timestamp.isoformat(),
                            event.correlation_id,
                            event.causation_id,
                            json.dumps(event.data),
                            json.dumps(event.metadata),
                        )
                    )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
```

### 1.2 Checkpoint Storage

```python
@dataclass
class Checkpoint:
    """Snapshot for fast recovery."""
    id: str
    stream_id: str
    version: int  # Event version at snapshot time
    state: dict  # Serialized aggregate state
    created_at: datetime

class CheckpointStore:
    """Store and retrieve checkpoints."""

    async def save(self, checkpoint: Checkpoint) -> None:
        """Save checkpoint."""
        pass

    async def load_latest(self, stream_id: str) -> Checkpoint | None:
        """Load most recent checkpoint for stream."""
        pass

    async def load_at_version(
        self, stream_id: str, version: int
    ) -> Checkpoint | None:
        """Load checkpoint at or before version."""
        pass
```

### 1.3 Acceptance Criteria (Phase 1)

- [ ] Events persist across process restarts
- [ ] Optimistic concurrency prevents lost updates
- [ ] Checkpoints reduce replay time by 90%+
- [ ] Migration strategy documented for schema changes
- [ ] Backup/restore tested

---

## Phase 2: Token Budget System

### 2.1 Provider-Specific Token Counting

**Problem:** Design used GPT tokenizer for all providers.

**Solution:** Provider-specific counting with fallback estimation.

```python
from abc import ABC, abstractmethod

class TokenCounter(ABC):
    """Provider-specific token counter."""

    @abstractmethod
    def count(self, text: str) -> int:
        """Count tokens in text."""
        pass

    @abstractmethod
    def count_messages(self, messages: list[dict]) -> int:
        """Count tokens in message array (includes overhead)."""
        pass

class ClaudeTokenCounter(TokenCounter):
    """Token counter for Claude models."""

    def __init__(self):
        # Claude uses a custom tokenizer
        # For accurate counting, use Anthropic's count_tokens API
        self._client = anthropic.Anthropic()

    def count(self, text: str) -> int:
        """Count tokens using Anthropic API."""
        # Use beta token counting endpoint
        response = self._client.beta.messages.count_tokens(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": text}]
        )
        return response.input_tokens

    def count_messages(self, messages: list[dict]) -> int:
        """Count tokens for message array."""
        response = self._client.beta.messages.count_tokens(
            model="claude-sonnet-4-20250514",
            messages=messages
        )
        return response.input_tokens

class OpenAITokenCounter(TokenCounter):
    """Token counter for OpenAI models."""

    def __init__(self, model: str = "gpt-4"):
        import tiktoken
        self._encoder = tiktoken.encoding_for_model(model)

    def count(self, text: str) -> int:
        return len(self._encoder.encode(text))

    def count_messages(self, messages: list[dict]) -> int:
        # GPT message overhead: 3 tokens per message + 3 for reply priming
        count = 3
        for msg in messages:
            count += 3  # Per-message overhead
            count += self.count(msg.get("content", ""))
            if msg.get("name"):
                count += 1
        return count

def get_token_counter(provider: str) -> TokenCounter:
    """Factory for token counters."""
    counters = {
        "anthropic": ClaudeTokenCounter,
        "openai": OpenAITokenCounter,
        # Add more providers
    }
    return counters.get(provider, EstimationTokenCounter)()
```

### 2.2 Atomic Budget Operations

**Problem:** Race conditions in budget tracking.

**Solution:** Atomic operations with database transactions.

```python
class AtomicBudgetTracker:
    """
    Thread-safe budget tracking with persistence.

    SQLite vs PostgreSQL:
    - SQLite: Uses BEGIN IMMEDIATE for write lock (no FOR UPDATE)
    - PostgreSQL: Uses FOR UPDATE for row-level locking

    This implementation supports both via database adapter pattern.
    """

    def __init__(self, db: DatabaseAdapter):
        self.db = db

    async def reserve(
        self,
        budget_id: str,
        tokens: int,
    ) -> ReservationResult:
        """
        Atomically reserve tokens.
        Returns reservation ID or rejection reason.
        """
        # Use database-specific transaction handling
        async with self.db.exclusive_transaction() as tx:
            # SELECT without FOR UPDATE - transaction isolation handles it
            # SQLite: BEGIN IMMEDIATE already holds write lock
            # PostgreSQL: Use FOR UPDATE via adapter if needed
            budget = await tx.fetch_one(
                self.db.select_for_update("budgets", "id = ?"),
                (budget_id,)
            )

            if not budget:
                return ReservationResult(success=False, reason="Budget not found")

            available = budget["limit"] - budget["used"] - budget["reserved"]

            if tokens > available:
                return ReservationResult(
                    success=False,
                    reason=f"Insufficient budget: need {tokens}, have {available}",
                )

            # Create reservation
            reservation_id = str(uuid.uuid4())
            await tx.execute(
                """
                INSERT INTO reservations (id, budget_id, tokens, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (reservation_id, budget_id, tokens, now(), now() + timedelta(minutes=5))
            )

            # Update reserved count
            await tx.execute(
                "UPDATE budgets SET reserved = reserved + ? WHERE id = ?",
                (tokens, budget_id)
            )

            return ReservationResult(
                success=True,
                reservation_id=reservation_id,
            )

    async def commit(self, reservation_id: str, actual_tokens: int) -> None:
        """Commit reservation with actual usage."""
        async with self.db.exclusive_transaction() as tx:
            reservation = await tx.fetch_one(
                self.db.select_for_update("reservations", "id = ?"),
                (reservation_id,)
            )

            if not reservation:
                raise ValueError(f"Reservation not found: {reservation_id}")

            # Update budget: move from reserved to used
            await tx.execute(
                """
                UPDATE budgets
                SET reserved = reserved - ?,
                    used = used + ?
                WHERE id = ?
                """,
                (reservation["tokens"], actual_tokens, reservation["budget_id"])
            )

            # Delete reservation
            await tx.execute(
                "DELETE FROM reservations WHERE id = ?",
                (reservation_id,)
            )

    async def rollback(self, reservation_id: str) -> None:
        """Release reservation without using tokens."""
        async with self.db.exclusive_transaction() as tx:
            reservation = await tx.fetch_one(
                "SELECT * FROM reservations WHERE id = ?",
                (reservation_id,)
            )

            if reservation:
                await tx.execute(
                    "UPDATE budgets SET reserved = reserved - ? WHERE id = ?",
                    (reservation["tokens"], reservation["budget_id"])
                )
                await tx.execute(
                    "DELETE FROM reservations WHERE id = ?",
                    (reservation_id,)
                )


class DatabaseAdapter(ABC):
    """Abstract database adapter for SQLite/PostgreSQL compatibility."""

    @abstractmethod
    def exclusive_transaction(self) -> AsyncContextManager:
        """Return transaction context with appropriate locking."""
        pass

    @abstractmethod
    def select_for_update(self, table: str, where: str) -> str:
        """Return SELECT query with appropriate locking syntax."""
        pass


class SQLiteAdapter(DatabaseAdapter):
    """SQLite adapter - uses BEGIN IMMEDIATE for locking."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    @asynccontextmanager
    async def exclusive_transaction(self):
        async with aiosqlite.connect(self.db_path) as conn:
            # BEGIN IMMEDIATE acquires write lock immediately
            await conn.execute("BEGIN IMMEDIATE")
            try:
                yield SQLiteTransaction(conn)
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    def select_for_update(self, table: str, where: str) -> str:
        # SQLite: No FOR UPDATE, BEGIN IMMEDIATE handles locking
        return f"SELECT * FROM {table} WHERE {where}"


class PostgreSQLAdapter(DatabaseAdapter):
    """PostgreSQL adapter - uses FOR UPDATE for row locking."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @asynccontextmanager
    async def exclusive_transaction(self):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield PostgreSQLTransaction(conn)

    def select_for_update(self, table: str, where: str) -> str:
        # PostgreSQL: Use FOR UPDATE for row-level locking
        return f"SELECT * FROM {table} WHERE {where} FOR UPDATE"
```

### 2.3 Acceptance Criteria (Phase 2)

- [ ] Token counting accurate within 5% for each provider
- [ ] Concurrent budget updates don't cause overdraft
- [ ] Reservation timeout releases held tokens
- [ ] Budget hierarchy enforced (org > team > user > workflow)
- [ ] Usage persisted for billing/analytics

---

## Phase 3: Gate System

### 3.1 Event-Driven Gates (Replace Polling)

**Problem:** HumanApprovalGate polling every 30s for 24h = 2,880 queries.

**Solution:** Event-driven with webhook support.

```python
class EventDrivenApprovalGate(Gate):
    """Human approval via webhooks, not polling."""

    def __init__(
        self,
        webhook_url: str,
        callback_url: str,  # Where approvals POST back
        required_approvers: list[str],
        timeout: int = 86400,
    ):
        self.webhook_url = webhook_url
        self.callback_url = callback_url
        self.required_approvers = required_approvers
        self.timeout = timeout

    async def check(self, context: GateContext) -> GateResult:
        # Create approval request
        request = await self._create_approval_request(context)

        # Send webhook notification
        await self._send_webhook(request)

        # Return PENDING - caller should wait for callback
        return GateResult(
            status=GateStatus.PENDING,
            metadata={
                "request_id": request.id,
                "callback_url": self.callback_url,
                "expires_at": request.expires_at.isoformat(),
            }
        )

    async def handle_callback(
        self,
        request_id: str,
        approval: Approval,
    ) -> GateResult:
        """Handle approval callback from webhook."""
        # Verify approval signature
        if not approval.verify(self._signing_key):
            return GateResult(
                status=GateStatus.FAILED,
                reason="Invalid approval signature",
            )

        # Verify approver is authorized
        if not self._is_authorized(approval.approved_by):
            return GateResult(
                status=GateStatus.FAILED,
                reason=f"Approver not authorized: {approval.approved_by}",
            )

        # Verify artifact hash matches
        request = await self._get_request(request_id)
        if approval.artifact_hash != request.artifact_hash:
            return GateResult(
                status=GateStatus.FAILED,
                reason="Artifact hash mismatch - content changed since approval requested",
            )

        return GateResult(
            status=GateStatus.PASSED,
            metadata={
                "approved_by": approval.approved_by,
                "approved_at": approval.approved_at.isoformat(),
            }
        )
```

### 3.2 External Review Gate with Secret Redaction

**Problem:** ExternalReviewGate POSTs raw diffs without redaction.

**Solution:** Redact secrets before sending.

```python
import re

class SecretRedactor:
    """Redact secrets from content before external transmission."""

    PATTERNS = [
        # API keys
        (r'(?i)(api[_-]?key|apikey)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_-]{20,})', r'\1=<REDACTED>'),
        # AWS keys
        (r'(?i)(aws[_-]?(?:access|secret)[_-]?(?:key)?[_-]?(?:id)?)["\']?\s*[:=]\s*["\']?([A-Z0-9]{16,})', r'\1=<REDACTED>'),
        # Passwords
        (r'(?i)(password|passwd|pwd)["\']?\s*[:=]\s*["\']?([^\s"\']{8,})', r'\1=<REDACTED>'),
        # Tokens
        (r'(?i)(token|bearer)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_.-]{20,})', r'\1=<REDACTED>'),
        # Private keys
        (r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', '<REDACTED_PRIVATE_KEY>'),
        # Connection strings
        (r'(?i)(mongodb|postgres|mysql|redis)://[^\s"\']+', r'\1://<REDACTED>'),
    ]

    def redact(self, content: str) -> str:
        """Redact secrets from content."""
        result = content
        for pattern, replacement in self.PATTERNS:
            result = re.sub(pattern, replacement, result)
        return result

class SafeExternalReviewGate(Gate):
    """External review with secret redaction."""

    def __init__(self, review_url: str, redactor: SecretRedactor):
        self.review_url = review_url
        self.redactor = redactor

    async def check(self, context: GateContext) -> GateResult:
        # Redact secrets from diff before sending
        safe_diff = self.redactor.redact(context.diff)

        # Verify nothing sensitive remains
        if self._contains_sensitive_patterns(safe_diff):
            return GateResult(
                status=GateStatus.FAILED,
                reason="Unable to safely redact all secrets from diff",
            )

        # Now safe to send externally
        response = await self._send_for_review(safe_diff)
        # ...
```

### 3.3 Acceptance Criteria (Phase 3)

- [ ] No polling-based gates
- [ ] Webhook delivery with retry and dead-letter queue
- [ ] All external payloads pass secret scan
- [ ] Gates produce signed audit log entries
- [ ] Timeout handling with escalation

---

## Phase 4: Chat Mode

### 4.1 Safe Context Summarization

**Problem:** Summarization can corrupt state (lossy, recursive LLM calls).

**Solution:** Deterministic compression with validation.

```python
class SafeContextManager:
    """Context management with safety guarantees."""

    def __init__(
        self,
        max_tokens: int,
        summarizer: Summarizer,
        validator: SummaryValidator,
    ):
        self.max_tokens = max_tokens
        self.summarizer = summarizer
        self.validator = validator

    async def prepare_context(
        self,
        messages: list[Message],
        pinned: list[str],  # Message IDs that must be preserved
    ) -> list[Message]:
        """Prepare context, summarizing if needed."""
        token_count = self._count_tokens(messages)

        if token_count <= self.max_tokens * 0.7:
            return messages  # No compression needed

        # Identify messages to summarize (not pinned, not recent)
        recent_count = 20
        to_summarize = [
            m for m in messages[:-recent_count]
            if m.id not in pinned
        ]
        to_keep = [
            m for m in messages[:-recent_count]
            if m.id in pinned
        ] + messages[-recent_count:]

        # Generate summary
        summary_text = await self.summarizer.summarize(to_summarize)

        # CRITICAL: Validate summary preserves key information
        validation = await self.validator.validate(
            original=to_summarize,
            summary=summary_text,
        )

        if not validation.is_valid:
            # Fall back to truncation instead of lossy summary
            logger.warning(
                f"Summary validation failed: {validation.reason}. "
                "Falling back to truncation."
            )
            return self._truncate(messages, self.max_tokens)

        # Create summary message
        summary_message = Message(
            id=f"summary_{uuid.uuid4().hex[:8]}",
            role=MessageRole.SYSTEM,
            content=f"[Conversation summary: {len(to_summarize)} messages]\n{summary_text}",
            metadata={"summarized_count": len(to_summarize)},
        )

        return [summary_message] + to_keep

class SummaryValidator:
    """Validate summaries preserve critical information."""

    async def validate(
        self,
        original: list[Message],
        summary: str,
    ) -> ValidationResult:
        """Check summary contains key entities and decisions."""
        # Extract key entities from original
        original_text = "\n".join(m.content for m in original)
        original_entities = self._extract_entities(original_text)
        original_decisions = self._extract_decisions(original_text)

        # Check summary contains them
        missing_entities = [
            e for e in original_entities
            if e.lower() not in summary.lower()
        ]
        missing_decisions = [
            d for d in original_decisions
            if not self._decision_preserved(d, summary)
        ]

        if missing_entities or missing_decisions:
            return ValidationResult(
                is_valid=False,
                reason=f"Missing: {missing_entities + missing_decisions}",
            )

        return ValidationResult(is_valid=True)
```

### 4.2 Acceptance Criteria (Phase 4)

- [ ] Chat sessions persist and restore correctly
- [ ] Meta-commands work (`/status`, `/approve`, etc.)
- [ ] Context summarization validated before use
- [ ] Checkpoint/restore tested with complex sessions
- [ ] Crash recovery works mid-conversation

---

## Phase 5: API Runner & Observability

### 5.1 Distributed Circuit Breaker

**Problem:** Circuit breaker state is local (useless in distributed deployment).

**Solution:** Redis-backed distributed circuit breaker.

```python
import redis.asyncio as redis

class DistributedCircuitBreaker:
    """Redis-backed circuit breaker for distributed deployment."""

    def __init__(
        self,
        redis_client: redis.Redis,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
    ):
        self.redis = redis_client
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

    async def allow_request(self) -> bool:
        """Check if request should be allowed."""
        state = await self.redis.get(f"circuit:{self.name}:state")

        if state == b"open":
            # Check if recovery period elapsed
            opened_at = await self.redis.get(f"circuit:{self.name}:opened_at")
            if opened_at:
                elapsed = time.time() - float(opened_at)
                if elapsed >= self.recovery_timeout:
                    # Move to half-open
                    await self.redis.set(f"circuit:{self.name}:state", "half-open")
                    return True
            return False

        return True

    async def record_success(self) -> None:
        """Record successful request."""
        state = await self.redis.get(f"circuit:{self.name}:state")

        if state == b"half-open":
            # Recovery successful, close circuit
            await self.redis.set(f"circuit:{self.name}:state", "closed")
            await self.redis.set(f"circuit:{self.name}:failures", 0)

    async def record_failure(self) -> None:
        """Record failed request."""
        failures = await self.redis.incr(f"circuit:{self.name}:failures")

        if failures >= self.failure_threshold:
            await self.redis.set(f"circuit:{self.name}:state", "open")
            await self.redis.set(f"circuit:{self.name}:opened_at", time.time())
```

### 5.2 Observability

```python
from opentelemetry import trace, metrics
from opentelemetry.trace import Span

tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Metrics
llm_request_duration = meter.create_histogram(
    "llm_request_duration_seconds",
    description="LLM request duration",
)
llm_tokens_used = meter.create_counter(
    "llm_tokens_total",
    description="Total tokens used",
)
gate_evaluations = meter.create_counter(
    "gate_evaluations_total",
    description="Gate evaluation count",
)

class InstrumentedRunner(AgentRunner):
    """Runner with observability instrumentation."""

    def __init__(self, inner: AgentRunner):
        self.inner = inner

    async def invoke(self, phase_input: PhaseInput) -> PhaseOutput:
        with tracer.start_as_current_span("llm_invoke") as span:
            span.set_attribute("workflow_id", phase_input.context.get("workflow_id"))
            span.set_attribute("phase_id", phase_input.phase_id)

            start = time.time()
            try:
                output = await self.inner.invoke(phase_input)

                # Record metrics
                duration = time.time() - start
                llm_request_duration.record(duration, {
                    "provider": self.inner.provider,
                    "phase": phase_input.phase_id,
                    "success": "true",
                })

                if hasattr(output, "token_usage"):
                    llm_tokens_used.add(
                        output.token_usage.total,
                        {"provider": self.inner.provider},
                    )

                span.set_attribute("success", True)
                return output

            except Exception as e:
                span.set_attribute("success", False)
                span.record_exception(e)
                llm_request_duration.record(time.time() - start, {
                    "provider": self.inner.provider,
                    "phase": phase_input.phase_id,
                    "success": "false",
                })
                raise
```

### 5.3 Acceptance Criteria (Phase 5)

- [ ] Circuit breaker state shared across instances
- [ ] OpenTelemetry traces exported
- [ ] Prometheus metrics available at `/metrics`
- [ ] Alerts configured for error rates
- [ ] Health check endpoint working

---

## Implementation Timeline

| Phase | Duration | Dependencies | Deliverables |
|-------|----------|--------------|--------------|
| **Phase 0** | 2 weeks | None | Security hardening, tests |
| **Phase 1** | 2 weeks | Phase 0 | Event store, checkpoints |
| **Phase 2** | 2 weeks | Phase 1 | Token budgets, atomic ops |
| **Phase 3** | 2 weeks | Phase 1, 2 | Gates, webhooks, redaction |
| **Phase 4** | 2 weeks | Phase 1, 3 | Chat mode, summarization |
| **Phase 5** | 2 weeks | Phase 3, 4 | API runner, observability |

**Total: 12 weeks** (vs. original 8 weeks - adjusted per review feedback)

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Security vulnerabilities | External security audit before Phase 1 |
| Performance regression | Benchmark suite, load testing in Phase 5 |
| Breaking changes | Versioned event schemas, migration scripts |
| Scope creep | Strict phase gates, defer to V4.3 if needed |

---

## Success Criteria (Overall)

1. All Phase 0 security tests pass
2. Event replay produces identical state
3. Token budgets accurate within 5% per provider
4. Zero polling-based gates
5. P99 latency < 500ms for gate evaluation
6. Mean time to recovery < 30s after crash
7. Security audit passes with no critical findings
