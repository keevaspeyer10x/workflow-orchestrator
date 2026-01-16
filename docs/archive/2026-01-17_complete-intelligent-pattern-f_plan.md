# Implementation Plan: Self-Healing Phases 4 & 5

## Summary

Implement CLI commands and observability features for the self-healing infrastructure. Phases 0-3 are complete and provide: error detection, fingerprinting, pattern memory (Supabase), three-tier lookup, validation pipeline, and fix application.

## User Decisions (from clarifying questions)

1. **Issues review**: Simple CLI-based (not TUI)
2. **Circuit breaker**: State persisted to Supabase
3. **Backfill**: Explicit command (`orchestrator heal backfill`), optionally prompt on first install

---

## Phase 4: CLI & Workflow Integration

### 4.1 `orchestrator heal` Command Group

Add to `src/cli.py`:

```
orchestrator heal status           # Show healing system status
orchestrator heal apply <fix_id>   # Apply a suggested fix
orchestrator heal ignore <fp>      # Permanently ignore a pattern
orchestrator heal unquarantine <fp> # Reset quarantined pattern
orchestrator heal explain <fp>     # Show why fix wasn't auto-applied
orchestrator heal export           # Export all patterns (yaml/json)
orchestrator heal backfill         # Process historical logs (explicit)
```

**Implementation files:**
- `src/healing/cli_heal.py` - Command implementations (keep cli.py clean)
- Integration in `src/cli.py` - Add `heal` subparser with nested commands

### 4.2 `orchestrator issues` Command Group

```
orchestrator issues list           # List accumulated issues
orchestrator issues review         # Simple CLI review workflow (y/n prompts)
```

**Implementation files:**
- `src/healing/cli_issues.py` - Command implementations

### 4.3 Workflow Hooks Integration

Create hook points in the workflow engine:
- `on_phase_complete` - Detect errors after each phase
- `on_subprocess_complete` - Capture subprocess failures
- `on_workflow_complete` - Display error summary with suggested fixes
- `on_learn_phase_complete` - Feed learnings back to pattern memory

**Implementation files:**
- `src/healing/hooks.py` - Hook implementation (exists, needs integration)
- `src/engine.py` - Add hook invocation points

### 4.4 Test Files

```
tests/healing/test_cli_heal.py
tests/healing/test_cli_issues.py
tests/healing/test_hooks_integration.py
```

---

## Phase 5: Observability & Hardening

### 5.1 Metrics Collection

Add `orchestrator heal metrics` command to display:
- Detection rate (errors detected / total failures)
- Auto-fix rate (auto-applied / detected)
- Success rate (successful fixes / applied)
- Cost history (daily spend)
- Pattern growth (new patterns over time)
- Top errors (most frequent patterns)

**Implementation files:**
- `src/healing/metrics.py` - Metrics collection from Supabase

### 5.2 Circuit Breaker (Supabase-persisted)

Prevent runaway auto-fixing:
- Trip after 2 reverts/hour
- 30-minute cooldown
- State persisted to `healing_config` table

**Implementation files:**
- `src/healing/circuit_breaker.py` - Circuit breaker state machine

### 5.3 Flakiness Detection

Detect intermittently-failing errors:
- Track occurrence patterns over time
- Calculate determinism score (0.0 = flaky, 1.0 = deterministic)
- Flag patterns with high variance in occurrence intervals

**Implementation files:**
- `src/healing/flakiness.py` - Flakiness analysis

### 5.4 Cache Warming

Optimize local performance:
- Pre-load top 100 frequently-used patterns into local cache
- Run on session start (local environments only)

**Implementation files:**
- `src/healing/cache_optimizer.py` - Cache warming

### 5.5 Historical Backfill

Process existing logs:
- `orchestrator heal backfill` command
- Optionally prompt on first install (default: no)
- Repo-aware: detect log locations for current repo

**Implementation files:**
- `src/healing/backfill.py` - Backfill processing

### 5.6 Test Files

```
tests/healing/test_metrics.py
tests/healing/test_circuit_breaker.py
tests/healing/test_flakiness.py
tests/healing/test_backfill.py
tests/healing/test_cache_optimizer.py
```

---

## Execution Strategy

### Parallel Execution Assessment

**Will use: SEQUENTIAL execution**

**Reason:** The components have dependencies that make parallel execution risky:
1. Phase 4 CLI commands depend on stable healing client interfaces
2. Phase 5 components (circuit breaker, metrics) share Supabase schema
3. Hooks integration touches multiple files (engine.py, cli.py, healing/hooks.py)
4. Testing requires incremental verification

However, within each phase, some work can be parallelized:
- Phase 4: `heal` and `issues` CLI commands are independent
- Phase 5: `flakiness`, `cache_optimizer` are independent of each other

### Implementation Order

```
Phase 4.1: CLI commands (heal status, apply, ignore, explain, export)
Phase 4.2: CLI commands (issues list, review)
Phase 4.3: Workflow hooks integration
Phase 4.4: Tests for Phase 4

Phase 5.1: Metrics collection
Phase 5.2: Circuit breaker with Supabase persistence
Phase 5.3: Flakiness detection
Phase 5.4: Cache warming
Phase 5.5: Backfill command
Phase 5.6: Tests for Phase 5
```

---

## Files to Create

| File | Purpose | Lines (est.) |
|------|---------|--------------|
| `src/healing/cli_heal.py` | Heal CLI commands | ~250 |
| `src/healing/cli_issues.py` | Issues CLI commands | ~150 |
| `src/healing/metrics.py` | Metrics collection | ~100 |
| `src/healing/circuit_breaker.py` | Circuit breaker | ~120 |
| `src/healing/flakiness.py` | Flakiness detection | ~80 |
| `src/healing/cache_optimizer.py` | Cache warming | ~50 |
| `src/healing/backfill.py` | Historical backfill | ~100 |
| `tests/healing/test_cli_heal.py` | CLI tests | ~200 |
| `tests/healing/test_cli_issues.py` | Issues tests | ~100 |
| `tests/healing/test_metrics.py` | Metrics tests | ~80 |
| `tests/healing/test_circuit_breaker.py` | Circuit breaker tests | ~100 |
| `tests/healing/test_flakiness.py` | Flakiness tests | ~80 |
| `tests/healing/test_backfill.py` | Backfill tests | ~80 |
| `tests/healing/test_cache_optimizer.py` | Cache tests | ~50 |

## Files to Modify

| File | Changes |
|------|---------|
| `src/cli.py` | Add `heal` and `issues` subparsers, integrate commands |
| `src/engine.py` | Add hook invocation points for healing integration |
| `src/healing/__init__.py` | Export new modules |

---

## Risk Mitigation

1. **Supabase schema changes**: Circuit breaker uses existing `healing_config` table
2. **CLI integration**: Keep command logic in separate files to minimize cli.py changes
3. **Engine modifications**: Add hooks as optional callbacks, no breaking changes
4. **Cost controls**: Backfill respects existing daily cost limits

---

## Success Criteria

- [ ] `orchestrator heal status` shows healing system status
- [ ] `orchestrator heal apply` applies fixes
- [ ] `orchestrator heal explain` explains why fixes weren't auto-applied
- [ ] `orchestrator issues list` shows accumulated issues
- [ ] `orchestrator issues review` provides simple CLI review
- [ ] Circuit breaker trips after 2 reverts/hour
- [ ] Metrics endpoint returns dashboard data
- [ ] Flakiness detection identifies intermittent errors
- [ ] Cache warming improves local lookup performance
- [ ] All new code has test coverage
