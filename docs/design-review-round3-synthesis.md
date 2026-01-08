# Design Review Round 3: AI Feedback Synthesis

**Date:** January 2026
**Reviewers:** OpenAI Codex (gpt-5.1-codex-max)
**Note:** Gemini CLI requires authentication reconfiguration (sessions from 1 day ago exist but credentials expired)

---

## Summary

This review round gathered feedback from Codex on both:
1. The existing orchestrator codebase (bonus: found critical security issues)
2. The multi-agent coordination system design document

---

## Part A: Existing Orchestrator Issues (Pre-existing)

Before implementing the multi-agent system, these issues in the current codebase should be addressed:

### Critical Security Issues

| Issue | Location | Severity | Fix |
|-------|----------|----------|-----|
| Path traversal bypass | `src/engine.py:700-708` | CRITICAL | Use `Path.is_relative_to()` instead of string prefix |
| Manual gates bypassable | `src/schema.py:74-82` | HIGH | Default `skippable=False` for manual_gate items |
| Dashboard CSRF vulnerability | `src/dashboard.py:592-609` | HIGH | Add CSRF tokens, make approve API opt-in |
| Template vars unvalidated | `src/cli.py:188-210` | MEDIUM | Validate template vars exist before execution |
| Command injection risk | `src/engine.py:715-757` | MEDIUM | Add command allow-list or prompt for dangerous commands |
| No integrity checks | `src/engine.py:264-306` | MEDIUM | Enforce stored checksum on reload |

### Recommended Fixes Before Multi-Agent Implementation

1. Fix path safety with `Path.is_relative_to()`
2. Make manual-gate items non-skippable by default
3. Add auth/CSRF defenses to dashboard
4. Enforce stored YAML checksum on reload
5. Add test coverage for security-critical paths

---

## Part B: Multi-Agent Design Document Review

### Security Enhancements Needed

1. **Branch Ping Resource Isolation**
   - Validate artifact contents, size, MIME
   - Cap artifact size/count to prevent DoS
   - Add signing/attestation for artifacts
   - Disable Actions on claude/** branches

2. **Manifest Security**
   - Retention/GC policy
   - Cross-linking (branch SHA + manifest SHA)
   - Replay protection (single-use tokens)
   - Lightweight manifest summary in commit message for traceability

3. **Coordinator Hardening**
   - Clone with `--no-tags`/shallow
   - Never run untrusted scripts from diffs

### Scalability Concerns

**Problem:** Git merge-tree + temp merge per pair scales **O(n²)** for 50+ agents

**Solutions:**
- Batch by touched path/symbol
- Add concurrency limits and priority queues
- Pre-cluster by repo zones (monorepo packages/modules)
- Keep Stage 0 bounded

### Pipeline Improvements

1. **Add fail-fast guard** for "no viable candidate" early
2. **Adapter tech debt rule**: Refactor adapters when same interface chosen twice
3. **Flaky test handling**: Deterministic seed, quarantine, retry budget
4. **Build caching**: Cache artifacts between candidates

### Candidate Strategy Enhancements

| Scenario | Current | Recommendation |
|----------|---------|----------------|
| High-risk conflicts | 3 strategies | Add "minimal merge" (4th strategy) |
| Low-risk/orthogonal | 3 strategies | Skip to single candidate |
| Overlapping refactors | 3 strategies | Conditional 4th strategy |

### Validation Tier Improvements

- Add dependency graph/lint **before** build for JS/TS monorepos
- Need mapping from touched files to test selectors
- Add coverage estimation to avoid silent gaps
- Full suite only for high-risk OR critical paths touched

### Intent Extraction Risk Mitigation

**Problem:** LLM errors can mis-route merges

**Mitigations:**
1. Cross-check intent against diff-derived signals (filenames, symbols, commit message)
2. Auto-flag low-confidence intents for human-in-loop on critical components
3. For conflicting valid intents:
   - Prefer explicit product priority rules
   - Use owner map (CODEOWNERS)
   - Split features behind flags

### Escalation Refinements

| Concern | Current Design | Recommendation |
|---------|----------------|----------------|
| Timeout | 72h fixed | Policy-based: 24h critical, 72h standard |
| Non-responsive | Auto-select after timeout | + logging/notification to team channel |
| Format | Plain-English | + crisp diffs + risk summaries |

### Learning System Safeguards

**Prevent bad pattern drift:**
1. Require human acceptance OR passing validations before storing pattern
2. Add expiry/decay
3. Add context keys (language, framework, conflict type)

**Bootstrap strategy:**
- Seed with heuristics (rename conflicts, formatter clashes)
- Capture resolution metadata for tuning

### Edge Case Handling

| Edge Case | Detection | Response |
|-----------|-----------|----------|
| Circular dependencies | Graph build over changes | Fail early, suggest split |
| Clean merge but broken | Stage 0 build/test | Baseline snapshot for non-determinism |
| Flaky tests | Flake classifier | Retry budget, quarantine, downgrade to warning |
| All candidates fail | Validation pipeline | Minimal revert OR manual escalation with precise logs |

### Missing Operational Concerns

1. **Observability**: Per-stage metrics, timeouts
2. **Cost controls**: Rate limits on agents
3. **Coordinator race condition**: Use locks or GitHub environment protection rules
4. **Audit trail**: Link PRs to agent branches/manifests

---

## Validated Design Choices

Codex explicitly validated these as **sound**:

1. **Split workflows** (untrusted trigger + trusted coordinator) - solid security model
2. **Manifest-as-artifact** - avoids merge churn effectively
3. **Tiered validation** - correct cost/speed tradeoff
4. **"Derive, don't trust"** - strong foundation for manifest verification

---

## Action Items for Design Update

### High Priority (Before Implementation)

1. [ ] Fix existing orchestrator security issues (path traversal, CSRF, etc.)
2. [ ] Add artifact validation and size caps to Branch Ping workflow
3. [ ] Add O(n²) mitigation for conflict clustering at scale
4. [ ] Add fail-fast guard for "no viable candidate"
5. [ ] Make escalation timeout policy-based

### Medium Priority (During Implementation)

6. [ ] Add signing/attestation for artifacts and coordinator outputs
7. [ ] Add dependency graph/lint tier before build (for JS/TS)
8. [ ] Add intent cross-checking against diff-derived signals
9. [ ] Add coordinator concurrency locks
10. [ ] Add observability (per-stage metrics)

### Lower Priority (Polish)

11. [ ] Add conditional 4th "minimal merge" strategy
12. [ ] Add pattern expiry/decay in learning system
13. [ ] Add CODEOWNERS integration for intent conflicts
14. [ ] Add adapter refactoring rules

---

## Conclusion

The design is fundamentally sound with strong foundations:
- Security model (split workflows)
- Verification approach ("derive, don't trust")
- Cost management (tiered validation)

Key areas needing attention:
1. **Scalability**: O(n²) clustering needs optimization
2. **Robustness**: Need fail-fast guards and better edge case handling
3. **Operations**: Need observability, cost controls, and race condition handling
4. **Existing code**: Fix security issues before building multi-agent layer on top

The design is **ready for implementation** with these enhancements incorporated.
