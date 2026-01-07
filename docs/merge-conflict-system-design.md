# Merge Conflict Resolution System: Detailed Design

## 1. North Star: The Vibe Coder Experience

### What the user does:
```
1. Opens Claude Web: "Add user authentication"
   → Starts working, pushes to claude/auth-abc123

2. 15 minutes later, opens Claude CLI: "Build a dashboard"
   → Starts working, pushes to claude/dashboard-def456

3. Both finish around the same time
   → System automatically detects, resolves conflicts, creates PR

4. User sees notification:
   "✓ Both features complete! Review and merge: github.com/.../pull/42"

5. User clicks "Merge" in GitHub
   → Done. Both features on main.
```

### What the user never sees:
- Branch names
- Git commands
- Merge conflicts
- Resolution candidates
- Technical decisions (unless they ask)

### When user input IS needed:
```
┌────────────────────────────────────────────────────────────┐
│  Need your input                                           │
│                                                            │
│  Two different approaches were found for user validation:  │
│                                                            │
│  [A] Strict validation (checks email, phone, address)      │
│      → More secure, slightly slower signup                 │
│                                                            │
│  [B] Basic validation (checks email only)                  │
│      → Faster signup, less data verification               │
│                                                            │
│  Your app handles: payment information                     │
│  Recommendation: A (stricter is safer for payments)        │
│                                                            │
│  Choose [A/B] or type "show details" for technical view    │
└────────────────────────────────────────────────────────────┘
```

---

## 2. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         USER'S PERSPECTIVE                               │
│                                                                         │
│    Claude Web          Claude CLI          GitHub                       │
│    "Add auth"          "Add dashboard"     [Merge button]               │
│         │                    │                  ▲                       │
│         └────────────────────┴──────────────────┼───────────────────────┤
│                                                 │                       │
├─────────────────────────────────────────────────┼───────────────────────┤
│                    INVISIBLE LAYER              │                       │
│                                                 │                       │
│  ┌──────────────┐    ┌──────────────┐    ┌─────┴────────┐              │
│  │ Agent Work   │    │ Agent Work   │    │    Final     │              │
│  │ claude/auth- │    │ claude/dash- │    │     PR       │              │
│  │    abc123    │    │    def456    │    │              │              │
│  └──────┬───────┘    └──────┬───────┘    └──────────────┘              │
│         │                   │                   ▲                       │
│         └─────────┬─────────┘                   │                       │
│                   ▼                             │                       │
│         ┌─────────────────────────────────────────────┐                │
│         │         COORDINATION LAYER                   │                │
│         │         (GitHub Actions)                     │                │
│         │                                             │                │
│         │  1. Watch for claude/* branches             │                │
│         │  2. Detect completion signals               │                │
│         │  3. Analyze conflicts                       │                │
│         │  4. Resolve automatically (or escalate)     │                │
│         │  5. Create unified PR                       │                │
│         └─────────────────────────────────────────────┘                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Design Decision: GitHub Actions as Coordinator

**Why GitHub Actions (not local daemon):**
- Works identically for CLI and Web (both push to GitHub)
- No background process for user to manage
- Scales naturally with repo activity
- Already integrated with their workflow
- Survives user closing laptop

**Tradeoff:** Slight delay (Actions trigger on push), but acceptable for vibe coder use case.

---

## 3. Component Details

### 3.1 Agent Manifest (Structured Decision Record)

When any Claude agent starts work, it creates a manifest file on its branch:

**File:** `.claude/agent-manifest.json`

```json
{
  "schema_version": "1.0",
  "agent": {
    "id": "claude-web-abc123",
    "type": "claude-web",
    "session_id": "abc123",
    "started_at": "2026-01-07T10:00:00Z"
  },
  "task": {
    "description": "Add user authentication",
    "user_prompt": "Add authentication to the app",
    "inferred_requirements": [
      "User login/logout functionality",
      "Session management",
      "Password hashing"
    ]
  },
  "work": {
    "status": "in_progress",
    "files_read": [
      "src/app.ts",
      "src/routes/index.ts",
      "package.json"
    ],
    "files_modified": [],
    "decisions": [],
    "tests_added": [],
    "dependencies_added": []
  },
  "constraints": {
    "hard": [],
    "soft": [],
    "assumptions": []
  },
  "completion": {
    "completed_at": null,
    "summary": null,
    "verification": {
      "build_passed": null,
      "tests_passed": null,
      "lint_passed": null
    }
  }
}
```

**Updated as agent works:**
- `files_modified` populated as changes made
- `decisions` logged with evidence
- `tests_added` tracked
- On completion: `status` → "complete", verification results filled

### 3.2 Decision Record Format

Each significant decision logged:

```json
{
  "id": "decision-001",
  "timestamp": "2026-01-07T10:15:00Z",
  "type": "library_choice",
  "description": "Chose bcrypt for password hashing",
  "options_considered": [
    {"name": "bcrypt", "chosen": true, "reason": "Industry standard, already in package.json"},
    {"name": "argon2", "chosen": false, "reason": "Better but adds new dependency"}
  ],
  "evidence": {
    "existing_usage": "package.json already has bcrypt@5.0.0",
    "security_level": "high"
  },
  "constraints_satisfied": ["use existing dependencies when possible"],
  "reversible": true
}
```

### 3.3 Branch Naming Convention

```
claude/<task-slug>-<session-id>

Examples:
  claude/add-authentication-abc123
  claude/build-dashboard-def456
  claude/fix-login-bug-ghi789
```

**Rules:**
- `task-slug`: Lowercase, hyphens, max 30 chars, derived from task
- `session-id`: Random 6-char hex, ensures uniqueness

### 3.4 Coordination Layer (GitHub Actions)

**Workflow triggers:**
1. Push to `claude/*` branch
2. Scheduled check every 5 minutes (catch edge cases)
3. Manual trigger (for debugging)

**Workflow file:** `.github/workflows/claude-coordinator.yml`

```yaml
name: Claude Agent Coordinator

on:
  push:
    branches:
      - 'claude/**'
  schedule:
    - cron: '*/5 * * * *'
  workflow_dispatch:

jobs:
  coordinate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Run Coordinator
        run: |
          python -m orchestrator.coordinator \
            --mode=check \
            --auto-resolve=true \
            --escalation-webhook=${{ secrets.ESCALATION_WEBHOOK }}
```

### 3.5 Coordinator Logic (Python Module)

**File:** `src/coordinator.py`

```
orchestrator.coordinator
├── discover_agent_branches()      # Find all claude/* branches
├── load_agent_manifests()         # Parse manifest from each branch
├── detect_completion()            # Which agents are done?
├── analyze_conflicts()            # Do completed branches conflict?
├── classify_conflict()            # Textual? Semantic? Architectural?
├── can_auto_resolve()             # Is this safe to auto-resolve?
├── resolve_conflict()             # Run resolution pipeline
├── escalate_to_human()            # Create issue/notification for input
├── create_unified_pr()            # Merge all resolved work into PR
└── notify_user()                  # Send completion notification
```

---

## 4. Conflict Resolution Pipeline

### 4.1 Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CONFLICT RESOLUTION PIPELINE                          │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 0: DETECTION & CLASSIFICATION                              │   │
│  │                                                                   │   │
│  │  Input: Two+ completed agent branches                            │   │
│  │                                                                   │   │
│  │  Steps:                                                          │   │
│  │  1. Git merge-tree to find textual conflicts                     │   │
│  │  2. Build both branches, check for compile errors                │   │
│  │  3. Analyze file overlap (same files modified?)                  │   │
│  │  4. Analyze symbol overlap (same functions/classes?)             │   │
│  │  5. Check dependency conflicts (incompatible packages?)          │   │
│  │                                                                   │   │
│  │  Output: Conflict classification                                 │   │
│  │    - NONE: No conflicts, proceed to fast merge                   │   │
│  │    - TEXTUAL: Git conflicts only, likely auto-resolvable         │   │
│  │    - SEMANTIC: Same area, different approaches                   │   │
│  │    - ARCHITECTURAL: Fundamental design disagreement              │   │
│  │                                                                   │   │
│  │  Fast path: If NONE → skip to PR creation                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 1: CONTEXT ASSEMBLY                                        │   │
│  │                                                                   │   │
│  │  Input: Classified conflict + agent manifests                    │   │
│  │                                                                   │   │
│  │  Gather:                                                         │   │
│  │  - Agent A's manifest (task, decisions, constraints)             │   │
│  │  - Agent B's manifest (task, decisions, constraints)             │   │
│  │  - Base commit (state before either agent)                       │   │
│  │  - Conflicting files from all three states                       │   │
│  │  - Related files (imports, callers) via AST analysis             │   │
│  │  - Project conventions (.editorconfig, lint rules, patterns)     │   │
│  │                                                                   │   │
│  │  Output: Conflict context package                                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 2: INTENT EXTRACTION                                       │   │
│  │                                                                   │   │
│  │  Input: Conflict context package                                 │   │
│  │                                                                   │   │
│  │  For each agent, extract:                                        │   │
│  │  - Primary intent (one sentence)                                 │   │
│  │  - Hard constraints (must satisfy)                               │   │
│  │  - Soft constraints (prefer if possible)                         │   │
│  │  - Assumptions made                                              │   │
│  │  - Evidence supporting each (from manifest + code)               │   │
│  │                                                                   │   │
│  │  Compare intents:                                                │   │
│  │  - Compatible: Both can be satisfied                             │   │
│  │  - Conflicting: Mutually exclusive                               │   │
│  │  - Orthogonal: Independent, no interaction                       │   │
│  │                                                                   │   │
│  │  Confidence scoring:                                             │   │
│  │  - HIGH: Strong evidence alignment                               │   │
│  │  - MEDIUM: Reasonable inference                                  │   │
│  │  - LOW: Guessing (escalate if low)                               │   │
│  │                                                                   │   │
│  │  Output: Intent analysis with confidence scores                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 3: INTERFACE HARMONIZATION                                 │   │
│  │                                                                   │   │
│  │  Input: Intent analysis + both codebases                         │   │
│  │                                                                   │   │
│  │  Problem: Tests may not compile if interfaces changed            │   │
│  │                                                                   │   │
│  │  Steps:                                                          │   │
│  │  1. Identify interface changes (function signatures, types)      │   │
│  │  2. Determine canonical interface (usually from primary intent)  │   │
│  │  3. Generate adapter code if needed                              │   │
│  │  4. Update call sites in non-canonical branch                    │   │
│  │  5. Verify build passes                                          │   │
│  │                                                                   │   │
│  │  Output: Build-compatible merged codebase (tests may fail)       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 4: TEST SYNTHESIS                                          │   │
│  │                                                                   │   │
│  │  Input: Harmonized codebase + both agents' tests                 │   │
│  │                                                                   │   │
│  │  Steps:                                                          │   │
│  │  1. Collect tests from both branches                             │   │
│  │  2. Deduplicate (same test, different locations)                 │   │
│  │  3. Fix test imports/references for harmonized interfaces        │   │
│  │  4. Generate integration tests for interaction points            │   │
│  │  5. Run mutation testing to verify test quality                  │   │
│  │                                                                   │   │
│  │  Output: Unified test suite that defines success criteria        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 5: CANDIDATE GENERATION                                    │   │
│  │                                                                   │   │
│  │  Input: Harmonized code + unified tests + intent analysis        │   │
│  │                                                                   │   │
│  │  Generate candidates using distinct strategies:                  │   │
│  │                                                                   │   │
│  │  Strategy A - "Agent 1 Primary"                                  │   │
│  │    Keep Agent 1's architecture, adapt Agent 2's features         │   │
│  │                                                                   │   │
│  │  Strategy B - "Agent 2 Primary"                                  │   │
│  │    Keep Agent 2's architecture, adapt Agent 1's features         │   │
│  │                                                                   │   │
│  │  Strategy C - "Fresh Synthesis"                                  │   │
│  │    Given both intents, implement from scratch on base            │   │
│  │    (Gemini's "Agentic Rebase" approach)                          │   │
│  │                                                                   │   │
│  │  Strategy D - "Conservative Merge"                               │   │
│  │    Keep both implementations, add routing/adapter layer          │   │
│  │                                                                   │   │
│  │  Output: 2-4 candidate implementations                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 6: VALIDATION & SELECTION                                  │   │
│  │                                                                   │   │
│  │  Input: Candidates + unified test suite                          │   │
│  │                                                                   │   │
│  │  Tiered validation (fast to slow):                               │   │
│  │                                                                   │   │
│  │  Tier 1 - Build (seconds)                                        │   │
│  │    Compile/typecheck each candidate                              │   │
│  │    Eliminate: candidates that don't build                        │   │
│  │                                                                   │   │
│  │  Tier 2 - Lint (seconds)                                         │   │
│  │    Run linters, static analysis                                  │   │
│  │    Score: convention compliance                                  │   │
│  │                                                                   │   │
│  │  Tier 3 - Targeted Tests (minutes)                               │   │
│  │    Run tests for modified files only                             │   │
│  │    Eliminate: candidates failing core tests                      │   │
│  │                                                                   │   │
│  │  Tier 4 - Full Suite (minutes, only if needed)                   │   │
│  │    Run complete test suite                                       │   │
│  │    Score: test pass rate                                         │   │
│  │                                                                   │   │
│  │  Scoring dimensions:                                             │   │
│  │  - Correctness (tests passed)                                    │   │
│  │  - Simplicity (diff size, complexity metrics)                    │   │
│  │  - Convention fit (matches project patterns)                     │   │
│  │  - Both intents satisfied (check against extracted intents)      │   │
│  │                                                                   │   │
│  │  Output: Ranked candidates with scores                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 7: DECISION                                                │   │
│  │                                                                   │   │
│  │  Input: Ranked candidates + scores                               │   │
│  │                                                                   │   │
│  │  Decision tree:                                                  │   │
│  │                                                                   │   │
│  │  IF top candidate passes all tests AND                           │   │
│  │     score significantly better than others AND                   │   │
│  │     no high-risk flags (security, data, API changes):            │   │
│  │    → AUTO-SELECT winner                                          │   │
│  │                                                                   │   │
│  │  ELSE IF multiple candidates viable AND                          │   │
│  │     difference is subjective (style, approach):                  │   │
│  │    → AUTO-SELECT simplest (smallest diff)                        │   │
│  │                                                                   │   │
│  │  ELSE IF candidates have different tradeoffs AND                 │   │
│  │     user judgment needed:                                        │   │
│  │    → ESCALATE with plain-English options                         │   │
│  │                                                                   │   │
│  │  ELSE IF no candidates pass tests:                               │   │
│  │    → ESCALATE with error details                                 │   │
│  │                                                                   │   │
│  │  Escalation triggers (always escalate):                          │   │
│  │  - Security-sensitive files modified                             │   │
│  │  - Database migrations involved                                  │   │
│  │  - Public API changed                                            │   │
│  │  - Intent confidence was LOW                                     │   │
│  │  - Tests were removed or weakened                                │   │
│  │                                                                   │   │
│  │  Output: Selected candidate OR escalation request                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ STAGE 8: DELIVERY                                                │   │
│  │                                                                   │   │
│  │  IF auto-resolved:                                               │   │
│  │    1. Create branch: claude/resolved-<timestamp>                 │   │
│  │    2. Push resolved code                                         │   │
│  │    3. Create PR to main with summary                             │   │
│  │    4. Notify user: "Ready to merge: [link]"                      │   │
│  │                                                                   │   │
│  │  IF escalated:                                                   │   │
│  │    1. Create GitHub Issue with decision request                  │   │
│  │    2. Include plain-English options                              │   │
│  │    3. Add "show details" expandable section                      │   │
│  │    4. Notify user: "Need your input: [link]"                     │   │
│  │    5. Wait for response, then continue pipeline                  │   │
│  │                                                                   │   │
│  │  Output: PR ready for user's one-click merge                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Fast Paths (Skip Expensive Stages)

```
FAST PATH 1: No Conflicts
  Trigger: Stage 0 finds no textual or semantic conflicts
  Action: Skip directly to Stage 8 (create PR)
  Expected: ~60% of multi-agent work

FAST PATH 2: Textual Only, Same Intent
  Trigger: Git conflicts exist, but intents clearly compatible
  Action: Use git's merge resolution + minimal LLM cleanup
  Expected: ~20% of multi-agent work

FAST PATH 3: Orthogonal Changes
  Trigger: Agents modified completely different areas
  Action: Simple git merge, verify build + tests
  Expected: ~10% of multi-agent work

FULL PIPELINE: ~10% of cases
  Complex semantic or architectural conflicts
```

---

## 5. Human Escalation Design

### 5.1 Escalation Format (Plain English)

**GitHub Issue Template:**

```markdown
## 🤔 Need Your Input

While combining work from your Claude agents, I found a situation where
your judgment is needed.

### What happened

Two features were built that approach the same problem differently:

**Feature 1: User Authentication** (from Claude Web session)
- Added login with email/password
- Stores sessions in cookies

**Feature 2: Dashboard** (from Claude CLI session)
- Added admin dashboard
- Also added login, but using JWT tokens

### The decision

Both login approaches work, but they're incompatible. Pick one:

---

### Option A: Cookie-based sessions (from Auth feature)

**Good for:**
- Simple web apps
- Traditional server-rendered pages
- Easier to implement

**Tradeoffs:**
- Doesn't work well for mobile apps
- Requires CSRF protection

---

### Option B: JWT tokens (from Dashboard feature)

**Good for:**
- Mobile apps and SPAs
- Microservices architecture
- Stateless scaling

**Tradeoffs:**
- More complex to implement correctly
- Token refresh logic needed

---

### My recommendation

Based on your codebase (I see you're building a Next.js web app with no
mobile plans), **Option A (cookies)** is simpler and fits your stack.

---

**Your choice:** Reply with `A` or `B`

Or reply `explain more` and I'll provide technical details.

---

<details>
<summary>🔧 Technical details (click to expand)</summary>

### Files involved

**From Auth feature:**
- `src/auth/session.ts` - Cookie session management
- `src/middleware/auth.ts` - Session validation

**From Dashboard feature:**
- `src/auth/jwt.ts` - JWT generation/validation
- `src/middleware/auth.ts` - Token validation (conflicts)

### Code comparison

[Diff view would be here]

</details>
```

### 5.2 Escalation Response Handling

**User replies in GitHub Issue:**

```
User: A
```

**System response:**

```markdown
✅ Got it! Using Option A (cookie-based sessions).

Combining the features now...

**Update:** Done! PR ready for review:
→ https://github.com/user/repo/pull/42
```

### 5.3 Escalation via Other Channels

For users who don't check GitHub Issues:

1. **Email notification** (if configured)
2. **Slack webhook** (if configured)
3. **CLI notification** (next time they run orchestrator)

---

## 6. Data Models

### 6.1 Conflict Analysis Result

```python
@dataclass
class ConflictAnalysis:
    """Result of Stage 0 conflict detection."""

    # Classification
    conflict_type: Literal["none", "textual", "semantic", "architectural"]
    severity: Literal["low", "medium", "high", "critical"]

    # Details
    conflicting_files: List[str]
    conflicting_symbols: List[str]  # Functions, classes, etc.
    dependency_conflicts: List[DependencyConflict]

    # Agents involved
    agents: List[AgentManifest]

    # Recommendation
    recommended_path: Literal["fast_merge", "auto_resolve", "escalate"]
    confidence: float  # 0.0 to 1.0
```

### 6.2 Intent Extraction Result

```python
@dataclass
class ExtractedIntent:
    """Result of Stage 2 intent extraction for one agent."""

    agent_id: str

    # Intent
    primary_intent: str  # One sentence
    secondary_effects: List[str]

    # Constraints
    hard_constraints: List[Constraint]
    soft_constraints: List[Constraint]
    assumptions: List[str]

    # Evidence
    evidence: List[Evidence]
    confidence: Literal["high", "medium", "low"]


@dataclass
class Constraint:
    description: str
    evidence: str
    source: Literal["task", "code", "tests", "manifest", "inferred"]


@dataclass
class IntentComparison:
    """Comparison between two agents' intents."""

    relationship: Literal["compatible", "conflicting", "orthogonal"]

    # Where they agree
    shared_constraints: List[Constraint]

    # Where they conflict
    conflicting_constraints: List[Tuple[Constraint, Constraint]]

    # Resolution hints
    suggested_resolution: str
    requires_human_judgment: bool
```

### 6.3 Resolution Candidate

```python
@dataclass
class ResolutionCandidate:
    """One candidate resolution from Stage 5."""

    id: str
    strategy: Literal["agent1_primary", "agent2_primary", "fresh_synthesis", "conservative"]

    # The code
    branch_name: str
    diff_from_base: str
    files_modified: List[str]

    # Validation results
    build_passed: bool
    lint_score: float
    tests_passed: int
    tests_failed: int
    test_coverage: float

    # Scoring
    scores: Dict[str, float]  # dimension -> score
    total_score: float

    # Explanation
    summary: str  # Plain English
    technical_details: str  # For "show details"
```

### 6.4 Escalation Request

```python
@dataclass
class EscalationRequest:
    """Request for human input."""

    id: str
    created_at: datetime

    # Context
    conflict_analysis: ConflictAnalysis
    intent_comparison: IntentComparison
    candidates: List[ResolutionCandidate]

    # For user
    title: str  # Plain English
    description: str  # Plain English explanation
    options: List[EscalationOption]
    recommendation: str
    recommendation_reason: str

    # Status
    status: Literal["pending", "resolved", "timeout"]
    user_choice: Optional[str]
    resolved_at: Optional[datetime]


@dataclass
class EscalationOption:
    id: str  # "A", "B", etc.
    title: str  # "Cookie-based sessions"
    description: str  # Plain English pros/cons
    candidate_id: str  # Links to ResolutionCandidate
```

---

## 7. Workflow Definition (YAML)

New workflow type for the orchestrator:

**File:** `workflows/merge-conflict-resolution.yaml`

```yaml
name: "Merge Conflict Resolution"
version: "1.0"
description: "Resolve conflicts between multiple Claude agent branches"

settings:
  auto_resolve_threshold: 0.8  # Confidence threshold for auto-resolution
  max_candidates: 4
  test_timeout_seconds: 300
  escalation_timeout_hours: 48

phases:
  - id: "DETECTION"
    name: "Conflict Detection"
    description: "Detect and classify conflicts between agent branches"
    items:
      - id: "discover_branches"
        name: "Discover agent branches"
        description: "Find all claude/* branches with completed work"
        verification:
          type: "command"
          command: "python -m orchestrator.coordinator discover"

      - id: "analyze_conflicts"
        name: "Analyze conflicts"
        description: "Determine conflict type and severity"
        verification:
          type: "command"
          command: "python -m orchestrator.coordinator analyze"

      - id: "classify"
        name: "Classify resolution path"
        description: "Determine if fast-path or full pipeline"
        verification:
          type: "command"
          command: "python -m orchestrator.coordinator classify"

  - id: "CONTEXT"
    name: "Context Assembly"
    description: "Gather all context needed for resolution"
    items:
      - id: "load_manifests"
        name: "Load agent manifests"
        verification:
          type: "file_exists"
          path: ".claude/conflict-context.json"

      - id: "gather_code"
        name: "Gather conflicting code"

      - id: "gather_conventions"
        name: "Gather project conventions"

  - id: "INTENT"
    name: "Intent Extraction"
    description: "Extract and compare agent intents"
    items:
      - id: "extract_intents"
        name: "Extract intents from each agent"
        agent: "claude_code"

      - id: "compare_intents"
        name: "Compare and classify intent relationship"

      - id: "confidence_check"
        name: "Verify confidence levels"
        skip_conditions:
          - "All intents have HIGH confidence"

  - id: "HARMONIZE"
    name: "Interface Harmonization"
    description: "Ensure code can build before test synthesis"
    items:
      - id: "identify_interface_changes"
        name: "Find interface mismatches"

      - id: "generate_adapters"
        name: "Generate adapter code if needed"
        skippable: true

      - id: "verify_build"
        name: "Verify merged code builds"
        verification:
          type: "command"
          command: "{{build_command}}"

  - id: "TESTS"
    name: "Test Synthesis"
    description: "Create unified test suite"
    items:
      - id: "collect_tests"
        name: "Collect tests from both branches"

      - id: "deduplicate"
        name: "Deduplicate test cases"

      - id: "fix_imports"
        name: "Fix test imports for harmonized code"

      - id: "generate_integration"
        name: "Generate integration tests"
        agent: "claude_code"
        skippable: true

  - id: "GENERATE"
    name: "Candidate Generation"
    description: "Generate resolution candidates"
    items:
      - id: "strategy_agent1_primary"
        name: "Generate Agent 1 primary candidate"
        agent: "claude_code"

      - id: "strategy_agent2_primary"
        name: "Generate Agent 2 primary candidate"
        agent: "claude_code"

      - id: "strategy_fresh"
        name: "Generate fresh synthesis candidate"
        agent: "claude_code"
        skippable: true
        skip_conditions:
          - "Conflict is simple textual overlap"

  - id: "VALIDATE"
    name: "Validation & Selection"
    description: "Validate candidates and select winner"
    items:
      - id: "tier1_build"
        name: "Tier 1: Build check"
        verification:
          type: "command"
          command: "{{build_command}}"

      - id: "tier2_lint"
        name: "Tier 2: Lint check"
        verification:
          type: "command"
          command: "{{lint_command}}"

      - id: "tier3_targeted"
        name: "Tier 3: Targeted tests"
        verification:
          type: "command"
          command: "{{test_command}} --only-affected"

      - id: "tier4_full"
        name: "Tier 4: Full test suite"
        skippable: true
        skip_conditions:
          - "Low risk conflict"
          - "Targeted tests provide sufficient coverage"
        verification:
          type: "command"
          command: "{{test_command}}"

      - id: "score_candidates"
        name: "Score and rank candidates"

      - id: "select_winner"
        name: "Select winning candidate"

  - id: "DECIDE"
    name: "Decision"
    description: "Auto-resolve or escalate"
    items:
      - id: "check_auto_resolve"
        name: "Check if auto-resolution is safe"

      - id: "escalate"
        name: "Escalate to human if needed"
        skippable: true
        skip_conditions:
          - "Auto-resolution is safe"
        verification:
          type: "manual_gate"
          description: "Waiting for human decision"

  - id: "DELIVER"
    name: "Delivery"
    description: "Create PR and notify user"
    items:
      - id: "create_branch"
        name: "Create resolution branch"

      - id: "create_pr"
        name: "Create pull request"
        verification:
          type: "command"
          command: "gh pr create --title '{{pr_title}}' --body '{{pr_body}}'"

      - id: "notify_user"
        name: "Notify user"
        verification:
          type: "command"
          command: "python -m orchestrator.notify --channel={{notification_channel}}"

      - id: "cleanup"
        name: "Clean up agent branches"
        skippable: true
```

---

## 8. Integration with Existing Orchestrator

### 8.1 New Modules to Add

```
src/
├── schema.py              # Existing - add new models
├── engine.py              # Existing - no changes needed
├── cli.py                 # Existing - add new commands
├── coordinator.py         # NEW - agent coordination logic
├── conflict_detector.py   # NEW - Stage 0 detection
├── intent_extractor.py    # NEW - Stage 2 extraction
├── resolver.py            # NEW - Stages 3-6 resolution
├── escalation.py          # NEW - Human escalation handling
├── git_integration.py     # NEW - Git operations
└── notification.py        # NEW - User notifications
```

### 8.2 New CLI Commands

```bash
# Start multi-agent task (optional - agents self-register)
orchestrator multi "Add auth and dashboard"

# Check coordination status
orchestrator agents                    # List active agent branches
orchestrator agents --status           # Detailed status

# Manual trigger (usually automatic)
orchestrator resolve                   # Trigger conflict resolution
orchestrator resolve --dry-run         # Preview what would happen

# Respond to escalation
orchestrator decide <escalation-id> A  # Choose option A

# View history
orchestrator history --conflicts       # Past resolutions
```

### 8.3 GitHub Actions Integration

**File:** `.github/workflows/claude-coordinator.yml`

```yaml
name: Claude Agent Coordinator

on:
  push:
    branches:
      - 'claude/**'
  schedule:
    - cron: '*/5 * * * *'  # Every 5 minutes
  workflow_dispatch:
    inputs:
      force_resolve:
        description: 'Force resolution even if not all agents complete'
        type: boolean
        default: false

jobs:
  coordinate:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      issues: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          ref: ${{ github.event.push.ref || 'main' }}

      - name: Fetch all branches
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
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}  # For LLM calls
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          python -m orchestrator.coordinator \
            --mode=auto \
            --create-pr=true \
            --notify=true

      - name: Report status
        if: always()
        run: |
          echo "Coordination complete"
          cat .claude/coordinator-log.json || true
```

---

## 9. Agent Instrumentation

### 9.1 How Agents Create Manifests

Agents need minimal changes - just create/update the manifest file.

**Pseudo-code for agent startup:**

```python
# At start of agent work
manifest = {
    "schema_version": "1.0",
    "agent": {
        "id": f"claude-{agent_type}-{session_id}",
        "type": agent_type,  # "web" or "cli"
        "session_id": session_id,
        "started_at": datetime.utcnow().isoformat()
    },
    "task": {
        "description": infer_task_description(user_prompt),
        "user_prompt": user_prompt,
        "inferred_requirements": extract_requirements(user_prompt)
    },
    "work": {
        "status": "in_progress",
        "files_read": [],
        "files_modified": [],
        "decisions": [],
        "tests_added": [],
        "dependencies_added": []
    },
    "constraints": {
        "hard": [],
        "soft": [],
        "assumptions": []
    },
    "completion": None
}

write_file(".claude/agent-manifest.json", manifest)
git_commit("Initialize agent manifest")
git_push()
```

**Pseudo-code for ongoing updates:**

```python
# When reading a file
manifest["work"]["files_read"].append(file_path)

# When modifying a file
manifest["work"]["files_modified"].append(file_path)

# When making a decision
manifest["work"]["decisions"].append({
    "id": f"decision-{len(decisions)+1}",
    "timestamp": datetime.utcnow().isoformat(),
    "type": decision_type,
    "description": description,
    "options_considered": options,
    "evidence": evidence
})

# Periodic save (every few minutes or after significant changes)
write_file(".claude/agent-manifest.json", manifest)
git_commit("Update agent manifest")
git_push()
```

**Pseudo-code for completion:**

```python
# When agent completes work
manifest["work"]["status"] = "complete"
manifest["completion"] = {
    "completed_at": datetime.utcnow().isoformat(),
    "summary": generate_summary(),
    "verification": {
        "build_passed": run_build(),
        "tests_passed": run_tests(),
        "lint_passed": run_lint()
    }
}

write_file(".claude/agent-manifest.json", manifest)
git_commit("Mark agent work complete")
git_push()
```

### 9.2 Branch Creation

Agents create branches with naming convention:

```bash
# Branch name format
claude/<task-slug>-<session-id>

# Examples
claude/add-authentication-abc123
claude/build-dashboard-def456
```

**Slug generation:**
```python
def generate_branch_name(task: str, session_id: str) -> str:
    # Extract key words from task
    slug = task.lower()
    slug = re.sub(r'[^a-z0-9\s]', '', slug)  # Remove special chars
    slug = '-'.join(slug.split()[:4])  # First 4 words
    slug = slug[:30]  # Max 30 chars
    return f"claude/{slug}-{session_id}"
```

---

## 10. Notification System

### 10.1 Notification Channels

```python
class NotificationChannel(Enum):
    GITHUB_ISSUE = "github_issue"      # Always available
    GITHUB_PR_COMMENT = "pr_comment"   # On PR creation
    EMAIL = "email"                     # If configured
    SLACK = "slack"                     # If webhook configured
    CLI = "cli"                         # Next orchestrator command
```

### 10.2 Notification Templates

**Completion (no conflicts):**
```
✅ Your Claude agents finished!

Features completed:
- Add user authentication (Claude Web)
- Build admin dashboard (Claude CLI)

Everything merged cleanly. Ready for your review:
→ https://github.com/you/repo/pull/42

One click to merge when you're ready.
```

**Completion (auto-resolved):**
```
✅ Your Claude agents finished!

Features completed:
- Add user authentication (Claude Web)
- Build admin dashboard (Claude CLI)

There were some overlapping changes, but I resolved them automatically.
Here's what I did:
- Both added login functionality → kept the cookie-based approach
- Combined the user settings pages

Ready for your review:
→ https://github.com/you/repo/pull/42
```

**Escalation needed:**
```
🤔 Need your input

Your Claude agents built features that approach login differently.
I need you to pick which approach to use.

Takes 30 seconds:
→ https://github.com/you/repo/issues/15
```

---

## 11. Configuration

### 11.1 User Configuration File

**File:** `.claude/config.yaml` (in repo root)

```yaml
# Claude Agent Coordinator Configuration

coordination:
  # Enable automatic coordination
  enabled: true

  # How confident must we be to auto-resolve?
  auto_resolve_confidence: 0.8

  # Always escalate these patterns
  always_escalate:
    - "*.env*"
    - "**/auth/**"
    - "**/security/**"
    - "**/migrations/**"

  # Never auto-resolve if these change
  protected_files:
    - "package.json"
    - "requirements.txt"
    - "Dockerfile"

notifications:
  # Where to send notifications
  channels:
    - github_issue
    # - email  # Uncomment to enable
    # - slack  # Uncomment to enable

  # Slack webhook (if enabled)
  # slack_webhook: "https://hooks.slack.com/..."

  # Email (if enabled)
  # email: "you@example.com"

build:
  # Build command for your project
  command: "npm run build"

  # Test command
  test_command: "npm test"

  # Lint command
  lint_command: "npm run lint"

resolution:
  # Max candidates to generate
  max_candidates: 4

  # Timeout for test runs (seconds)
  test_timeout: 300

  # Hours to wait for human response before reminder
  escalation_reminder_hours: 24

  # Hours to wait before auto-selecting recommendation
  escalation_timeout_hours: 72
```

### 11.2 Default Configuration

If no config file exists, use sensible defaults:

```python
DEFAULT_CONFIG = {
    "coordination": {
        "enabled": True,
        "auto_resolve_confidence": 0.8,
        "always_escalate": [],
        "protected_files": []
    },
    "notifications": {
        "channels": ["github_issue"]
    },
    "build": {
        "command": "npm run build || yarn build || make build",
        "test_command": "npm test || yarn test || pytest",
        "lint_command": "npm run lint || yarn lint || true"
    },
    "resolution": {
        "max_candidates": 4,
        "test_timeout": 300,
        "escalation_reminder_hours": 24,
        "escalation_timeout_hours": 72
    }
}
```

---

## 12. Security Considerations

### 12.1 Sensitive Files

Never include in manifests or escalation details:
- `.env` files
- API keys
- Credentials
- Private keys

```python
SENSITIVE_PATTERNS = [
    "*.env*",
    "*secret*",
    "*credential*",
    "*password*",
    "*.pem",
    "*.key",
    "**/secrets/**"
]

def is_sensitive(path: str) -> bool:
    return any(fnmatch(path, pattern) for pattern in SENSITIVE_PATTERNS)
```

### 12.2 Code Execution

All code execution happens in GitHub Actions (sandboxed):
- No arbitrary code on user machines
- Actions run with limited permissions
- Secrets managed through GitHub Secrets

### 12.3 LLM Prompts

Never include in LLM prompts:
- Full file contents of sensitive files
- User credentials
- API keys from environment

---

## 13. Metrics & Learning

### 13.1 Metrics to Track

```python
@dataclass
class ResolutionMetrics:
    # Timing
    detection_duration_seconds: float
    resolution_duration_seconds: float
    total_duration_seconds: float

    # Outcomes
    resolution_type: Literal["fast_path", "auto_resolved", "escalated"]
    escalation_reason: Optional[str]
    human_choice: Optional[str]  # If escalated

    # Quality
    tests_before: int
    tests_after: int
    build_failures_during: int

    # Complexity
    files_conflicting: int
    agents_involved: int
    candidates_generated: int

    # User satisfaction (inferred)
    pr_merged: bool
    pr_reverted: bool
    time_to_merge_hours: float
```

### 13.2 Learning Signals

**Positive signals (resolution was good):**
- PR merged without changes
- No revert within 7 days
- No bug reports linked to merged code

**Negative signals (resolution had issues):**
- User edited PR before merging
- PR reverted
- Bug report linked to resolution
- User manually resolved instead

### 13.3 Future: Adaptive Thresholds

Use metrics to adjust:
- `auto_resolve_confidence` threshold
- Which file patterns should always escalate
- Which resolution strategies work best for different conflict types

---

## 14. Implementation Phases

### Phase 1: Foundation (MVP)
- [ ] Agent manifest schema and creation
- [ ] Branch naming convention
- [ ] Basic conflict detection (git merge-tree)
- [ ] GitHub Action for coordination
- [ ] Simple PR creation (no resolution, just notification)

### Phase 2: Auto-Resolution
- [ ] Intent extraction (LLM-based)
- [ ] Single candidate generation
- [ ] Basic validation (build + test)
- [ ] Auto-merge for clean conflicts

### Phase 3: Smart Resolution
- [ ] Multiple candidate strategies
- [ ] Tiered validation
- [ ] Scoring and selection
- [ ] Escalation system

### Phase 4: Polish
- [ ] Notification channels (Slack, email)
- [ ] Configuration file support
- [ ] Metrics collection
- [ ] Learning/adaptation

---

## 15. Open Questions for Review

1. **Manifest updates during work**: Should agents push manifest updates continuously, or only at completion? (Tradeoff: visibility vs. noise)

2. **LLM provider**: Which LLM for intent extraction and candidate generation? (Claude, GPT-4, local?) Should be configurable.

3. **Test synthesis scope**: How aggressive should integration test generation be? (Risk of generating bad tests)

4. **Escalation timeout**: If user doesn't respond, should system auto-select recommendation after N hours?

5. **Branch cleanup**: When should agent branches be deleted? (After merge? After N days?)

6. **Multi-repo**: Future consideration - what if agents work across multiple repos?

---

*Design document v1.0 - January 2026*
