# Design Review Feedback Synthesis (Round 2)

Feedback from Codex, Grok, Gemini, and ChatGPT on the detailed system design.

## Critical Issues (Must Fix Before Implementation)

### 1. 🔴 SECURITY: GitHub Actions + Secrets Vulnerability
**Identified by:** ChatGPT (detailed), implied by others
**Severity:** Critical

**The Problem:**
```yaml
on:
  push:
    branches:
      - 'claude/**'
# ... later runs with ANTHROPIC_API_KEY
```
If the workflow runs "in the context of the branch," any compromised agent can modify workflow files to exfiltrate secrets.

**The Fix: Split into Two Workflows**

```
Workflow A: "Branch Ping" (untrusted)
├── Trigger: push to claude/**
├── Permissions: contents: read (minimal)
├── Secrets: NONE
└── Action: Emit repository_dispatch event

Workflow B: "Coordinator" (trusted)
├── Trigger: repository_dispatch + schedule
├── Runs from: default branch ONLY
├── Has: secrets, write permissions
└── Action: Fetch claude branches as DATA, run resolution
```

Why this works: `repository_dispatch` and `schedule` only trigger workflows on the default branch.

---

### 2. 🔴 "Lying Manifest" - Agents May Not Update Reliably
**Identified by:** Gemini, Codex, ChatGPT
**Severity:** Critical

**The Problem:**
Design relies on agents keeping `.claude/agent-manifest.json` updated. LLMs are notoriously bad at administrative side-tasks. If manifest doesn't match code, intent extraction operates on hallucinations.

**The Fix: "Derive, Don't Trust"**
- Coordinator DERIVES "what changed" by diffing branch against main
- Use cheap/fast model to summarize changes factually
- Agent manifest is treated as INPUT/HINTS, not ground truth
- Cross-check manifest claims against actual diff

---

### 3. 🔴 Manifest Path Will Cause Constant Conflicts
**Identified by:** ChatGPT
**Severity:** High

**The Problem:**
If every agent writes `.claude/agent-manifest.json`, merging two branches will always conflict on that file.

**The Fix Options (in order of preference):**

**Option A: Store manifests out-of-tree (BEST)**
- Don't commit manifests to git
- Store as: GitHub Action artifacts, or external blob store keyed by `{repo, branch, sha}`
- Eliminates manifest conflicts entirely

**Option B: Unique path per agent**
- `.claude/manifests/<session-id>.json`
- Exclude from final merge or keep in coordination-only folder

**Option C: Commit only at start + completion**
- Avoid continuous updates
- Keep intermediate state as Action artifacts

---

### 4. 🔴 Stage 0 Must Test MERGED Result
**Identified by:** ChatGPT, Codex, Grok
**Severity:** High

**The Problem:**
Stage 0 says "build both branches" but "clean merge" doesn't guarantee correctness. Classic "no textual conflict, but integration fails" bugs slip through.

**The Fix:**
```
Stage 0 Enhanced:
1. Git merge-tree for textual conflicts
2. Create TEMPORARY merge (even if git says clean)
3. Run on merged result:
   - Compile/typecheck
   - Smoke tests or impacted tests
4. If fails → flag as semantic conflict even though git said clean
```

---

### 5. 🔴 "Winner Takes All" Orphans the Losing Feature
**Identified by:** Gemini
**Severity:** High

**The Problem:**
If user picks "Cookies over JWT" but Dashboard feature relied on JWT, simply picking cookies might break/delete Dashboard entirely.

**The Fix: "Porting" Workflow**
When user picks Architecture A:
1. Don't discard Feature B
2. Trigger new job: "Refactor Feature B to use Architecture A"
3. The "loser" gets rebased onto winner's architecture, not deleted

---

### 6. 🟠 Race Condition: Main Changes During Resolution
**Identified by:** Gemini
**Severity:** Medium-High

**The Problem:**
- Agent A finishes, Coordinator takes 3 minutes to resolve
- Human pushes hotfix to main during those 3 minutes
- Coordinator tries to push PR but it's out of date

**The Fix: Optimistic Concurrency in Stage 8**
```
Before creating PR:
1. Fetch main one last time
2. If main has moved:
   a. Attempt git rebase of resolution onto new main
   b. If rebase fails → trigger "Quick Repair" loop
   c. If still fails → escalate
3. Only then create PR
```

---

### 7. 🟠 Validation Cost Explosion
**Identified by:** Gemini, ChatGPT, Grok
**Severity:** Medium-High

**The Problem:**
Full test suites on 4 candidates in GitHub Actions:
- Large repos: 10-20 min per full suite
- 4 candidates = 40-80 minutes
- Hits 60-min timeout or burns budget

**The Fix: Predictive Test Selection + Budgets**
- Use `files_modified` to run ONLY relevant tests
- Tools: `jest --findRelatedTests`, `pytest-testmon`
- Fail Fast: If build fails (Tier 1), drop candidate immediately
- Time budgets: Max 5 minutes per candidate, escalate with partial results if exceeded
- Cache build/lint results across candidates

---

### 8. 🟠 Dependency Conflicts Need Special Handling
**Identified by:** Gemini, ChatGPT
**Severity:** Medium

**The Problem:**
If Agent A installs `react-query@3` and Agent B installs `tanstack-query@4`, text merge fails or leaves both installed.

**The Fix: Dedicated Dependency Resolver**
```
Before code merging:
1. Detect dependency file changes (package.json, requirements.txt, etc.)
2. Run specialized resolver:
   - Allow additive deps if non-overlapping
   - Detect version conflicts
   - Regenerate lockfile deterministically
   - Run install + tests
3. Escalate only when version constraints collide or security policy blocks
```

---

## Important Enhancements (Should Include)

### 9. Provenance Completeness Scoring
**Source:** Codex

Add explicit scoring for how complete the context is:
- Task prompt present? Files read logged? Tests documented? Decisions captured?
- Propagate score into conflict confidence
- Require minimum completeness for auto-resolution
- Capture "negatives" - explicit "not doing X" decisions

### 10. Semantic Conflict Detection Beyond Textual
**Source:** Grok, Codex

Enhance Stage 0:
- Run targeted tests on naive merge even if git says clean
- Static analysis for duplicate functionality (AST similarity)
- Manifest-based domain overlap detection
- Module dependency graph analysis (imports, call graph)
- "Semantic adjacency" signals (same interface, same domain boundary)

### 11. Candidate Diversity Enforcement
**Source:** Codex, Grok

Current strategies can converge. Enforce diversity via:
- Hard constraints per candidate:
  - A: Must preserve API of Agent 1
  - B: Must preserve API of Agent 2
  - C: Must minimize diff size
  - D: Must maximize internal consistency
- Add redundancy detection (if too similar, generate another)
- Add "test-first" strategy as optional candidate

### 12. Git Blame Preservation
**Source:** Gemini

If Coordinator synthesizes new code, `git blame` shows "Coordinator Bot" as author.

**Fix:** Add Git trailers to commit messages:
```
Co-authored-by: Claude Web <agent-abc123@claude.ai>
Co-authored-by: Claude CLI <agent-def456@claude.ai>
```

### 13. Concurrency + Idempotency in Actions
**Source:** ChatGPT

Prevent duplicate runs and PR spam:
```yaml
concurrency:
  group: claude-coordinator-${{ github.repository }}
  cancel-in-progress: false  # or true, pick semantics
```
- Add idempotency key: "this set of branch SHAs already produced PR #42"
- Define batch window (e.g., 10 min of inactivity before creating PR)

### 14. Flaky Test Handling
**Source:** ChatGPT

Don't auto-eliminate candidates on single test failure:
- Retry once for known-flaky tests
- Track flakiness rate and downweight
- Quarantine persistently flaky tests

### 15. N-Way Conflict Support (Future)
**Source:** Grok

Current design assumes pairwise. For 3+ concurrent agents:
- Group by conflict clusters (auth-related vs dashboard-related)
- Run pipeline per cluster, then final integration
- Candidate strategies could include "best-of-each" composition

---

## UX Refinements

### 16. Escalation Improvements
**Source:** All

- Present TWO options max (top two candidates) to reduce cognitive load
- Always include "recommended safe default"
- Add risk indicators ("higher security", "more compatible", "faster to ship")
- Add confidence score ("90% confident in recommendation")
- Add reversibility indicator ("Option A is reversible later")
- Add "show minimal diff" option (3 files change vs full narrative)
- Add "none of the above" / custom direction option

### 17. Escalation Timeout Policy
**Source:** ChatGPT, Grok

Recommendation:
- **High-risk (auth, security, DB, public API):** Never auto-select
- **Low-risk:** Auto-select after 72h BUT:
  - Open PR as DRAFT
  - Label "auto-selected"
  - Include undo option (revert PR)
  - Notify again

---

## Additional Manifest Fields Needed
**Source:** ChatGPT

```json
{
  "base_sha": "abc123",
  "head_sha": "def456",
  "model": {
    "provider": "anthropic",
    "model_name": "claude-sonnet-4-20250514",
    "temperature": 0.7
  },
  "risk_flags": ["auth", "db_migration", "public_api"],
  "interfaces_changed": ["exportedFunction", "/api/users"],
  "feature_flag": "optional-ff-name"
}
```

---

## Answers to Open Questions (Consensus)

| Question | Consensus Answer |
|----------|-----------------|
| **Manifest updates** | Completion-only for git commits. Intermediate updates as Action artifacts or logs, not committed. |
| **LLM provider** | Configurable + role-based: cheap model for classification/extraction, best model for synthesis, optional critic model |
| **Test synthesis scope** | Conservative: merge/dedupe existing tests, generate integration tests ONLY at clear interaction points, mark generated tests for review |
| **Escalation timeout** | No auto-select for high-risk. Low-risk: auto-select after 72h with draft PR + notification |
| **Branch cleanup** | Delete after PR merged + 7-day grace period. Keep 30 days if escalated. Archive by tagging head SHA. |
| **Multi-repo** | Design IDs for it now (include repo slug), don't build until needed |

---

## Additional Ideas Worth Considering

### Conflict Caching ("rerere for agents")
Record fingerprint of conflict context → chosen resolution. Auto-resolve recurring patterns faster over time.

### Structured Merge Pre-Pass
Before invoking LLM for "textual" conflict, try structured/semi-structured merge on AST boundaries. Reduces spurious conflicts and saves tokens.

### "Policy & Convention Primary" Strategy
Add fifth candidate strategy:
- Retrieve similar patterns from repo ("how do we do auth?")
- Choose approach matching existing architecture
- Adapt other agent's behavior into that pattern
- Reduces long-term drift

### Treat Agent Branches as Untrusted Input
Even if agents are "trusted," prompt injection and tool misuse can produce dangerous outputs:
- Coordinator code is pinned/trusted
- Branch contents are DATA
- Secrets only accessible in trusted coordinator path

---

*Synthesis generated from Codex, Grok, Gemini, and ChatGPT feedback - January 2026*
