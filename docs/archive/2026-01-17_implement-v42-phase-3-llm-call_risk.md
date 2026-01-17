# V4.2 Phase 2: Token Budget System - Risk Analysis

## Risk Summary

| Risk | Severity | Probability | Mitigation |
|------|----------|-------------|------------|
| Anthropic API Dependency | High | Medium | EstimationTokenCounter fallback |
| Concurrency Bugs | High | Low | BEGIN IMMEDIATE locking |
| tiktoken Version Compatibility | Medium | Low | Pin version |
| Reservation Timeout | Medium | Medium | Background cleanup |
| Schema Migration | Low | Low | Auto-create tables |

## High Risk

### 1. Anthropic API Dependency

**Description**: ClaudeTokenCounter requires API call for accurate counting.

**Impact**: If API unavailable, token counting fails.

**Mitigation**:
- EstimationTokenCounter as automatic fallback
- Warning log when falling back
- No blocking behavior - system remains functional

### 2. Concurrency Bugs

**Description**: Race conditions in budget tracking could cause overdraft.

**Impact**: Budget limits not enforced, billing issues.

**Mitigation**:
- SQLite BEGIN IMMEDIATE locking (proven in Phase 1)
- Reservation pattern prevents concurrent overdraft
- Comprehensive concurrent test suite

## Medium Risk

### 3. tiktoken Version Compatibility

**Description**: OpenAI tokenizer encoding may change between versions.

**Impact**: Minor token count drift affecting budget accuracy.

**Mitigation**:
- Pin tiktoken version in requirements.txt
- Use specific encoding name (cl100k_base)
- Document expected accuracy tolerance

### 4. Reservation Timeout

**Description**: Expired reservations must release reserved tokens.

**Impact**: Tokens stuck in limbo, reduced available budget.

**Mitigation**:
- Default 5-minute reservation timeout
- Explicit timeout check on commit/status
- Background cleanup task (future enhancement)

## Low Risk

### 5. Schema Migration

**Description**: New database tables required (budgets, reservations).

**Impact**: First-time setup complexity.

**Mitigation**:
- Auto-create tables on first use (existing pattern from Phase 1)
- No migration needed for greenfield deployments

## Impact Analysis

### Backward Compatibility

- ✅ No changes to existing V4 modules
- ✅ New tables are isolated (budgets, reservations)
- ✅ Budget tracking is opt-in

### New Dependencies

| Dependency | Purpose | Version |
|------------|---------|---------|
| anthropic | Claude token counting | >=0.37.0 |
| tiktoken | OpenAI token counting | >=0.7.0 |
| aiosqlite | Async DB (existing) | >=0.17.0 |

### Performance Impact

- Claude counting: +100-300ms per count (API call)
- OpenAI counting: <1ms (local)
- Estimation: <1ms (local)
- Budget operations: <10ms (SQLite)
