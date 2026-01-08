# Multi-Agent Coordination & Merge Conflict Resolution System
## Final Design Specification v2.0

**Status:** Ready for Implementation
**Last Updated:** January 2026
**Target:** Workflow Orchestrator Extension

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [North Star: The Vibe Coder Experience](#2-north-star-the-vibe-coder-experience)
3. [System Architecture](#3-system-architecture)
4. [Security Model](#4-security-model)
5. [Agent Registration & Tracking](#5-agent-registration--tracking)
6. [Conflict Detection & Classification](#6-conflict-detection--classification)
7. [Resolution Pipeline](#7-resolution-pipeline)
8. [Human Escalation System](#8-human-escalation-system)
9. [Auto-Merge & PRD Execution Mode](#9-auto-merge--prd-execution-mode)
10. [Learning & Self-Improvement](#10-learning--self-improvement)
11. [Data Models](#11-data-models)
12. [Configuration](#12-configuration)
13. [GitHub Actions Workflows](#13-github-actions-workflows)
14. [New Modules to Implement](#14-new-modules-to-implement)
15. [Implementation Phases](#15-implementation-phases)
16. [Testing Strategy](#16-testing-strategy)
17. [Additional Features](#17-additional-features-from-design-review)
18. [Operational Resilience](#18-operational-resilience-from-ai-reviews)

---

## 1. Executive Summary

This system extends the workflow orchestrator to support **multiple concurrent AI agents** working on the same codebase. It automatically detects conflicts between their work, resolves them intelligently, and delivers unified PRs—all invisible to the user.

### Key Capabilities

- **Multi-agent coordination:** 10-50+ concurrent agents for full PRD execution
- **Automatic conflict detection:** Textual AND semantic conflicts
- **Intelligent resolution:** Intent-aware merging with multiple candidate strategies
- **Seamless UX:** User just works; system handles everything
- **Configurable auto-merge:** From fully manual to fully automated
- **Learning loop:** System improves over time

### Critical Design Decisions (from review feedback)

1. **Split GitHub Actions workflows** for security (untrusted trigger → trusted coordinator)
2. **Derive, don't trust** agent manifests (verify via git diff)
3. **Store manifests as artifacts**, not committed files (avoid path conflicts)
4. **Test merged results** in Stage 0, not just individual branches
5. **Port losing features** to winning architecture (don't orphan)
6. **Handle race conditions** with main branch
7. **Predictive test selection** to control costs
8. **Dedicated dependency resolver** for package conflicts

---

## 2. North Star: The Vibe Coder Experience

### What the user does:

```
Morning:
  Opens Claude Web: "Build user authentication"
  → Works for a while, then closes laptop

Afternoon:
  Opens Claude CLI: "Add a product catalog"
  → Works on it

Later:
  Opens Claude Web again: "Create checkout flow"
  → Works on it

Evening:
  Gets notification: "✓ All 3 features complete! Review PR: [link]"
  → Clicks "Merge" button
  → Done.
```

### What the user NEVER sees:

- Branch names or git commands
- Merge conflicts or resolution details
- Technical decisions (unless they ask)
- Coordination between agents

### When user input IS needed (rare):

```
┌────────────────────────────────────────────────────────────┐
│  🤔 Need your input (takes 30 seconds)                     │
│                                                            │
│  Two approaches to user sessions were built:               │
│                                                            │
│  [A] Cookie-based (simpler, web-only)                      │
│      Best for: Traditional web apps                        │
│      Risk: Low                                             │
│                                                            │
│  [B] JWT tokens (more complex, works everywhere)           │
│      Best for: Mobile apps, APIs                           │
│      Risk: Medium (more code to maintain)                  │
│                                                            │
│  Your app type: Web application (detected)                 │
│  Recommendation: A ✓                                       │
│                                                            │
│  Reply: A, B, or "explain more"                            │
└────────────────────────────────────────────────────────────┘
```

---

## 3. System Architecture

### 3.1 High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER LAYER                                      │
│                                                                             │
│    Claude Web        Claude CLI        Claude Web        GitHub UI          │
│    Session 1         Session 2         Session 3         [Merge button]     │
│         │                │                 │                  ▲             │
└─────────┼────────────────┼─────────────────┼──────────────────┼─────────────┘
          │                │                 │                  │
          ▼                ▼                 ▼                  │
┌─────────────────────────────────────────────────────────────────────────────┐
│                            GIT LAYER                                         │
│                                                                             │
│   claude/auth-abc123  claude/catalog-def456  claude/checkout-ghi789         │
│         │                    │                      │                       │
│         └────────────────────┼──────────────────────┘                       │
│                              │                                              │
│                        GitHub Remote                                        │
└──────────────────────────────┼──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      COORDINATION LAYER (GitHub Actions)                     │
│                                                                             │
│  ┌─────────────────────┐         ┌─────────────────────────────────────┐   │
│  │   WORKFLOW A        │         │         WORKFLOW B                   │   │
│  │   "Branch Ping"     │         │         "Coordinator"                │   │
│  │                     │         │                                     │   │
│  │   Trigger: push     │ ─────►  │   Trigger: repository_dispatch     │   │
│  │   Secrets: NONE     │  event  │   Secrets: LLM keys, write access  │   │
│  │   Trust: UNTRUSTED  │         │   Trust: TRUSTED (default branch)  │   │
│  └─────────────────────┘         └─────────────────────────────────────┘   │
│                                                  │                          │
│                                                  ▼                          │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    COORDINATION ENGINE                                │  │
│  │                                                                      │  │
│  │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │  │
│  │   │   DISCOVER   │  │   CLUSTER    │  │   RESOLVE    │              │  │
│  │   │   Agents     │─▶│   Conflicts  │─▶│   Conflicts  │              │  │
│  │   └──────────────┘  └──────────────┘  └──────────────┘              │  │
│  │          │                                    │                      │  │
│  │          ▼                                    ▼                      │  │
│  │   ┌──────────────┐                    ┌──────────────┐              │  │
│  │   │   REGISTRY   │                    │   DELIVERY   │              │  │
│  │   │   (Artifacts)│                    │   PR/Merge   │              │  │
│  │   └──────────────┘                    └──────────────┘              │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LEARNING LAYER                                       │
│                                                                             │
│   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│   │  Pattern Memory │  │ Strategy Stats  │  │ Feedback Loop   │            │
│   │  (rerere-like)  │  │ (win rates)     │  │ (to agents)     │            │
│   └─────────────────┘  └─────────────────┘  └─────────────────┘            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Multi-Agent Scale Architecture (PRD Mode)

For full PRD execution with many agents:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PRD EXECUTION MODE                                   │
│                                                                             │
│   PRD: "Build complete e-commerce platform"                                 │
│         │                                                                   │
│         ▼                                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                    TASK DECOMPOSITION                                │  │
│   │                                                                     │  │
│   │   Feature 1: Auth        Feature 2: Products    Feature 3: Cart    │  │
│   │   Feature 4: Checkout    Feature 5: Orders      Feature 6: Admin   │  │
│   │   ...                                                               │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│         │                                                                   │
│         ▼                                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                    PARALLEL AGENT EXECUTION                          │  │
│   │                                                                     │  │
│   │   Agent 1 ──► claude/auth-xxx      ─┐                               │  │
│   │   Agent 2 ──► claude/products-xxx   │                               │  │
│   │   Agent 3 ──► claude/cart-xxx       ├──► Conflict Cluster A (data) │  │
│   │   Agent 4 ──► claude/checkout-xxx  ─┘                               │  │
│   │   Agent 5 ──► claude/orders-xxx    ─┬──► Conflict Cluster B (api)  │  │
│   │   Agent 6 ──► claude/admin-xxx     ─┘                               │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│         │                                                                   │
│         ▼                                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                    WAVE-BASED RESOLUTION                             │  │
│   │                                                                     │  │
│   │   Wave 1: Resolve Cluster A (auth + products + cart + checkout)    │  │
│   │           → Integration branch updated                              │  │
│   │                                                                     │  │
│   │   Wave 2: Resolve Cluster B (orders + admin)                       │  │
│   │           → Integration branch updated                              │  │
│   │                                                                     │  │
│   │   Wave 3: Final integration (Cluster A + Cluster B)                │  │
│   │           → PR to main                                              │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│         │                                                                   │
│         ▼                                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                    DELIVERY                                          │  │
│   │                                                                     │  │
│   │   Option A: Checkpoint PRs (human reviews accumulated work)         │  │
│   │   Option B: Auto-merge to integration, human PR to main            │  │
│   │   Option C: Full auto (all tests green → merge to main)            │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Security Model

### 4.1 Core Principle: Agent Branches Are Untrusted

Even if agents are "ours," prompt injection or tool misuse could produce dangerous outputs.

```
TRUSTED:
  - Coordinator code (on default branch)
  - Secrets (only accessible to trusted workflow)
  - Main branch

UNTRUSTED:
  - Agent branch contents (treated as DATA)
  - Agent manifests (verified, not trusted)
  - Any code pushed to claude/* branches
```

### 4.2 Split Workflow Security Model

**CRITICAL: Two separate GitHub Actions workflows**

```yaml
# Workflow A: Branch Ping (UNTRUSTED)
# File: .github/workflows/claude-branch-ping.yml
name: Claude Branch Ping

on:
  push:
    branches:
      - 'claude/**'

# MINIMAL permissions - no secrets
permissions:
  contents: read

jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - name: Notify coordinator
        run: |
          # Only emit event, no secrets, no checkout of branch code
          curl -X POST \
            -H "Accept: application/vnd.github+json" \
            -H "Authorization: Bearer ${{ secrets.GITHUB_TOKEN }}" \
            https://api.github.com/repos/${{ github.repository }}/dispatches \
            -d '{"event_type":"claude-branch-update","client_payload":{"branch":"${{ github.ref_name }}","sha":"${{ github.sha }}"}}'
```

```yaml
# Workflow B: Coordinator (TRUSTED)
# File: .github/workflows/claude-coordinator.yml
name: Claude Coordinator

on:
  repository_dispatch:
    types: [claude-branch-update]
  schedule:
    - cron: '*/5 * * * *'  # Backup: every 5 minutes
  workflow_dispatch:
    inputs:
      force_resolve:
        description: 'Force resolution even if not all agents complete'
        type: boolean
        default: false

# Full permissions - runs from default branch only
permissions:
  contents: write
  pull-requests: write
  issues: write
  actions: read

jobs:
  coordinate:
    runs-on: ubuntu-latest

    # Prevent duplicate runs
    concurrency:
      group: claude-coordinator-${{ github.repository }}
      cancel-in-progress: false

    steps:
      - name: Checkout default branch (trusted code)
        uses: actions/checkout@v4
        with:
          ref: main  # Always use trusted code
          fetch-depth: 0

      - name: Fetch all branches (as data)
        run: git fetch --all

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install orchestrator
        run: pip install -e .

      - name: Run coordinator
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          python -m orchestrator.coordinator \
            --mode=auto \
            --create-pr=true
```

### 4.3 Sensitive File Handling

Never include in LLM prompts or escalation details:

```python
SENSITIVE_PATTERNS = [
    "*.env*",
    "*secret*",
    "*credential*",
    "*password*",
    "*.pem",
    "*.key",
    "**/secrets/**",
    "**/.aws/**",
    "**/credentials/**"
]
```

### 4.4 Additional Security Hardening (from review feedback)

**Artifact Validation (DoS Prevention):**

```python
ARTIFACT_LIMITS = {
    "max_manifest_size_kb": 100,      # Manifests should be small
    "max_artifact_count": 10,         # Per agent
    "allowed_mime_types": ["application/json"],
    "branch_name_pattern": r"^claude/[a-z0-9-]+$",  # Strict allowlist
}

def validate_artifact(artifact: bytes, metadata: dict) -> bool:
    """Validate artifact before processing."""
    if len(artifact) > ARTIFACT_LIMITS["max_manifest_size_kb"] * 1024:
        raise SecurityError("Artifact exceeds size limit")

    # Never execute manifest contents - treat as pure data
    try:
        data = json.loads(artifact)  # Parse only, never eval
    except json.JSONDecodeError:
        raise SecurityError("Invalid JSON in artifact")

    return True
```

**Coordinator Clone Hardening:**

```yaml
# In coordinator workflow, use shallow clone without tags
- name: Checkout default branch (trusted code)
  uses: actions/checkout@v4
  with:
    ref: main
    fetch-depth: 1        # Shallow clone
    fetch-tags: false     # No tags from agent branches
```

**Disable Workflows on Agent Branches:**

```yaml
# .github/workflows/ci.yml - Add condition to skip agent branches
jobs:
  build:
    if: "!startsWith(github.ref, 'refs/heads/claude/')"
    # ... rest of job
```

**Artifact Signing (Optional, for high-security environments):**

```python
def sign_artifact(artifact: bytes, key: bytes) -> str:
    """Sign artifact for integrity verification."""
    import hmac
    import hashlib
    return hmac.new(key, artifact, hashlib.sha256).hexdigest()

def verify_artifact(artifact: bytes, signature: str, key: bytes) -> bool:
    """Verify artifact signature."""
    expected = sign_artifact(artifact, key)
    return hmac.compare_digest(expected, signature)
```

**Manifest Cross-Linking (Replay Protection):**

```json
{
  "manifest_id": "unique-random-token",
  "branch_sha": "abc123",
  "created_at": "2026-01-07T10:00:00Z",
  "expires_at": "2026-01-08T10:00:00Z",
  "single_use": true
}
```

### 4.5 Container Isolation for Stage-0 Builds (from Gemini/ChatGPT o3/Grok reviews)

**CRITICAL: Stage-0 builds run untrusted agent code. Must be sandboxed.**

The temporary merge build/test step executes arbitrary code from agent branches. A malicious or buggy agent could:
- `rm -rf $GITHUB_WORKSPACE` - corrupt other agents' artifacts
- Exfiltrate `GITHUB_TOKEN` if available
- Write malicious files to `.ssh/` or `.github/workflows/`

**Solution: Containerized Build Environment**

```yaml
# In coordinator workflow - Stage-0 build/test
- name: Run Stage-0 Build in Sandbox
  uses: docker/build-push-action@v5
  with:
    context: .
    file: .claude/Dockerfile.sandbox
    push: false
    tags: stage0-build:${{ github.sha }}

- name: Execute Sandboxed Build/Test
  run: |
    docker run --rm \
      --network=none \                    # No network access
      --cap-drop=ALL \                    # Drop all capabilities
      --security-opt=no-new-privileges \  # Prevent privilege escalation
      --read-only \                       # Read-only filesystem
      --tmpfs /tmp:size=512M \            # Limited temp space
      --memory=2g \                       # Memory limit
      --cpus=2 \                          # CPU limit
      -v "$(pwd):/workspace:ro" \         # Read-only source
      -v "/tmp/build-output:/output" \    # Write-only output
      stage0-build:${{ github.sha }} \
      /workspace/.claude/scripts/build-test.sh
```

```dockerfile
# .claude/Dockerfile.sandbox
FROM node:20-slim AS sandbox

# Minimal tools only
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -m -s /bin/bash sandbox
USER sandbox

WORKDIR /workspace

# No secrets in image
# No network in runtime
# Read-only source mount
```

**Network Isolation:**

```yaml
# Allow only package registry access
sandbox_network:
  allowed_hosts:
    - "registry.npmjs.org"
    - "pypi.org"
    - "files.pythonhosted.org"
  denied_hosts:
    - "*"  # Block everything else
```

### 4.6 Rate Limiting and DoS Prevention (from Grok 4.1 review)

**Problem:** Malicious actors could flood `claude/**` pushes to exhaust GitHub Actions minutes.

**Solution: Multi-layer Rate Limiting**

```yaml
# Workflow A: Add rate limit check before dispatch
- name: Rate Limit Check
  id: rate_check
  run: |
    # Count dispatches in last hour
    DISPATCH_COUNT=$(gh api repos/${{ github.repository }}/actions/runs \
      --jq '[.workflow_runs[] | select(.created_at > (now - 3600 | todate))] | length')

    if [ "$DISPATCH_COUNT" -gt 50 ]; then
      echo "::warning::Rate limit exceeded - skipping dispatch"
      echo "skip=true" >> $GITHUB_OUTPUT
    else
      echo "skip=false" >> $GITHUB_OUTPUT
    fi

- name: Notify Coordinator
  if: steps.rate_check.outputs.skip != 'true'
  run: |
    # Dispatch event...
```

```python
class RateLimiter:
    """Multi-tier rate limiting for coordinator."""

    LIMITS = {
        "per_minute": 10,      # Max dispatches per minute
        "per_hour": 100,       # Max per hour
        "per_agent": 20,       # Max per agent per hour
        "concurrent": 5,       # Max concurrent builds
    }

    def __init__(self):
        self.redis = Redis()  # Or use GitHub Actions cache

    def check_rate_limit(self, agent_id: str) -> RateLimitResult:
        """Check if request should be rate limited."""
        now = time.time()

        # Check per-minute limit
        minute_key = f"rate:minute:{int(now / 60)}"
        minute_count = self.redis.incr(minute_key)
        self.redis.expire(minute_key, 120)

        if minute_count > self.LIMITS["per_minute"]:
            return RateLimitResult(
                allowed=False,
                reason="per_minute_exceeded",
                retry_after=60 - (now % 60)
            )

        # Check per-agent limit
        agent_key = f"rate:agent:{agent_id}:{int(now / 3600)}"
        agent_count = self.redis.incr(agent_key)
        self.redis.expire(agent_key, 7200)

        if agent_count > self.LIMITS["per_agent"]:
            return RateLimitResult(
                allowed=False,
                reason="agent_limit_exceeded",
                retry_after=3600 - (now % 3600)
            )

        return RateLimitResult(allowed=True)

class BackPressureController:
    """Prevent resource exhaustion via back-pressure."""

    def __init__(self, max_queue_size: int = 50):
        self.max_queue_size = max_queue_size
        self.queue = PriorityQueue()

    def enqueue_or_reject(self, request: CoordinatorRequest) -> bool:
        """Add request to queue or reject if overloaded."""
        if self.queue.qsize() >= self.max_queue_size:
            # Reject with back-pressure signal
            return False

        # Priority: high-risk conflicts first, then FIFO
        priority = self._calculate_priority(request)
        self.queue.put((priority, request))
        return True
```

### 4.7 Cryptographic Manifest Attestation (from ChatGPT o3/Grok reviews)

**Problem:** Any agent can upload another agent's manifest ID with different data (confused deputy attack).

**Solution: Signed Manifests with SHA Binding**

```python
import hashlib
import hmac
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed25519

class ManifestAttestor:
    """Cryptographically attest manifest integrity."""

    def __init__(self, private_key: ed25519.Ed25519PrivateKey):
        self.private_key = private_key
        self.public_key = private_key.public_key()

    def create_attestation(self,
                           manifest: dict,
                           branch_sha: str) -> Attestation:
        """
        Create cryptographic attestation binding:
        - Manifest content hash
        - Branch SHA at time of creation
        - Timestamp
        - Coordinator signature
        """
        # Canonical JSON encoding
        manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()

        # Attestation payload
        payload = {
            "manifest_hash": manifest_hash,
            "branch_sha": branch_sha,
            "created_at": datetime.utcnow().isoformat(),
            "coordinator_id": os.getenv("COORDINATOR_ID"),
        }
        payload_bytes = json.dumps(payload, sort_keys=True).encode()

        # Sign with coordinator's private key
        signature = self.private_key.sign(payload_bytes)

        return Attestation(
            payload=payload,
            signature=signature.hex(),
            public_key=self.public_key.public_bytes_raw().hex()
        )

    def verify_attestation(self,
                           manifest: dict,
                           attestation: Attestation,
                           expected_sha: str) -> VerificationResult:
        """Verify attestation before using manifest."""
        # Verify signature
        payload_bytes = json.dumps(attestation.payload, sort_keys=True).encode()
        try:
            self.public_key.verify(
                bytes.fromhex(attestation.signature),
                payload_bytes
            )
        except Exception:
            return VerificationResult(valid=False, reason="invalid_signature")

        # Verify SHA matches
        if attestation.payload["branch_sha"] != expected_sha:
            return VerificationResult(
                valid=False,
                reason="sha_mismatch",
                details=f"Expected {expected_sha}, got {attestation.payload['branch_sha']}"
            )

        # Verify manifest hash
        manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
        actual_hash = hashlib.sha256(manifest_bytes).hexdigest()
        if actual_hash != attestation.payload["manifest_hash"]:
            return VerificationResult(valid=False, reason="manifest_tampered")

        return VerificationResult(valid=True)

@dataclass
class Attestation:
    """Cryptographic attestation for manifest."""
    payload: dict
    signature: str
    public_key: str
```

**Artifact Naming with SHA Binding:**

```yaml
# When uploading manifest artifact
- name: Upload Manifest with SHA Binding
  uses: actions/upload-artifact@v4
  with:
    # Include SHA in artifact name for integrity
    name: manifest-${{ github.sha }}-${{ hashFiles('manifest.json') }}
    path: manifest.json
    retention-days: 7
```

---

## 5. Agent Registration & Tracking

### 5.1 Agent Manifest Schema

**CRITICAL: Manifests stored as GitHub Action artifacts, NOT committed to repo**

This avoids:
- Constant merge conflicts on manifest files
- Commit noise from manifest updates
- Security issues with manifest tampering

```json
{
  "schema_version": "2.0",

  "agent": {
    "id": "claude-web-abc123",
    "type": "claude-web",
    "session_id": "abc123",
    "started_at": "2026-01-07T10:00:00Z",
    "model": {
      "provider": "anthropic",
      "model_name": "claude-sonnet-4-20250514"
    }
  },

  "git": {
    "branch": "claude/add-authentication-abc123",
    "base_sha": "def456",
    "head_sha": "ghi789"
  },

  "task": {
    "description": "Add user authentication",
    "user_prompt": "Add authentication to the app",
    "prd_reference": null,
    "parent_task_id": null
  },

  "work": {
    "status": "in_progress",
    "files_read": [],
    "files_modified": [],
    "decisions": [],
    "tests_added": [],
    "dependencies_added": []
  },

  "risk_flags": [],

  "interfaces_changed": [],

  "completion": null
}
```

### 5.2 Manifest Storage & Retrieval

```python
class ManifestStore:
    """Store and retrieve agent manifests via GitHub Artifacts."""

    def store_manifest(self, agent_id: str, manifest: dict):
        """Store manifest as GitHub Action artifact."""
        artifact_name = f"agent-manifest-{agent_id}"
        # Upload as artifact with 7-day retention

    def get_manifest(self, agent_id: str) -> Optional[dict]:
        """Retrieve manifest from artifacts."""

    def get_all_active_manifests(self) -> List[dict]:
        """Get all manifests for active agent branches."""

    def derive_manifest(self, branch: str, base: str = "main") -> dict:
        """
        CRITICAL: Derive actual changes from git diff.
        Don't trust agent-provided manifest blindly.
        """
        diff = git_diff(base, branch)
        files_modified = extract_modified_files(diff)
        # Use cheap LLM to summarize changes
        summary = llm_summarize_diff(diff)
        return {
            "derived_files_modified": files_modified,
            "derived_summary": summary,
            "derived_at": datetime.utcnow().isoformat()
        }
```

### 5.3 Agent Registry

Central tracking of all active agents:

```python
@dataclass
class AgentRegistry:
    """Track all active agent sessions."""

    agents: Dict[str, AgentInfo]  # agent_id -> info

    def register_agent(self, manifest: dict):
        """Register new agent from manifest."""

    def update_agent_status(self, agent_id: str, status: str):
        """Update agent status (in_progress, complete, failed)."""

    def get_completed_agents(self) -> List[AgentInfo]:
        """Get all agents that have completed their work."""

    def get_agents_by_conflict_cluster(self) -> Dict[str, List[AgentInfo]]:
        """Group agents by potential conflict clusters."""
        # Cluster by: modified files, domains (auth, db, api), dependencies

    def cleanup_stale_agents(self, max_age_hours: int = 72):
        """Remove agents that have been inactive too long."""
```

### 5.4 Agent Completion Detection (from design review)

**CRITICAL: How do we know an agent is "done"?**

Claude Web/CLI don't have a "done" button - users just stop responding or close the tab. The system must infer completion.

```python
class CompletionDetector:
    """
    Detect when an agent has completed its work.

    Problem: No explicit "done" signal from Claude Web/CLI.
    Solution: Multi-signal heuristic approach.
    """

    COMPLETION_SIGNALS = {
        "explicit_marker": 10,      # .claude-complete file or [COMPLETE] in commit
        "tests_pass": 3,            # All tests pass on branch
        "no_wip_commits": 2,        # No "WIP", "fixup", "squash" in recent commits
        "inactivity": 1,            # No commits for threshold period
        "pr_ready_marker": 5,       # Branch has PR-ready indicators
    }

    COMPLETION_THRESHOLD = 5  # Sum of signals needed to consider complete

    def detect_completion(self, agent: AgentInfo) -> CompletionStatus:
        """
        Determine if agent work is complete.

        Returns:
            CompletionStatus with confidence score and signals detected
        """
        signals = []
        score = 0

        # Signal 1: Explicit completion marker
        if self._has_completion_marker(agent.branch):
            signals.append("explicit_marker")
            score += self.COMPLETION_SIGNALS["explicit_marker"]

        # Signal 2: Tests pass
        if self._tests_pass(agent.branch):
            signals.append("tests_pass")
            score += self.COMPLETION_SIGNALS["tests_pass"]

        # Signal 3: No WIP commits
        if not self._has_wip_commits(agent.branch):
            signals.append("no_wip_commits")
            score += self.COMPLETION_SIGNALS["no_wip_commits"]

        # Signal 4: Inactivity threshold
        if self._inactive_for(agent, hours=4):
            signals.append("inactivity")
            score += self.COMPLETION_SIGNALS["inactivity"]

        # Signal 5: PR-ready indicators (clean history, good commit messages)
        if self._is_pr_ready(agent.branch):
            signals.append("pr_ready_marker")
            score += self.COMPLETION_SIGNALS["pr_ready_marker"]

        return CompletionStatus(
            is_complete=score >= self.COMPLETION_THRESHOLD,
            confidence=min(score / 10.0, 1.0),
            signals=signals,
            score=score
        )

    def _has_completion_marker(self, branch: str) -> bool:
        """Check for explicit completion signals."""
        # Option A: .claude-complete file exists
        # Option B: Last commit message contains [COMPLETE] or [DONE]
        # Option C: Branch has specific tag
        pass

    def _has_wip_commits(self, branch: str) -> bool:
        """Check if recent commits are WIP."""
        wip_patterns = ["WIP", "wip", "fixup!", "squash!", "FIXME", "TODO"]
        # Check last 3 commits
        pass

@dataclass
class CompletionStatus:
    """Result of completion detection."""
    is_complete: bool
    confidence: float  # 0.0 to 1.0
    signals: List[str]
    score: int
```

**Completion Signal Options for Agents:**

| Signal Type | How Agent Triggers It | Reliability |
|-------------|----------------------|-------------|
| Explicit marker | Create `.claude-complete` file | HIGH |
| Commit message | Include `[COMPLETE]` in final commit | HIGH |
| Inactivity | Stop pushing commits | MEDIUM |
| Tests pass | Ensure all tests pass | MEDIUM |
| No WIP | Don't use WIP/fixup commits | LOW |

**Recommended Agent Behavior:**

Agents should be instructed to signal completion explicitly:
```
When you have finished implementing the feature:
1. Ensure all tests pass
2. Create a final commit with "[COMPLETE]" in the message
3. Or create a .claude-complete file with summary of work done
```

---

## 6. Conflict Detection & Classification

### 6.1 Stage 0: Detection Pipeline

**CRITICAL: Test the MERGED result, not just individual branches**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STAGE 0: CONFLICT DETECTION                          │
│                                                                             │
│  Input: List of completed agent branches                                    │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │ Step 1: TEXTUAL CONFLICT CHECK                                      │    │
│  │                                                                     │    │
│  │   git merge-tree $(git merge-base main branch1) branch1 branch2    │    │
│  │   → Detects: overlapping line changes                               │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│                              ▼                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │ Step 2: CREATE TEMPORARY MERGE (even if git says "clean")           │    │
│  │                                                                     │    │
│  │   git checkout -b temp-merge main                                   │    │
│  │   git merge --no-commit branch1 branch2 ...                        │    │
│  │   → Creates merged state for testing                                │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│                              ▼                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │ Step 3: BUILD TEST (catches "clean but broken" merges)              │    │
│  │                                                                     │    │
│  │   Run: compile/typecheck                                           │    │
│  │   If fails → SEMANTIC CONFLICT (even though git said clean)        │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│                              ▼                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │ Step 4: SMOKE TEST (catches runtime conflicts)                      │    │
│  │                                                                     │    │
│  │   Run: targeted tests for modified files                           │    │
│  │   If fails → SEMANTIC CONFLICT                                     │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│                              ▼                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │ Step 5: DEPENDENCY CHECK                                            │    │
│  │                                                                     │    │
│  │   Analyze: package.json, requirements.txt, etc.                    │    │
│  │   Detect: version conflicts, incompatible packages                 │    │
│  │   If conflicts → DEPENDENCY CONFLICT (special handling)            │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│                              ▼                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │ Step 6: SEMANTIC ANALYSIS                                           │    │
│  │                                                                     │    │
│  │   - Module dependency graph overlap                                 │    │
│  │   - Symbol/function overlap (same names, different implementations)│    │
│  │   - Domain overlap (both touch auth, both touch DB schema)         │    │
│  │   - API surface changes                                            │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│                              ▼                                              │
│  Output: ConflictClassification                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Conflict Classification

```python
class ConflictType(Enum):
    NONE = "none"                    # No conflicts, fast-path merge
    TEXTUAL = "textual"              # Git-level conflicts only
    SEMANTIC = "semantic"            # Same area, different approaches
    ARCHITECTURAL = "architectural"   # Fundamental design disagreement
    DEPENDENCY = "dependency"         # Package/library conflicts

class ConflictSeverity(Enum):
    LOW = "low"           # Auto-resolve with high confidence
    MEDIUM = "medium"     # Auto-resolve with caution
    HIGH = "high"         # Consider escalation
    CRITICAL = "critical" # Must escalate

@dataclass
class ConflictClassification:
    conflict_type: ConflictType
    severity: ConflictSeverity

    # What's conflicting
    conflicting_files: List[str]
    conflicting_symbols: List[str]
    dependency_conflicts: List[DependencyConflict]

    # Context
    agents_involved: List[str]
    conflict_clusters: List[ConflictCluster]

    # Recommendation
    recommended_path: Literal["fast_merge", "auto_resolve", "escalate"]
    confidence: float

    # Risk flags
    risk_flags: List[str]  # ["auth", "security", "db_migration", "public_api"]
```

### 6.3 Conflict Clustering (for scale)

Group related conflicts to resolve in waves:

```python
@dataclass
class ConflictCluster:
    """A group of related conflicts to resolve together."""

    cluster_id: str
    cluster_type: str  # "domain", "file", "dependency"

    # Agents in this cluster
    agent_ids: List[str]

    # What defines this cluster
    shared_files: List[str]
    shared_domains: List[str]  # auth, db, api, ui
    shared_dependencies: List[str]

    # Resolution order
    depends_on_clusters: List[str]  # Must resolve these first

    # Estimated complexity
    estimated_resolution_time: str  # "fast", "medium", "slow"


def cluster_conflicts(agents: List[AgentInfo]) -> List[ConflictCluster]:
    """
    Group agents into conflict clusters for wave-based resolution.

    Strategy:
    1. Build file overlap graph
    2. Build domain overlap graph (infer from paths, manifests)
    3. Build dependency overlap graph
    4. Find connected components = clusters
    5. Order clusters by dependencies
    """
    pass
```

### 6.4 Scalability for 50+ Agents (from review feedback)

**Problem:** Naive pairwise merge-tree checks scale O(n²) for n agents.

**Solution: Pre-clustering by Repository Zones**

```python
# SCALABILITY CONSTANTS
MAX_CONCURRENT_CLUSTERING = 10  # Max agents to cluster simultaneously
CLUSTERING_BATCH_SIZE = 20      # Process in batches
PRIORITY_QUEUE_ENABLED = True   # Prioritize high-risk or blocking conflicts

class ScalableClusterer:
    """Optimized clustering for large agent counts."""

    def pre_cluster_by_zone(self, agents: List[AgentInfo]) -> Dict[str, List[AgentInfo]]:
        """
        Pre-cluster agents by repository zone BEFORE pairwise analysis.
        Reduces O(n²) to O(n²/k²) where k is number of zones.

        Zone examples:
        - Monorepo packages: packages/auth/**, packages/api/**
        - Domain areas: src/auth/**, src/db/**, src/api/**
        - Module boundaries: defined in CODEOWNERS or config
        """
        zones = defaultdict(list)

        for agent in agents:
            # Determine zone from modified files
            primary_zone = self._infer_zone(agent.derived_changes["files_modified"])
            zones[primary_zone].append(agent)

        return zones

    def cluster_with_limits(self,
                            agents: List[AgentInfo],
                            max_batch: int = CLUSTERING_BATCH_SIZE) -> List[ConflictCluster]:
        """
        Cluster with concurrency limits and batching.
        """
        # Pre-cluster by zone first
        zones = self.pre_cluster_by_zone(agents)

        all_clusters = []

        # Process each zone independently (parallelizable)
        for zone_name, zone_agents in zones.items():
            if len(zone_agents) <= max_batch:
                # Small zone: cluster normally
                clusters = cluster_conflicts(zone_agents)
            else:
                # Large zone: batch processing with priority queue
                clusters = self._batch_cluster(zone_agents, max_batch)

            all_clusters.extend(clusters)

        # Final pass: check for cross-zone conflicts
        cross_zone = self._find_cross_zone_conflicts(all_clusters)
        all_clusters.extend(cross_zone)

        return all_clusters

    def _batch_cluster(self,
                       agents: List[AgentInfo],
                       batch_size: int) -> List[ConflictCluster]:
        """Process large agent groups in batches with priority queue."""
        # Sort by risk/priority
        sorted_agents = sorted(agents, key=lambda a: a.risk_score, reverse=True)

        clusters = []
        processed = set()

        for i in range(0, len(sorted_agents), batch_size):
            batch = sorted_agents[i:i + batch_size]
            batch_clusters = cluster_conflicts(batch)
            clusters.extend(batch_clusters)

        return clusters
```

**Concurrency Controls:**

```yaml
# In coordinator config
clustering:
  max_concurrent_agents: 50          # Hard limit
  batch_size: 20                     # Process in batches
  priority_queue: true               # High-risk first
  zone_parallelism: 4                # Parallel zone processing
  timeout_per_cluster_minutes: 30    # Fail-safe timeout
```

### 6.5 Graph-Based Clustering (from ChatGPT o3 review)

**Problem:** Even with zone pre-clustering, pairwise merge-tree diffs are expensive.

**Solution: File-Agent Bipartite Graph**

Instead of N² pairwise comparisons, build a graph where:
- Nodes = file paths
- Edges = which agent modifies which file

Connected components = conflict clusters. Complexity: O(N × average_files_per_agent).

```python
from collections import defaultdict
from typing import Set, List, Dict

class GraphBasedClusterer:
    """
    Build file-agent graph for O(N * files) clustering.
    Avoids expensive pairwise git merge-tree checks.
    """

    def cluster_via_graph(self, agents: List[AgentInfo]) -> List[ConflictCluster]:
        """
        Build bipartite graph and find connected components.

        Algorithm:
        1. For each agent, get list of modified files
        2. Build graph: file → set of agents that modify it
        3. Find connected components (agents that share files)
        4. Each component = one conflict cluster
        """
        # Build file → agents mapping
        file_to_agents: Dict[str, Set[str]] = defaultdict(set)
        agent_to_files: Dict[str, Set[str]] = {}

        for agent in agents:
            files = set(agent.derived_changes.get("files_modified", []))
            agent_to_files[agent.agent_id] = files
            for file in files:
                file_to_agents[file].append(agent.agent_id)

        # Find connected components via union-find
        parent = {a.agent_id: a.agent_id for a in agents}

        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Union agents that share any file
        for file, agent_ids in file_to_agents.items():
            agent_list = list(agent_ids)
            for i in range(1, len(agent_list)):
                union(agent_list[0], agent_list[i])

        # Group by component
        components: Dict[str, List[AgentInfo]] = defaultdict(list)
        for agent in agents:
            root = find(agent.agent_id)
            components[root].append(agent)

        # Convert to ConflictClusters
        clusters = []
        for root, cluster_agents in components.items():
            if len(cluster_agents) == 1:
                # Single agent = no conflict, skip clustering
                continue

            # Find shared files for this cluster
            shared_files = set()
            for agent in cluster_agents:
                for file in agent_to_files[agent.agent_id]:
                    if len(file_to_agents[file]) > 1:
                        shared_files.add(file)

            clusters.append(ConflictCluster(
                cluster_id=f"cluster-{root[:8]}",
                cluster_type="file_overlap",
                agent_ids=[a.agent_id for a in cluster_agents],
                shared_files=list(shared_files),
                estimated_resolution_time=self._estimate_time(cluster_agents)
            ))

        return clusters

    def _estimate_time(self, agents: List[AgentInfo]) -> str:
        """Estimate resolution time based on cluster size and complexity."""
        total_files = sum(len(a.derived_changes.get("files_modified", [])) for a in agents)
        if len(agents) <= 2 and total_files <= 10:
            return "fast"
        elif len(agents) <= 5 and total_files <= 50:
            return "medium"
        else:
            return "slow"
```

**Hybrid Approach (Best of Both):**

```python
class HybridClusterer:
    """
    Combine graph-based clustering with git merge-tree validation.

    1. Fast pass: Graph-based clustering (O(N × files))
    2. Validation: Only run merge-tree on flagged clusters
    """

    def cluster(self, agents: List[AgentInfo]) -> List[ConflictCluster]:
        # Step 1: Fast graph-based clustering
        graph_clusters = GraphBasedClusterer().cluster_via_graph(agents)

        # Step 2: For each cluster, validate with actual git merge
        validated_clusters = []
        for cluster in graph_clusters:
            # Only do expensive merge-tree check if cluster is complex
            if cluster.estimated_resolution_time == "slow":
                # Split large clusters based on actual merge conflicts
                sub_clusters = self._validate_with_merge_tree(cluster)
                validated_clusters.extend(sub_clusters)
            else:
                validated_clusters.append(cluster)

        return validated_clusters

    def _validate_with_merge_tree(self, cluster: ConflictCluster) -> List[ConflictCluster]:
        """Use git merge-tree to validate/refine cluster."""
        # Check if files actually have textual conflicts
        # May split cluster if some agents don't actually conflict
        pass
```

---

## 7. Resolution Pipeline

### 7.1 Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RESOLUTION PIPELINE                                  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ FAST PATH CHECK                                                      │   │
│  │                                                                     │   │
│  │ IF conflict_type == NONE:                                           │   │
│  │   → Skip to DELIVERY (just merge)                                   │   │
│  │                                                                     │   │
│  │ IF conflict_type == TEXTUAL AND confidence > 0.9:                   │   │
│  │   → Skip to SIMPLE_MERGE (git merge with basic cleanup)             │   │
│  │                                                                     │   │
│  │ IF conflict_type == DEPENDENCY:                                     │   │
│  │   → Route to DEPENDENCY_RESOLVER (special handling)                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 1: CONTEXT ASSEMBLY                                            │   │
│  │                                                                     │   │
│  │ Gather:                                                             │   │
│  │ - Agent manifests (from artifacts)                                  │   │
│  │ - Derived changes (from git diff) ← VERIFY AGAINST MANIFEST         │   │
│  │ - Base commit state                                                 │   │
│  │ - Conflicting file contents (base, agent1, agent2)                 │   │
│  │ - Related files (imports, callers)                                  │   │
│  │ - Project conventions                                               │   │
│  │                                                                     │   │
│  │ Output: ConflictContext                                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 2: INTENT EXTRACTION                                           │   │
│  │                                                                     │   │
│  │ For each agent, extract:                                            │   │
│  │ - Primary intent (one sentence)                                     │   │
│  │ - Hard constraints (must satisfy)                                   │   │
│  │ - Soft constraints (prefer)                                         │   │
│  │ - Evidence (citations to task, tests, code)                         │   │
│  │ - Confidence score                                                  │   │
│  │                                                                     │   │
│  │ Compare intents:                                                    │   │
│  │ - Compatible: both can be satisfied                                 │   │
│  │ - Conflicting: mutually exclusive                                   │   │
│  │ - Orthogonal: independent                                           │   │
│  │                                                                     │   │
│  │ CRITICAL: If confidence LOW → escalate, don't guess                 │   │
│  │                                                                     │   │
│  │ Output: IntentAnalysis                                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 3: INTERFACE HARMONIZATION                                     │   │
│  │                                                                     │   │
│  │ Problem: Tests may not compile if interfaces changed                │   │
│  │                                                                     │   │
│  │ Steps:                                                              │   │
│  │ 1. Identify interface changes (signatures, types, exports)          │   │
│  │ 2. Pick canonical interface (prefer: existing in main, more usage) │   │
│  │ 3. Generate adapter code if needed (mark as temporary)             │   │
│  │ 4. Update call sites                                                │   │
│  │ 5. Verify build passes                                              │   │
│  │                                                                     │   │
│  │ CRITICAL: Log adapter decisions for potential escalation            │   │
│  │                                                                     │   │
│  │ Output: HarmonizedCodebase (builds, tests may still fail)          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 4: TEST SYNTHESIS                                              │   │
│  │                                                                     │   │
│  │ Steps:                                                              │   │
│  │ 1. Collect tests from all branches                                  │   │
│  │ 2. Deduplicate                                                      │   │
│  │ 3. Fix imports for harmonized interfaces                            │   │
│  │ 4. Generate integration tests ONLY at clear interaction points     │   │
│  │ 5. Mark generated tests for review                                  │   │
│  │                                                                     │   │
│  │ CONSERVATIVE: Don't over-generate (hallucinated tests are bad)     │   │
│  │                                                                     │   │
│  │ Output: UnifiedTestSuite                                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 5: CANDIDATE GENERATION                                        │   │
│  │                                                                     │   │
│  │ Generate 3 candidates using DISTINCT strategies:                    │   │
│  │                                                                     │   │
│  │ Strategy A: "Agent 1 Primary"                                       │   │
│  │   Keep Agent 1's architecture, adapt Agent 2's features             │   │
│  │   Constraint: Must preserve Agent 1's API                           │   │
│  │                                                                     │   │
│  │ Strategy B: "Agent 2 Primary"                                       │   │
│  │   Keep Agent 2's architecture, adapt Agent 1's features             │   │
│  │   Constraint: Must preserve Agent 2's API                           │   │
│  │                                                                     │   │
│  │ Strategy C: "Convention Primary"                                    │   │
│  │   Match existing repo patterns, adapt both agents to fit            │   │
│  │   Constraint: Must minimize deviation from existing code style      │   │
│  │                                                                     │   │
│  │ (Optional) Strategy D: "Fresh Synthesis"                            │   │
│  │   Re-implement both intents from scratch on clean base              │   │
│  │   Only for architectural conflicts                                  │   │
│  │                                                                     │   │
│  │ CRITICAL: Check candidate diversity, regenerate if too similar      │   │
│  │                                                                     │   │
│  │ Output: List[ResolutionCandidate]                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 6: VALIDATION & SELECTION                                      │   │
│  │                                                                     │   │
│  │ TIERED VALIDATION (fast → slow, bail early):                        │   │
│  │                                                                     │   │
│  │ Tier 1: Build (seconds)                                             │   │
│  │   → Eliminate candidates that don't compile                         │   │
│  │                                                                     │   │
│  │ Tier 2: Lint (seconds)                                              │   │
│  │   → Score convention compliance                                     │   │
│  │                                                                     │   │
│  │ Tier 3: Targeted Tests (minutes)                                    │   │
│  │   → Run ONLY tests for modified files                               │   │
│  │   → Tools: jest --findRelatedTests, pytest-testmon                  │   │
│  │   → Time budget: 5 min per candidate max                            │   │
│  │                                                                     │   │
│  │ Tier 4: Full Suite (only if high-risk)                              │   │
│  │   → Run complete test suite                                         │   │
│  │   → Only for: security changes, public API, DB migrations          │   │
│  │                                                                     │   │
│  │ FLAKY TEST HANDLING:                                                │   │
│  │   → Retry once for known-flaky tests                                │   │
│  │   → Track flakiness, downweight in scoring                          │   │
│  │                                                                     │   │
│  │ SCORING:                                                            │   │
│  │   - Correctness (tests passed)                                      │   │
│  │   - Simplicity (diff size)                                          │   │
│  │   - Convention fit (matches repo patterns)                          │   │
│  │   - Distance to original agents (preserve their work)              │   │
│  │   - Both intents satisfied                                          │   │
│  │                                                                     │   │
│  │ Output: RankedCandidates                                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 7: DECISION                                                    │   │
│  │                                                                     │   │
│  │ AUTO-RESOLVE IF ALL:                                                │   │
│  │   - Top candidate passes all tests                                  │   │
│  │   - Score significantly better than others (gap > threshold)        │   │
│  │   - No high-risk flags (auth, security, DB, public API)            │   │
│  │   - Confidence > config threshold (default 0.8)                     │   │
│  │                                                                     │   │
│  │ ESCALATE IF ANY:                                                    │   │
│  │   - Multiple candidates viable with different tradeoffs             │   │
│  │   - High-risk flags present                                         │   │
│  │   - Intent confidence was LOW                                       │   │
│  │   - Tests removed or weakened                                       │   │
│  │   - No candidates pass tests                                        │   │
│  │                                                                     │   │
│  │ Output: Decision (auto_resolve | escalate)                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 8: DELIVERY                                                    │   │
│  │                                                                     │   │
│  │ SAFETY CHECK (handle race condition):                               │   │
│  │   1. Fetch main                                                     │   │
│  │   2. If main has moved:                                             │   │
│  │      a. Rebase resolution onto new main                             │   │
│  │      b. Re-run Tier 1-2 validation                                  │   │
│  │      c. If fails → back to STAGE 5                                  │   │
│  │                                                                     │   │
│  │ IF auto-resolved:                                                   │   │
│  │   1. Create branch: claude/resolved-<timestamp>                     │   │
│  │   2. Add git trailers for attribution                               │   │
│  │   3. Create PR (or auto-merge per config)                           │   │
│  │   4. Notify user                                                    │   │
│  │                                                                     │   │
│  │ IF escalated:                                                       │   │
│  │   1. Create GitHub Issue with decision request                      │   │
│  │   2. Wait for user response                                         │   │
│  │   3. When response received → PORT losing feature to winner         │   │
│  │   4. Continue to PR creation                                        │   │
│  │                                                                     │   │
│  │ Output: PR URL or Escalation Issue URL                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Dependency Resolver (Special Handler)

```python
class DependencyResolver:
    """
    Special handler for package.json, requirements.txt, etc.

    These files need dedicated handling because:
    1. Text merge often breaks them
    2. Lockfile regeneration is required
    3. Version conflicts need semantic resolution
    """

    def resolve(self,
                base_deps: Dict[str, str],
                agent1_deps: Dict[str, str],
                agent2_deps: Dict[str, str]) -> DependencyResolution:
        """
        Resolve dependency conflicts.

        Strategy:
        1. Identify added/removed/changed deps per agent
        2. Non-overlapping additions → accept both
        3. Same dep, same version → accept
        4. Same dep, different versions → resolve:
           - Prefer higher semver if compatible
           - Check for known incompatibilities
           - Escalate if can't resolve
        5. Regenerate lockfile
        6. Run install + smoke test
        """
        pass

    def regenerate_lockfile(self, resolved_deps: Dict[str, str]):
        """Regenerate package-lock.json or similar."""
        pass

    def verify_installation(self) -> bool:
        """Run package install and basic smoke test."""
        pass
```

### 7.3 Pipeline Enhancements (from review feedback)

**A) Fail-Fast Guards:**

```python
class PipelineGuards:
    """Guards to fail fast and avoid wasted computation."""

    def check_before_candidate_generation(self,
                                           context: ConflictContext,
                                           intents: IntentAnalysis) -> Optional[FailFastResult]:
        """
        Check if we should bail out before expensive candidate generation.
        """
        # Guard 1: No viable path detected
        if intents.relationship == "incompatible" and intents.confidence > 0.9:
            return FailFastResult(
                reason="no_viable_merge",
                action="escalate",
                message="Intents are fundamentally incompatible - needs human decision"
            )

        # Guard 2: Too many files changed
        if len(context.all_modified_files) > 500:
            return FailFastResult(
                reason="too_large",
                action="escalate",
                message="Change set too large for automated resolution"
            )

        # Guard 3: Critical files with low confidence
        if context.has_critical_files and intents.confidence < 0.7:
            return FailFastResult(
                reason="critical_low_confidence",
                action="escalate",
                message="Critical files modified with uncertain intent"
            )

        return None  # Continue pipeline
```

**B) Conditional Fourth Strategy: "Minimal Merge"**

```python
# Add to candidate generation strategies
CANDIDATE_STRATEGIES = {
    "agent1_primary": "Keep Agent 1's architecture, adapt Agent 2's features",
    "agent2_primary": "Keep Agent 2's architecture, adapt Agent 1's features",
    "convention_primary": "Match existing repo patterns",
    "minimal_merge": "Only merge shared intent, defer contested changes",  # NEW
}

def should_use_minimal_merge(conflict: ConflictClassification) -> bool:
    """
    Use minimal merge when semantic overlap is high but
    neither architecture is clearly better.
    """
    return (
        conflict.conflict_type == ConflictType.ARCHITECTURAL and
        conflict.severity in [ConflictSeverity.HIGH, ConflictSeverity.CRITICAL] and
        len(conflict.conflicting_symbols) > 10  # High overlap
    )

class MinimalMergeStrategy:
    """
    Conservative merge that only includes uncontested changes.
    Contested changes are deferred for human review.
    """

    def generate(self, context: ConflictContext) -> ResolutionCandidate:
        # Find uncontested changes (only one agent touched)
        uncontested = self._find_uncontested_files(context)

        # Merge only those
        candidate = self._merge_files(uncontested)

        # Mark contested changes for manual review
        candidate.deferred_changes = context.all_modified_files - uncontested
        candidate.requires_followup = True

        return candidate
```

**C) Enhanced Flaky Test Handling:**

```python
class FlakyTestHandler:
    """Advanced flaky test detection and handling."""

    def __init__(self):
        self.flaky_db = FlakyTestDatabase()  # Persisted flaky test history
        self.retry_budget = 3  # Max retries per test

    def run_with_flaky_handling(self,
                                 tests: List[str],
                                 candidate: ResolutionCandidate) -> TestResult:
        """Run tests with intelligent flaky handling."""
        results = {}
        deterministic_seed = hash(candidate.candidate_id)  # Reproducible

        for test in tests:
            flaky_score = self.flaky_db.get_flakiness(test)

            if flaky_score > 0.5:  # Known flaky
                # Run multiple times with same seed
                outcomes = []
                for i in range(self.retry_budget):
                    outcome = run_test(test, seed=deterministic_seed + i)
                    outcomes.append(outcome)

                # Majority vote
                if outcomes.count("pass") > outcomes.count("fail"):
                    results[test] = TestOutcome.PASS_FLAKY
                else:
                    results[test] = TestOutcome.FAIL_FLAKY
            else:
                # Normal test
                results[test] = run_test(test, seed=deterministic_seed)

        return TestResult(
            outcomes=results,
            flaky_tests=[t for t, r in results.items() if "FLAKY" in str(r)],
            quarantined=self.flaky_db.get_quarantined_tests()
        )

    def update_flakiness(self, test: str, passed: bool, context: str):
        """Update flakiness score based on outcome."""
        self.flaky_db.record_outcome(test, passed, context)
```

**D) Intent Cross-Checking Against Diff Signals:**

```python
class IntentValidator:
    """Cross-check LLM intent extraction against concrete signals."""

    def validate_intent(self,
                        extracted_intent: ExtractedIntent,
                        diff_signals: DiffSignals) -> IntentValidation:
        """
        Compare LLM-extracted intent against diff-derived signals.
        Reduces risk of intent mis-routing.
        """
        confidence_adjustments = []

        # Check 1: Do modified filenames match intent keywords?
        filename_match = self._check_filename_match(
            extracted_intent.keywords,
            diff_signals.modified_files
        )
        if not filename_match:
            confidence_adjustments.append(("filename_mismatch", -0.2))

        # Check 2: Do code symbols match intent?
        symbol_match = self._check_symbol_match(
            extracted_intent.domain,
            diff_signals.new_symbols
        )
        if not symbol_match:
            confidence_adjustments.append(("symbol_mismatch", -0.15))

        # Check 3: Does commit message align?
        if diff_signals.commit_message:
            message_match = self._check_message_alignment(
                extracted_intent.summary,
                diff_signals.commit_message
            )
            if not message_match:
                confidence_adjustments.append(("message_mismatch", -0.1))

        # Adjust confidence
        final_confidence = extracted_intent.confidence
        for reason, adjustment in confidence_adjustments:
            final_confidence += adjustment

        # If confidence drops too low, flag for human review
        needs_human_review = final_confidence < 0.6

        return IntentValidation(
            original_confidence=extracted_intent.confidence,
            adjusted_confidence=final_confidence,
            adjustments=confidence_adjustments,
            needs_human_review=needs_human_review
        )
```

---

### 7.4 Feature Porting (When User Picks Winner)

**CRITICAL: Don't orphan the losing feature**

```python
class FeaturePorter:
    """
    When user picks Architecture A over Architecture B,
    port Feature B to use Architecture A.
    """

    def port_feature(self,
                     winning_architecture: str,
                     losing_feature_branch: str,
                     losing_feature_intent: Intent) -> PortingResult:
        """
        Port the losing feature to the winning architecture.

        Steps:
        1. Extract the INTENT of losing feature (what it does)
        2. Extract the TESTS of losing feature (what it should do)
        3. Checkout winning architecture
        4. Re-implement losing feature's intent on winning architecture
        5. Ensure losing feature's tests pass
        6. Return ported code
        """
        pass
```

---

## 8. Human Escalation System

### 8.1 Escalation Triggers

```python
ALWAYS_ESCALATE = [
    # Risk flags
    "security_sensitive_files",
    "auth_changes",
    "db_migrations",
    "public_api_changes",
    "payment_processing",

    # Confidence issues
    "low_intent_confidence",
    "conflicting_intents",
    "no_passing_candidates",

    # Quality issues
    "tests_removed",
    "tests_weakened",
    "coverage_decreased",
]

CONSIDER_ESCALATE = [
    # Multiple good options
    "candidates_too_similar_in_score",
    "different_tradeoffs",

    # Complexity
    "many_files_changed",
    "architectural_changes",
]
```

### 8.2 Escalation Format

**GitHub Issue Template:**

```markdown
## 🤔 Need Your Input

**Time needed:** ~30 seconds

While combining work from your Claude agents, I found a decision that needs
your judgment.

---

### What Happened

Two features were built that approach **user sessions** differently:

| Feature | Approach | Agent |
|---------|----------|-------|
| Authentication | Cookie-based sessions | Claude Web (abc123) |
| Dashboard | JWT tokens | Claude CLI (def456) |

---

### Your Options

#### [A] Cookie-based sessions ✓ Recommended

**What it means:**
- Sessions stored in browser cookies
- Simpler implementation
- Works great for web apps

**Tradeoffs:**
- Won't work for mobile apps later
- Need CSRF protection

**Risk level:** Low

---

#### [B] JWT tokens

**What it means:**
- Tokens stored client-side
- More complex but more flexible
- Works for web, mobile, and APIs

**Tradeoffs:**
- More code to maintain
- Token refresh logic needed

**Risk level:** Medium

---

### My Recommendation

Based on your codebase (Next.js web app, no mobile), **Option A** is simpler
and fits your current needs. You can migrate to JWT later if you add mobile.

**Confidence:** 85%

---

### Your Response

Reply with one of:
- `A` - Use cookies (recommended)
- `B` - Use JWT
- `explain` - Show me more technical details
- `custom: <your preference>` - Tell me what you want instead

---

<details>
<summary>📋 Technical Details (click to expand)</summary>

### Files Involved

**From Authentication (cookies):**
- `src/lib/session.ts`
- `src/middleware.ts`

**From Dashboard (JWT):**
- `src/lib/jwt.ts`
- `src/middleware.ts` ← CONFLICT

### Code Diff

[Collapsed diff view here]

</details>
```

### 8.3 Escalation Response Handling

```python
class EscalationHandler:
    """Handle user responses to escalations."""

    def process_response(self,
                         escalation_id: str,
                         response: str) -> EscalationResult:
        """
        Process user's response to escalation.

        Responses:
        - "A" or "B" → Select that option
        - "explain" → Post detailed technical comment
        - "custom: ..." → Parse custom preference, generate new candidate
        """

        if response.upper() in ["A", "B", "C", "D"]:
            winner = self.get_option(escalation_id, response.upper())
            losers = self.get_other_options(escalation_id, response.upper())

            # CRITICAL: Port losing features to winning architecture
            for loser in losers:
                self.port_feature(winner, loser)

            return EscalationResult(
                resolved=True,
                winner=winner,
                ported_features=losers
            )

        elif response.lower() == "explain":
            self.post_technical_details(escalation_id)
            return EscalationResult(resolved=False, awaiting_response=True)

        elif response.lower().startswith("custom:"):
            custom_pref = response[7:].strip()
            new_candidate = self.generate_custom_candidate(
                escalation_id, custom_pref
            )
            return EscalationResult(
                resolved=True,
                winner=new_candidate,
                custom=True
            )
```

### 8.4 Escalation Timeout Policy (Enhanced from review feedback)

**Policy-Based Timeouts:**

```python
# Different timeouts for different urgency levels
ESCALATION_TIMEOUT_POLICY = {
    "critical": {
        "reminder_hours": 4,
        "timeout_hours": 24,
        "auto_select": False,  # Never auto-select critical
        "notify_channels": ["github", "slack", "email"],
    },
    "high": {
        "reminder_hours": 12,
        "timeout_hours": 48,
        "auto_select": False,
        "notify_channels": ["github", "slack"],
    },
    "standard": {
        "reminder_hours": 24,
        "timeout_hours": 72,
        "auto_select": True,
        "notify_channels": ["github"],
    },
    "low": {
        "reminder_hours": 48,
        "timeout_hours": 168,  # 1 week
        "auto_select": True,
        "notify_channels": ["github"],
    },
}

class EscalationTimeout:
    """Handle escalation timeouts with policy-based SLAs."""

    def get_timeout_policy(self, escalation: Escalation) -> dict:
        """Determine timeout policy based on escalation characteristics."""
        if escalation.has_risk_flag("security") or escalation.has_risk_flag("payment"):
            return ESCALATION_TIMEOUT_POLICY["critical"]
        elif escalation.has_risk_flag("auth") or escalation.has_risk_flag("db_migration"):
            return ESCALATION_TIMEOUT_POLICY["high"]
        elif escalation.severity == ConflictSeverity.HIGH:
            return ESCALATION_TIMEOUT_POLICY["standard"]
        else:
            return ESCALATION_TIMEOUT_POLICY["low"]

    def check_timeouts(self):
        """Check for escalations that need attention."""

        for escalation in self.get_pending_escalations():
            policy = self.get_timeout_policy(escalation)
            age_hours = escalation.age_in_hours()

            # Reminder at policy-defined time
            if age_hours >= policy["reminder_hours"] and not escalation.reminder_sent:
                self.send_reminder(escalation, policy["notify_channels"])

            # Timeout at policy-defined time
            if age_hours >= policy["timeout_hours"]:
                if policy["auto_select"]:
                    self.auto_select_recommendation(escalation)
                else:
                    # Escalate to team channel for urgent attention
                    self.send_urgent_escalation(escalation)

    def auto_select_recommendation(self, escalation: Escalation):
        """
        Auto-select the recommended option.

        Safeguards:
        - Create PR as DRAFT
        - Add "auto-selected" label
        - Include revert instructions
        - Notify user
        - Log to audit trail
        """
        pass

    def handle_non_responsive_user(self, escalation: Escalation):
        """
        For users who never respond, escalate to default policy.
        """
        if escalation.reminder_count >= 3:
            # After 3 reminders, notify team channel
            self.notify_team_channel(
                f"Escalation {escalation.id} has no response after "
                f"{escalation.reminder_count} reminders. "
                f"Auto-selecting recommendation per policy."
            )
```

---

## 9. Auto-Merge & PRD Execution Mode

### 9.1 Auto-Merge Configuration

```yaml
# .claude/config.yaml

auto_merge:
  # Master switch
  enabled: false  # Default: manual (user clicks merge)

  # Conditions for auto-merge (ALL must be true)
  conditions:
    all_tests_pass: true
    lint_clean: true
    build_passes: true
    no_high_risk_flags: true
    min_confidence: 0.9
    max_files_changed: 50
    no_manual_escalations_pending: true

  # What to auto-merge to
  target: "integration"  # or "main" for full auto

  # Require checks
  required_checks:
    - "build"
    - "test"
    - "lint"

# PRD Execution Mode
prd_mode:
  enabled: false

  # When running full PRD with many agents:
  settings:
    # Auto-merge individual agent work to integration branch
    auto_merge_to_integration: true

    # But require human approval for integration → main
    require_human_for_main: true

    # Create checkpoint PRs every N completed features
    checkpoint_interval: 5

    # Maximum concurrent agents
    max_concurrent_agents: 20

    # Conflict resolution timeout per cluster
    cluster_resolution_timeout_minutes: 30
```

### 9.2 Integration Branch Strategy

For PRD execution with many agents:

```
main ─────────────────────────────────────────────────────► (stable)
       │
       └─── integration ──┬──┬──┬──┬──► (accumulates work)
                          │  │  │  │
            Agent 1 done ─┘  │  │  │
            Agent 2 done ────┘  │  │
            Agent 3 done ───────┘  │
            Agent 4 done ──────────┘
                          │
                          ▼
                    Checkpoint PR to main
                    (human reviews accumulated work)
```

### 9.3 PRD Execution Flow

```python
class PRDExecutor:
    """Execute a full PRD with multiple agents."""

    def execute_prd(self, prd: PRDDocument):
        """
        Execute PRD with automatic coordination.

        Flow:
        1. Decompose PRD into tasks
        2. Spawn agents for tasks (respecting dependencies)
        3. Monitor agent progress
        4. Resolve conflicts as agents complete
        5. Merge to integration branch
        6. Create checkpoint PRs at intervals
        7. Final PR when all tasks complete
        """

        # Decompose
        tasks = self.decompose_prd(prd)

        # Create dependency graph
        task_graph = self.build_dependency_graph(tasks)

        # Execute in waves
        while not task_graph.all_complete():
            # Get tasks ready to execute (dependencies met)
            ready_tasks = task_graph.get_ready_tasks()

            # Spawn agents (up to max_concurrent)
            for task in ready_tasks[:self.config.max_concurrent_agents]:
                self.spawn_agent(task)

            # Wait for completions
            completed = self.wait_for_completions()

            # Resolve conflicts for completed batch
            self.resolve_batch(completed)

            # Checkpoint if needed
            if self.should_checkpoint():
                self.create_checkpoint_pr()

        # Final PR
        self.create_final_pr()
```

### 9.4 Rollback Strategy (from design review)

**CRITICAL: What if a merged PR breaks production?**

The system needs a clear rollback path, not just forward progress.

```python
class RollbackManager:
    """
    Handle rollbacks when merged PRs cause issues.

    Key capabilities:
    - Track which commits came from which agent
    - Support selective revert of individual agent contributions
    - Maintain "known good" checkpoints
    """

    def __init__(self):
        self.checkpoints = CheckpointStore()
        self.agent_commit_map = AgentCommitMap()

    def create_checkpoint(self, branch: str, description: str) -> Checkpoint:
        """
        Create a known-good checkpoint before risky operations.

        Called:
        - Before merging any resolution
        - After successful test suite
        - At PRD wave boundaries
        """
        return Checkpoint(
            sha=get_current_sha(branch),
            branch=branch,
            created_at=datetime.utcnow(),
            description=description,
            tests_passed=True
        )

    def rollback_to_checkpoint(self, checkpoint: Checkpoint) -> RollbackResult:
        """
        Rollback to a known-good checkpoint.

        Steps:
        1. Create backup of current state
        2. Reset to checkpoint SHA
        3. Force push (with safety checks)
        4. Notify affected agents
        """
        pass

    def rollback_agent_contribution(self,
                                     agent_id: str,
                                     preserve_others: bool = True) -> RollbackResult:
        """
        Selectively revert one agent's work while preserving others.

        Useful when:
        - One agent's code causes issues
        - Need to re-do one feature without losing others
        """
        # Get all commits from this agent
        agent_commits = self.agent_commit_map.get_commits(agent_id)

        if preserve_others:
            # Revert only agent's commits (may create conflicts)
            return self._selective_revert(agent_commits)
        else:
            # Full rollback to before agent's first commit
            return self._rollback_to_before(agent_commits[0])

    def identify_breaking_agent(self, failure: TestFailure) -> Optional[str]:
        """
        Use git bisect-like approach to identify which agent's
        contribution caused a failure.
        """
        # Binary search through merge order
        pass

@dataclass
class Checkpoint:
    """A known-good state we can rollback to."""
    sha: str
    branch: str
    created_at: datetime
    description: str
    tests_passed: bool
    agent_ids_included: List[str] = field(default_factory=list)

@dataclass
class AgentCommitMap:
    """Track which commits came from which agent."""
    # Maps commit SHA -> agent_id
    commit_to_agent: Dict[str, str] = field(default_factory=dict)

    def record_merge(self, agent_id: str, commits: List[str]):
        """Record commits from an agent merge."""
        for commit in commits:
            self.commit_to_agent[commit] = agent_id
```

**Rollback Triggers:**

| Trigger | Action | Automation Level |
|---------|--------|------------------|
| Tests fail after merge | Auto-rollback to last checkpoint | AUTOMATIC |
| Production error detected | Alert + manual rollback option | MANUAL |
| User requests rollback | Provide rollback UI | MANUAL |
| CI/CD pipeline fails | Block merge, no rollback needed | AUTOMATIC |

**Checkpoint Strategy:**

```yaml
# .claude/config.yaml
rollback:
  # When to create checkpoints
  checkpoint_triggers:
    - before_any_merge
    - after_successful_tests
    - at_wave_boundaries
    - before_auto_merge_to_main

  # How many checkpoints to keep
  max_checkpoints: 20
  checkpoint_retention_days: 30

  # Auto-rollback settings
  auto_rollback:
    enabled: true
    triggers:
      - test_failure
      - build_failure
    notify_on_rollback: true
```

### 9.5 Edge Cases Handling (from design review)

**Edge Case 1: Agent A depends on Agent B's incomplete work**

```python
class DependencyConflictDetector:
    """Detect when one agent mocked/stubbed another's incomplete API."""

    def detect_mock_mismatch(self,
                              agent_a: AgentInfo,
                              agent_b: AgentInfo) -> Optional[MockMismatch]:
        """
        Scenario: Agent A needs Agent B's API, but B isn't done.
        A mocks it. B finishes with different API signature.

        Detection:
        1. Find mocks/stubs in A's code
        2. Find actual implementations in B's code
        3. Compare signatures
        """
        a_mocks = self._extract_mocks(agent_a.branch)
        b_implementations = self._extract_implementations(agent_b.branch)

        mismatches = []
        for mock in a_mocks:
            impl = b_implementations.get(mock.target)
            if impl and not self._signatures_match(mock, impl):
                mismatches.append(MockMismatch(
                    mock=mock,
                    implementation=impl,
                    agent_a=agent_a.agent_id,
                    agent_b=agent_b.agent_id
                ))

        return mismatches if mismatches else None
```

**Edge Case 2: Same name, different location (semantic duplicate)**

```python
class SemanticDuplicateDetector:
    """
    Detect when two agents create same-named symbols in different locations.
    Git merges cleanly but runtime breaks (duplicate function).
    """

    def detect_duplicates(self, merged_branch: str) -> List[SemanticDuplicate]:
        """
        Scenario: Agent A adds getUserId() at line 50.
        Agent B adds getUserId() at line 200.
        Git says "clean merge". Runtime: duplicate function error.
        """
        # Parse AST of merged code
        # Find all symbol definitions
        # Check for duplicates
        pass
```

**Edge Case 3: Circular resolution dependencies**

```python
class CircularDependencyDetector:
    """
    Detect when resolution order creates circular dependency.

    Scenario: Resolving A+B requires knowing C+D result.
    But resolving C+D requires knowing A+B result.
    """

    def detect_circular_dependencies(self,
                                      clusters: List[ConflictCluster]) -> List[Cycle]:
        """Build resolution dependency graph and find cycles."""
        graph = self._build_resolution_graph(clusters)
        return self._find_cycles(graph)

    def break_cycle(self, cycle: Cycle) -> ResolutionOrder:
        """
        Break circular dependency by:
        1. Finding lowest-risk cluster to resolve first
        2. Using "provisional" resolution
        3. Re-validating after all resolved
        """
        pass
```

**Edge Case 4: All candidates fail validation**

```python
class AllCandidatesFailedHandler:
    """Handle the case when no resolution candidate passes validation."""

    def handle_all_failed(self,
                          conflict: ConflictContext,
                          candidates: List[ResolutionCandidate],
                          failures: List[ValidationFailure]) -> Resolution:
        """
        When all candidates fail:
        1. Analyze failure patterns
        2. Try "minimal merge" (only uncontested changes)
        3. If still fails, escalate with detailed diagnostics
        """
        # Analyze what's failing
        common_failures = self._find_common_failures(failures)

        # Try minimal merge
        minimal = self._generate_minimal_candidate(conflict)
        if self._validate(minimal):
            return Resolution(
                candidate=minimal,
                type="minimal_fallback",
                warning="Used minimal merge - some changes deferred"
            )

        # Escalate with detailed info
        return Resolution(
            candidate=None,
            type="escalate",
            escalation=Escalation(
                reason="all_candidates_failed",
                details=self._format_failure_details(failures),
                suggested_action="manual_resolution"
            )
        )
```

### 9.6 Merge Queue for Main Branch (from Gemini review)

**Problem:** Race condition where main branch updates while resolution is in progress.

The design identifies this race but the solution is vague. In a highly active repo, constant rebase-and-revalidate can cause "livelock" - the coordinator never completes before main changes again.

**Solution: Serialized Merge Queue**

```python
class MergeQueue:
    """
    Serialize final merges to main branch.

    Instead of directly merging to main (race-prone), resolutions
    are placed in a queue. A separate, single-threaded worker
    processes the queue one at a time.
    """

    def __init__(self):
        self.queue: List[QueuedMerge] = []
        self.lock = threading.Lock()
        self.processing = False

    def enqueue(self, resolution: Resolution, branch: str) -> QueueEntry:
        """Add validated resolution to merge queue."""
        entry = QueueEntry(
            id=generate_id(),
            resolution=resolution,
            branch=branch,
            enqueued_at=datetime.utcnow(),
            status="pending"
        )

        with self.lock:
            self.queue.append(entry)
            self._notify_queue_update()

        return entry

    def process_queue(self):
        """
        Process queue entries one at a time.

        Run as a separate workflow or cron job.
        Single-threaded to prevent race conditions.
        """
        while True:
            entry = self._get_next_pending()
            if not entry:
                time.sleep(5)  # Poll interval
                continue

            try:
                entry.status = "processing"

                # Fast-forward check - is main still at expected base?
                if not self._can_fast_forward(entry):
                    # Rebase and revalidate
                    if not self._rebase_and_validate(entry):
                        entry.status = "needs_rebase"
                        continue

                # Perform the merge
                self._merge_to_main(entry)
                entry.status = "merged"

            except Exception as e:
                entry.status = "failed"
                entry.error = str(e)
                self._notify_failure(entry)

    def _can_fast_forward(self, entry: QueueEntry) -> bool:
        """Check if merge would be a fast-forward (no conflicts)."""
        current_main = git_rev_parse("main")
        return entry.resolution.base_sha == current_main

    def _rebase_and_validate(self, entry: QueueEntry) -> bool:
        """Rebase resolution onto current main and revalidate."""
        # Rebase
        if not git_rebase(entry.branch, "main"):
            return False

        # Run quick validation (tests already passed before queuing)
        return self._quick_validate(entry.branch)

@dataclass
class QueueEntry:
    """An entry in the merge queue."""
    id: str
    resolution: Resolution
    branch: str
    enqueued_at: datetime
    status: str  # pending, processing, merged, failed, needs_rebase
    error: Optional[str] = None
    processed_at: Optional[datetime] = None
```

**GitHub Actions Merge Queue Workflow:**

```yaml
# .github/workflows/merge-queue.yml
name: Merge Queue Processor

on:
  schedule:
    - cron: '* * * * *'  # Every minute
  workflow_dispatch:

concurrency:
  group: merge-queue-${{ github.repository }}
  cancel-in-progress: false  # Never cancel - single processor

jobs:
  process:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: main
          fetch-depth: 0

      - name: Process Merge Queue
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python -m orchestrator.merge_queue process --single
```

### 9.7 Kill Switch (from Gemini/ChatGPT o3 reviews)

**Problem:** No mechanism for admins to immediately halt the coordination system.

If the coordinator goes rogue (infinite loop, bad resolutions, cost overrun), there's no clearly defined way to stop it.

**Solution: Multi-Level Kill Switch**

```python
class KillSwitch:
    """
    Emergency stop mechanism for the coordination system.

    Levels:
    1. PAUSE - Stop processing new work, complete in-progress
    2. STOP - Cancel in-progress work, archive branches
    3. EMERGENCY - Immediate halt, may leave inconsistent state
    """

    KILL_SWITCH_FILE = ".claude/KILL_SWITCH"
    KILL_SWITCH_LABEL = "stop-claude"

    @classmethod
    def check_kill_switch(cls) -> Optional[KillSwitchStatus]:
        """Check if kill switch is engaged. Call at start of every operation."""
        # Check 1: File-based kill switch
        if Path(cls.KILL_SWITCH_FILE).exists():
            content = Path(cls.KILL_SWITCH_FILE).read_text()
            return KillSwitchStatus(
                engaged=True,
                level=content.strip().upper() or "PAUSE",
                source="file"
            )

        # Check 2: GitHub issue/PR with kill switch label
        if cls._has_kill_switch_label():
            return KillSwitchStatus(
                engaged=True,
                level="STOP",
                source="github_label"
            )

        # Check 3: Environment variable
        if os.getenv("CLAUDE_KILL_SWITCH"):
            return KillSwitchStatus(
                engaged=True,
                level=os.getenv("CLAUDE_KILL_SWITCH_LEVEL", "PAUSE"),
                source="env"
            )

        return None

    @classmethod
    def _has_kill_switch_label(cls) -> bool:
        """Check for kill switch label on any open issue/PR."""
        # gh api repos/:owner/:repo/issues?labels=stop-claude
        pass

    @classmethod
    def engage(cls, level: str, reason: str):
        """Engage the kill switch."""
        Path(cls.KILL_SWITCH_FILE).write_text(f"{level}\n{reason}\n{datetime.utcnow()}")
        logging.critical(f"Kill switch engaged: {level} - {reason}")

        # Create GitHub issue for visibility
        cls._create_kill_switch_issue(level, reason)

    @classmethod
    def disengage(cls, operator: str):
        """Disengage the kill switch (requires explicit action)."""
        if Path(cls.KILL_SWITCH_FILE).exists():
            Path(cls.KILL_SWITCH_FILE).unlink()

        logging.info(f"Kill switch disengaged by {operator}")
        cls._close_kill_switch_issue(operator)

@dataclass
class KillSwitchStatus:
    """Current kill switch status."""
    engaged: bool
    level: str  # PAUSE, STOP, EMERGENCY
    source: str  # file, github_label, env
    message: Optional[str] = None
```

**Kill Switch Actions by Level:**

| Level | In-Progress Work | New Work | Branches | Recovery |
|-------|-----------------|----------|----------|----------|
| PAUSE | Complete | Reject | Keep | Automatic when disengaged |
| STOP | Cancel gracefully | Reject | Archive to `claude-archive/**` | Manual review required |
| EMERGENCY | Immediate kill | Reject | Keep as-is | Manual cleanup required |

**Integration with Coordinator:**

```python
class Coordinator:
    def run(self):
        # Check kill switch at start
        kill_status = KillSwitch.check_kill_switch()
        if kill_status:
            logging.warning(f"Kill switch engaged: {kill_status}")
            if kill_status.level == "PAUSE":
                return {"status": "paused", "reason": kill_status.message}
            elif kill_status.level == "STOP":
                self._archive_in_progress_work()
                return {"status": "stopped", "reason": kill_status.message}
            else:  # EMERGENCY
                sys.exit(1)

        # Normal operation...
        for step in self.pipeline:
            # Check kill switch before each step
            if KillSwitch.check_kill_switch():
                self._handle_mid_operation_kill()
                return
            step.execute()
```

**CLI Commands:**

```bash
# Engage kill switch
./orchestrator kill-switch engage --level=PAUSE --reason="Cost overrun"
./orchestrator kill-switch engage --level=STOP --reason="Bad resolutions detected"

# Check status
./orchestrator kill-switch status

# Disengage (requires confirmation)
./orchestrator kill-switch disengage --operator="admin@example.com" --confirm
```

---

## 10. Learning & Self-Improvement

### 10.1 Conflict Pattern Memory ("rerere for agents")

```python
class ConflictPatternMemory:
    """
    Remember how similar conflicts were resolved.
    Like git rerere, but for semantic conflicts.
    """

    def __init__(self):
        self.patterns_db = PatternDatabase()

    def compute_pattern_hash(self, conflict: ConflictContext) -> str:
        """
        Compute a hash that identifies similar conflicts.

        Factors:
        - Files involved (normalized paths)
        - Conflict type
        - Intent categories (auth, db, api, etc.)
        - Code structure (AST-level similarity)
        """
        pass

    def find_similar_resolution(self,
                                 conflict: ConflictContext) -> Optional[Resolution]:
        """
        Look up similar past conflicts and their resolutions.

        Returns resolution if:
        - Similar conflict found
        - Resolution was successful (PR merged, no revert)
        - Confidence threshold met
        """
        pattern_hash = self.compute_pattern_hash(conflict)
        matches = self.patterns_db.find_similar(pattern_hash)

        for match in matches:
            if match.was_successful() and match.confidence > 0.8:
                return match.resolution

        return None

    def record_resolution(self,
                          conflict: ConflictContext,
                          resolution: Resolution,
                          outcome: ResolutionOutcome):
        """
        Record a resolution for future matching.

        Outcome tracking:
        - PR merged without edits → strong positive
        - PR merged with minor edits → weak positive
        - PR reverted → strong negative
        - Bug linked to resolution → negative
        """
        pass
```

### 10.2 Strategy Performance Tracking

```python
class StrategyTracker:
    """Track which resolution strategies work best."""

    def __init__(self):
        self.stats = StrategyStats()

    def record_outcome(self,
                       conflict_type: ConflictType,
                       strategy_used: str,
                       outcome: Outcome):
        """Record strategy outcome for learning."""
        self.stats.record(
            conflict_type=conflict_type,
            strategy=strategy_used,
            outcome=outcome
        )

    def get_recommended_strategies(self,
                                    conflict_type: ConflictType) -> List[str]:
        """
        Get strategies ranked by historical performance.

        Returns strategies ordered by win rate for this conflict type.
        """
        return self.stats.rank_strategies(conflict_type)

    def should_skip_strategy(self,
                              conflict_type: ConflictType,
                              strategy: str) -> bool:
        """
        Check if a strategy consistently fails for this conflict type.

        Skip if win rate < 10% with sufficient sample size.
        """
        win_rate = self.stats.get_win_rate(conflict_type, strategy)
        sample_size = self.stats.get_sample_size(conflict_type, strategy)

        return win_rate < 0.1 and sample_size > 10
```

### 10.3 Self-Critique Stage

```python
class SelfCritic:
    """
    Optional critic pass on winning candidate before delivery.
    Uses separate LLM call to find subtle issues.
    """

    def critique(self,
                 candidate: ResolutionCandidate,
                 context: ConflictContext) -> CritiqueResult:
        """
        Critique a resolution candidate.

        Checks:
        - Security issues
        - Performance regressions
        - Missing error handling
        - Inconsistent patterns
        - Subtle logic errors
        """

        prompt = f"""
        Review this code resolution for subtle issues.

        Context:
        - Agent 1 was trying to: {context.intent1.summary}
        - Agent 2 was trying to: {context.intent2.summary}

        Resolution:
        {candidate.diff}

        Check for:
        1. Does this fully satisfy BOTH intents?
        2. Any security vulnerabilities introduced?
        3. Any performance issues?
        4. Any missing error handling?
        5. Any deviation from project patterns?

        Respond with:
        - APPROVED if no issues
        - ISSUES: <list> if problems found
        """

        result = self.llm.invoke(prompt)
        return self.parse_critique(result)

    def should_block(self, critique: CritiqueResult) -> bool:
        """Determine if critique should block delivery."""
        return critique.has_security_issues or critique.has_critical_bugs
```

### 10.4 Feedback Loop to Agents

```python
class AgentFeedbackLoop:
    """
    Provide feedback to agents about conflict patterns.
    Helps prevent recurring conflicts.
    """

    def generate_guidance(self) -> AgentGuidance:
        """
        Generate guidance for agents based on conflict history.

        Examples:
        - "Auth module is being modified by another agent. Coordinate or wait."
        - "Last 3 conflicts were in src/api/. Consider modular boundaries."
        - "Prefer existing session library over new implementations."
        """

        # Analyze recent conflicts
        recent_conflicts = self.get_recent_conflicts(days=7)

        # Find patterns
        hot_spots = self.find_hot_spots(recent_conflicts)
        recurring_issues = self.find_recurring_issues(recent_conflicts)

        # Generate guidance
        guidance = AgentGuidance()

        for hot_spot in hot_spots:
            guidance.add_warning(
                f"File {hot_spot.path} is frequently conflicted. "
                f"Check if another agent is working here before modifying."
            )

        for issue in recurring_issues:
            guidance.add_recommendation(issue.recommendation)

        return guidance

    def inject_guidance(self, agent_context: str, guidance: AgentGuidance) -> str:
        """Add guidance to agent's context."""
        return f"""
        {agent_context}

        ## Coordination Guidance

        {guidance.format()}
        """
```

### 10.5 Integration with Orchestrator Learning

```python
class ConflictLearningIntegration:
    """
    Integrate conflict resolution learning with orchestrator's
    existing learning system.
    """

    def __init__(self, orchestrator_learning: LearningEngine):
        self.orchestrator = orchestrator_learning

    def report_resolution(self, resolution: Resolution, outcome: Outcome):
        """Report resolution to orchestrator's learning system."""

        # Convert to orchestrator's learning format
        learning_entry = {
            "type": "conflict_resolution",
            "conflict_type": resolution.conflict_type,
            "strategy_used": resolution.strategy,
            "agents_involved": resolution.agent_ids,
            "files_affected": resolution.files,
            "outcome": outcome.status,
            "human_intervention_required": outcome.was_escalated,
            "time_to_resolve": outcome.resolution_time,
            "lessons": self.extract_lessons(resolution, outcome)
        }

        self.orchestrator.record_learning(learning_entry)

    def extract_lessons(self,
                        resolution: Resolution,
                        outcome: Outcome) -> List[str]:
        """Extract lessons for the learning report."""
        lessons = []

        if outcome.was_reverted:
            lessons.append(
                f"Resolution of {resolution.conflict_type} using "
                f"{resolution.strategy} was reverted. Consider different approach."
            )

        if outcome.human_edited_before_merge:
            lessons.append(
                f"Human edited resolution before merge. "
                f"Patterns: {outcome.edit_patterns}"
            )

        return lessons
```

---

## 11. Data Models

### 11.1 Core Models

```python
from dataclasses import dataclass
from typing import List, Dict, Optional, Literal
from datetime import datetime
from enum import Enum


# ============================================================================
# Agent Models
# ============================================================================

@dataclass
class AgentInfo:
    """Information about an active agent."""
    agent_id: str
    agent_type: Literal["claude-web", "claude-cli"]
    session_id: str
    branch: str
    base_sha: str
    head_sha: str
    task_description: str
    status: Literal["in_progress", "complete", "failed", "stale"]
    started_at: datetime
    completed_at: Optional[datetime]
    manifest: Optional[dict]
    derived_changes: Optional[dict]  # From git diff, not manifest


@dataclass
class AgentManifest:
    """Agent's self-reported manifest (verified against git)."""
    schema_version: str
    agent: dict
    git: dict
    task: dict
    work: dict
    risk_flags: List[str]
    interfaces_changed: List[str]
    completion: Optional[dict]


# ============================================================================
# Conflict Models
# ============================================================================

class ConflictType(str, Enum):
    NONE = "none"
    TEXTUAL = "textual"
    SEMANTIC = "semantic"
    ARCHITECTURAL = "architectural"
    DEPENDENCY = "dependency"


class ConflictSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DependencyConflict:
    """A conflict in package dependencies."""
    package: str
    agent1_version: Optional[str]
    agent2_version: Optional[str]
    conflict_type: Literal["version_mismatch", "incompatible", "duplicate"]
    resolution: Optional[str]


@dataclass
class ConflictCluster:
    """A group of related conflicts."""
    cluster_id: str
    cluster_type: Literal["domain", "file", "dependency"]
    agent_ids: List[str]
    shared_files: List[str]
    shared_domains: List[str]
    depends_on_clusters: List[str]


@dataclass
class ConflictClassification:
    """Complete classification of a conflict."""
    conflict_type: ConflictType
    severity: ConflictSeverity
    conflicting_files: List[str]
    conflicting_symbols: List[str]
    dependency_conflicts: List[DependencyConflict]
    agents_involved: List[str]
    clusters: List[ConflictCluster]
    recommended_path: Literal["fast_merge", "auto_resolve", "escalate"]
    confidence: float
    risk_flags: List[str]


# ============================================================================
# Intent Models
# ============================================================================

@dataclass
class Constraint:
    """A constraint extracted from agent intent."""
    description: str
    constraint_type: Literal["hard", "soft"]
    evidence: str
    source: Literal["task", "code", "tests", "manifest", "inferred"]


@dataclass
class ExtractedIntent:
    """Intent extracted from an agent's work."""
    agent_id: str
    primary_intent: str
    secondary_effects: List[str]
    hard_constraints: List[Constraint]
    soft_constraints: List[Constraint]
    assumptions: List[str]
    evidence: List[dict]
    confidence: Literal["high", "medium", "low"]


@dataclass
class IntentComparison:
    """Comparison of intents from multiple agents."""
    relationship: Literal["compatible", "conflicting", "orthogonal"]
    shared_constraints: List[Constraint]
    conflicting_constraints: List[tuple]
    suggested_resolution: str
    requires_human_judgment: bool


# ============================================================================
# Resolution Models
# ============================================================================

@dataclass
class ResolutionCandidate:
    """A candidate resolution."""
    candidate_id: str
    strategy: Literal[
        "agent1_primary",
        "agent2_primary",
        "convention_primary",
        "fresh_synthesis"
    ]
    branch_name: str
    diff_from_base: str
    files_modified: List[str]

    # Validation results
    build_passed: bool
    lint_score: float
    tests_passed: int
    tests_failed: int

    # Scores
    correctness_score: float
    simplicity_score: float
    convention_score: float
    intent_satisfaction_score: float
    total_score: float

    # Explanation
    summary: str
    technical_details: str


@dataclass
class Resolution:
    """Final resolution result."""
    resolution_id: str
    winning_candidate: ResolutionCandidate
    ported_features: List[str]
    pr_number: Optional[int]
    pr_url: Optional[str]
    was_escalated: bool
    escalation_response: Optional[str]
    resolved_at: datetime


# ============================================================================
# Escalation Models
# ============================================================================

@dataclass
class EscalationOption:
    """An option presented in escalation."""
    option_id: str
    title: str
    description: str
    tradeoffs: List[str]
    risk_level: Literal["low", "medium", "high"]
    is_recommended: bool
    candidate_id: str


@dataclass
class Escalation:
    """An escalation request."""
    escalation_id: str
    created_at: datetime
    conflict: ConflictClassification
    intent_comparison: IntentComparison
    options: List[EscalationOption]
    recommendation: str
    recommendation_reason: str
    confidence: float

    # Status
    status: Literal["pending", "resolved", "timeout"]
    response: Optional[str]
    resolved_at: Optional[datetime]

    # GitHub references
    issue_number: Optional[int]
    issue_url: Optional[str]


# ============================================================================
# Learning Models
# ============================================================================

@dataclass
class ResolutionOutcome:
    """Outcome of a resolution for learning."""
    resolution_id: str
    pr_merged: bool
    pr_reverted: bool
    human_edited_before_merge: bool
    edit_patterns: List[str]
    bugs_linked: List[str]
    time_to_merge_hours: float
    success_score: float  # Computed from above


@dataclass
class ConflictPattern:
    """A recorded conflict pattern for rerere-like matching."""
    pattern_hash: str
    conflict_type: ConflictType
    files_involved: List[str]
    intent_categories: List[str]
    resolution_strategy: str
    resolution_diff_hash: str
    outcomes: List[ResolutionOutcome]
    success_rate: float
```

---

## 12. Configuration

### 12.1 Complete Configuration Schema

```yaml
# .claude/config.yaml
# Multi-Agent Coordination Configuration

# ============================================================================
# COORDINATION
# ============================================================================
coordination:
  # Enable multi-agent coordination
  enabled: true

  # How confident must we be to auto-resolve?
  auto_resolve_confidence: 0.8

  # Maximum concurrent agents
  max_concurrent_agents: 20

  # Batch window: wait this long for more agents before resolving
  batch_window_minutes: 10

  # Stale agent timeout
  stale_agent_hours: 72

# ============================================================================
# CONFLICT DETECTION
# ============================================================================
detection:
  # Always escalate changes to these paths
  always_escalate_paths:
    - "*.env*"
    - "**/auth/**"
    - "**/security/**"
    - "**/migrations/**"
    - "**/payment/**"

  # Protected files (changes require extra scrutiny)
  protected_files:
    - "package.json"
    - "requirements.txt"
    - "Dockerfile"
    - "*.lock"

  # Risk flag patterns
  risk_patterns:
    auth: ["**/auth/**", "**/login/**", "**/session/**"]
    security: ["**/security/**", "**/crypto/**", "**/*secret*"]
    database: ["**/migrations/**", "**/models/**", "**/schema/**"]
    api: ["**/api/**", "**/routes/**", "**/endpoints/**"]

# ============================================================================
# RESOLUTION
# ============================================================================
resolution:
  # Maximum candidates to generate
  max_candidates: 3

  # Strategies to use (order matters)
  strategies:
    - "agent1_primary"
    - "agent2_primary"
    - "convention_primary"
    # - "fresh_synthesis"  # Uncomment for architectural conflicts

  # Time budget per candidate (seconds)
  candidate_time_budget: 300

  # Require minimum candidate diversity
  min_candidate_diversity: 0.3

# ============================================================================
# VALIDATION
# ============================================================================
validation:
  # Build command (auto-detected if not specified)
  build_command: null  # e.g., "npm run build"

  # Test commands by tier
  test_commands:
    targeted: null  # e.g., "npm test -- --findRelatedTests"
    full: null      # e.g., "npm test"

  # Lint command
  lint_command: null  # e.g., "npm run lint"

  # Timeouts
  build_timeout: 300
  test_timeout: 600

  # Flaky test handling
  flaky_test_retry: true
  known_flaky_tests: []

# ============================================================================
# AUTO-MERGE
# ============================================================================
auto_merge:
  # Master switch
  enabled: false

  # Conditions (ALL must be true)
  conditions:
    all_tests_pass: true
    lint_clean: true
    build_passes: true
    no_high_risk_flags: true
    min_confidence: 0.9
    max_files_changed: 50

  # Target branch
  target: "integration"  # or "main"

  # Required status checks
  required_checks:
    - "build"
    - "test"

# ============================================================================
# PRD MODE
# ============================================================================
prd_mode:
  enabled: false

  # Auto-merge to integration branch
  auto_merge_to_integration: true

  # Require human for main
  require_human_for_main: true

  # Checkpoint every N features
  checkpoint_interval: 5

  # Wave-based resolution
  enable_clustering: true
  cluster_resolution_timeout: 1800  # 30 minutes

# ============================================================================
# ESCALATION
# ============================================================================
escalation:
  # Notification channels
  channels:
    - github_issue
    # - slack
    # - email

  # Slack webhook (if enabled)
  slack_webhook: null

  # Reminder after N hours
  reminder_hours: 24

  # Timeout policy
  timeout:
    hours: 72
    action: "auto_select_low_risk"  # or "keep_waiting"

  # Max options to show (reduce cognitive load)
  max_options: 2

# ============================================================================
# LEARNING
# ============================================================================
learning:
  # Enable pattern memory
  pattern_memory_enabled: true

  # Enable strategy tracking
  strategy_tracking_enabled: true

  # Enable self-critique
  self_critique_enabled: false  # Optional, adds latency

  # Enable agent feedback
  agent_feedback_enabled: true

  # Pattern matching threshold
  pattern_match_threshold: 0.8

# ============================================================================
# NOTIFICATIONS
# ============================================================================
notifications:
  # Notify on completion
  on_completion: true

  # Notify on escalation
  on_escalation: true

  # Notify on auto-merge
  on_auto_merge: true

  # Include in notification
  include_summary: true
  include_file_list: true
  include_pr_link: true

# ============================================================================
# LLM CONFIGURATION
# ============================================================================
llm:
  # Provider for different tasks
  providers:
    intent_extraction: "anthropic"  # cheaper/faster
    code_generation: "anthropic"    # best quality
    critic: "anthropic"             # optional

  # Models
  models:
    intent_extraction: "claude-3-haiku-20240307"
    code_generation: "claude-sonnet-4-20250514"
    critic: "claude-sonnet-4-20250514"

  # Fallback provider
  fallback_provider: "openai"
```

### 12.2 Default Detection

```python
class ConfigAutoDetector:
    """Auto-detect configuration based on project type."""

    def detect_config(self, repo_path: str) -> dict:
        """Detect optimal configuration for this repo."""

        config = {}

        # Detect build system
        if (repo_path / "package.json").exists():
            config["build_command"] = "npm run build"
            config["test_commands"] = {
                "targeted": "npm test -- --findRelatedTests",
                "full": "npm test"
            }
            config["lint_command"] = "npm run lint"

        elif (repo_path / "requirements.txt").exists():
            config["build_command"] = "python -m py_compile"
            config["test_commands"] = {
                "targeted": "pytest --testmon",
                "full": "pytest"
            }
            config["lint_command"] = "flake8"

        elif (repo_path / "go.mod").exists():
            config["build_command"] = "go build ./..."
            config["test_commands"] = {
                "targeted": "go test ./...",
                "full": "go test ./..."
            }
            config["lint_command"] = "golangci-lint run"

        # Add more detectors...

        return config
```

### 12.3 Operational Configuration (from review feedback)

**Observability & Metrics:**

```yaml
# .claude/config.yaml (continued)

# ============================================================================
# OBSERVABILITY (from review feedback)
# ============================================================================
observability:
  # Enable metrics collection
  metrics_enabled: true

  # Per-stage timing metrics
  stage_metrics:
    - stage: conflict_detection
      timeout_minutes: 10
      alert_threshold_minutes: 5
    - stage: intent_extraction
      timeout_minutes: 5
      alert_threshold_minutes: 3
    - stage: candidate_generation
      timeout_minutes: 15
      alert_threshold_minutes: 10
    - stage: validation
      timeout_minutes: 30
      alert_threshold_minutes: 20
    - stage: delivery
      timeout_minutes: 5
      alert_threshold_minutes: 2

  # Export metrics to (optional)
  export:
    prometheus: false
    statsd: false
    cloudwatch: false

# ============================================================================
# COST CONTROLS (from review feedback)
# ============================================================================
cost_controls:
  # Rate limits on agent operations
  max_agents_per_hour: 50
  max_resolution_attempts_per_day: 100

  # LLM cost controls
  max_tokens_per_resolution: 50000
  prefer_cheaper_models: true  # Use haiku for simple tasks

  # Test budget (prevent runaway test suites)
  max_test_time_per_candidate_minutes: 10
  skip_full_suite_if_targeted_passes: true

# ============================================================================
# CONCURRENCY CONTROLS (from review feedback)
# ============================================================================
concurrency:
  # Coordinator race condition handling
  use_github_environment_locks: true
  lock_environment_name: "claude-coordinator"

  # Prevent multiple coordinators running
  coordinator_lock:
    type: "github_concurrency"  # or "file_lock", "redis_lock"
    timeout_minutes: 60
    cancel_in_progress: false

  # Agent branch protection
  agent_branch_rules:
    max_branches_per_agent: 5
    stale_branch_cleanup_hours: 168  # 1 week

# ============================================================================
# AUDIT & TRACEABILITY (from review feedback)
# ============================================================================
audit:
  # Link PRs to agent branches and manifests
  include_agent_links_in_pr: true

  # Audit log retention
  log_retention_days: 90

  # What to log
  log_events:
    - agent_registered
    - conflict_detected
    - resolution_started
    - candidate_generated
    - validation_passed
    - validation_failed
    - escalation_created
    - escalation_resolved
    - pr_created
    - pr_merged
```

**Coordinator Concurrency Guard:**

```python
class CoordinatorLock:
    """
    Prevent multiple coordinator instances from running simultaneously.
    Uses GitHub environment protection rules or external locking.
    """

    def __init__(self, config: dict):
        self.lock_type = config.get("type", "github_concurrency")
        self.timeout = config.get("timeout_minutes", 60)

    async def acquire(self) -> bool:
        """Acquire coordinator lock. Returns False if another instance is running."""
        if self.lock_type == "github_concurrency":
            # GitHub handles this via concurrency: group in workflow
            return True
        elif self.lock_type == "file_lock":
            return self._acquire_file_lock()
        elif self.lock_type == "redis_lock":
            return await self._acquire_redis_lock()

    async def release(self):
        """Release coordinator lock."""
        pass

    def _check_for_race(self, main_sha_at_start: str, main_sha_now: str) -> bool:
        """Check if main branch moved during resolution."""
        return main_sha_at_start != main_sha_now
```

**Stage Metrics Collector:**

```python
class StageMetrics:
    """Collect and export per-stage metrics."""

    def __init__(self, config: dict):
        self.enabled = config.get("metrics_enabled", True)
        self.stage_configs = {s["stage"]: s for s in config.get("stage_metrics", [])}

    @contextmanager
    def track_stage(self, stage_name: str):
        """Context manager to track stage duration."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self._record_metric(stage_name, duration)
            self._check_timeout(stage_name, duration)

    def _record_metric(self, stage: str, duration: float):
        """Record metric for export."""
        # Export to configured backends (prometheus, statsd, etc.)
        pass

    def _check_timeout(self, stage: str, duration: float):
        """Check if stage exceeded timeout and alert if needed."""
        config = self.stage_configs.get(stage, {})
        timeout = config.get("timeout_minutes", 60) * 60
        if duration > timeout:
            self._alert_timeout(stage, duration, timeout)
```

---

## 13. GitHub Actions Workflows

### 13.1 Branch Ping Workflow (Untrusted)

```yaml
# .github/workflows/claude-branch-ping.yml
name: Claude Branch Ping

on:
  push:
    branches:
      - 'claude/**'

permissions:
  contents: read

jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - name: Notify coordinator
        uses: peter-evans/repository-dispatch@v2
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          event-type: claude-branch-update
          client-payload: |
            {
              "branch": "${{ github.ref_name }}",
              "sha": "${{ github.sha }}",
              "actor": "${{ github.actor }}",
              "timestamp": "${{ github.event.head_commit.timestamp }}"
            }
```

### 13.2 Coordinator Workflow (Trusted)

```yaml
# .github/workflows/claude-coordinator.yml
name: Claude Coordinator

on:
  repository_dispatch:
    types: [claude-branch-update]
  schedule:
    - cron: '*/5 * * * *'
  workflow_dispatch:
    inputs:
      force_resolve:
        description: 'Force resolution'
        type: boolean
        default: false
      dry_run:
        description: 'Dry run (no PRs)'
        type: boolean
        default: false

permissions:
  contents: write
  pull-requests: write
  issues: write
  actions: read

concurrency:
  group: claude-coordinator-${{ github.repository }}
  cancel-in-progress: false

jobs:
  coordinate:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout (trusted code from main)
        uses: actions/checkout@v4
        with:
          ref: main
          fetch-depth: 0

      - name: Fetch all branches
        run: |
          git fetch --all
          git branch -r | grep 'origin/claude/' || echo "No claude branches"

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install orchestrator
        run: pip install -e .

      - name: Load configuration
        id: config
        run: |
          if [ -f ".claude/config.yaml" ]; then
            echo "config_exists=true" >> $GITHUB_OUTPUT
          else
            echo "config_exists=false" >> $GITHUB_OUTPUT
          fi

      - name: Run coordinator
        id: coordinate
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          python -m orchestrator.coordinator \
            --mode=${{ github.event_name == 'repository_dispatch' && 'event' || 'scheduled' }} \
            --force=${{ inputs.force_resolve || 'false' }} \
            --dry-run=${{ inputs.dry_run || 'false' }} \
            --output=github

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: coordinator-logs-${{ github.run_id }}
          path: |
            .claude/logs/
            .claude/manifests/
          retention-days: 30

      - name: Post summary
        if: always()
        run: |
          echo "## Coordination Summary" >> $GITHUB_STEP_SUMMARY
          cat .claude/logs/summary.md >> $GITHUB_STEP_SUMMARY || echo "No summary generated"
```

### 13.3 Escalation Response Workflow

```yaml
# .github/workflows/claude-escalation-response.yml
name: Claude Escalation Response

on:
  issue_comment:
    types: [created]

jobs:
  process-response:
    if: |
      contains(github.event.issue.labels.*.name, 'claude-escalation') &&
      github.event.comment.user.login != 'github-actions[bot]'

    runs-on: ubuntu-latest

    permissions:
      contents: write
      pull-requests: write
      issues: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          ref: main
          fetch-depth: 0

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install orchestrator
        run: pip install -e .

      - name: Process response
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          ISSUE_NUMBER: ${{ github.event.issue.number }}
          COMMENT_BODY: ${{ github.event.comment.body }}
        run: |
          python -m orchestrator.escalation_handler \
            --issue=$ISSUE_NUMBER \
            --response="$COMMENT_BODY"
```

---

## 14. New Modules to Implement

### 14.1 Module Structure

```
src/
├── __init__.py                    # Existing
├── schema.py                      # Existing - extend with new models
├── engine.py                      # Existing - no changes
├── cli.py                         # Existing - add new commands
├── coordinator/                   # NEW: Coordination package
│   ├── __init__.py
│   ├── main.py                    # Entry point for coordinator
│   ├── discovery.py               # Agent branch discovery
│   ├── registry.py                # Agent registry management
│   └── manifest_store.py          # Manifest storage (artifacts)
├── conflict/                      # NEW: Conflict detection
│   ├── __init__.py
│   ├── detector.py                # Stage 0: Detection
│   ├── classifier.py              # Conflict classification
│   ├── clusterer.py               # Conflict clustering
│   └── dependency_resolver.py     # Dependency conflict handling
├── resolution/                    # NEW: Resolution pipeline
│   ├── __init__.py
│   ├── pipeline.py                # Main pipeline orchestration
│   ├── context.py                 # Stage 1: Context assembly
│   ├── intent.py                  # Stage 2: Intent extraction
│   ├── harmonizer.py              # Stage 3: Interface harmonization
│   ├── test_synthesis.py          # Stage 4: Test synthesis
│   ├── candidate_generator.py     # Stage 5: Candidate generation
│   ├── validator.py               # Stage 6: Validation
│   ├── selector.py                # Stage 7: Selection
│   └── porter.py                  # Feature porting
├── escalation/                    # NEW: Escalation handling
│   ├── __init__.py
│   ├── creator.py                 # Create escalation issues
│   ├── handler.py                 # Handle responses
│   └── templates.py               # Issue templates
├── delivery/                      # NEW: PR/merge delivery
│   ├── __init__.py
│   ├── pr_creator.py              # Create PRs
│   ├── auto_merger.py             # Auto-merge logic
│   └── notifier.py                # Notifications
├── learning/                      # Existing - extend
│   ├── __init__.py
│   ├── pattern_memory.py          # NEW: Conflict pattern memory
│   ├── strategy_tracker.py        # NEW: Strategy performance
│   ├── self_critic.py             # NEW: Self-critique
│   └── feedback_loop.py           # NEW: Agent feedback
├── git_ops/                       # NEW: Git operations
│   ├── __init__.py
│   ├── branch_ops.py              # Branch operations
│   ├── merge_ops.py               # Merge operations
│   └── diff_analyzer.py           # Diff analysis
└── config/                        # NEW: Configuration
    ├── __init__.py
    ├── loader.py                  # Load config
    ├── detector.py                # Auto-detect config
    └── schema.py                  # Config validation
```

### 14.2 Key Module Interfaces

```python
# coordinator/main.py
class Coordinator:
    """Main coordinator entry point."""

    def __init__(self, config: Config):
        self.config = config
        self.discovery = AgentDiscovery()
        self.registry = AgentRegistry()
        self.detector = ConflictDetector()
        self.pipeline = ResolutionPipeline()
        self.delivery = DeliveryManager()
        self.learning = LearningManager()

    def run(self, mode: str, force: bool = False, dry_run: bool = False):
        """
        Main coordination loop.

        Args:
            mode: "event" (triggered by push) or "scheduled" (cron)
            force: Force resolution even if not all agents complete
            dry_run: Don't create PRs, just report what would happen
        """
        # 1. Discover agent branches
        branches = self.discovery.find_claude_branches()

        # 2. Load/derive manifests
        for branch in branches:
            manifest = self.registry.get_or_create_manifest(branch)

        # 3. Find completed agents
        completed = self.registry.get_completed_agents()

        if not completed:
            return CoordinatorResult(status="no_completed_agents")

        # 4. Detect conflicts
        classification = self.detector.classify(completed)

        # 5. Route based on classification
        if classification.conflict_type == ConflictType.NONE:
            # Fast path: just merge
            result = self.delivery.fast_merge(completed, dry_run)

        elif classification.recommended_path == "escalate":
            # Must escalate
            result = self.escalation.create(classification)

        else:
            # Run resolution pipeline
            resolution = self.pipeline.resolve(classification)

            if resolution.needs_escalation:
                result = self.escalation.create(resolution)
            else:
                result = self.delivery.deliver(resolution, dry_run)

        # 6. Record for learning
        self.learning.record(classification, result)

        return result
```

```python
# resolution/pipeline.py
class ResolutionPipeline:
    """Main resolution pipeline."""

    def resolve(self, classification: ConflictClassification) -> Resolution:
        """Run the full resolution pipeline."""

        # Stage 1: Context Assembly
        context = self.context_assembler.assemble(classification)

        # Stage 2: Intent Extraction
        intents = self.intent_extractor.extract(context)

        if intents.confidence == "low":
            return Resolution(needs_escalation=True, reason="low_intent_confidence")

        # Stage 3: Interface Harmonization
        harmonized = self.harmonizer.harmonize(context, intents)

        if not harmonized.build_passes:
            return Resolution(needs_escalation=True, reason="cannot_harmonize")

        # Stage 4: Test Synthesis
        tests = self.test_synthesizer.synthesize(harmonized, intents)

        # Stage 5: Candidate Generation
        candidates = self.candidate_generator.generate(
            harmonized, intents, tests
        )

        # Stage 6: Validation
        validated = self.validator.validate(candidates, tests)

        # Stage 7: Selection
        selected = self.selector.select(validated, intents, classification)

        if selected.needs_escalation:
            return Resolution(
                needs_escalation=True,
                candidates=validated,
                reason=selected.escalation_reason
            )

        return Resolution(
            needs_escalation=False,
            winning_candidate=selected.winner,
            ported_features=selected.ported
        )
```

---

## 15. Implementation Phases

### Phase 1: Foundation (MVP)
**Goal:** Basic coordination without intelligent resolution

- [ ] Agent manifest schema
- [ ] Manifest storage (GitHub artifacts)
- [ ] Agent discovery (find claude/* branches)
- [ ] Basic conflict detection (git merge-tree)
- [ ] Fast-path merge (no conflicts → create PR)
- [ ] GitHub Actions workflows (ping + coordinator)
- [ ] Simple notifications

**Deliverable:** System that auto-merges non-conflicting agent work

### Phase 2: Conflict Detection
**Goal:** Accurate conflict classification

- [ ] Stage 0: Full detection pipeline
- [ ] Build/test merged result
- [ ] Semantic conflict detection
- [ ] Dependency conflict detection
- [ ] Conflict clustering
- [ ] Risk flag detection

**Deliverable:** System that accurately identifies and classifies conflicts

### Phase 3: Basic Resolution
**Goal:** Resolve simple conflicts automatically

- [ ] Stage 1: Context assembly
- [ ] Stage 2: Intent extraction (basic)
- [ ] Stage 3: Interface harmonization
- [ ] Single candidate generation
- [ ] Basic validation (build + targeted tests)
- [ ] Auto-resolve low-risk conflicts

**Deliverable:** System that auto-resolves ~60% of conflicts

### Phase 4: Escalation System
**Goal:** Handle complex conflicts gracefully

- [ ] Escalation issue creation
- [ ] Plain-English options
- [ ] Response handling
- [ ] Feature porting (winner/loser)
- [ ] Timeout handling

**Deliverable:** Complete escalation workflow for complex conflicts

### Phase 5: Advanced Resolution
**Goal:** Resolve more conflicts automatically

- [ ] Multiple candidate strategies
- [ ] Full validation tiers
- [ ] Candidate diversity enforcement
- [ ] Self-critique (optional)
- [ ] Flaky test handling

**Deliverable:** System that auto-resolves ~80% of conflicts

### Phase 6: PRD Mode & Scale
**Goal:** Handle full PRD execution

- [ ] PRD mode configuration
- [ ] Wave-based resolution
- [ ] Integration branch management
- [ ] Checkpoint PRs
- [ ] Auto-merge configuration
- [ ] Scale to 20+ concurrent agents

**Deliverable:** System that executes full PRDs with many agents

### Phase 7: Learning & Optimization
**Goal:** System improves over time

- [ ] Pattern memory (rerere-like)
- [ ] Strategy performance tracking
- [ ] Agent feedback loop
- [ ] Integration with orchestrator learning
- [ ] Performance optimization

**Deliverable:** Self-improving system

---

## 16. Testing Strategy

### 16.1 Unit Tests

```python
# tests/unit/test_conflict_detector.py
class TestConflictDetector:
    def test_detects_textual_conflict(self):
        """Test detection of overlapping line changes."""

    def test_detects_semantic_conflict(self):
        """Test detection of same-area different-approach."""

    def test_detects_clean_but_broken(self):
        """Test detection when git says clean but build fails."""

    def test_classifies_severity(self):
        """Test severity classification."""


# tests/unit/test_intent_extractor.py
class TestIntentExtractor:
    def test_extracts_primary_intent(self):
        """Test primary intent extraction."""

    def test_extracts_constraints(self):
        """Test constraint extraction with evidence."""

    def test_compares_intents(self):
        """Test intent comparison."""

    def test_confidence_scoring(self):
        """Test confidence scoring."""
```

### 16.2 Integration Tests

```python
# tests/integration/test_resolution_pipeline.py
class TestResolutionPipeline:
    def test_full_pipeline_textual_conflict(self):
        """Test full pipeline with textual conflict."""

    def test_full_pipeline_semantic_conflict(self):
        """Test full pipeline with semantic conflict."""

    def test_escalation_flow(self):
        """Test escalation creation and response handling."""

    def test_feature_porting(self):
        """Test porting losing feature to winning architecture."""
```

### 16.3 End-to-End Tests

```python
# tests/e2e/test_coordinator_e2e.py
class TestCoordinatorE2E:
    def test_two_agents_no_conflict(self):
        """
        Scenario: Two agents work on unrelated features.
        Expected: Fast-path merge, single PR.
        """

    def test_two_agents_textual_conflict(self):
        """
        Scenario: Two agents modify same file differently.
        Expected: Auto-resolved, single PR.
        """

    def test_two_agents_semantic_conflict(self):
        """
        Scenario: Two agents implement same feature differently.
        Expected: Escalation with options.
        """

    def test_prd_mode_multiple_agents(self):
        """
        Scenario: 5 agents execute PRD tasks.
        Expected: Wave-based resolution, checkpoint PRs.
        """
```

### 16.4 Test Fixtures

```python
# tests/fixtures/
#
# ├── repos/
# │   ├── simple-node/          # Simple Node.js project
# │   ├── complex-typescript/   # Complex TS project
# │   └── python-django/        # Python Django project
# │
# ├── conflicts/
# │   ├── textual/              # Textual conflict scenarios
# │   ├── semantic/             # Semantic conflict scenarios
# │   ├── architectural/        # Architectural conflicts
# │   └── dependency/           # Dependency conflicts
# │
# └── manifests/
#     ├── complete/             # Well-formed manifests
#     └── incomplete/           # Edge case manifests
```

---

## 17. Additional Features (from design review)

### 17.1 Dry Run Mode

**Purpose:** Build trust and enable testing without making actual changes.

```python
class DryRunCoordinator:
    """
    Run the full resolution pipeline without making any changes.

    Benefits:
    - Test configuration before enabling auto-merge
    - Debug resolution logic
    - Preview what would happen
    - Build user confidence
    """

    def dry_run(self, agents: List[AgentInfo]) -> DryRunReport:
        """
        Execute full pipeline in dry-run mode.

        Returns:
        - What conflicts would be detected
        - Which resolution strategy would be selected
        - What the merged code would look like
        - What PR would be created
        - NO actual changes made
        """
        report = DryRunReport()

        # Stage 0: Detect conflicts (read-only)
        report.conflicts = self.detect_conflicts(agents)

        # Stage 1-5: Resolution pipeline (in-memory only)
        for conflict in report.conflicts:
            resolution = self.resolve_in_memory(conflict)
            report.resolutions.append(resolution)

        # Stage 6: What PR would look like
        report.pr_preview = self.generate_pr_preview(report.resolutions)

        # Confidence assessment
        report.overall_confidence = self.calculate_confidence(report)

        return report

@dataclass
class DryRunReport:
    """Report from dry-run execution."""
    conflicts: List[ConflictClassification]
    resolutions: List[ResolutionPreview]
    pr_preview: PRPreview
    overall_confidence: float
    warnings: List[str]
    would_escalate: bool
    estimated_time_seconds: int
```

**CLI Usage:**

```bash
# Dry run before enabling auto-merge
./orchestrator coordinate --dry-run

# Output:
# DRY RUN RESULTS
# ===============
# Detected: 3 conflicts
# - auth vs checkout: TEXTUAL (auto-resolvable)
# - products vs orders: SEMANTIC (would generate 3 candidates)
# - admin vs config: NO CONFLICT (fast-path)
#
# Would create PR: "Merge 4 agent features"
# Confidence: 85%
# Estimated time: 45 seconds
#
# No changes made. Run without --dry-run to execute.
```

### 17.2 Resolution Confidence in PRs

**Purpose:** Help human reviewers focus attention where it matters.

```python
class PRConfidenceAnnotator:
    """Add confidence scores to PR descriptions and code comments."""

    def annotate_pr(self, pr: PullRequest, resolution: Resolution) -> PullRequest:
        """
        Add confidence metadata to PR.

        Includes:
        - Overall resolution confidence
        - Per-file confidence (which files need more scrutiny)
        - Intent extraction confidence
        - Risk flags
        """
        confidence_section = f"""
## Resolution Confidence

| Metric | Score | Notes |
|--------|-------|-------|
| Overall | {resolution.confidence:.0%} | {self._confidence_note(resolution.confidence)} |
| Intent Extraction | {resolution.intent_confidence:.0%} | {resolution.intent_notes} |
| Candidate Selection | {resolution.candidate_confidence:.0%} | Strategy: {resolution.strategy} |
| Test Coverage | {resolution.test_confidence:.0%} | {resolution.test_notes} |

### Files Needing Extra Review

{self._format_low_confidence_files(resolution)}

### Risk Flags

{self._format_risk_flags(resolution)}
"""
        pr.body += confidence_section
        return pr

    def add_code_comments(self, pr: PullRequest, resolution: Resolution):
        """Add inline comments on low-confidence sections."""
        for file_result in resolution.file_results:
            if file_result.confidence < 0.7:
                self._add_review_comment(
                    pr, file_result.path, file_result.line,
                    f"⚠️ Low confidence ({file_result.confidence:.0%}): {file_result.reason}"
                )
```

### 17.3 Veto Files Configuration

**Purpose:** Ensure high-risk files always get human review.

```yaml
# .claude/config.yaml

# Files that should NEVER be auto-resolved
veto_files:
  # Security-sensitive
  - "src/core/security/**"
  - "src/auth/**"
  - "**/middleware/auth*"

  # Database migrations (dangerous to auto-merge)
  - "migrations/**"
  - "**/*.sql"
  - "**/schema.*"

  # Configuration
  - ".env*"
  - "config/production.*"

  # Payment/billing
  - "**/payment/**"
  - "**/billing/**"
  - "**/stripe/**"

# Files that trigger extra validation
high_scrutiny_files:
  - "package.json"
  - "requirements.txt"
  - "Dockerfile"
  - ".github/workflows/**"
```

```python
class VetoFileChecker:
    """Check if any modified files are in the veto list."""

    def check_veto(self, files: List[str], config: dict) -> VetoResult:
        """
        Check if resolution should be blocked due to veto files.

        Returns:
        - is_vetoed: Whether auto-resolution is blocked
        - veto_files: Which files triggered the veto
        - action: What to do (escalate, require_human_review)
        """
        veto_patterns = config.get("veto_files", [])
        vetoed = []

        for file in files:
            for pattern in veto_patterns:
                if fnmatch(file, pattern):
                    vetoed.append((file, pattern))

        if vetoed:
            return VetoResult(
                is_vetoed=True,
                veto_files=vetoed,
                action="require_human_review",
                message=f"{len(vetoed)} files require human review"
            )

        return VetoResult(is_vetoed=False)
```

### 17.4 Conflict Prevention Feedback

**Purpose:** Help agents learn to avoid future conflicts.

```python
class ConflictPreventionFeedback:
    """
    After resolution, send feedback to agents about how to
    avoid similar conflicts in the future.
    """

    def generate_feedback(self,
                          resolution: Resolution,
                          agents: List[AgentInfo]) -> List[AgentFeedback]:
        """
        Generate actionable feedback for each agent.

        Examples:
        - "Your auth changes conflicted with checkout. Consider using shared session module."
        - "Multiple agents added to package.json. Use dependency coordination API."
        - "You and Agent B both created getUserId(). Check existing utilities first."
        """
        feedback = []

        for agent in agents:
            agent_feedback = AgentFeedback(agent_id=agent.agent_id)

            # Analyze what this agent contributed to the conflict
            contribution = self._analyze_contribution(agent, resolution)

            # Generate specific advice
            if contribution.type == "duplicate_code":
                agent_feedback.add(
                    f"You created {contribution.symbol} which already exists in "
                    f"{contribution.existing_location}. Check existing code first."
                )

            if contribution.type == "dependency_conflict":
                agent_feedback.add(
                    f"Your package.json changes conflicted. For shared dependencies, "
                    f"consider using the shared-deps API or coordinate with other agents."
                )

            if contribution.type == "interface_mismatch":
                agent_feedback.add(
                    f"Your mock of {contribution.interface} didn't match the actual "
                    f"implementation. Check interface definitions before mocking."
                )

            feedback.append(agent_feedback)

        return feedback

    def store_feedback_for_learning(self, feedback: List[AgentFeedback]):
        """Store feedback patterns for future agent guidance."""
        # Add to pattern memory for proactive guidance
        pass
```

### 17.5 Local Development Mode

**Purpose:** Enable testing without GitHub Actions.

```python
class LocalDevelopmentMode:
    """
    Run the coordinator locally for development/testing.

    Features:
    - Mock GitHub API
    - Local webhook receiver
    - Test fixtures for common scenarios
    - Fast iteration without pushing to GitHub
    """

    def __init__(self, config: dict):
        self.github = MockGitHubAPI()
        self.webhook_server = LocalWebhookServer()
        self.fixture_loader = FixtureLoader()

    def start(self):
        """Start local development environment."""
        # Start mock GitHub API server
        self.github.start(port=8080)

        # Start webhook receiver
        self.webhook_server.start(port=8081)

        print("Local development mode started")
        print("  Mock GitHub API: http://localhost:8080")
        print("  Webhook receiver: http://localhost:8081")
        print("")
        print("To simulate agent push:")
        print("  curl -X POST localhost:8081/webhook -d '{\"branch\": \"claude/test\"}'")

    def load_scenario(self, scenario_name: str):
        """Load a test scenario from fixtures."""
        scenario = self.fixture_loader.load(scenario_name)
        self.github.setup_branches(scenario.branches)
        self.github.setup_manifests(scenario.manifests)
        print(f"Loaded scenario: {scenario_name}")

    def run_coordinator(self):
        """Run coordinator against mock environment."""
        coordinator = Coordinator(
            github=self.github,
            config=self.config
        )
        return coordinator.run()
```

**CLI Usage:**

```bash
# Start local dev environment
./orchestrator local-dev start

# Load a test scenario
./orchestrator local-dev load-scenario two-agents-textual-conflict

# Run coordinator
./orchestrator local-dev run

# Simulate agent push
./orchestrator local-dev simulate-push --branch claude/test-feature
```

### 17.6 Monitoring & Alerting

**Purpose:** Operational visibility and proactive issue detection.

```yaml
# .claude/config.yaml

monitoring:
  # Metrics to track
  metrics:
    - resolution_time_seconds
    - conflicts_detected_total
    - auto_resolved_total
    - escalations_total
    - rollbacks_total
    - validation_failures_total

  # Alerting thresholds
  alerts:
    # Critical - immediate attention needed
    critical:
      - condition: "rollbacks_total > 3 in 1h"
        message: "High rollback rate - system may be misconfigured"
        channels: ["slack", "pagerduty"]

      - condition: "validation_failures_total > 10 in 1h"
        message: "High validation failure rate"
        channels: ["slack", "pagerduty"]

    # Warning - investigate soon
    warning:
      - condition: "resolution_time_seconds > 300"
        message: "Resolution taking longer than 5 minutes"
        channels: ["slack"]

      - condition: "escalations_total > 5 in 24h"
        message: "High escalation rate - review auto-resolution settings"
        channels: ["slack"]

    # Info - for visibility
    info:
      - condition: "resolution_completed"
        message: "Resolution completed successfully"
        channels: ["slack"]

  # Export to monitoring systems
  exporters:
    prometheus:
      enabled: true
      port: 9090

    datadog:
      enabled: false
      api_key: "${DATADOG_API_KEY}"
```

```python
class AlertManager:
    """Send alerts based on monitoring conditions."""

    def check_and_alert(self, metrics: Metrics):
        """Check metrics against alert thresholds and send alerts."""
        for alert in self.config.alerts.critical:
            if self._evaluate_condition(alert.condition, metrics):
                self._send_alert(
                    level="critical",
                    message=alert.message,
                    channels=alert.channels,
                    metrics=metrics
                )

    def _send_alert(self, level: str, message: str,
                    channels: List[str], metrics: Metrics):
        """Send alert to configured channels."""
        for channel in channels:
            if channel == "slack":
                self._send_slack_alert(level, message, metrics)
            elif channel == "pagerduty":
                self._send_pagerduty_alert(level, message, metrics)
            elif channel == "email":
                self._send_email_alert(level, message, metrics)
```

---

## 18. Operational Resilience (from AI reviews)

### 18.1 Idempotency and Retries (from Grok 4.1 review)

**Problem:** GitHub Actions can fail mid-execution. Without idempotency, retries may corrupt state.

**Solution: Operation IDs and Checkpointing**

```python
import hashlib
from contextlib import contextmanager

class IdempotentOperation:
    """
    Wrapper for idempotent operations with retry support.

    Each operation has a unique ID derived from its inputs.
    If the same operation is retried, it returns cached result.
    """

    def __init__(self, storage: OperationStorage):
        self.storage = storage

    def compute_operation_id(self, operation: str, inputs: dict) -> str:
        """Compute deterministic operation ID from inputs."""
        canonical = json.dumps(inputs, sort_keys=True)
        return hashlib.sha256(f"{operation}:{canonical}".encode()).hexdigest()[:16]

    @contextmanager
    def idempotent(self, operation: str, inputs: dict):
        """
        Context manager for idempotent operations.

        Usage:
            with coordinator.idempotent("resolve_conflict", {"cluster_id": "abc"}) as op:
                if op.already_done:
                    return op.cached_result
                # Do work...
                op.complete(result)
        """
        op_id = self.compute_operation_id(operation, inputs)

        # Check if already completed
        existing = self.storage.get_operation(op_id)
        if existing and existing.status == "completed":
            yield IdempotentContext(
                operation_id=op_id,
                already_done=True,
                cached_result=existing.result
            )
            return

        # Start operation
        self.storage.start_operation(op_id, operation, inputs)

        ctx = IdempotentContext(operation_id=op_id, already_done=False)
        try:
            yield ctx
            if ctx.result is not None:
                self.storage.complete_operation(op_id, ctx.result)
        except Exception as e:
            self.storage.fail_operation(op_id, str(e))
            raise

@dataclass
class IdempotentContext:
    """Context for idempotent operation execution."""
    operation_id: str
    already_done: bool
    cached_result: Any = None
    result: Any = None

    def complete(self, result: Any):
        """Mark operation as complete with result."""
        self.result = result

class OperationStorage:
    """Persist operation state for idempotency."""

    def __init__(self):
        # Use GitHub Actions cache or external store
        self.cache_key_prefix = "coordinator-ops"

    def get_operation(self, op_id: str) -> Optional[OperationRecord]:
        """Retrieve operation state."""
        # Try GitHub cache first
        cache_file = Path(f"/tmp/ops/{op_id}.json")
        if cache_file.exists():
            return OperationRecord.from_json(cache_file.read_text())
        return None

    def start_operation(self, op_id: str, operation: str, inputs: dict):
        """Record operation start."""
        record = OperationRecord(
            id=op_id,
            operation=operation,
            inputs=inputs,
            status="in_progress",
            started_at=datetime.utcnow()
        )
        self._save(op_id, record)

    def complete_operation(self, op_id: str, result: Any):
        """Record operation completion."""
        record = self.get_operation(op_id)
        record.status = "completed"
        record.result = result
        record.completed_at = datetime.utcnow()
        self._save(op_id, record)
```

**Exponential Backoff for Retries:**

```python
class RetryPolicy:
    """Configurable retry policy with exponential backoff."""

    def __init__(self,
                 max_retries: int = 3,
                 base_delay_seconds: float = 1.0,
                 max_delay_seconds: float = 60.0,
                 exponential_base: float = 2.0):
        self.max_retries = max_retries
        self.base_delay = base_delay_seconds
        self.max_delay = max_delay_seconds
        self.exponential_base = exponential_base

    def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with retry on failure."""
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except RetryableError as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = min(
                        self.base_delay * (self.exponential_base ** attempt),
                        self.max_delay
                    )
                    # Add jitter to prevent thundering herd
                    delay *= (0.5 + random.random())
                    time.sleep(delay)
                    logging.warning(f"Retry {attempt + 1}/{self.max_retries}: {e}")

        raise MaxRetriesExceeded(f"Failed after {self.max_retries} retries") from last_error
```

### 18.2 State Management for PRD Mode (from Gemini review)

**Problem:** Coordinator is largely stateless. For long-running PRD execution, this is insufficient.

**Solution: Persistent State Machine**

```python
from enum import Enum
from dataclasses import dataclass, field
import json

class PRDState(Enum):
    """States for PRD execution state machine."""
    INITIALIZING = "initializing"
    DECOMPOSING = "decomposing"
    SPAWNING_AGENTS = "spawning_agents"
    MONITORING = "monitoring"
    RESOLVING = "resolving"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"

@dataclass
class PRDExecutionState:
    """Persistent state for PRD execution."""
    prd_id: str
    state: PRDState
    created_at: datetime

    # Task tracking
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0

    # Agent tracking
    active_agents: List[str] = field(default_factory=list)
    completed_agents: List[str] = field(default_factory=list)

    # Wave tracking
    current_wave: int = 0
    waves_completed: List[int] = field(default_factory=list)

    # Artifacts
    checkpoints: List[str] = field(default_factory=list)
    prs_created: List[str] = field(default_factory=list)

    # Error tracking
    errors: List[dict] = field(default_factory=list)
    last_error: Optional[str] = None

    # Timestamps
    last_updated: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class PRDStateMachine:
    """
    Manage PRD execution state with persistence.

    Survives coordinator restarts and GitHub Actions timeouts.
    """

    STATE_FILE = ".claude/prd_state.json"

    def __init__(self, prd_id: str):
        self.prd_id = prd_id
        self.state = self._load_or_create_state()

    def _load_or_create_state(self) -> PRDExecutionState:
        """Load existing state or create new."""
        state_file = Path(self.STATE_FILE)
        if state_file.exists():
            data = json.loads(state_file.read_text())
            if data.get("prd_id") == self.prd_id:
                return PRDExecutionState(**data)

        return PRDExecutionState(
            prd_id=self.prd_id,
            state=PRDState.INITIALIZING,
            created_at=datetime.utcnow()
        )

    def transition(self, new_state: PRDState, **updates):
        """Transition to new state with updates."""
        old_state = self.state.state
        self.state.state = new_state
        self.state.last_updated = datetime.utcnow()

        for key, value in updates.items():
            if hasattr(self.state, key):
                setattr(self.state, key, value)

        self._save_state()
        logging.info(f"PRD state transition: {old_state} -> {new_state}")

    def record_agent_complete(self, agent_id: str):
        """Record agent completion."""
        if agent_id in self.state.active_agents:
            self.state.active_agents.remove(agent_id)
        if agent_id not in self.state.completed_agents:
            self.state.completed_agents.append(agent_id)
        self.state.completed_tasks += 1
        self._save_state()

    def record_error(self, error: str, context: dict):
        """Record an error for debugging."""
        self.state.errors.append({
            "error": error,
            "context": context,
            "timestamp": datetime.utcnow().isoformat()
        })
        self.state.last_error = error
        self._save_state()

    def can_resume(self) -> bool:
        """Check if execution can be resumed from current state."""
        return self.state.state not in [
            PRDState.COMPLETED,
            PRDState.FAILED
        ]

    def get_resume_point(self) -> dict:
        """Get information needed to resume execution."""
        return {
            "state": self.state.state,
            "current_wave": self.state.current_wave,
            "pending_agents": [
                a for a in self.state.active_agents
                if a not in self.state.completed_agents
            ],
            "last_checkpoint": self.state.checkpoints[-1] if self.state.checkpoints else None
        }

    def _save_state(self):
        """Persist state to file and GitHub artifact."""
        Path(self.STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(self.STATE_FILE).write_text(
            json.dumps(asdict(self.state), default=str, indent=2)
        )
```

### 18.3 Cost Management and Circuit Breakers (from Grok 4.1 review)

**Problem:** LLM calls + tests + git ops can explode costs at 50 agents (~$10-100/PR).

**Solution: Budget Tracking and Circuit Breakers**

```python
@dataclass
class CostBudget:
    """Track and limit costs per execution."""
    max_llm_tokens: int = 1_000_000      # ~$10 at Claude pricing
    max_build_minutes: int = 100          # GitHub Actions minutes
    max_api_calls: int = 1000             # GitHub API calls
    max_resolution_attempts: int = 10     # Per conflict

    # Current usage
    llm_tokens_used: int = 0
    build_minutes_used: int = 0
    api_calls_used: int = 0
    resolution_attempts: Dict[str, int] = field(default_factory=dict)

class CostController:
    """Monitor and enforce cost limits."""

    def __init__(self, budget: CostBudget):
        self.budget = budget
        self.circuit_breaker_open = False

    def record_llm_usage(self, tokens: int):
        """Record LLM token usage."""
        self.budget.llm_tokens_used += tokens
        self._check_limits()

    def record_build_time(self, minutes: float):
        """Record build/test time."""
        self.budget.build_minutes_used += minutes
        self._check_limits()

    def can_proceed(self, operation: str) -> CostCheckResult:
        """Check if operation should proceed given current costs."""
        if self.circuit_breaker_open:
            return CostCheckResult(
                allowed=False,
                reason="circuit_breaker_open",
                message="Cost limits exceeded - circuit breaker engaged"
            )

        # Check specific limits
        if operation == "llm_call":
            remaining = self.budget.max_llm_tokens - self.budget.llm_tokens_used
            if remaining < 10000:  # Need at least 10k tokens
                return CostCheckResult(
                    allowed=False,
                    reason="llm_budget_exceeded",
                    remaining=remaining
                )

        return CostCheckResult(allowed=True)

    def _check_limits(self):
        """Check if any limits exceeded and engage circuit breaker."""
        if self.budget.llm_tokens_used > self.budget.max_llm_tokens:
            self._engage_circuit_breaker("LLM token budget exceeded")

        if self.budget.build_minutes_used > self.budget.max_build_minutes:
            self._engage_circuit_breaker("Build minutes budget exceeded")

    def _engage_circuit_breaker(self, reason: str):
        """Stop all operations when limits exceeded."""
        self.circuit_breaker_open = True
        logging.critical(f"Circuit breaker engaged: {reason}")

        # Notify admin
        self._send_alert(
            level="critical",
            message=f"Coordinator circuit breaker: {reason}",
            budget_status=asdict(self.budget)
        )

    def get_cost_estimate(self, operation: str) -> CostEstimate:
        """Estimate cost of an operation before executing."""
        estimates = {
            "resolve_cluster_small": CostEstimate(llm_tokens=50000, build_minutes=5),
            "resolve_cluster_medium": CostEstimate(llm_tokens=200000, build_minutes=15),
            "resolve_cluster_large": CostEstimate(llm_tokens=500000, build_minutes=30),
            "create_pr": CostEstimate(llm_tokens=10000, build_minutes=1),
        }
        return estimates.get(operation, CostEstimate(llm_tokens=0, build_minutes=0))
```

**Configuration:**

```yaml
# .claude/config.yaml
cost_management:
  budgets:
    per_resolution:
      max_llm_tokens: 100000
      max_build_minutes: 10
      max_candidates: 5

    per_prd:
      max_llm_tokens: 2000000
      max_build_minutes: 200
      max_agents: 50

  circuit_breakers:
    enabled: true
    auto_reset_after_hours: 24

  alerts:
    warn_at_percentage: 80
    critical_at_percentage: 95
```

### 18.4 Flight Recorder for Debugging (from Gemini review)

**Problem:** When complex merges go wrong, debugging is nearly impossible without detailed traces.

**Solution: Comprehensive Flight Recorder**

```python
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, List
import json

@dataclass
class FlightRecorderEntry:
    """A single entry in the flight recorder."""
    timestamp: datetime
    category: str  # llm, git, conflict, validation, decision
    operation: str
    inputs: dict
    outputs: Optional[dict] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None

class FlightRecorder:
    """
    Detailed logging of all coordinator operations for debugging.

    Think of it as an airplane's black box - records everything
    needed to understand what happened when things go wrong.
    """

    def __init__(self, resolution_id: str):
        self.resolution_id = resolution_id
        self.entries: List[FlightRecorderEntry] = []
        self.start_time = datetime.utcnow()

    @contextmanager
    def record(self, category: str, operation: str, inputs: dict):
        """Record an operation with timing."""
        start = datetime.utcnow()
        entry = FlightRecorderEntry(
            timestamp=start,
            category=category,
            operation=operation,
            inputs=self._sanitize_inputs(inputs)
        )

        try:
            result = {"outputs": None}
            yield result
            entry.outputs = result.get("outputs")
        except Exception as e:
            entry.error = str(e)
            raise
        finally:
            entry.duration_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
            self.entries.append(entry)

    def record_llm_call(self, prompt: str, response: str, model: str, tokens: int):
        """Record LLM interaction."""
        self.entries.append(FlightRecorderEntry(
            timestamp=datetime.utcnow(),
            category="llm",
            operation="call",
            inputs={
                "model": model,
                "prompt_preview": prompt[:500] + "..." if len(prompt) > 500 else prompt,
                "prompt_tokens": len(prompt.split())
            },
            outputs={
                "response_preview": response[:500] + "..." if len(response) > 500 else response,
                "total_tokens": tokens
            }
        ))

    def record_git_operation(self, operation: str, args: List[str], result: str, success: bool):
        """Record git operation."""
        self.entries.append(FlightRecorderEntry(
            timestamp=datetime.utcnow(),
            category="git",
            operation=operation,
            inputs={"args": args},
            outputs={"result": result[:1000], "success": success}
        ))

    def record_decision(self, decision_type: str, options: List[str],
                        chosen: str, reason: str, confidence: float):
        """Record an automated decision."""
        self.entries.append(FlightRecorderEntry(
            timestamp=datetime.utcnow(),
            category="decision",
            operation=decision_type,
            inputs={"options": options},
            outputs={
                "chosen": chosen,
                "reason": reason,
                "confidence": confidence
            }
        ))

    def export(self) -> dict:
        """Export flight recorder data."""
        return {
            "resolution_id": self.resolution_id,
            "started_at": self.start_time.isoformat(),
            "ended_at": datetime.utcnow().isoformat(),
            "total_entries": len(self.entries),
            "entries": [self._entry_to_dict(e) for e in self.entries],
            "summary": self._generate_summary()
        }

    def save_to_artifact(self):
        """Save as GitHub Action artifact."""
        artifact_path = Path(f"/tmp/flight-recorder-{self.resolution_id}.json")
        artifact_path.write_text(json.dumps(self.export(), indent=2, default=str))
        return artifact_path

    def _generate_summary(self) -> dict:
        """Generate summary statistics."""
        by_category = {}
        for entry in self.entries:
            if entry.category not in by_category:
                by_category[entry.category] = {"count": 0, "errors": 0, "total_ms": 0}
            by_category[entry.category]["count"] += 1
            if entry.error:
                by_category[entry.category]["errors"] += 1
            if entry.duration_ms:
                by_category[entry.category]["total_ms"] += entry.duration_ms

        return {
            "total_operations": len(self.entries),
            "total_errors": sum(1 for e in self.entries if e.error),
            "by_category": by_category
        }

    def _sanitize_inputs(self, inputs: dict) -> dict:
        """Remove sensitive data from inputs before recording."""
        sanitized = {}
        for key, value in inputs.items():
            if any(s in key.lower() for s in ["secret", "token", "password", "key"]):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, str) and len(value) > 10000:
                sanitized[key] = value[:1000] + f"... [truncated, {len(value)} chars]"
            else:
                sanitized[key] = value
        return sanitized
```

**Integration with Coordinator:**

```python
class Coordinator:
    def __init__(self):
        self.flight_recorder = None

    def resolve_conflict(self, conflict: ConflictContext):
        self.flight_recorder = FlightRecorder(conflict.conflict_id)

        try:
            with self.flight_recorder.record("pipeline", "stage_0_detection", {}):
                # Stage 0 work...
                pass

            with self.flight_recorder.record("pipeline", "stage_1_context", {}):
                # Stage 1 work...
                pass

            # etc.

        finally:
            # Always save flight recorder, even on failure
            artifact = self.flight_recorder.save_to_artifact()
            logging.info(f"Flight recorder saved: {artifact}")
```

**Querying Flight Recorder Data:**

```bash
# Download and analyze flight recorder
gh run download --name flight-recorder-conflict-abc123

# Parse and query with jq
cat flight-recorder-*.json | jq '.entries[] | select(.category == "decision")'
cat flight-recorder-*.json | jq '.entries[] | select(.error != null)'
cat flight-recorder-*.json | jq '.summary.by_category'
```

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **Agent** | A Claude instance (Web or CLI) working on a task |
| **Agent Branch** | Git branch created by an agent (claude/*) |
| **Manifest** | Structured record of agent's work and decisions |
| **Conflict Cluster** | Group of related conflicts resolved together |
| **Intent** | What an agent was trying to achieve |
| **Candidate** | A proposed resolution to a conflict |
| **Escalation** | Request for human decision |
| **Porting** | Adapting a feature to a different architecture |
| **Fast Path** | Skipping expensive resolution for simple cases |
| **Integration Branch** | Branch accumulating resolved work before main |

---

## Appendix B: Error Handling

### B.1 Error Categories

```python
class CoordinatorError(Exception):
    """Base exception for coordinator errors."""
    pass

class ManifestError(CoordinatorError):
    """Error loading or parsing manifest."""
    pass

class ConflictDetectionError(CoordinatorError):
    """Error during conflict detection."""
    pass

class ResolutionError(CoordinatorError):
    """Error during resolution pipeline."""
    pass

class EscalationError(CoordinatorError):
    """Error in escalation handling."""
    pass

class DeliveryError(CoordinatorError):
    """Error creating PR or merging."""
    pass
```

### B.2 Recovery Strategies

| Error | Recovery |
|-------|----------|
| Manifest parse failure | Use derived manifest from git diff |
| Build failure during detection | Mark as semantic conflict, escalate |
| LLM API failure | Retry with backoff, fallback provider |
| Git operation failure | Log and retry, escalate if persistent |
| Timeout during resolution | Save partial state, notify, retry later |

---

## Appendix C: Metrics & Monitoring

### C.1 Key Metrics

```python
METRICS = {
    # Performance
    "resolution_duration_seconds": Histogram,
    "detection_duration_seconds": Histogram,
    "candidates_generated": Counter,

    # Outcomes
    "conflicts_detected": Counter,  # by type
    "conflicts_resolved": Counter,  # by method (auto, escalated)
    "escalations_created": Counter,
    "escalations_resolved": Counter,
    "prs_created": Counter,
    "prs_merged": Counter,
    "prs_reverted": Counter,

    # Quality
    "auto_resolve_success_rate": Gauge,
    "escalation_response_time_hours": Histogram,
    "human_edit_rate": Gauge,  # How often humans edit before merge

    # Scale
    "active_agents": Gauge,
    "pending_escalations": Gauge,
    "clusters_in_progress": Gauge,
}
```

---

*Final Design Document v2.0*
*Ready for Implementation*
*January 2026*
