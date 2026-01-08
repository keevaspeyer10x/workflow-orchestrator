# Codex Design Review: Multi-Agent Coordination System

**Date:** January 2026
**Reviewer:** OpenAI Codex (gpt-5.1-codex-max)
**Focus:** Design document review for multi-agent merge conflict resolution system

---

## Security Gaps

- **Branch Ping workflow lacks explicit resource isolation**
  - Need to ensure agent artifacts cannot be used for RCE against Coordinator
  - Validate artifact contents, size, and MIME
  - Treat manifests as data and never execute
  - Enforce branch name allowlist/format and cap artifact size/count to prevent DoS
  - Add signing/attestation for artifacts and coordinator outputs to avoid tampering/replay
  - Ensure Coordinator clones with `--no-tags`/shallow and does not run untrusted scripts from diffs
  - Disable Actions on claude/** branches to avoid lateral movement

---

## Manifests as Artifacts

- Good for avoiding merge conflicts, but require:
  - Retention/GC policy and immutability checks
  - Cross-linking (branch SHA + manifest SHA) and replay protection (single-use tokens)
  - Consider a lightweight manifest summary in branch commit message to aid traceability without storing the full manifest

---

## Conflict Clustering at 50+ Agents

- Git merge-tree + temp merge per pair scales **O(n²)**
- Need:
  - Batching by touched path/symbol to avoid blowup
  - Concurrency limits and priority queues
  - Pre-cluster by repo zones (monorepo packages/modules) to keep Stage 0 bounded

---

## Pipeline Necessity

- Stages are reasonable but should include:
  - Guard for "no viable candidate" early (fail fast instead of proceeding to validation)
  - Stage 3 adapters can create technical debt—add a rule to refactor adapters when the same interface is chosen twice
  - Stage 6 should include a deterministic seed and flaky-test quarantine
  - Cache build artifacts to keep costs down

---

## Candidate Diversity

- Three strategies might be **too narrow** for high-risk conflicts (e.g., overlapping refactors)
- Consider conditional fourth strategy: "minimal merge" (only shared intent) triggered when semantic overlap is high
- Conversely, for low-risk/orthogonal changes, skip to single candidate to save time

---

## Validation Tiers

- Order is good
- Suggestions:
  - Add dependency graph/lint before build for JS/TS monorepos (fast failures)
  - Targeted tests need a mapping from touched files to test selectors
  - Ensure coverage estimation to avoid silent gaps
  - Full suite only for high-risk or when critical paths touched

---

## Intent Extraction Risk

- **LLM errors can mis-route merges**
- Mitigations:
  - Cross-checks: compare extracted intent to diff-derived signals (filenames, symbols, commit message)
  - Auto-flag low-confidence intents for human-in-loop on critical components
  - For conflicting valid intents, prefer explicit product priority rules or owner map
  - Otherwise split features behind flags

---

## Escalation

- Plain-English options work if paired with crisp diffs and risk summaries
- **72h timeout is long for hotfixes**
  - Make SLA policy-based (e.g., 24h for critical, 72h standard)
- For non-responsive users:
  - Escalate to default policy (auto-apply recommendation)
  - Plus logging/notification to team channel

---

## Learning System

- **Worth it**, but guard against bad pattern drift:
  - Require human acceptance or passing validations before a pattern is stored
  - Add expiry/decay and context keys (language, framework, conflict type)
- Bootstrap with:
  - Seeded heuristics (rename conflicts, formatter clashes)
  - Capture resolution metadata for later tuning

---

## Edge Cases

- **Circular dependencies**: Need detection (graph build over changes; fail early with suggestion to split)
- **"Clean merge but broken"**: Covered by Stage 0 build/test; include baseline snapshot to detect non-determinism
- **Flaky tests**: Add flake classifier and retry budget; otherwise quarantine test and downgrade to warning
- **All candidates fail**: Fall back to minimal revert or manual escalation with precise failure logs

---

## Missing Operational Concerns

- **Observability**: per-stage metrics, timeouts
- **Cost controls** and clear rate limits on agents
- **Race handling**: when two coordinators run concurrently—use locks or GitHub environment protection rules
- **Audit log**: tying PRs to agent branches/manifests for traceability

---

## Sound Choices Validated

- Split workflows with untrusted trigger + trusted coordinator is **solid**
- Manifest-as-artifact avoids merge churn
- Tiered validation and "derive, don't trust" are **strong foundations**
