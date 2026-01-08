# Phase 5: Advanced Resolution - Implementation Plan

**Goal:** Increase auto-resolve rate from ~60% to ~80% through multiple candidate generation, better validation, and robustness improvements.

## Components

### 1. Multiple Candidate Strategies (`multi_candidate.py`)

**Current State:** Phase 3 generates a single candidate using the "best" strategy.
**Target:** Generate 3 candidates using DISTINCT strategies, then select the best.

**Strategies:**
- `agent1_primary` - Keep Agent 1's architecture, adapt Agent 2's features
- `agent2_primary` - Keep Agent 2's architecture, adapt Agent 1's features
- `convention_primary` - Match existing repo patterns, adapt both agents
- `fresh_synthesis` (optional) - Re-implement from scratch (architectural conflicts only)

**Configuration:**
```yaml
resolution:
  max_candidates: 3
  strategies: [agent1_primary, agent2_primary, convention_primary]
  candidate_time_budget: 300  # seconds per candidate
```

### 2. Candidate Diversity Enforcement (`diversity.py`)

**Problem:** Candidates might be too similar if strategies produce similar outputs.
**Solution:** Measure diversity and regenerate if below threshold.

**Implementation:**
- `DiversityChecker` class computes similarity between candidate diffs
- Uses Jaccard similarity on changed line sets
- If diversity < `min_candidate_diversity` (0.3), regenerate with tweaked params
- Max 3 regeneration attempts before proceeding anyway

### 3. Validation Tiers (`validation_tiers.py`)

**Current State:** Phase 3 runs build + targeted tests.
**Target:** Tiered validation with early elimination.

**Tiers:**
| Tier | Name | Time | Action |
|------|------|------|--------|
| 1 | Smoke | ~seconds | Build only - eliminate non-compiling |
| 2 | Lint | ~seconds | Score convention compliance |
| 3 | Targeted | ~5 min | Tests for modified files only |
| 4 | Comprehensive | ~varies | Full suite (high-risk only) |

**High-risk triggers for Tier 4:**
- Security-related files
- Public API changes
- Database migrations
- Authentication/authorization

### 4. Flaky Test Handling (`flaky_handler.py`)

**Problem:** Flaky tests cause false failures and inconsistent results.
**Solution:** Track flakiness, retry known flaky tests, adjust scoring.

**Implementation:**
- `FlakyTestHandler` with JSON-based persistence (`.flaky_tests.json`)
- Track pass/fail history per test (last N runs)
- Flakiness score = (inconsistent_runs / total_runs)
- Retry mechanism: up to 3 retries for tests with flakiness > 0.3
- Scoring adjustment: downweight flaky test failures
- Quarantine: tests with flakiness > 0.8 are noted but not blocking

### 5. Self-Critique (`self_critic.py`) - Optional

**Purpose:** LLM-based review of winning candidate before delivery.
**Implementation:**
- Uses LiteLLM to query external models (GPT-5.2 Max preferred)
- Checks: security issues, performance regressions, error handling, pattern consistency
- Returns: APPROVED or ISSUES list
- Blocking issues: security vulnerabilities, critical bugs
- Config: `self_critique_enabled: false` (optional, adds latency)

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `src/resolution/multi_candidate.py` | CREATE | MultiCandidateGenerator class |
| `src/resolution/diversity.py` | CREATE | DiversityChecker class |
| `src/resolution/validation_tiers.py` | CREATE | TieredValidator class |
| `src/resolution/flaky_handler.py` | CREATE | FlakyTestHandler class |
| `src/resolution/self_critic.py` | CREATE | SelfCritic class |
| `src/resolution/schema.py` | MODIFY | Add ValidationTier enum, FlakyTestRecord, CritiqueResult |
| `src/resolution/pipeline.py` | MODIFY | Integrate new Phase 5 components |
| `tests/resolution/test_phase5.py` | CREATE | Tests for all Phase 5 components |

## Implementation Order

1. **Schema additions** - Add new data models first
2. **Multi-candidate generation** - Core feature, enables diversity checking
3. **Diversity enforcement** - Works with multi-candidate
4. **Validation tiers** - Enhance existing validator
5. **Flaky test handling** - Integrate with validation
6. **Self-critique** - Optional, add last
7. **Pipeline integration** - Wire everything together
8. **Tests** - Write tests for each component

## Success Criteria

- [ ] Generates 3 candidates instead of 1
- [ ] Candidates are measurably diverse (>0.3 Jaccard distance)
- [ ] Validation uses tiered approach with early elimination
- [ ] Flaky tests are detected and handled gracefully
- [ ] Self-critique (when enabled) catches issues Claude missed
- [ ] All 21+ existing resolution tests still pass
- [ ] New tests cover Phase 5 functionality
- [ ] External model review passes before commit
