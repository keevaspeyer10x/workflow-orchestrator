# V4.2 Phase 3: Risk Analysis

## Risk Matrix

| # | Risk | Severity | Likelihood | Impact | Mitigation |
|---|------|----------|------------|--------|------------|
| 1 | Token estimation significantly different from actual usage | Medium | Medium | Budget tracking inaccurate | Use provider-specific counters with API fallback; add 10% buffer in reservation |
| 2 | Reservation timeout during long-running streaming calls | Medium | Low | Call fails mid-stream | Set appropriate timeouts based on max_tokens; streaming updates budget progressively |
| 3 | Concurrent calls exhaust budget unexpectedly | Medium | Medium | Multiple calls proceed when budget nearly exhausted | Atomic operations in Phase 2 handle this; `BEGIN IMMEDIATE` ensures serialization |
| 4 | API client library changes break adapters | Low | Low | Adapters fail to extract token usage | Version-pin dependencies; abstract interface allows quick adapter updates |
| 5 | Retry loop causes budget overrun | Medium | Low | Budget consumed by failed retries | Same-reservation approach prevents this; max retry limit of 3 |

## Risk Details

### 1. Token Estimation Mismatch

**Description:** The estimated token count before an LLM call may differ from the actual tokens used.

**Consequences:**
- Over-estimation: Unnecessarily blocks calls when budget available
- Under-estimation: Budget exceeded after call completes

**Mitigation:**
- Use provider-specific counters (ClaudeTokenCounter, OpenAITokenCounter)
- Add configurable buffer (default 10%) to reservations
- Commit actual usage (not estimated) to track accurately

### 2. Reservation Timeout

**Description:** Long-running LLM calls (especially streaming with high max_tokens) may exceed the default 5-minute reservation timeout.

**Consequences:**
- Reservation expires mid-call
- Budget rollback triggers while call still active
- Tracking becomes inaccurate

**Mitigation:**
- Calculate timeout based on max_tokens (roughly 50-100 tokens/sec)
- For streaming: update reservation as chunks arrive
- Make timeout configurable in InterceptorConfig

### 3. Concurrent Budget Exhaustion

**Description:** Multiple concurrent calls each pass pre-check but together exceed budget.

**Consequences:**
- Budget overrun
- Billing surprises

**Mitigation:**
- Phase 2's `AtomicBudgetTracker` uses `BEGIN IMMEDIATE` for SQLite
- Reservations are atomic - concurrent reserve() calls serialize
- Budget check includes both `used` and `reserved` amounts

### 4. API Library Changes

**Description:** Updates to `anthropic` or `openai` Python packages may change response structure.

**Consequences:**
- Token extraction fails
- Usage not tracked

**Mitigation:**
- Pin specific versions in requirements
- Abstract `LLMAdapter` interface allows quick updates
- Fallback to estimation counter on extraction failure

### 5. Retry Budget Overrun

**Description:** Multiple retry attempts each consuming budget could exhaust it quickly.

**Consequences:**
- Budget depleted by transient failures
- Legitimate calls blocked

**Mitigation:**
- Same reservation used for all retries (not new reservation per retry)
- Maximum 3 retries by default
- Exponential backoff reduces API load

## Residual Risks

After mitigations, the following residual risks remain:

1. **Estimation accuracy:** Even with provider-specific counters, some edge cases (complex tool use, images) may have higher variance
2. **Network failures:** If budget commit fails after successful LLM call, usage may be undertracked
3. **Clock skew:** Reservation expiration relies on system time; significant clock drift could cause issues

These risks are acceptable given the scope and will be monitored during initial deployment.
