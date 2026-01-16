# Self-Healing Infrastructure Implementation Plan

**Design Document:** `docs/design/self-healing-infrastructure.md` (v3.2)
**Status:** Phase 3 Complete - Ready for Phase 4
**Date:** 2026-01-16
**Revised:** Based on 5-model review (Claude, Gemini, GPT, Grok, DeepSeek)

---

## Infrastructure

**Supabase Project:** `https://igalnlhcblswjtwaruvy.supabase.co`

**Target Environments:**
- Local development (full filesystem access)
- Claude Code Web (no local filesystem - API-only)
- CI/CD (limited filesystem, GitHub Actions available)

---

## Overview

This plan uses a **cloud-first architecture** where everything works via APIs (Supabase + GitHub). Local caching is an optimization, not a requirement.

```
Phase 0: Abstraction Layer (adapters for storage, git, execution)        ✓ COMPLETE
Phase 1: Detection & Fingerprinting + Config + Environment              ✓ COMPLETE
Phase 2: Pattern Memory & Lookup + Pattern Generation + Security        ✓ COMPLETE
Phase 3a: Validation Logic (testable without applying)                  ✓ COMPLETE
Phase 3b: Fix Application (environment-aware)                           ✓ COMPLETE
Phase 4: CLI & Workflow Integration                                     ○ NEXT
Phase 5: Observability & Hardening                                      ○ PENDING
```

**Key Principle:** Every phase works in cloud environments (Claude Code Web) from day one.

---

## Phase 0: Abstraction Layer

**Goal:** Create adapters that abstract local vs cloud operations. This is the foundation that enables cloud deployment.

### Components

#### 0.1 Environment Detection
```python
# src/healing/environment.py
from enum import Enum
import os

class Environment(Enum):
    LOCAL = "local"      # Full filesystem + git CLI
    CLOUD = "cloud"      # API-only (Claude Code Web)
    CI = "ci"            # GitHub Actions context

def detect_environment() -> Environment:
    """Auto-detect execution environment."""
    if os.environ.get("CLAUDE_CODE_WEB"):
        return Environment.CLOUD
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        return Environment.CI
    return Environment.LOCAL

# Global singleton
ENVIRONMENT = detect_environment()
```

#### 0.2 Storage Adapter
```python
# src/healing/adapters/storage.py
from abc import ABC, abstractmethod

class StorageAdapter(ABC):
    """Abstract file operations for local/cloud compatibility."""

    @abstractmethod
    async def read_file(self, path: str) -> str:
        """Read file content."""

    @abstractmethod
    async def write_file(self, path: str, content: str) -> None:
        """Write file content."""

    @abstractmethod
    async def file_exists(self, path: str) -> bool:
        """Check if file exists."""

    @abstractmethod
    async def list_files(self, pattern: str) -> list[str]:
        """List files matching pattern."""


# src/healing/adapters/storage_local.py
class LocalStorageAdapter(StorageAdapter):
    """Local filesystem implementation."""

    async def read_file(self, path: str) -> str:
        return Path(path).read_text()

    async def write_file(self, path: str, content: str) -> None:
        Path(path).write_text(content)


# src/healing/adapters/storage_github.py
class GitHubStorageAdapter(StorageAdapter):
    """GitHub API implementation for cloud environments."""

    def __init__(self, owner: str, repo: str, token: str):
        self.owner = owner
        self.repo = repo
        self.token = token

    async def read_file(self, path: str) -> str:
        """Read file via GitHub Contents API."""
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/contents/{path}"
        # ... API call

    async def write_file(self, path: str, content: str) -> None:
        """Write file via GitHub Contents API (creates commit)."""
        # ... API call with base64 content
```

#### 0.3 Git Adapter
```python
# src/healing/adapters/git.py
from abc import ABC, abstractmethod

class GitAdapter(ABC):
    """Abstract git operations for local CLI vs GitHub API."""

    @abstractmethod
    async def create_branch(self, name: str, base: str = "main") -> None:
        """Create a new branch."""

    @abstractmethod
    async def apply_diff(self, diff: str, message: str) -> str:
        """Apply diff and commit. Returns commit SHA."""

    @abstractmethod
    async def create_pr(self, title: str, body: str, head: str, base: str) -> str:
        """Create pull request. Returns PR URL."""

    @abstractmethod
    async def merge_branch(self, branch: str, into: str) -> None:
        """Merge branch."""

    @abstractmethod
    async def delete_branch(self, name: str) -> None:
        """Delete branch."""

    @abstractmethod
    async def get_recent_commits(self, count: int = 10) -> list[dict]:
        """Get recent commits for causality analysis."""


# src/healing/adapters/git_local.py
class LocalGitAdapter(GitAdapter):
    """Git CLI implementation."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    async def create_branch(self, name: str, base: str = "main") -> None:
        await run_command(f"git checkout -b {name} {base}", cwd=self.repo_path)


# src/healing/adapters/git_github.py
class GitHubAPIAdapter(GitAdapter):
    """GitHub API implementation for cloud environments."""

    def __init__(self, owner: str, repo: str, token: str):
        self.owner = owner
        self.repo = repo
        self.token = token
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"

    async def create_branch(self, name: str, base: str = "main") -> None:
        """Create branch via GitHub Refs API."""
        # Get base SHA
        ref = await self._get(f"/git/refs/heads/{base}")
        base_sha = ref["object"]["sha"]
        # Create new ref
        await self._post("/git/refs", {"ref": f"refs/heads/{name}", "sha": base_sha})

    async def create_pr(self, title: str, body: str, head: str, base: str) -> str:
        """Create PR via GitHub API."""
        pr = await self._post("/pulls", {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
        })
        return pr["html_url"]
```

#### 0.4 Cache Adapter
```python
# src/healing/adapters/cache.py
from abc import ABC, abstractmethod

class CacheAdapter(ABC):
    """Abstract cache for local SQLite vs Supabase-only."""

    @abstractmethod
    async def get(self, key: str) -> dict | None:
        """Get cached value."""

    @abstractmethod
    async def set(self, key: str, value: dict, ttl_seconds: int = 3600) -> None:
        """Set cached value with TTL."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete cached value."""


# src/healing/adapters/cache_local.py
class LocalSQLiteCache(CacheAdapter):
    """SQLite cache for local environments."""

    def __init__(self, path: Path = Path(".claude/healing_cache.sqlite")):
        self.path = path
        self._init_db()


# src/healing/adapters/cache_memory.py
class InMemoryCache(CacheAdapter):
    """In-memory cache for cloud environments (session-scoped)."""

    def __init__(self):
        self._cache: dict[str, tuple[dict, float]] = {}  # key -> (value, expires_at)


# src/healing/adapters/cache_supabase.py
class SupabaseCacheAdapter(CacheAdapter):
    """Supabase-backed cache for cloud environments (persistent)."""

    def __init__(self, client: "SupabaseClient"):
        self.client = client
```

#### 0.5 Execution Adapter
```python
# src/healing/adapters/execution.py
from abc import ABC, abstractmethod

class ExecutionAdapter(ABC):
    """Abstract command execution for local subprocess vs CI triggers."""

    @abstractmethod
    async def run_command(
        self,
        command: str,
        timeout_seconds: int = 300
    ) -> tuple[int, str, str]:
        """Run command. Returns (exit_code, stdout, stderr)."""

    @abstractmethod
    async def run_tests(self, test_pattern: str = None) -> "TestResult":
        """Run tests and return structured result."""

    @abstractmethod
    async def run_build(self) -> "BuildResult":
        """Run build and return structured result."""

    @abstractmethod
    async def run_lint(self) -> "LintResult":
        """Run linter and return structured result."""


# src/healing/adapters/execution_local.py
class LocalExecutionAdapter(ExecutionAdapter):
    """Subprocess-based execution for local environments."""

    async def run_command(self, command: str, timeout_seconds: int = 300):
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_seconds
            )
            return proc.returncode, stdout.decode(), stderr.decode()
        except asyncio.TimeoutError:
            proc.kill()
            raise ExecutionTimeoutError(command, timeout_seconds)


# src/healing/adapters/execution_github.py
class GitHubActionsAdapter(ExecutionAdapter):
    """Trigger GitHub Actions workflows for verification."""

    async def run_tests(self, test_pattern: str = None) -> "TestResult":
        """Trigger test workflow and poll for result."""
        # Dispatch workflow
        run_id = await self._dispatch_workflow("test.yml", {"pattern": test_pattern})
        # Poll for completion
        result = await self._wait_for_workflow(run_id, timeout=600)
        return TestResult.from_workflow_result(result)
```

#### 0.6 Adapter Factory
```python
# src/healing/adapters/factory.py
from .environment import ENVIRONMENT, Environment

class AdapterFactory:
    """Create appropriate adapters based on environment."""

    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        github_token: str = None,
        github_owner: str = None,
        github_repo: str = None,
    ):
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
        self.github_token = github_token
        self.github_owner = github_owner
        self.github_repo = github_repo

    def create_storage(self) -> StorageAdapter:
        if ENVIRONMENT == Environment.LOCAL:
            return LocalStorageAdapter()
        else:
            return GitHubStorageAdapter(
                self.github_owner, self.github_repo, self.github_token
            )

    def create_git(self) -> GitAdapter:
        if ENVIRONMENT == Environment.LOCAL:
            return LocalGitAdapter(Path.cwd())
        else:
            return GitHubAPIAdapter(
                self.github_owner, self.github_repo, self.github_token
            )

    def create_cache(self) -> CacheAdapter:
        if ENVIRONMENT == Environment.LOCAL:
            return LocalSQLiteCache()
        else:
            # Cloud: use in-memory with Supabase backup
            return InMemoryCache()

    def create_execution(self) -> ExecutionAdapter:
        if ENVIRONMENT == Environment.LOCAL:
            return LocalExecutionAdapter()
        else:
            return GitHubActionsAdapter(
                self.github_owner, self.github_repo, self.github_token
            )
```

### Dependencies
- None (foundation layer)

### Done Criteria
- [ ] All 5 adapter interfaces defined (Storage, Git, Cache, Execution, Factory)
- [ ] Local implementations work for all adapters
- [ ] GitHub API implementations work for Storage and Git
- [ ] GitHub Actions adapter triggers workflows
- [ ] Environment detection correctly identifies LOCAL/CLOUD/CI
- [ ] Factory creates correct adapters per environment
- [ ] Unit tests for each adapter
- [ ] Integration test: same code runs in both environments

### Tests
```
tests/healing/adapters/
├── test_environment.py
├── test_storage_local.py
├── test_storage_github.py
├── test_git_local.py
├── test_git_github.py
├── test_cache_local.py
├── test_cache_memory.py
├── test_execution_local.py
├── test_execution_github.py
└── test_factory.py
```

---

## Phase 1: Detection, Fingerprinting & Config

**Goal:** Capture and deduplicate errors. No fixing yet - observe, fingerprint, and configure.

### Components

#### 1.1 Configuration (Moved from Phase 5)
```python
# src/healing/config.py
from dataclasses import dataclass, field
from typing import Optional
import os

@dataclass
class HealingConfig:
    """Configuration loaded from env vars or Supabase."""

    # Feature flags
    enabled: bool = True
    auto_apply_safe: bool = True
    auto_apply_moderate: bool = False

    # Cost controls (needed early!)
    max_daily_cost_usd: float = 10.0
    max_validations_per_day: int = 100
    max_cost_per_validation_usd: float = 0.50

    # Safety
    protected_paths: list[str] = field(default_factory=lambda: [
        "src/auth/**",
        "migrations/**",
        "*.env*",
    ])

    # Kill switch
    kill_switch_active: bool = False

    # Timeouts (critical for production)
    build_timeout_seconds: int = 300
    test_timeout_seconds: int = 600
    lint_timeout_seconds: int = 60
    judge_timeout_seconds: int = 30

    @classmethod
    def from_environment(cls) -> "HealingConfig":
        """Load config from environment variables."""
        return cls(
            enabled=os.environ.get("HEALING_ENABLED", "true").lower() == "true",
            max_daily_cost_usd=float(os.environ.get("HEALING_MAX_DAILY_COST", "10.0")),
            kill_switch_active=os.environ.get("HEALING_KILL_SWITCH", "false").lower() == "true",
            # ... etc
        )

    @classmethod
    async def from_supabase(cls, client: "SupabaseClient", project_id: str) -> "HealingConfig":
        """Load config from Supabase (for cloud environments)."""
        result = await client.table("healing_config").select("*").eq("project_id", project_id).single()
        if result.data:
            return cls(**result.data)
        return cls()  # Defaults


# Global config (initialized once)
CONFIG: HealingConfig = None

async def init_config(client: "SupabaseClient" = None, project_id: str = None):
    global CONFIG
    if ENVIRONMENT == Environment.CLOUD and client:
        CONFIG = await HealingConfig.from_supabase(client, project_id)
    else:
        CONFIG = HealingConfig.from_environment()
```

#### 1.2 Error Event Model
```python
# src/healing/models.py
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

@dataclass
class ErrorEvent:
    """Unified error event from any source."""

    error_id: str
    timestamp: datetime
    source: Literal["workflow_log", "transcript", "subprocess", "hook"]

    # Content
    description: str
    error_type: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    stack_trace: Optional[str] = None
    command: Optional[str] = None
    exit_code: Optional[int] = None

    # Computed (by Fingerprinter)
    fingerprint: Optional[str] = None
    fingerprint_coarse: Optional[str] = None

    # Context
    workflow_id: Optional[str] = None
    phase_id: Optional[str] = None
    project_id: Optional[str] = None
```

#### 1.3 Fingerprinter
**Design Doc:** Section 4.7

```python
# src/healing/fingerprint.py
import hashlib
import re
from dataclasses import dataclass, field

@dataclass
class FingerprintConfig:
    """Normalization rules for fingerprinting."""

    strip_patterns: list[tuple[str, str]] = field(default_factory=lambda: [
        # File paths: /home/user/project/foo.py → <path>/foo.py
        (r'/[\w/.-]+/([^/]+\.\w+)', r'<path>/\1'),
        # Line numbers: foo.py:123 → foo.py:<line>
        (r'(\.\w+):(\d+)', r'\1:<line>'),
        # UUIDs
        (r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '<uuid>'),
        # Timestamps
        (r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[Z\d:+-]*', '<timestamp>'),
        # Memory addresses
        (r'0x[0-9a-fA-F]+', '<addr>'),
        # PIDs
        (r'pid[=:]\s*\d+', 'pid=<pid>'),
        # Temp paths
        (r'/tmp/[\w.-]+/', '<tmpdir>/'),
        # Long strings in quotes
        (r'"[^"]{20,}"', '"<string>"'),
    ])


class Fingerprinter:
    """Generate stable fingerprints for error deduplication."""

    def __init__(self, config: FingerprintConfig = None):
        self.config = config or FingerprintConfig()

    def fingerprint(self, error: ErrorEvent) -> str:
        """Generate fine-grained fingerprint."""
        components = []

        # Error type
        error_type = self._extract_error_type(error.error_type or error.description)
        components.append(f"type:{error_type}")

        # Normalized message
        normalized = self._normalize(error.description or "")
        components.append(f"msg:{normalized[:200]}")

        # Top stack frame
        if error.stack_trace:
            top_frame = self._extract_top_frame(error.stack_trace)
            if top_frame:
                components.append(f"frame:{top_frame}")

        content = "|".join(components)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def fingerprint_coarse(self, error: ErrorEvent) -> str:
        """Generate coarse fingerprint for broad grouping."""
        error_type = self._extract_error_type(error.error_type or error.description)
        return hashlib.sha256(f"coarse:{error_type}".encode()).hexdigest()[:8]

    def _normalize(self, text: str) -> str:
        result = text
        for pattern, replacement in self.config.strip_patterns:
            result = re.sub(pattern, replacement, result)
        return result.strip()

    def _extract_error_type(self, text: str) -> str:
        # Python
        match = re.match(r'^(\w+Error|\w+Exception|\w+Warning):', text)
        if match:
            return match.group(1)
        # Node
        if text.startswith("Error:"):
            return "Error"
        # Rust
        match = re.match(r'error\[(E\d+)\]', text)
        if match:
            return f"RustError_{match.group(1)}"
        # Go
        if text.startswith("panic:"):
            return "GoPanic"
        return "UnknownError"

    def _extract_top_frame(self, stack_trace: str) -> str | None:
        # Python
        match = re.search(r'File "([^"]+)", line \d+, in (\w+)', stack_trace)
        if match:
            filename = match.group(1).split('/')[-1]
            function = match.group(2)
            return f"{filename}:{function}"
        # Node.js
        match = re.search(r'at (\w+) \(([^)]+)\)', stack_trace)
        if match:
            function = match.group(1)
            filename = match.group(2).split('/')[-1].split(':')[0]
            return f"{filename}:{function}"
        return None
```

#### 1.4 Error Detectors
```python
# src/healing/detectors/base.py
from abc import ABC, abstractmethod

class BaseDetector(ABC):
    def __init__(self, fingerprinter: Fingerprinter):
        self.fingerprinter = fingerprinter

    @abstractmethod
    async def detect(self, source: any) -> list[ErrorEvent]:
        """Detect errors from source."""

    def _fingerprint(self, error: ErrorEvent) -> ErrorEvent:
        """Add fingerprints to error."""
        error.fingerprint = self.fingerprinter.fingerprint(error)
        error.fingerprint_coarse = self.fingerprinter.fingerprint_coarse(error)
        return error


# src/healing/detectors/workflow_log.py
class WorkflowLogDetector(BaseDetector):
    """Detect errors from .workflow_log.jsonl."""

    async def detect(self, log_path: str) -> list[ErrorEvent]:
        errors = []
        # Parse JSONL, extract failures
        # ... implementation
        return [self._fingerprint(e) for e in errors]


# src/healing/detectors/subprocess.py
class SubprocessDetector(BaseDetector):
    """Detect errors from command output."""

    ERROR_PATTERNS = [
        (r"^(\w+Error): (.+)$", "python"),
        (r"^error\[E\d+\]: (.+)$", "rust"),
        (r"^panic: (.+)$", "go"),
        (r"FAILED.*::(\w+)", "pytest"),
    ]

    async def detect(self, exit_code: int, stdout: str, stderr: str, command: str) -> list[ErrorEvent]:
        if exit_code == 0:
            return []
        # Parse stderr for error patterns
        # ... implementation
```

#### 1.5 Error Accumulator
```python
# src/healing/accumulator.py
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class ErrorAccumulator:
    """Accumulate and deduplicate errors during a workflow session."""

    _errors: dict[str, ErrorEvent] = field(default_factory=dict)  # fingerprint -> event
    _counts: dict[str, int] = field(default_factory=dict)  # fingerprint -> count
    _first_seen: dict[str, datetime] = field(default_factory=dict)

    def add(self, error: ErrorEvent) -> bool:
        """Add error. Returns True if new, False if duplicate."""
        fp = error.fingerprint
        if fp in self._errors:
            self._counts[fp] += 1
            return False
        else:
            self._errors[fp] = error
            self._counts[fp] = 1
            self._first_seen[fp] = error.timestamp
            return True

    def get_unique_errors(self) -> list[ErrorEvent]:
        """Get deduplicated errors."""
        return list(self._errors.values())

    def get_count(self, fingerprint: str) -> int:
        """Get occurrence count for fingerprint."""
        return self._counts.get(fingerprint, 0)

    def get_summary(self) -> dict:
        """Get summary statistics."""
        return {
            "unique_errors": len(self._errors),
            "total_occurrences": sum(self._counts.values()),
            "by_type": self._group_by_type(),
        }

    def clear(self) -> None:
        """Clear accumulated errors."""
        self._errors.clear()
        self._counts.clear()
        self._first_seen.clear()
```

### Dependencies
- Phase 0 (adapters for environment-aware operation)

### Done Criteria
- [ ] Config loads from env vars (local) or Supabase (cloud)
- [ ] Kill switch stops all operations when active
- [ ] Fingerprinter passes stability tests
- [ ] All 4 detectors implemented
- [ ] Accumulator correctly deduplicates
- [ ] Works in both LOCAL and CLOUD environments
- [ ] Unit tests for all components
- [ ] Integration test: run detection on real workflow

### Tests
```
tests/healing/
├── test_config.py
├── test_fingerprint.py
├── test_detectors/
│   ├── test_workflow_log.py
│   ├── test_subprocess.py
│   ├── test_transcript.py
│   └── test_hook.py
├── test_accumulator.py
└── fixtures/
    ├── sample_errors.json
    └── sample_workflow_log.jsonl
```

---

## Phase 2: Pattern Memory, Lookup & Security

**Goal:** Store patterns in Supabase, implement three-tier lookup, add security scrubbing.

### Components

#### 2.1 Supabase Schema
```sql
-- migrations/001_healing_schema.sql

-- Enable pgvector extension
create extension if not exists vector;

-- Configuration per project
create table healing_config (
    id uuid primary key default gen_random_uuid(),
    project_id text unique not null,
    enabled boolean default true,
    auto_apply_safe boolean default true,
    auto_apply_moderate boolean default false,
    max_daily_cost_usd float default 10.0,
    protected_paths text[] default array['src/auth/**', 'migrations/**'],
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

-- Error patterns (Tier 1 lookup)
create table error_patterns (
    id uuid primary key default gen_random_uuid(),
    project_id text not null,
    fingerprint text not null,
    fingerprint_coarse text,

    -- Precedent tracking (zero-human mode)
    is_preseeded boolean default false,
    verified_apply_count int default 0,
    human_correction_count int default 0,

    -- Stats
    success_count int default 0,
    failure_count int default 0,
    use_count int default 0,

    -- Safety
    safety_category text check (safety_category in ('safe', 'moderate', 'risky')),
    quarantined boolean default false,
    quarantine_reason text,

    -- Metadata
    created_at timestamptz default now(),
    updated_at timestamptz default now(),

    unique(project_id, fingerprint)
);

-- Learnings with RAG embeddings (Tier 2 lookup)
create table learnings (
    id uuid primary key default gen_random_uuid(),
    project_id text not null,
    pattern_id uuid references error_patterns(id),

    -- Content
    title text not null,
    description text,
    action jsonb not null,  -- Fix template (see 2.3 for schema)

    -- RAG
    embedding vector(1536),
    embedding_model text default 'text-embedding-ada-002',

    -- Lifecycle (4-state)
    lifecycle text default 'draft' check (lifecycle in ('draft', 'active', 'automated', 'deprecated')),

    -- Tracking
    confidence float default 0.5,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

-- Causality edges (Tier 3 lookup)
create table causality_edges (
    id uuid primary key default gen_random_uuid(),
    project_id text not null,
    error_fingerprint text not null,
    error_timestamp timestamptz not null,

    -- Cause
    causing_commit text not null,
    causing_file text not null,
    causing_function text,

    -- Evidence
    evidence_type text check (evidence_type in ('temporal', 'git_blame', 'dependency', 'cascade', 'manual')),
    confidence float default 0.5,
    occurrence_count int default 1,

    created_at timestamptz default now(),

    unique(error_fingerprint, causing_commit, causing_file)
);

-- Audit log (for cloud environments without local files)
create table healing_audit (
    id uuid primary key default gen_random_uuid(),
    project_id text not null,
    timestamp timestamptz default now(),

    action text not null,  -- 'fix_attempted', 'fix_applied', 'fix_reverted', etc.
    fingerprint text,
    fix_id uuid,
    details jsonb,
    success boolean,
    error_message text
);

-- Indexes
create index on error_patterns(project_id, fingerprint);
create index on error_patterns(fingerprint_coarse);
create index on learnings(project_id, lifecycle);
create index on learnings using ivfflat (embedding vector_cosine_ops) with (lists = 100);
create index on causality_edges(error_fingerprint);
create index on causality_edges(causing_file);
create index on healing_audit(project_id, timestamp);
```

#### 2.2 Security Scrubber (Moved from Phase 5)
```python
# src/healing/security.py
import re

class SecurityScrubber:
    """Remove secrets and PII before storing in Supabase."""

    SECRET_PATTERNS = [
        # API keys
        (r'(?i)(api[_-]?key|apikey)[=:]\s*["\']?[\w-]{20,}["\']?', r'\1=<REDACTED>'),
        # Tokens
        (r'(?i)(token|bearer)[=:\s]+["\']?[\w.-]{20,}["\']?', r'\1=<REDACTED>'),
        # Passwords
        (r'(?i)(password|passwd|pwd)[=:]\s*["\']?[^\s"\']+["\']?', r'\1=<REDACTED>'),
        # AWS keys
        (r'AKIA[0-9A-Z]{16}', '<AWS_KEY>'),
        # Private keys
        (r'-----BEGIN [\w\s]+ PRIVATE KEY-----[\s\S]+?-----END [\w\s]+ PRIVATE KEY-----', '<PRIVATE_KEY>'),
        # Connection strings
        (r'(?i)(postgres|mysql|mongodb)://[^\s]+', r'\1://<REDACTED>'),
        # Email addresses (PII)
        (r'[\w.-]+@[\w.-]+\.\w+', '<EMAIL>'),
    ]

    def scrub(self, text: str) -> str:
        """Remove secrets and PII from text."""
        result = text
        for pattern, replacement in self.SECRET_PATTERNS:
            result = re.sub(pattern, replacement, result)
        return result

    def scrub_error(self, error: ErrorEvent) -> ErrorEvent:
        """Scrub all text fields in an error."""
        error.description = self.scrub(error.description) if error.description else None
        error.stack_trace = self.scrub(error.stack_trace) if error.stack_trace else None
        return error
```

#### 2.3 Fix Action Schema
```python
# src/healing/models.py (addition)

@dataclass
class FixAction:
    """Schema for fix actions stored in learnings.action JSONB."""

    action_type: Literal["diff", "command", "file_edit", "multi_step"]

    # For action_type="diff"
    diff: Optional[str] = None

    # For action_type="command"
    command: Optional[str] = None

    # For action_type="file_edit"
    file_path: Optional[str] = None
    find: Optional[str] = None  # Text to find
    replace: Optional[str] = None  # Replacement text

    # For action_type="multi_step"
    steps: Optional[list["FixAction"]] = None

    # Metadata
    requires_context: bool = False  # Needs current file content
    context_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FixAction":
        return cls(**data)
```

#### 2.4 Supabase Client
```python
# src/healing/supabase_client.py
from supabase import create_client, Client

class HealingSupabaseClient:
    """Supabase client for healing operations."""

    def __init__(self, url: str, key: str, project_id: str):
        self.client: Client = create_client(url, key)
        self.project_id = project_id
        self.scrubber = SecurityScrubber()

    # Tier 1: Exact match
    async def lookup_pattern(self, fingerprint: str) -> dict | None:
        result = await self.client.table("error_patterns")\
            .select("*, learnings(*)")\
            .eq("project_id", self.project_id)\
            .eq("fingerprint", fingerprint)\
            .eq("quarantined", False)\
            .single()\
            .execute()
        return result.data

    # Tier 2: RAG semantic search
    async def lookup_similar(self, embedding: list[float], limit: int = 5) -> list[dict]:
        result = await self.client.rpc("match_learnings", {
            "query_embedding": embedding,
            "match_threshold": 0.7,
            "match_count": limit,
            "p_project_id": self.project_id,
        }).execute()
        return result.data

    # Tier 3: Causality
    async def get_causes(self, fingerprint: str, depth: int = 2) -> list[dict]:
        result = await self.client.rpc("get_error_causes", {
            "p_fingerprint": fingerprint,
            "p_depth": depth,
        }).execute()
        return result.data

    # Write operations
    async def record_pattern(self, pattern: dict) -> None:
        # Scrub before storing
        if "description" in pattern:
            pattern["description"] = self.scrubber.scrub(pattern["description"])
        pattern["project_id"] = self.project_id
        await self.client.table("error_patterns").upsert(pattern).execute()

    async def record_fix_result(self, fingerprint: str, success: bool) -> None:
        column = "success_count" if success else "failure_count"
        await self.client.rpc("increment_pattern_stat", {
            "p_fingerprint": fingerprint,
            "p_project_id": self.project_id,
            "p_column": column,
        }).execute()

    async def audit_log(self, action: str, details: dict) -> None:
        await self.client.table("healing_audit").insert({
            "project_id": self.project_id,
            "action": action,
            "details": details,
        }).execute()
```

#### 2.5 Pre-seeded Patterns
```python
# src/healing/preseeded_patterns.py

PRESEEDED_PATTERNS = [
    # Python import errors
    {
        "fingerprint_pattern": r"ModuleNotFoundError: No module named '(\w+)'",
        "safety_category": "safe",
        "action": {
            "action_type": "command",
            "command": "pip install {match_1}",
        },
    },
    # Python syntax errors
    {
        "fingerprint_pattern": r"SyntaxError: f-string: single '\}' is not allowed",
        "safety_category": "safe",
        "action": {
            "action_type": "file_edit",
            "find": "}}",
            "replace": "\\}",
            "requires_context": True,
        },
    },
    # Type errors - None handling
    {
        "fingerprint_pattern": r"TypeError: '(\w+)' object is not (subscriptable|iterable|callable)",
        "safety_category": "safe",
        "action": {
            "action_type": "diff",
            "requires_context": True,  # Need to see the code
        },
    },
    # pytest fixture
    {
        "fingerprint_pattern": r"fixture '(\w+)' not found",
        "safety_category": "safe",
        "action": {
            "action_type": "multi_step",
            "steps": [
                {"action_type": "command", "command": "grep -r 'def {match_1}' tests/"},
            ],
        },
    },
    # Node.js
    {
        "fingerprint_pattern": r"Cannot find module '(.+)'",
        "safety_category": "safe",
        "action": {
            "action_type": "command",
            "command": "npm install {match_1}",
        },
    },
    # Go
    {
        "fingerprint_pattern": r"cannot find package \"(.+)\"",
        "safety_category": "safe",
        "action": {
            "action_type": "command",
            "command": "go get {match_1}",
        },
    },
    # ... ~25 more patterns
]

async def seed_patterns(client: HealingSupabaseClient) -> int:
    """Seed pre-built patterns. Returns count inserted."""
    count = 0
    for pattern_def in PRESEEDED_PATTERNS:
        # Generate fingerprint from pattern
        fingerprint = hashlib.sha256(pattern_def["fingerprint_pattern"].encode()).hexdigest()[:16]

        pattern = {
            "fingerprint": fingerprint,
            "fingerprint_coarse": fingerprint[:8],
            "is_preseeded": True,
            "safety_category": pattern_def["safety_category"],
        }
        await client.record_pattern(pattern)

        # Create learning
        learning = {
            "title": f"Fix for: {pattern_def['fingerprint_pattern'][:50]}",
            "action": pattern_def["action"],
            "lifecycle": "active",  # Pre-seeded start as active
            "confidence": 0.8,
        }
        await client.client.table("learnings").insert(learning).execute()
        count += 1

    return count
```

#### 2.6 Pattern Generator (NEW - from review)
```python
# src/healing/pattern_generator.py

class PatternGenerator:
    """Generate fix patterns from successful resolutions."""

    def __init__(self, llm_client):
        self.llm = llm_client

    async def generate_from_diff(
        self,
        error: ErrorEvent,
        fix_diff: str,
        context: str = None,
    ) -> dict:
        """Use LLM to generalize a specific fix into a reusable pattern."""

        prompt = f"""Analyze this error and fix to create a reusable pattern.

ERROR:
{error.description}

FIX DIFF:
{fix_diff}

{f"CONTEXT:{chr(10)}{context}" if context else ""}

Create a generalized fix pattern that could apply to similar errors.
Return JSON with:
- fingerprint_pattern: regex to match similar errors
- safety_category: "safe", "moderate", or "risky"
- action: the fix action (diff, command, or file_edit)
- confidence: 0.0-1.0 how confident this pattern will work
"""

        response = await self.llm.complete(prompt)
        return json.loads(response)

    async def extract_from_transcript(
        self,
        transcript: str,
        errors: list[ErrorEvent],
    ) -> list[dict]:
        """Find error→fix sequences in conversation history."""

        prompt = f"""Analyze this transcript to find error resolutions.

KNOWN ERRORS:
{json.dumps([e.description for e in errors])}

TRANSCRIPT:
{transcript}

For each error that was fixed, return JSON array with:
- error_index: which error was fixed (0-indexed)
- fix_description: what was done to fix it
- suggested_pattern: if generalizable, the pattern
"""

        response = await self.llm.complete(prompt)
        return json.loads(response)
```

#### 2.7 Embedding Service
```python
# src/healing/embeddings.py
import openai

class EmbeddingService:
    """Generate embeddings for RAG."""

    def __init__(self, api_key: str, model: str = "text-embedding-ada-002"):
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        response = await self.client.embeddings.create(
            model=self.model,
            input=text,
        )
        return response.data[0].embedding

    async def embed_error(self, error: ErrorEvent) -> list[float]:
        """Generate embedding for error (combines relevant fields)."""
        text = f"{error.error_type or ''}: {error.description}"
        if error.file_path:
            text += f" in {error.file_path}"
        return await self.embed(text)
```

#### 2.8 Healing Client (Unified with Adapters)
```python
# src/healing/client.py

class HealingClient:
    """Unified client with environment-aware adapters."""

    def __init__(
        self,
        supabase_client: HealingSupabaseClient,
        cache: CacheAdapter,
        embedding_service: EmbeddingService,
    ):
        self.supabase = supabase_client
        self.cache = cache
        self.embeddings = embedding_service

    async def lookup(self, error: ErrorEvent) -> "LookupResult":
        """Three-tier lookup."""

        # Tier 1: Exact match (check cache first)
        cached = await self.cache.get(f"pattern:{error.fingerprint}")
        if cached:
            return LookupResult(tier=1, pattern=cached, source="cache")

        pattern = await self.supabase.lookup_pattern(error.fingerprint)
        if pattern:
            await self.cache.set(f"pattern:{error.fingerprint}", pattern)
            return LookupResult(tier=1, pattern=pattern, source="supabase")

        # Tier 2: RAG semantic search
        embedding = await self.embeddings.embed_error(error)
        similar = await self.supabase.lookup_similar(embedding)
        if similar and similar[0].get("similarity", 0) > 0.85:
            return LookupResult(tier=2, pattern=similar[0], source="rag")

        # Tier 3: Causality (for investigation, not auto-fix)
        causes = await self.supabase.get_causes(error.fingerprint)

        return LookupResult(
            tier=3 if causes else None,
            pattern=None,
            causes=causes,
            source="none",
        )
```

### Dependencies
- Phase 0 (adapters)
- Phase 1 (ErrorEvent, Fingerprinter, Config)

### Done Criteria
- [ ] Supabase schema deployed to `igalnlhcblswjtwaruvy.supabase.co`
- [ ] Pre-seeded patterns loaded (~30)
- [ ] Security scrubber removes secrets before storage
- [ ] Three-tier lookup returns results
- [ ] Embedding generation works
- [ ] Pattern generator creates patterns from diffs
- [ ] Cache works (local SQLite or in-memory for cloud)
- [ ] Works in both LOCAL and CLOUD environments
- [ ] Concurrent access tested (multiple workflows)

### Tests
```
tests/healing/
├── test_supabase_client.py
├── test_security.py
├── test_preseeded.py
├── test_pattern_generator.py
├── test_embeddings.py
├── test_healing_client.py
└── test_lookup_tiers.py
```

---

## Phase 3a: Validation Logic

**Goal:** Implement validation pipeline (testable without actually applying fixes).

### Components

#### 3a.1 Safety Categorizer
```python
# src/healing/safety.py
import re

class SafetyCategorizer:
    """Categorize fix safety based on diff analysis."""

    def categorize(self, diff: str, affected_files: list[str]) -> SafetyCategory:
        """Analyze diff and return safety category."""

        # Check protected paths first
        for path in affected_files:
            if self._is_protected(path):
                return SafetyCategory.RISKY

        # Analyze diff content
        if self._only_formatting(diff):
            return SafetyCategory.SAFE

        if self._only_imports(diff):
            return SafetyCategory.SAFE

        if self._only_type_hints(diff):
            return SafetyCategory.SAFE

        if self._changes_function_signature(diff):
            return SafetyCategory.RISKY

        if self._changes_return_type(diff):
            return SafetyCategory.RISKY

        if self._modifies_error_handling(diff):
            return SafetyCategory.MODERATE

        if self._modifies_conditionals(diff):
            return SafetyCategory.MODERATE

        # Default to moderate
        return SafetyCategory.MODERATE

    def _is_protected(self, path: str) -> bool:
        from fnmatch import fnmatch
        for pattern in CONFIG.protected_paths:
            if fnmatch(path, pattern):
                return True
        return False

    def _only_formatting(self, diff: str) -> bool:
        # Only whitespace changes
        added = [l for l in diff.split('\n') if l.startswith('+') and not l.startswith('+++')]
        removed = [l for l in diff.split('\n') if l.startswith('-') and not l.startswith('---')]
        # Compare stripped versions
        return [l[1:].strip() for l in added] == [l[1:].strip() for l in removed]

    def _only_imports(self, diff: str) -> bool:
        added = [l for l in diff.split('\n') if l.startswith('+') and not l.startswith('+++')]
        for line in added:
            content = line[1:].strip()
            if content and not (content.startswith('import ') or content.startswith('from ')):
                return False
        return True

    # ... other analysis methods
```

#### 3a.2 Multi-Model Judge
```python
# src/healing/judges.py
import asyncio
from dataclasses import dataclass

@dataclass
class JudgeVote:
    model: str
    approved: bool
    confidence: float
    reasoning: str
    issues: list[str]

@dataclass
class JudgeResult:
    approved: bool
    votes: list[JudgeVote]
    consensus_score: float

class MultiModelJudge:
    """Multi-model validation for fixes."""

    # Updated: includes Gemini
    DEFAULT_MODELS = [
        "claude-opus-4-5",
        "gemini-3-pro",
        "gpt-5.2",
        "grok-4.1",
    ]

    def __init__(self, models: list[str] = None, api_keys: dict = None):
        self.models = models or self.DEFAULT_MODELS
        self.api_keys = api_keys or {}

    async def judge(
        self,
        fix: "SuggestedFix",
        error: ErrorEvent,
        safety_category: SafetyCategory,
    ) -> JudgeResult:
        """Get votes from multiple models based on safety category."""

        # Tiered judge count
        judge_count = self._get_judge_count(safety_category)
        selected_models = self.models[:judge_count]

        # Parallel judging with timeout
        tasks = [
            asyncio.wait_for(
                self._get_vote(model, fix, error),
                timeout=CONFIG.judge_timeout_seconds
            )
            for model in selected_models
        ]

        votes = []
        for coro in asyncio.as_completed(tasks):
            try:
                vote = await coro
                votes.append(vote)
            except asyncio.TimeoutError:
                # Record timeout but continue
                votes.append(JudgeVote(
                    model="timeout",
                    approved=False,
                    confidence=0,
                    reasoning="Judge timed out",
                    issues=["timeout"],
                ))

        # Calculate consensus
        approvals = sum(1 for v in votes if v.approved)
        threshold = (judge_count // 2) + 1

        return JudgeResult(
            approved=approvals >= threshold,
            votes=votes,
            consensus_score=approvals / len(votes) if votes else 0,
        )

    def _get_judge_count(self, safety: SafetyCategory) -> int:
        """Tiered validation: more judges for riskier fixes."""
        if safety == SafetyCategory.SAFE:
            return 1
        elif safety == SafetyCategory.MODERATE:
            return 2
        else:  # RISKY
            return 3

    async def _get_vote(self, model: str, fix: "SuggestedFix", error: ErrorEvent) -> JudgeVote:
        """Get a single model's vote."""
        prompt = self._build_judge_prompt(fix, error)

        # Route to appropriate API
        if "claude" in model:
            response = await self._call_anthropic(model, prompt)
        elif "gemini" in model:
            response = await self._call_google(model, prompt)
        elif "gpt" in model:
            response = await self._call_openai(model, prompt)
        elif "grok" in model:
            response = await self._call_xai(model, prompt)

        return self._parse_vote(model, response)

    def _build_judge_prompt(self, fix: "SuggestedFix", error: ErrorEvent) -> str:
        return f"""You are reviewing an automated code fix. Evaluate whether this fix is safe to apply.

ERROR:
{error.description}

PROPOSED FIX:
{fix.diff or fix.action}

SAFETY CATEGORY: {fix.safety_category}

Evaluate:
1. Does this fix address the actual error?
2. Could this fix introduce new bugs?
3. Are there any security concerns?
4. Is the fix minimal and focused?

Respond with JSON:
{{
    "approved": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "explanation",
    "issues": ["list", "of", "concerns"]
}}
"""
```

#### 3a.3 Validation Pipeline
```python
# src/healing/validation.py
import asyncio
from dataclasses import dataclass
from enum import Enum

class ValidationPhase(Enum):
    PRE_FLIGHT = "pre_flight"
    VERIFICATION = "verification"
    APPROVAL = "approval"

@dataclass
class ValidationResult:
    approved: bool
    phase: ValidationPhase
    reason: str
    votes: list[JudgeVote] = None
    verification_output: dict = None

class ValidationPipeline:
    """3-phase validation pipeline."""

    def __init__(
        self,
        config: HealingConfig,
        judge: MultiModelJudge,
        execution: ExecutionAdapter,
        cascade_detector: "CascadeDetector",
    ):
        self.config = config
        self.judge = judge
        self.execution = execution
        self.cascade = cascade_detector

    async def validate(
        self,
        fix: "SuggestedFix",
        error: ErrorEvent,
    ) -> ValidationResult:
        """Run all validation phases."""

        # PHASE 1: Pre-flight (parallel fast checks)
        preflight = await self._run_preflight(fix, error)
        if not preflight.approved:
            return preflight

        # PHASE 2: Verification (parallel build/test/lint)
        verification = await self._run_verification(fix)
        if not verification.approved:
            return verification

        # PHASE 3: Approval (tiered multi-model)
        approval = await self._run_approval(fix, error)
        return approval

    async def _run_preflight(self, fix: "SuggestedFix", error: ErrorEvent) -> ValidationResult:
        """Phase 1: Fast parallel checks."""

        checks = await asyncio.gather(
            self._check_kill_switch(),
            self._check_hard_constraints(fix),
            self._check_precedent(fix),
            self._check_cascade(error),
            return_exceptions=True,
        )

        for i, result in enumerate(checks):
            if isinstance(result, Exception):
                return ValidationResult(
                    approved=False,
                    phase=ValidationPhase.PRE_FLIGHT,
                    reason=f"Check failed with error: {result}",
                )
            if not result[0]:  # (passed, reason) tuple
                return ValidationResult(
                    approved=False,
                    phase=ValidationPhase.PRE_FLIGHT,
                    reason=result[1],
                )

        return ValidationResult(
            approved=True,
            phase=ValidationPhase.PRE_FLIGHT,
            reason="All pre-flight checks passed",
        )

    async def _run_verification(self, fix: "SuggestedFix") -> ValidationResult:
        """Phase 2: Parallel build/test/lint."""

        results = await asyncio.gather(
            self._run_build_check(fix),
            self._run_test_check(fix),
            self._run_lint_check(fix),
            return_exceptions=True,
        )

        verification_output = {}
        for name, result in zip(["build", "test", "lint"], results):
            if isinstance(result, Exception):
                return ValidationResult(
                    approved=False,
                    phase=ValidationPhase.VERIFICATION,
                    reason=f"{name} failed with error: {result}",
                )
            verification_output[name] = result
            if not result.passed:
                return ValidationResult(
                    approved=False,
                    phase=ValidationPhase.VERIFICATION,
                    reason=f"{name} failed: {result.message}",
                    verification_output=verification_output,
                )

        return ValidationResult(
            approved=True,
            phase=ValidationPhase.VERIFICATION,
            reason="All verification checks passed",
            verification_output=verification_output,
        )

    async def _run_approval(self, fix: "SuggestedFix", error: ErrorEvent) -> ValidationResult:
        """Phase 3: Multi-model approval."""

        # RISKY never auto-applies
        if fix.safety_category == SafetyCategory.RISKY:
            return ValidationResult(
                approved=False,
                phase=ValidationPhase.APPROVAL,
                reason="RISKY category - queued for review",
            )

        judge_result = await self.judge.judge(fix, error, fix.safety_category)

        return ValidationResult(
            approved=judge_result.approved,
            phase=ValidationPhase.APPROVAL,
            reason=f"{sum(1 for v in judge_result.votes if v.approved)}/{len(judge_result.votes)} judges approved",
            votes=judge_result.votes,
        )

    # Pre-flight check implementations
    async def _check_kill_switch(self) -> tuple[bool, str]:
        if self.config.kill_switch_active:
            return False, "Kill switch is active"
        return True, "OK"

    async def _check_hard_constraints(self, fix: "SuggestedFix") -> tuple[bool, str]:
        if len(fix.affected_files) > 2:
            return False, f"Too many files affected ({len(fix.affected_files)} > 2)"
        if fix.lines_changed > 30:
            return False, f"Too many lines changed ({fix.lines_changed} > 30)"
        return True, "OK"

    async def _check_precedent(self, fix: "SuggestedFix") -> tuple[bool, str]:
        pattern = fix.pattern
        if not pattern:
            return False, "No pattern found"
        if pattern.get("is_preseeded"):
            return True, "Pre-seeded pattern"
        if pattern.get("verified_apply_count", 0) >= 5:
            return True, "Verified AI precedent"
        if pattern.get("human_correction_count", 0) >= 1:
            return True, "Human precedent"
        return False, "No precedent established"

    async def _check_cascade(self, error: ErrorEvent) -> tuple[bool, str]:
        if error.file_path and self.cascade.is_file_hot(error.file_path):
            return False, f"File {error.file_path} is hot (potential cascade)"
        return True, "OK"
```

#### 3a.4 Cost Controls
```python
# src/healing/costs.py
from dataclasses import dataclass, field
from datetime import datetime, date

@dataclass
class CostTracker:
    """Track and limit API costs."""

    # Daily tracking
    _daily_cost: float = 0.0
    _daily_validations: int = 0
    _daily_embeddings: int = 0
    _current_date: date = field(default_factory=lambda: date.today())

    # Cost estimates per operation
    COSTS = {
        "embedding": 0.0002,  # Per error
        "judge_claude": 0.05,
        "judge_gemini": 0.02,
        "judge_gpt": 0.05,
        "judge_grok": 0.02,
    }

    def can_validate(self, safety: SafetyCategory) -> tuple[bool, str]:
        """Check if we can afford another validation."""
        self._maybe_reset_daily()

        if self._daily_cost >= CONFIG.max_daily_cost_usd:
            return False, f"Daily cost limit reached (${self._daily_cost:.2f})"

        if self._daily_validations >= CONFIG.max_validations_per_day:
            return False, f"Daily validation limit reached ({self._daily_validations})"

        # Estimate this validation's cost
        judge_count = {
            SafetyCategory.SAFE: 1,
            SafetyCategory.MODERATE: 2,
            SafetyCategory.RISKY: 3,
        }[safety]
        estimated_cost = judge_count * 0.05  # Average judge cost

        if self._daily_cost + estimated_cost > CONFIG.max_daily_cost_usd:
            return False, f"Would exceed daily limit"

        return True, "OK"

    def record(self, operation: str, count: int = 1) -> None:
        """Record an operation's cost."""
        self._maybe_reset_daily()
        cost = self.COSTS.get(operation, 0) * count
        self._daily_cost += cost

        if operation.startswith("judge"):
            self._daily_validations += 1
        elif operation == "embedding":
            self._daily_embeddings += count

    def get_status(self) -> dict:
        """Get current cost status."""
        self._maybe_reset_daily()
        return {
            "daily_cost_usd": round(self._daily_cost, 4),
            "daily_limit_usd": CONFIG.max_daily_cost_usd,
            "daily_validations": self._daily_validations,
            "validation_limit": CONFIG.max_validations_per_day,
            "budget_remaining_usd": round(CONFIG.max_daily_cost_usd - self._daily_cost, 4),
        }

    def _maybe_reset_daily(self) -> None:
        today = date.today()
        if today > self._current_date:
            self._daily_cost = 0.0
            self._daily_validations = 0
            self._daily_embeddings = 0
            self._current_date = today
```

#### 3a.5 Cascade Detector
```python
# src/healing/cascade.py
from collections import defaultdict
from datetime import datetime, timedelta

class CascadeDetector:
    """Detect fix cascades (ping-pong fixes)."""

    def __init__(self, max_mods_per_hour: int = 3):
        self.max_mods_per_hour = max_mods_per_hour
        self._file_mods: dict[str, list[datetime]] = defaultdict(list)

    def record_modification(self, file_path: str) -> None:
        """Record that we modified a file."""
        self._file_mods[file_path].append(datetime.utcnow())

    def is_file_hot(self, file_path: str) -> bool:
        """Check if file has been modified too often recently."""
        if file_path not in self._file_mods:
            return False

        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent = [t for t in self._file_mods[file_path] if t > one_hour_ago]

        return len(recent) >= self.max_mods_per_hour

    def check_cascade(
        self,
        error: ErrorEvent,
        recent_fixes: list["AppliedFix"],
    ) -> str | None:
        """Check if error was likely caused by a recent fix."""
        for fix in recent_fixes:
            if error.file_path in fix.affected_files:
                time_since_fix = error.timestamp - fix.applied_at
                if time_since_fix < timedelta(minutes=30):
                    return fix.fix_id  # Likely caused by this fix
        return None
```

### Dependencies
- Phase 0 (adapters)
- Phase 1 (ErrorEvent, Config)
- Phase 2 (HealingClient, patterns)

### Done Criteria
- [ ] Safety categorization works on real diffs
- [ ] Multi-model judge returns votes (with Gemini)
- [ ] 3-phase validation runs in parallel
- [ ] Cost controls enforce limits
- [ ] Cascade detection prevents ping-pong
- [ ] Timeout handling for all external calls
- [ ] Works without actually applying fixes (testable in isolation)

### Tests
```
tests/healing/
├── test_safety.py
├── test_judges.py
├── test_validation.py
├── test_costs.py
└── test_cascade.py
```

---

## Phase 3b: Fix Application

**Goal:** Actually apply fixes using environment-aware adapters.

### Components

#### 3b.1 Fix Applicator
```python
# src/healing/applicator.py
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ApplyResult:
    success: bool
    fix_id: str
    branch: str = None
    pr_url: str = None
    commit_sha: str = None
    error: str = None
    rollback_available: bool = False

class FixApplicator:
    """Apply fixes using environment-appropriate adapters."""

    def __init__(
        self,
        git: GitAdapter,
        storage: StorageAdapter,
        execution: ExecutionAdapter,
        supabase: HealingSupabaseClient,
    ):
        self.git = git
        self.storage = storage
        self.execution = execution
        self.supabase = supabase

    async def apply(
        self,
        fix: "SuggestedFix",
        error: ErrorEvent,
        validation_result: ValidationResult,
    ) -> ApplyResult:
        """Apply fix and verify."""

        fix_id = f"fix-{error.fingerprint[:8]}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        branch = f"fix/auto-{fix_id}"

        try:
            # 1. Create branch
            await self.git.create_branch(branch)

            # 2. Apply the fix
            if fix.action.action_type == "diff":
                commit_sha = await self.git.apply_diff(fix.action.diff, f"fix: {fix.title}")
            elif fix.action.action_type == "command":
                await self.execution.run_command(fix.action.command)
                commit_sha = await self.git.apply_diff("", f"fix: ran {fix.action.command}")
            elif fix.action.action_type == "file_edit":
                content = await self.storage.read_file(fix.action.file_path)
                new_content = content.replace(fix.action.find, fix.action.replace)
                await self.storage.write_file(fix.action.file_path, new_content)
                commit_sha = await self.git.apply_diff("", f"fix: edit {fix.action.file_path}")

            # 3. Run verification
            verify_result = await self._verify(fix)

            if not verify_result.passed:
                # Rollback
                await self.git.delete_branch(branch)
                await self.supabase.record_fix_result(error.fingerprint, success=False)
                return ApplyResult(
                    success=False,
                    fix_id=fix_id,
                    error=f"Verification failed: {verify_result.message}",
                )

            # 4. Create PR or merge directly based on environment/safety
            if ENVIRONMENT == Environment.CLOUD or fix.safety_category != SafetyCategory.SAFE:
                # Create PR for review
                pr_url = await self.git.create_pr(
                    title=f"fix: {fix.title}",
                    body=self._build_pr_body(fix, error, validation_result),
                    head=branch,
                    base="main",
                )
                result = ApplyResult(
                    success=True,
                    fix_id=fix_id,
                    branch=branch,
                    pr_url=pr_url,
                    commit_sha=commit_sha,
                )
            else:
                # Merge directly (local + SAFE)
                await self.git.merge_branch(branch, into="main")
                await self.git.delete_branch(branch)
                result = ApplyResult(
                    success=True,
                    fix_id=fix_id,
                    commit_sha=commit_sha,
                )

            # Record success
            await self.supabase.record_fix_result(error.fingerprint, success=True)
            await self.supabase.audit_log("fix_applied", {
                "fix_id": fix_id,
                "fingerprint": error.fingerprint,
                "pr_url": pr_url if 'pr_url' in dir() else None,
            })

            return result

        except Exception as e:
            # Attempt cleanup
            try:
                await self.git.delete_branch(branch)
            except:
                pass

            await self.supabase.audit_log("fix_failed", {
                "fix_id": fix_id,
                "fingerprint": error.fingerprint,
                "error": str(e),
            })

            return ApplyResult(
                success=False,
                fix_id=fix_id,
                error=str(e),
            )

    async def rollback(self, fix_id: str) -> bool:
        """Rollback a fix."""
        # Implementation depends on whether it was merged or PR
        pass

    async def _verify(self, fix: "SuggestedFix") -> "VerifyResult":
        """Run verification suite."""
        build = await self.execution.run_build()
        if not build.passed:
            return VerifyResult(passed=False, message=f"Build failed: {build.error}")

        tests = await self.execution.run_tests()
        if not tests.passed:
            return VerifyResult(passed=False, message=f"Tests failed: {tests.error}")

        return VerifyResult(passed=True, message="All checks passed")

    def _build_pr_body(
        self,
        fix: "SuggestedFix",
        error: ErrorEvent,
        validation: ValidationResult,
    ) -> str:
        return f"""## Automated Fix

**Error:** {error.description[:200]}

**Fix:** {fix.title}

**Safety Category:** {fix.safety_category}

**Validation:**
- Pre-flight: ✅
- Verification: ✅
- Approval: {validation.votes}

---
*Generated by Self-Healing Infrastructure*
"""
```

#### 3b.2 Context Retriever (NEW - from Gemini's insight)
```python
# src/healing/context.py

class ContextRetriever:
    """Retrieve file context for fix generation."""

    def __init__(self, storage: StorageAdapter):
        self.storage = storage

    async def get_context(self, error: ErrorEvent, fix_action: FixAction) -> str:
        """Get relevant context for generating/applying a fix."""

        context_parts = []

        # Error file content
        if error.file_path:
            try:
                content = await self.storage.read_file(error.file_path)
                context_parts.append(f"## {error.file_path}\n```\n{content}\n```")
            except:
                pass

        # Additional context files from fix action
        for path in fix_action.context_files:
            try:
                content = await self.storage.read_file(path)
                context_parts.append(f"## {path}\n```\n{content}\n```")
            except:
                pass

        return "\n\n".join(context_parts)

    async def get_related_files(self, file_path: str) -> list[str]:
        """Find related files (imports, tests, etc.)."""
        related = []

        # Find test file
        if not file_path.startswith("test_"):
            test_path = file_path.replace(".py", "_test.py")
            if await self.storage.file_exists(test_path):
                related.append(test_path)

        # Find imports (simplified)
        try:
            content = await self.storage.read_file(file_path)
            imports = re.findall(r'from ([\w.]+) import', content)
            # Convert to paths and check existence
            # ...
        except:
            pass

        return related
```

### Dependencies
- Phase 0 (adapters - critical for cloud support)
- Phase 1-2 (models, client)
- Phase 3a (validation)

### Done Criteria
- [ ] Fix application works locally (git CLI)
- [ ] Fix application works in cloud (GitHub API PRs)
- [ ] Context retriever provides file content
- [ ] Verification runs build/test/lint
- [ ] Rollback works on failure
- [ ] PRs created for MODERATE+ or cloud environment
- [ ] Direct merge for SAFE + local
- [ ] Audit log records all actions

### Tests
```
tests/healing/
├── test_applicator_local.py
├── test_applicator_cloud.py
├── test_context.py
└── test_rollback.py
```

---

## Phase 4: CLI & Workflow Integration

**Goal:** User-facing commands and workflow hooks.

### Components

#### 4.1 CLI Commands
```python
# src/workflow_orchestrator/commands/heal.py
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Self-healing commands")
console = Console()

@app.command()
def status():
    """Show healing system status."""
    client = get_healing_client()

    # Get stats
    stats = asyncio.run(client.get_stats())
    costs = cost_tracker.get_status()

    table = Table(title="Healing Status")
    table.add_column("Metric")
    table.add_column("Value")

    table.add_row("Environment", ENVIRONMENT.value)
    table.add_row("Enabled", "✅" if CONFIG.enabled else "❌")
    table.add_row("Kill Switch", "🛑 ACTIVE" if CONFIG.kill_switch_active else "✅ Off")
    table.add_row("Patterns", str(stats["pattern_count"]))
    table.add_row("Today's Cost", f"${costs['daily_cost_usd']:.2f} / ${costs['daily_limit_usd']:.2f}")
    table.add_row("Validations", f"{costs['daily_validations']} / {costs['validation_limit']}")

    console.print(table)

@app.command()
def apply(
    fix_id: str = typer.Argument(..., help="Fix ID to apply"),
    force: bool = typer.Option(False, "--force", help="Bypass safety checks"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen"),
):
    """Apply a suggested fix."""
    client = get_healing_client()

    if dry_run:
        result = asyncio.run(client.preview_fix(fix_id))
        console.print(f"Would apply: {result}")
        return

    if force:
        console.print("[yellow]⚠️  Force mode - bypassing safety checks[/yellow]")

    result = asyncio.run(client.apply_fix(fix_id, force=force))

    if result.success:
        console.print(f"[green]✅ Fix applied[/green]")
        if result.pr_url:
            console.print(f"   PR: {result.pr_url}")
    else:
        console.print(f"[red]❌ Fix failed: {result.error}[/red]")

@app.command()
def ignore(
    fingerprint: str = typer.Argument(..., help="Error fingerprint to ignore"),
    reason: str = typer.Option(..., "--reason", "-r", help="Why ignoring"),
):
    """Permanently ignore an error pattern."""
    client = get_healing_client()
    asyncio.run(client.ignore_pattern(fingerprint, reason))
    console.print(f"[green]✅ Pattern {fingerprint} ignored[/green]")

@app.command()
def unquarantine(
    fingerprint: str = typer.Argument(..., help="Pattern fingerprint"),
    reason: str = typer.Option(..., "--reason", "-r", help="Why unquarantining"),
):
    """Reset a quarantined pattern."""
    client = get_healing_client()
    asyncio.run(client.unquarantine_pattern(fingerprint, reason))
    console.print(f"[green]✅ Pattern {fingerprint} unquarantined[/green]")

@app.command()
def explain(fingerprint: str = typer.Argument(..., help="Error fingerprint")):
    """Show why a fix wasn't auto-applied."""
    client = get_healing_client()
    result = asyncio.run(client.explain(fingerprint))

    console.print(f"\n[bold]Error:[/bold] {result['error_description'][:100]}")
    console.print(f"\n[bold]Why not auto-applied:[/bold]")
    for reason in result["reasons"]:
        console.print(f"  • {reason}")

    if result["suggestions"]:
        console.print(f"\n[bold]Suggestions:[/bold]")
        for suggestion in result["suggestions"]:
            console.print(f"  → {suggestion}")

@app.command()
def export(
    format: str = typer.Option("yaml", "--format", "-f", help="Output format (yaml/json)"),
    output: str = typer.Option(None, "--output", "-o", help="Output file"),
):
    """Export all patterns."""
    client = get_healing_client()
    data = asyncio.run(client.export_patterns(format))

    if output:
        Path(output).write_text(data)
        console.print(f"[green]✅ Exported to {output}[/green]")
    else:
        console.print(data)
```

#### 4.2 Issues Commands
```python
# src/workflow_orchestrator/commands/issues.py

app = typer.Typer(help="Issue queue commands")

@app.command("list")
def list_issues(
    status: str = typer.Option(None, "--status", "-s"),
    severity: str = typer.Option(None, "--severity"),
    limit: int = typer.Option(20, "--limit", "-n"),
):
    """List accumulated issues."""
    client = get_healing_client()
    issues = asyncio.run(client.list_issues(status=status, severity=severity, limit=limit))

    table = Table(title="Issues")
    table.add_column("Fingerprint", width=12)
    table.add_column("Error", width=40)
    table.add_column("Count")
    table.add_column("Status")
    table.add_column("Suggested Fix")

    for issue in issues:
        table.add_row(
            issue["fingerprint"][:12],
            issue["description"][:40],
            str(issue["count"]),
            issue["status"],
            "✅" if issue["has_fix"] else "❌",
        )

    console.print(table)

@app.command()
def review():
    """Interactive review of pending issues."""
    # TUI for reviewing issues
    pass
```

#### 4.3 Workflow Hooks
```python
# src/healing/hooks.py

class HealingHooks:
    """Hooks into workflow orchestrator."""

    def __init__(self, client: HealingClient, accumulator: ErrorAccumulator):
        self.client = client
        self.accumulator = accumulator

    async def on_phase_complete(self, phase: str, result: dict) -> None:
        """Called after each workflow phase."""
        # Detect errors from phase result
        detector = WorkflowLogDetector(Fingerprinter())
        errors = await detector.detect(result.get("log", ""))

        for error in errors:
            self.accumulator.add(error)

    async def on_subprocess_complete(
        self,
        command: str,
        exit_code: int,
        stdout: str,
        stderr: str,
    ) -> None:
        """Hook for subprocess monitoring."""
        if exit_code != 0:
            detector = SubprocessDetector(Fingerprinter())
            errors = await detector.detect(exit_code, stdout, stderr, command)

            for error in errors:
                self.accumulator.add(error)

    async def on_workflow_complete(self, workflow_id: str) -> None:
        """Called when workflow finishes."""
        errors = self.accumulator.get_unique_errors()

        if not errors:
            return

        # Present summary
        console.print(f"\n[bold]Detected {len(errors)} unique errors:[/bold]")

        for error in errors:
            # Check for fix
            result = await self.client.lookup(error)
            fix_available = result.pattern is not None

            console.print(f"  • {error.description[:60]}...")
            if fix_available:
                console.print(f"    [green]Fix available[/green] (tier {result.tier})")
            else:
                console.print(f"    [yellow]No fix found[/yellow]")

        # Offer batch actions
        if any(await self.client.lookup(e) for e in errors):
            console.print("\nRun 'orchestrator issues review' to apply fixes")

    async def on_learn_phase_complete(self, workflow_id: str, learnings: list) -> None:
        """Extract learnings and feed to pattern memory."""
        generator = PatternGenerator(self.client.llm)

        for learning in learnings:
            if learning.get("type") == "error_resolution":
                # Generate pattern from this learning
                pattern = await generator.generate_from_diff(
                    error=learning["error"],
                    fix_diff=learning["fix_diff"],
                    context=learning.get("context"),
                )
                await self.client.supabase.record_pattern(pattern)
```

### Dependencies
- Phases 0-3 (all core functionality)

### Done Criteria
- [ ] All `orchestrator heal` commands work
- [ ] All `orchestrator issues` commands work
- [ ] Workflow hooks integrated
- [ ] LEARN phase feeds pattern memory
- [ ] Works in both LOCAL and CLOUD environments
- [ ] Help text complete
- [ ] Batch operations handle partial failures

### Tests
```
tests/healing/
├── test_cli_heal.py
├── test_cli_issues.py
├── test_hooks.py
└── test_learn_integration.py
```

---

## Phase 5: Observability & Hardening

**Goal:** Production-ready with monitoring, circuit breakers, and optimizations.

### Components

#### 5.1 Metrics & Dashboard
```python
# src/healing/metrics.py

class HealingMetrics:
    """Collect and report metrics."""

    async def get_dashboard_data(self, days: int = 30) -> dict:
        """Get metrics for dashboard."""
        return {
            "detection_rate": await self._calc_detection_rate(days),
            "auto_fix_rate": await self._calc_auto_fix_rate(days),
            "success_rate": await self._calc_success_rate(days),
            "cost_history": await self._get_cost_history(days),
            "pattern_growth": await self._get_pattern_growth(days),
            "top_errors": await self._get_top_errors(days),
        }
```

#### 5.2 Circuit Breaker
```python
# src/healing/circuit_breaker.py

class HealingCircuitBreaker:
    """Prevent runaway auto-fixing."""

    def __init__(
        self,
        max_reverts_per_hour: int = 2,
        cooldown_minutes: int = 30,
    ):
        self.max_reverts_per_hour = max_reverts_per_hour
        self.cooldown_minutes = cooldown_minutes
        self._state = "closed"  # closed, open, half-open
        self._reverts: list[datetime] = []
        self._opened_at: datetime = None

    def record_revert(self) -> None:
        """Record a fix revert."""
        self._reverts.append(datetime.utcnow())
        self._check_threshold()

    def should_allow_fix(self) -> tuple[bool, str]:
        """Check if fixes are allowed."""
        if self._state == "open":
            if self._should_try_half_open():
                self._state = "half-open"
                return True, "Circuit half-open - allowing test fix"
            return False, f"Circuit open - cooling down until {self._opened_at + timedelta(minutes=self.cooldown_minutes)}"

        return True, "OK"

    def _check_threshold(self) -> None:
        """Trip circuit if too many reverts."""
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_reverts = [r for r in self._reverts if r > one_hour_ago]

        if len(recent_reverts) >= self.max_reverts_per_hour:
            self._state = "open"
            self._opened_at = datetime.utcnow()
```

#### 5.3 Flakiness Detection
```python
# src/healing/flakiness.py

class FlakinessDetector:
    """Detect flaky errors that appear intermittently."""

    async def is_flaky(self, fingerprint: str, window_hours: int = 24) -> bool:
        """Check if error appears intermittently."""
        occurrences = await self._get_occurrences(fingerprint, window_hours)

        if len(occurrences) < 3:
            return False  # Not enough data

        # Check for inconsistent timing (flaky indicator)
        intervals = [
            (occurrences[i+1] - occurrences[i]).total_seconds()
            for i in range(len(occurrences) - 1)
        ]

        # High variance in intervals suggests flakiness
        if intervals:
            variance = statistics.variance(intervals) if len(intervals) > 1 else 0
            return variance > 3600  # More than 1 hour variance

        return False

    def get_determinism_score(self, fingerprint: str) -> float:
        """0.0 = always flaky, 1.0 = always deterministic."""
        # Implementation
        pass
```

#### 5.4 Historical Backfill (from Grok's insight)
```python
# src/healing/backfill.py

class HistoricalBackfill:
    """Process existing logs from before the system existed."""

    async def backfill_workflow_logs(self, log_dir: Path) -> int:
        """Process historical workflow logs."""
        count = 0
        for log_file in log_dir.glob("*.jsonl"):
            detector = WorkflowLogDetector(Fingerprinter())
            errors = await detector.detect(log_file)
            for error in errors:
                await self.client.record_historical_error(error)
                count += 1
        return count
```

#### 5.5 Local Caching Optimization
```python
# src/healing/cache_optimizer.py

class CacheOptimizer:
    """Optimize local cache for frequently accessed patterns."""

    async def warm_cache(self, client: HealingClient) -> int:
        """Pre-load frequently used patterns into local cache."""
        if ENVIRONMENT != Environment.LOCAL:
            return 0  # No local cache in cloud

        # Get top patterns
        top_patterns = await client.supabase.get_top_patterns(limit=100)

        for pattern in top_patterns:
            await client.cache.set(
                f"pattern:{pattern['fingerprint']}",
                pattern,
                ttl_seconds=3600 * 24,  # 24 hours
            )

        return len(top_patterns)
```

### Dependencies
- Phases 0-4 (full system)

### Done Criteria
- [ ] Metrics endpoint returns dashboard data
- [ ] Circuit breaker prevents runaway fixes
- [ ] Flakiness detection works
- [ ] Historical backfill processes old logs
- [ ] Cache warming improves local performance
- [ ] All components have proper error handling
- [ ] Timeouts configured for all external calls

### Tests
```
tests/healing/
├── test_metrics.py
├── test_circuit_breaker.py
├── test_flakiness.py
├── test_backfill.py
└── test_cache_optimizer.py
```

---

## File Structure

```
src/
├── healing/
│   ├── __init__.py
│   ├── environment.py           # Environment detection
│   ├── config.py                # Configuration
│   ├── models.py                # Data models
│   │
│   ├── adapters/                # Phase 0: Abstraction layer
│   │   ├── __init__.py
│   │   ├── base.py              # Abstract interfaces
│   │   ├── storage_local.py
│   │   ├── storage_github.py
│   │   ├── git_local.py
│   │   ├── git_github.py
│   │   ├── cache_local.py
│   │   ├── cache_memory.py
│   │   ├── execution_local.py
│   │   ├── execution_github.py
│   │   └── factory.py
│   │
│   ├── fingerprint.py           # Phase 1
│   ├── detectors/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── workflow_log.py
│   │   ├── transcript.py
│   │   ├── subprocess.py
│   │   └── hook.py
│   ├── accumulator.py
│   │
│   ├── security.py              # Phase 2 (moved earlier)
│   ├── supabase_client.py
│   ├── embeddings.py
│   ├── preseeded_patterns.py
│   ├── pattern_generator.py
│   ├── client.py
│   │
│   ├── safety.py                # Phase 3a
│   ├── judges.py
│   ├── validation.py
│   ├── costs.py
│   ├── cascade.py
│   │
│   ├── applicator.py            # Phase 3b
│   ├── context.py
│   │
│   ├── hooks.py                 # Phase 4
│   │
│   ├── metrics.py               # Phase 5
│   ├── circuit_breaker.py
│   ├── flakiness.py
│   ├── backfill.py
│   └── cache_optimizer.py
│
├── workflow_orchestrator/
│   └── commands/
│       ├── heal.py
│       └── issues.py
│
└── migrations/
    └── 001_healing_schema.sql

tests/
└── healing/
    ├── adapters/
    │   └── ... (per adapter tests)
    ├── detectors/
    │   └── ... (per detector tests)
    └── ... (component tests)
```

---

## Implementation Order

```
Phase 0 (Abstraction) ─────────────────────────────────────────────────┐
   │ Required for cloud support                                        │
   │                                                                   │
   ▼                                                                   │
Phase 1 (Detection + Config) ──────────────────────────────────────┐   │
   │                                                               │   │
   ▼                                                               │   │
Phase 2 (Memory + Security) ───────────────────────────────────┐   │   │
   │                                                           │   │   │
   ├───────────────────────────────────────────────────────────┼───┼───┤
   │                                                           │   │   │
   ▼                                                           ▼   ▼   ▼
Phase 3a (Validation)                                      Phase 4
   │                                                       (CLI - read-only)
   ▼
Phase 3b (Application)
   │
   ▼
Phase 4 (CLI - write operations)
   │
   ▼
Phase 5 (Hardening)
```

**Key insight from review:** Phase 4 CLI can start in parallel with Phase 3a (read-only commands like `status`, `list`, `explain`), but write commands (`apply`, `ignore`) require Phase 3b.

---

## Open Questions (Resolved)

| Question | Resolution |
|----------|------------|
| Supabase project | `https://igalnlhcblswjtwaruvy.supabase.co` |
| Embedding model | OpenAI ada-002 (cloud fallback: can add local later) |
| Judge models | Claude, Gemini, GPT, Grok (4 models, tiered by safety) |
| Cloud support | Cloud-first architecture with adapters |
| GitHub Issues integration | Deferred - escalation path can be added later |

---

## Rollout Strategy

| Stage | Capability | Environments |
|-------|------------|--------------|
| 1 | Detection only (Phase 0-1) | Local + Cloud |
| 2 | Suggestions shown (Phase 2) | Local + Cloud |
| 3 | Auto-apply SAFE (Phase 3) | Local only first |
| 4 | Auto-apply SAFE in cloud | Local + Cloud |
| 5 | Auto-apply MODERATE if >90% success | Both |

**Kill switch:** Set `HEALING_KILL_SWITCH=true` or update Supabase config.
