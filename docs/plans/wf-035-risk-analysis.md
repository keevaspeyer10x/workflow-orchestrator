# WF-035 Risk & Impact Analysis

## Risk Assessment

### 🔴 HIGH RISK

#### 1. Autonomous Workflows Merge Bad Code
**Risk:** In zero_human mode, code merges without human review. If all 5 AI models miss a critical bug, bad code enters main branch.

**Likelihood:** LOW (multi-model reviews have high catch rate)
**Impact:** HIGH (production incidents, security vulnerabilities)

**Mitigation:**
- ✅ **Defense in depth:** 5 independent AI models (not just 1)
- ✅ **Fallback system:** Minimum 3 of 5 reviews must succeed
- ✅ **Test redundancy:** Tests run in EXECUTE + VERIFY phases
- ✅ **Automated smoke tests:** Catch runtime regressions
- ✅ **Default to supervised:** Users must explicitly opt-in to zero_human mode
- 🔄 **Rollback capability:** Git history allows instant revert
- 📊 **Monitoring:** Log all skipped gates for audit trail

**Acceptance Criteria:**
- ❌ **NOT ACCEPTED:** Single point of failure (1 model decides fate)
- ✅ **ACCEPTED:** 5-model quorum + test redundancy + opt-in + audit trail

---

#### 2. Review Fallbacks Degrade Quality
**Risk:** When primary models (GPT-5.2 Codex Max) fail, fallbacks (GPT-5.1) may be less capable. Lower quality reviews = more bugs slip through.

**Likelihood:** MEDIUM (API outages happen)
**Impact:** MEDIUM (degraded review quality, not complete failure)

**Mitigation:**
- ✅ **Minimum threshold:** Require 3 of 5 reviews (not all)
- ✅ **Fallback quality:** All fallbacks are frontier models (GPT-5.1, Claude Opus 4, Gemini 3 Pro)
- ✅ **Logging:** Track which models used (primary vs fallback) for analysis
- ✅ **Configurable behavior:** `on_insufficient_reviews: block` if user wants strict mode
- 📊 **Feedback loop:** Phase 3b feedback captures review effectiveness

**Acceptance Criteria:**
- ❌ **NOT ACCEPTED:** Fallback to non-frontier models (GPT-4, Claude 3)
- ✅ **ACCEPTED:** All fallbacks are frontier-class + user can block if <3 reviews

---

### 🟡 MEDIUM RISK

#### 3. Smoke Tests Give False Confidence
**Risk:** Passing smoke tests don't guarantee production-readiness. Agents may write trivial smoke tests that pass but don't test critical paths.

**Likelihood:** MEDIUM (depends on agent quality)
**Impact:** MEDIUM (missed regressions, but full test suite still runs)

**Mitigation:**
- ✅ **Test redundancy:** Smoke tests supplement (not replace) full test suite
- ✅ **Examples provided:** `tests/smoke/` shows real-world patterns
- ✅ **Workflow guidance:** Notes section explains what makes a good smoke test
- ✅ **Full tests still run:** EXECUTE phase runs complete test suite
- 📝 **Documentation:** VISUAL_TESTING.md and smoke test examples educate users

**Acceptance Criteria:**
- ❌ **NOT ACCEPTED:** Smoke tests replace full test suite
- ✅ **ACCEPTED:** Smoke tests = quick sanity check, full tests = thorough validation

---

#### 4. Visual Regression Tests Are Flaky
**Risk:** Playwright visual tests may have false positives (font rendering differences, timing issues, dynamic content).

**Likelihood:** MEDIUM (common pain point with visual testing)
**Impact:** LOW (agents can retry or skip, doesn't block workflow)

**Mitigation:**
- ✅ **Skip conditions:** Can skip for backend-only changes
- ✅ **Threshold configuration:** `maxDiffPixels` allows minor differences
- ✅ **Documentation:** VISUAL_TESTING.md covers flake mitigation strategies
- ✅ **Optional:** Not required for all workflows
- 🔧 **Best practices:** Wait for `networkidle`, use consistent viewport

**Acceptance Criteria:**
- ❌ **NOT ACCEPTED:** Visual tests mandatory for all workflows
- ✅ **ACCEPTED:** Visual tests optional + skip conditions + threshold tuning

---

### 🟢 LOW RISK

#### 5. Backward Compatibility Breaks Existing Workflows
**Risk:** Adding `supervision_mode` causes existing workflows to fail or behave unexpectedly.

**Likelihood:** LOW (careful design)
**Impact:** HIGH (breaks all users)

**Mitigation:**
- ✅ **Default to supervised:** Existing behavior unchanged
- ✅ **Optional fields:** All new settings have sensible defaults
- ✅ **Schema validation:** Pydantic ensures invalid configs caught early
- ✅ **Integration tests:** Test existing workflows continue working
- ✅ **Migration guide:** CHANGELOG.md documents new features clearly

**Acceptance Criteria:**
- ❌ **NOT ACCEPTED:** Any breaking change without major version bump
- ✅ **ACCEPTED:** Zero breaking changes, 100% backward compatible

---

#### 6. OpenRouter Rate Limits Block Fallbacks
**Risk:** When primary models fail and all agents use OpenRouter fallbacks simultaneously, rate limits may block reviews.

**Likelihood:** LOW (OpenRouter has generous limits)
**Impact:** MEDIUM (reviews fail, workflow blocked)

**Mitigation:**
- ✅ **Staggered execution:** Reviews run sequentially (not all at once)
- ✅ **Retry logic:** Exponential backoff on rate limit errors
- ✅ **Multiple fallbacks:** 2 fallback options per model (OpenRouter + direct)
- ✅ **Warn mode:** Can proceed with <3 reviews if user configures `on_insufficient_reviews: warn`

**Acceptance Criteria:**
- ❌ **NOT ACCEPTED:** Single fallback with no retry
- ✅ **ACCEPTED:** Multiple fallbacks + retry + configurable warn/block

---

## Impact Analysis

### Positive Impacts

#### 1. ✅ Enables True Autonomous Workflows
**Benefit:** Zero-human workflows can run end-to-end without manual gates
**Users Affected:** All users wanting autonomous operation
**Magnitude:** MAJOR - Removes fundamental blocker to autonomy

#### 2. ✅ Improves Reliability with Fallbacks
**Benefit:** Workflows continue even when 1-2 review models fail
**Users Affected:** All users (makes reviews more robust)
**Magnitude:** HIGH - Reduces workflow failures due to API outages

#### 3. ✅ Standardizes Testing Patterns
**Benefit:** Smoke tests + visual regression docs provide clear guidance
**Users Affected:** All users (especially new users)
**Magnitude:** MEDIUM - Reduces friction in test setup

#### 4. ✅ Zero Breaking Changes
**Benefit:** Existing workflows continue working unchanged
**Users Affected:** All existing users
**Magnitude:** HIGH - No migration burden

---

### Negative Impacts

#### 1. ⚠️ Configuration Complexity Increases
**Impact:** More settings to understand (`supervision_mode`, `reviews.minimum_required`, etc.)
**Users Affected:** Users customizing workflows
**Magnitude:** LOW - Settings optional with good defaults

**Mitigation:**
- Clear documentation in CLAUDE.md
- Examples in workflow.yaml
- Sensible defaults (no config required for basic usage)

#### 2. ⚠️ Testing Burden on Agents
**Impact:** Agents must write smoke tests + visual tests + full tests
**Users Affected:** AI agents implementing features
**Magnitude:** LOW - Tests were already required, just more structured now

**Mitigation:**
- Examples in tests/smoke/ and tests/visual/
- Skip conditions for backend-only changes
- Documentation guides agent through patterns

---

## Critical Path Analysis

### Must-Have for Launch
1. ✅ **Supervision mode configuration** - Core feature
2. ✅ **Gate skipping logic** - Enables autonomy
3. ✅ **Review fallbacks** - Prevents brittle failures
4. ✅ **Backward compatibility** - Protects existing users

### Nice-to-Have for Launch
5. ⚠️ **Smoke test examples** - Can document patterns without code examples
6. ⚠️ **Visual testing guide** - Can be a separate docs-only PR

### Defer to Post-Launch
7. 🔄 **Hybrid mode** - Risk-based gates + timeout logic (complexity not justified yet)
8. 🔄 **OpenRouter direct integration** - Can use existing review_providers.py patterns

---

## Rollback Plan

### If Critical Bug Found Post-Merge

**Immediate (< 5 minutes):**
1. Revert commit: `git revert <commit_hash>`
2. Push to main: `git push origin main`
3. Notify users via GitHub issue

**Why Fast:**
- Default `supervision_mode: supervised` means most users unaffected
- Only zero_human opt-in users impacted
- Git revert is instant (no data loss)

**If Only Zero-Human Mode Broken:**
1. Document workaround: "Use `supervision_mode: supervised` until fixed"
2. Fix in follow-up PR
3. No full revert needed (feature is opt-in)

---

## Monitoring & Observability

### Metrics to Track (Phase 3b Feedback)

**Tool Feedback (Anonymized):**
- `supervision_mode` distribution (supervised vs zero_human vs hybrid)
- Gate skip count (how many gates skipped per workflow)
- Review fallback usage (primary vs fallback model usage)
- Minimum reviews not met (how often <3 reviews succeed)

**Process Feedback (Local):**
- Workflows blocked by manual gates (before/after WF-035)
- Smoke test failures (are smoke tests catching real bugs?)
- Visual regression test flakiness (false positive rate)

### Success Metrics
- ✅ **Autonomy:** >90% of zero_human workflows complete without human intervention
- ✅ **Reliability:** <5% of workflows fail due to insufficient reviews
- ✅ **Adoption:** 20% of workflows use zero_human mode within 3 months
- ✅ **Safety:** 0 production incidents caused by skipped manual gates

---

## Security Considerations

### 1. Malicious Code in Zero-Human Mode
**Threat:** Attacker tricks AI agents into merging malicious code
**Existing Protection:**
- 5 independent AI model reviews
- Full test suite runs (EXECUTE + VERIFY)
- Automated smoke tests
- Git history enables instant rollback

**Additional Protection:**
- SAST tools can be added to REVIEW phase
- Secret scanning already in place
- Code signing can be added for releases

### 2. API Key Exposure via Fallbacks
**Threat:** OpenRouter API key leaked in logs
**Existing Protection:**
- Secrets management (SOPS encryption)
- Logs exclude API keys by default

**Additional Protection:**
- Audit log review (Phase 3b feedback)
- API key rotation procedures documented

---

## Complexity Analysis

### Code Complexity: MEDIUM

**New Code (LOC Estimate):**
- Configuration models: ~100 LOC
- Gate skipping logic: ~150 LOC
- Review fallbacks: ~200 LOC
- Tests: ~400 LOC
- Documentation: ~500 LOC (markdown)
- **Total:** ~1,350 LOC

**Cyclomatic Complexity:**
- Low per-function (mostly linear logic)
- Complexity in fallback chain (but well-tested)

### Conceptual Complexity: MEDIUM

**New Concepts:**
- Supervision modes (3 modes to understand)
- Review fallback chains (primary → fallback → fallback)
- Minimum review threshold (quorum logic)

**Mitigation:**
- Clear documentation
- Examples in workflow.yaml
- Sensible defaults (no config needed for basic use)

---

## Decision Log

### ✅ Approved Decisions

1. **Default to `supervised` mode** - Backward compatible, safe, opt-in for autonomy
2. **Use OpenRouter for fallbacks** - Unified integration, simple, consistent
3. **Minimum 3 of 5 reviews** - Balanced (resilient to 2 failures, but not too lax)
4. **100% backward compatible** - No breaking changes, no migration required
5. **Implement all 6 phases** - Complete solution, not partial MVP

### ⏸️ Deferred Decisions

1. **Hybrid mode implementation** - Defer to WF-036 (risk-based gates too complex for v1)
2. **Direct API integrations** - Defer (OpenRouter sufficient for fallbacks)
3. **Agent supervision UI** - Defer to separate epic (beyond scope)

---

## Sign-Off Criteria

### Before Moving to EXECUTE Phase

- [x] All high risks have mitigation plans
- [x] Backward compatibility confirmed (100%, default to supervised)
- [x] Scope agreed (all 6 phases)
- [x] Rollback plan documented (git revert + workaround)
- [x] Success metrics defined (autonomy, reliability, adoption, safety)
- [ ] User approval received

**Ready for user approval:** YES ✅
