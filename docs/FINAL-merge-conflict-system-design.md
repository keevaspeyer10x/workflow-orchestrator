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

### 7.3 Feature Porting (When User Picks Winner)

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

### 8.4 Escalation Timeout Policy

```python
class EscalationTimeout:
    """Handle escalation timeouts."""

    def check_timeouts(self):
        """Check for escalations that need attention."""

        for escalation in self.get_pending_escalations():
            age_hours = escalation.age_in_hours()

            # Reminder at 24 hours
            if age_hours >= 24 and not escalation.reminder_sent:
                self.send_reminder(escalation)

            # Auto-select at 72 hours (configurable)
            if age_hours >= 72:
                if escalation.is_high_risk():
                    # High risk: keep waiting, send urgent reminder
                    self.send_urgent_reminder(escalation)
                else:
                    # Low risk: auto-select recommendation
                    self.auto_select_recommendation(escalation)

    def auto_select_recommendation(self, escalation: Escalation):
        """
        Auto-select the recommended option.

        Safeguards:
        - Create PR as DRAFT
        - Add "auto-selected" label
        - Include revert instructions
        - Notify user
        """
        pass
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
