# Phase 2 Risk Analysis

## Security Risks (HIGH)

### 1. Security Scrubber Effectiveness
**Risk:** Regex patterns may miss novel secret formats (false negatives)
**Impact:** Secrets could be stored in Supabase
**Mitigation:**
- Comprehensive test suite with diverse secret patterns
- Defense in depth: scrub at multiple points (before storage, before embedding)
- Log scrubbing actions for audit

### 2. Error Data Sent to External APIs
**Risk:** Error descriptions sent to OpenAI for embeddings may contain sensitive data
**Impact:** Data exposure to third party
**Mitigation:**
- Scrub BEFORE embedding generation
- If scrubbing fails, skip embedding entirely
- Use graceful failure mode (Tier 2 disabled, not error)

### 3. Supabase Data Storage
**Risk:** Error data stored in cloud database
**Impact:** Potential data breach if Supabase compromised
**Mitigation:**
- All text fields scrubbed before storage
- Use Supabase Row Level Security (RLS) policies
- Project isolation via project_id

## External Dependency Risks (MEDIUM)

### 4. Supabase Unavailability
**Risk:** Supabase service down or network issues
**Impact:** Pattern lookup and storage fails
**Mitigation:**
- Graceful degradation to cache-only mode
- Local SQLite cache as fallback for lookups
- Queue writes for retry when service recovers

### 5. OpenAI API Unavailability
**Risk:** OpenAI API down or OPENAI_API_KEY not set
**Impact:** Cannot generate embeddings for Tier 2 lookup
**Mitigation:**
- Tier 2 lookup disabled, Tier 1+3 still functional
- Return None/skip embedding, don't raise error
- Log warning for observability

### 6. Claude API for Pattern Generator
**Risk:** Anthropic API unavailable or ANTHROPIC_API_KEY not set
**Impact:** Cannot generate new patterns from diffs
**Mitigation:**
- Return empty pattern, log warning
- Pattern generation is optional (pre-seeded patterns work)
- Manual pattern creation still possible

## Data Quality Risks (LOW)

### 7. Pre-seeded Pattern Coverage
**Risk:** Pre-seeded patterns may not match all error formats
**Impact:** Low Tier 1 hit rate initially
**Mitigation:**
- Conservative fingerprint patterns (broader matching)
- Start with ~30 well-tested common patterns
- Tier 2 (RAG) provides semantic fallback
- Pattern learning improves coverage over time

### 8. Causality False Correlations
**Risk:** Causality edges may correlate unrelated commits to errors
**Impact:** Incorrect root cause suggestions
**Mitigation:**
- Confidence scoring for all edges
- Minimum occurrence threshold before surfacing
- Evidence type tracking (temporal, git_blame, dependency)
- Human verification for high-impact causes

## Cost Risks (MEDIUM)

### 9. No Cost Tracking Yet
**Risk:** Cost tracking deferred to Phase 3a, but Phase 2 uses LLM
**Impact:** Potential unexpected API costs
**Mitigation:**
- Pattern generator is optional (can skip during testing)
- Embeddings are very cheap (~$0.0002 per error)
- Pre-seeded patterns require no LLM calls
- Document expected costs in plan

## Impact Assessment

| Category | Impact | Likelihood | Overall |
|----------|--------|------------|---------|
| Security | High | Medium | HIGH |
| External Dependencies | Medium | Medium | MEDIUM |
| Data Quality | Low | Medium | LOW |
| Cost | Medium | Low | LOW |

## Overall Assessment

**Changes are ADDITIVE** - Phase 2 builds on Phase 1 without modifying existing functionality. If any Phase 2 component fails:
- Detectors (Phase 1) continue working
- Fingerprinting (Phase 1) continues working
- Error accumulation (Phase 1) continues working

**Recommendation:** PROCEED with implementation. Risks are manageable with documented mitigations.
