# Risk Analysis: Self-Healing Phases 4 & 5

## Risk Matrix

| Risk | Likelihood | Impact | Severity | Mitigation |
|------|------------|--------|----------|------------|
| Supabase schema conflicts | Low | Medium | LOW | Uses existing tables; circuit breaker adds optional column |
| CLI integration breaks existing commands | Low | High | MEDIUM | Command logic isolated in separate files |
| Engine hooks cause regressions | Medium | High | MEDIUM | Hooks are optional callbacks, tested independently |
| Cost overruns from backfill | Low | Medium | LOW | Respects existing daily cost limits |
| Breaking changes to healing API | Very Low | High | LOW | All additions, no API signature changes |

## Detailed Risk Assessment

### 1. Supabase Schema Changes (LOW)

**What:** Circuit breaker needs to persist state to Supabase
**Risk:** Schema conflicts with existing tables
**Mitigation:**
- Uses existing `healing_config` table
- Adds optional columns: `circuit_state`, `circuit_opened_at`
- No migrations that touch existing data

### 2. CLI Integration (LOW)

**What:** Adding `heal` and `issues` subparsers to cli.py
**Risk:** CLI file is 6000+ lines, changes could break existing commands
**Mitigation:**
- Command implementations in separate files (`cli_heal.py`, `cli_issues.py`)
- cli.py only adds subparsers and delegates
- Each command has unit tests

### 3. Engine Hooks (MEDIUM)

**What:** Adding hook invocation points in engine.py
**Risk:** Could affect workflow execution flow
**Mitigation:**
- Hooks are optional callbacks (no-op if not configured)
- Hooks run in try/except (failures don't stop workflow)
- Integration tests verify engine behavior unchanged

### 4. Cost Controls (LOW)

**What:** Backfill processes historical logs, may incur API costs
**Risk:** Unexpected cost spikes
**Mitigation:**
- Backfill respects existing `max_daily_cost_usd` limit
- Explicit command only (not automatic)
- Shows cost estimate before processing

### 5. Breaking Changes (NONE)

**What:** Changes to existing healing module APIs
**Risk:** N/A - no breaking changes planned
**Verification:**
- All existing tests pass after implementation
- Phase 3 functionality unaffected

## Rollback Plan

If issues arise:
1. CLI commands can be disabled by removing subparser registration
2. Hooks can be disabled by setting `HEALING_HOOKS_ENABLED=false`
3. Circuit breaker can be reset via `orchestrator heal unquarantine`
4. Supabase schema additions are non-breaking

## Security Considerations

1. **Backfill command**: Processes local logs only, no external data sources
2. **API keys**: CLI commands use existing secret management
3. **Pattern export**: Scrubbed of secrets before export (existing security scrubber)

## Dependencies

- Phases 0-3 must be complete (verified)
- Supabase project must be accessible (verified: `igalnlhcblswjtwaruvy.supabase.co`)
- API keys must be configured for judge models (existing requirement)
