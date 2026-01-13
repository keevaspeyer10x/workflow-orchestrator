# PRD-007 Risk Analysis

## Critical Risks

### Risk 1: SDK Adoption Failure
**Severity:** CRITICAL
**Likelihood:** MEDIUM
**Impact:** If agents bypass SDK, entire enforcement system fails

**Concern:** Agents might try to bypass SDK and directly access files/git

**Mitigation Strategies:**
1. Make SDK the ONLY way to interact with orchestrator (no alternative paths)
2. Orchestrator owns all state files - agents get read-only snapshots
3. Tool execution proxied through `/api/v1/tools/execute` (permission-checked)
4. Clear documentation: "SDK is mandatory, not optional"
5. Spawn prompts make SDK usage crystal clear with examples

**Detection:**
- Monitor tool_audit.jsonl for non-SDK tool usage
- Alert if agent attempts direct file writes to .workflow_state.json

**Rollback Plan:**
- If adoption fails, keep `enforcement.mode: permissive` (warnings only)
- Fix SDK usability issues
- Re-enable strict mode after fixes

---

### Risk 2: Performance Overhead
**Severity:** HIGH
**Likelihood:** MEDIUM
**Impact:** API calls add latency, agents feel sluggish

**Concern:** Every tool call goes through orchestrator API, adding network latency

**Mitigation Strategies:**
1. Use local SQLite (fast, no network)
2. In-memory token cache (avoid repeated validation)
3. Batch tool calls where possible
4. Optimize hot paths (tool permission checks <100ms)
5. Async API endpoints (non-blocking)

**Performance Targets:**
- Tool permission check: <100ms
- Phase transition: <500ms
- State snapshot: <200ms

**Testing:**
- Benchmark all API endpoints
- Load testing: 10 concurrent agents
- Profile with cProfile

**Fallback:**
- If latency exceeds targets, add caching layer
- Consider connection pooling for SQLite

---

### Risk 3: Token Security Breach
**Severity:** CRITICAL
**Likelihood:** LOW
**Impact:** Stolen tokens allow bypassing gates

**Concern:** If tokens are stolen/leaked, agents could bypass workflow enforcement

**Mitigation Strategies:**
1. Short expiry (2 hours) - limits window of exploitation
2. Bind tokens to task_id + phase - can't reuse across tasks
3. Rotate JWT secret regularly (monthly)
4. Store secret in environment variable (never in code)
5. Audit log for forensics (detect suspicious patterns)

**Detection:**
- Monitor for token reuse across different tasks
- Alert on expired token usage attempts
- Track phase transition patterns (detect anomalies)

**Response Plan:**
- If breach detected: rotate JWT secret immediately
- Invalidate all existing tokens
- Force all agents to re-claim tasks

---

### Risk 4: YAML Complexity Explosion
**Severity:** MEDIUM
**Likelihood:** HIGH
**Impact:** agent_workflow.yaml becomes unmaintainable

**Concern:** As workflows get complex, YAML becomes hard to understand/modify

**Mitigation Strategies:**
1. Schema validation on load (catch errors early)
2. Clear documentation with examples
3. Validation tooling: `orchestrator validate-workflow agent_workflow.yaml`
4. Keep workflows simple (resist feature creep)
5. Use comments liberally in YAML

**Prevention:**
- Code reviews for workflow changes
- Version control for agent_workflow.yaml
- Test suite for workflow validation

**Monitoring:**
- Track workflow load errors
- Alert on validation failures

---

## Medium Risks

### Risk 5: SQLite Locking (Concurrent Access)
**Severity:** MEDIUM
**Likelihood:** MEDIUM
**Impact:** API requests block waiting for SQLite lock

**Concern:** Multiple agents hitting API concurrently → SQLite locks

**Mitigation:**
- Use connection pooling with timeout
- WAL mode (Write-Ahead Logging) for better concurrency
- If issues persist: upgrade to Redis/PostgreSQL

**Detection:**
- Monitor API response times
- Track database lock wait times

---

### Risk 6: Tool Constraints Too Complex
**Severity:** MEDIUM
**Likelihood:** MEDIUM
**Impact:** Hard to validate glob patterns in tool_constraints

**Concern:** `tool_constraints.write_files.allowed_patterns` uses globs - complex to validate

**Mitigation:**
- Start simple: just allowed/forbidden tools (v1)
- Add constraints in v2 after proving core works
- Use well-tested glob library (fnmatch)

**Fallback:**
- Remove constraints entirely if too complex
- Rely on code reviews instead

---

### Risk 7: Agent Crashes Mid-Phase
**Severity:** MEDIUM
**Likelihood:** MEDIUM
**Impact:** Orphaned tasks, incomplete state

**Concern:** If agent crashes, what happens to in-flight phase transition?

**Mitigation:**
- Orchestrator checkpoints state every 5 minutes
- Resume from last checkpoint on restart
- Timeout detection: if no heartbeat for 10 minutes, mark task as abandoned
- Cleanup command: `orchestrator prd cleanup` removes orphaned sessions

**Recovery:**
- Orchestrator detects timeout
- Marks task as "STALLED"
- Human can resume or reassign

---

## Low Risks

### Risk 8: Documentation Drift
**Severity:** LOW
**Likelihood:** HIGH
**Impact:** Docs don't match implementation

**Mitigation:**
- Document as we build (not at the end)
- Examples tested with real agent
- Version docs alongside code

---

### Risk 9: Backward Compatibility
**Severity:** LOW
**Likelihood:** LOW
**Impact:** Existing agents break when enforcement enabled

**Mitigation:**
- Staged rollout (permissive → strict)
- Migration guide for existing agents
- Deprecation period before full enforcement

---

## Risk Matrix

| Risk | Severity | Likelihood | Priority |
|------|----------|------------|----------|
| SDK Adoption Failure | CRITICAL | MEDIUM | P0 |
| Performance Overhead | HIGH | MEDIUM | P0 |
| Token Security Breach | CRITICAL | LOW | P1 |
| YAML Complexity | MEDIUM | HIGH | P1 |
| SQLite Locking | MEDIUM | MEDIUM | P2 |
| Tool Constraints Complex | MEDIUM | MEDIUM | P2 |
| Agent Crashes | MEDIUM | MEDIUM | P2 |
| Documentation Drift | LOW | HIGH | P3 |
| Backward Compatibility | LOW | LOW | P3 |

## Monitoring Plan

### Key Metrics to Track
- Gate pass rate (target: >90%)
- Gate block rate (if >50%, agents struggling)
- Tool permission check latency (target: <100ms)
- Phase transition latency (target: <500ms)
- Token validation failures
- API error rates
- SQLite lock wait times

### Alerting Thresholds
- Alert if gate block rate >50% (agents may be struggling)
- Alert if task stuck in phase >2 hours
- Alert if tool check latency >200ms
- Alert if API error rate >5%

### Logging
- All tool calls logged to `.orchestrator/tool_audit.jsonl`
- All phase transitions logged to `.orchestrator/events.db`
- All errors logged to `.orchestrator/errors.log`

## Contingency Plans

### If Strict Enforcement Breaks Everything
1. Immediately switch to `enforcement.mode: permissive`
2. Agents get warnings, not blocked
3. Fix issues in background
4. Re-enable strict mode after validation

### If Performance Is Unacceptable
1. Profile hot paths
2. Add caching layer
3. Consider async tool batching
4. If still bad: upgrade from SQLite to Redis

### If Security Breach Detected
1. Rotate JWT secret immediately
2. Invalidate all tokens
3. Audit logs for suspicious activity
4. Force re-authentication for all agents

## Success Indicators

Implementation is successful if:
- [ ] 100% of phase transitions go through orchestrator
- [ ] 0 SDK bypass attempts detected
- [ ] Tool check latency <100ms (p95)
- [ ] Phase transition latency <500ms (p95)
- [ ] Gate pass rate >90%
- [ ] No SQLite locking issues
- [ ] Documentation stays current
- [ ] Agents successfully use SDK without issues

## Review Schedule

- Day 5: Review performance metrics
- Day 10: Review SDK adoption rate
- Day 15: Review gate pass rate
- Day 20: Final risk review before production rollout
