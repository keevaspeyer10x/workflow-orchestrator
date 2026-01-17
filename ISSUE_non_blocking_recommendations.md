# Issue: Non-blocking recommendations: Capture, evaluate, and action review suggestions

**Repository:** keevaspeyer10x/workflow-orchestrator

---

## Problem

Non-blocking recommendations from code reviews (MEDIUM, LOW, INFO severity) currently disappear after the workflow completes. These may be:
- Feature-specific improvements (e.g., "add pagination to this endpoint")
- Performance suggestions (e.g., "consider caching here")
- Design improvements (e.g., "extract this into a utility")

Even if they don't recur, they may have genuine value. Currently:
- ✅ Captured during review phase
- ✅ Shown in summary count ("5 non-blocking findings")
- ❌ Lost after workflow completes
- ❌ No AI recommendation on what to do with them
- ❌ No auto-handling in zero-human mode

## Solution

### 1. Recommendation Engine

Each non-blocking suggestion gets evaluated and receives an AI recommendation:

```
┌─────────────────────────────────────────────────────────────┐
│ RECOMMENDATION: Add pagination to /api/users                │
├─────────────────────────────────────────────────────────────┤
│ Severity: MEDIUM    Consensus: 2/3 models    Effort: LOW    │
│ Category: performance                                        │
├─────────────────────────────────────────────────────────────┤
│ ✅ RECOMMEND: Create issue                                   │
│ Reasoning: High consensus, low effort, prevents future       │
│ scaling issues. Quick win worth tracking.                    │
└─────────────────────────────────────────────────────────────┘
```

### 2. Decision Criteria

| Factor | Weight | Logic |
|--------|--------|-------|
| Consensus | High | 2+ models agreed → stronger signal |
| Effort | High | Low effort + any value → just do it |
| Category | Medium | Security/correctness > style/refactor |
| Severity | Medium | MEDIUM > LOW > INFO |
| Scope | Low | Localized change easier to justify |

**Decision matrix:**
- `✅ APPLY NOW` - Low effort + high consensus + clear value
- `✅ CREATE ISSUE` - Worth doing, but not blocking this PR
- `⚠️ DEFER` - Uncertain value, save for later review
- `❌ DISMISS` - Noise, style nit, or already addressed

### 3. Human Mode (Interactive)

At `orchestrator finish`:
```
═══════════════════════════════════════════
NON-BLOCKING RECOMMENDATIONS (5)
═══════════════════════════════════════════
1. [MEDIUM] Add pagination to /api/users endpoint (src/api.py:45)
   → Gemini: "List could grow unbounded, consider cursor-based pagination"
   → AI RECOMMENDS: Create issue (consensus: 2, effort: low)

2. [LOW] Extract validation logic (src/auth.py:23)
   → Grok: "Same pattern in 3 places, could be a shared utility"
   → AI RECOMMENDS: Defer (consensus: 1, effort: medium)

Accept AI recommendations? [y] Yes to all  [s] Select individually  [n] Dismiss all
```

### 4. Zero-Human Mode (Autonomous)

When sub-agents run orchestrator without human intervention:

```yaml
# In workflow.yaml or orchestrator config
zero_human_mode:
  recommendation_handling: "auto"  # or "minds" or "conservative"

  auto_rules:
    apply_now:
      - consensus >= 2 AND effort == "low" AND category in ["security", "bug"]
    create_issue:
      - consensus >= 2 AND effort in ["low", "medium"]
      - category == "security"  # Always track security suggestions
    defer:
      - consensus == 1 AND effort == "high"
    dismiss:
      - severity == "info" AND consensus == 1
```

Output:
```
[ZERO-HUMAN MODE] Processing 5 non-blocking recommendations...
  ✅ Creating issue: "Add pagination to /api/users" (consensus: 2, effort: low)
  ✅ Creating issue: "Add rate limiting" (category: security)
  ⚠️ Deferred: "Extract validation logic" (effort: high, consensus: 1)
  ❌ Dismissed: "Consider renaming variable" (info, no consensus)
  ❌ Dismissed: "Add comment explaining logic" (info, style only)

Created 2 issues, deferred 1, dismissed 2.
```

### 5. Minds Escalation (Ambiguous Cases)

For edge cases where rules don't clearly apply:
```bash
minds ask "Should we create an issue for this recommendation?
Context: [recommendation details]
Consensus: 1 model, Effort: medium, Category: design
The feature works correctly without this change.
Respond: CREATE_ISSUE | DEFER | DISMISS with one-line reasoning"
```

## Implementation Tasks

### Phase 1: Schema & Storage
- [ ] Extend `ReviewIssue` schema with `effort_estimate: Literal["low", "medium", "high"]`
- [ ] Add `ai_recommendation: Literal["apply_now", "create_issue", "defer", "dismiss"]`
- [ ] Add `ai_reasoning: str` field
- [ ] Store non-blocking recommendations in workflow state (persist beyond review phase)

### Phase 2: Recommendation Engine
- [ ] Create `RecommendationEngine` class with decision logic
- [ ] Implement rule-based evaluation (consensus, effort, category, severity)
- [ ] Add effort estimation heuristic (lines changed, scope of suggestion)
- [ ] Generate reasoning string for each recommendation

### Phase 3: Human Mode Integration
- [ ] Add recommendation display to `orchestrator finish`
- [ ] Implement interactive triage: accept all / select / dismiss
- [ ] Create issues via `gh issue create` when selected
- [ ] Save deferred items to `.deferred_recommendations.jsonl`

### Phase 4: Zero-Human Mode
- [ ] Add `zero_human_mode.recommendation_handling` config
- [ ] Implement auto-decision based on configured rules
- [ ] Add minds escalation for ambiguous cases
- [ ] Log all decisions to workflow audit trail

### Phase 5: Deferred Review
- [ ] Add `orchestrator recommendations list` - show deferred items
- [ ] Add `orchestrator recommendations triage` - re-evaluate deferred items
- [ ] Add `orchestrator recommendations cleanup --older-than 30` - prune stale items

## Design Considerations

- **Don't over-engineer**: Start with rule-based decisions, add minds escalation only for genuine ambiguity
- **Respect user time**: In human mode, AI recommendations should reduce clicks, not add questions
- **Audit trail**: All decisions (human or auto) logged for learning system analysis
- **Issue quality**: Created issues should have enough context to be actionable without re-reading the PR

## Labels

`enhancement`, `workflow`, `zero-human-mode`, `learning-system`

## References

- Minds consensus on non-blocking recommendations handling
- Existing `SynthesizedReview.blocking_issues` pattern in `src/review/schema.py`
- Zero-human mode concept from WF-035
