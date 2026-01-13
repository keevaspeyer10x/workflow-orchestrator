# CORE-025 Phase 3: Session Management CLI - Risk Analysis

## Risk Assessment

### Overall Risk: LOW

The implementation is additive CLI commands using existing infrastructure. No changes to core workflow engine or state management.

## Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing CLI commands | Very Low | High | New subcommand group, no modification to existing commands |
| Data loss from cleanup | Low | High | Require confirmation, support --dry-run |
| Session switching breaks workflow | Very Low | Medium | SessionManager.set_current_session already validates |
| Performance with many sessions | Low | Low | Lazy loading, only read state when needed |

## Detailed Risk Analysis

### 1. CLI Namespace Collision (Risk: RESOLVED)
**Analysis:** Original spec used `sessions` which conflicts with CORE-024 transcripts.
**Resolution:** User approved `workflow` as the subcommand group.

### 2. Data Loss from Cleanup (Risk: LOW)
**Analysis:** `workflow cleanup` permanently deletes session directories.
**Mitigation:**
- Require explicit --yes flag or confirmation prompt
- Support --dry-run to preview changes
- Never delete current session
- Log all deletions

### 3. State Corruption (Risk: VERY LOW)
**Analysis:** Commands read/write to .orchestrator/current file.
**Mitigation:**
- Use existing SessionManager methods (already tested)
- Atomic file operations already implemented

### 4. Usability Issues (Risk: LOW)
**Analysis:** Users may find new command group confusing.
**Mitigation:**
- Clear help text
- Consistent output formatting
- Document in CLAUDE.md

## Impact Assessment

### Positive Impacts
1. **Visibility:** Users can see all workflow sessions in a repo
2. **Control:** Switch between sessions easily
3. **Cleanup:** Remove abandoned sessions to reduce clutter

### No Impact (Unchanged)
1. Existing `orchestrator start/status/complete/etc` commands
2. Session transcript commands (`orchestrator sessions`)
3. Core workflow engine behavior

## Security Considerations

### File System Access
- Only operates within .orchestrator/ directory
- Uses existing path resolution (no path traversal risk)
- Delete operations scoped to session directories only

## Rollback Plan

If issues arise:
1. Commands are additive - can be removed without affecting other functionality
2. No database migrations or schema changes
3. Session data format unchanged

## Conclusion

**Recommendation: PROCEED**

- Risk is very low due to using existing infrastructure
- Benefits (visibility, control) improve user experience
- Easy rollback if issues arise

---

# WF-035 Phase 4: Risk & Impact Analysis (Previous)

## Risk Assessment

### Overall Risk: LOW

The implementation is additive and backward-compatible. Existing functionality is preserved.

## Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing review flow | Low | High | Don't modify successful code paths, only add fallback on failure |
| API rate limits on fallbacks | Medium | Low | Add rate limiting/backoff, log which fallback used |
| All fallbacks fail | Low | Medium | Return aggregated error, log all attempts, suggest manual action |
| Performance impact (serial fallbacks) | Low | Low | Fallbacks only triggered on failure (rare) |
| Configuration errors | Low | Low | Validate ReviewSettings at load time, use defaults |

## Detailed Risk Analysis

### 1. Backward Compatibility (Risk: LOW)
**Analysis:** If ReviewSettings is not provided, default to current behavior.
**Mitigation:** Add `if self.settings is None: return current_behavior()`

### 2. Cascading Failures (Risk: LOW)
**Analysis:** If primary and all fallbacks fail, workflow should degrade gracefully.
**Mitigation:**
- on_insufficient_reviews="warn" (default): Log warning, continue
- on_insufficient_reviews="block": Raise exception with helpful message

### 3. API Key Management (Risk: MEDIUM)
**Analysis:** Fallback models may require different API keys.
**Mitigation:**
- OpenRouter provides single-key access to multiple models
- anthropic/claude-opus-4 fallback uses existing Claude access
- Check API key availability before adding to fallback chain

### 4. Timeout Handling (Risk: LOW)
**Analysis:** Fallback chain could take longer if multiple models fail.
**Mitigation:**
- Add per-model timeout (30 seconds default)
- Total timeout cap across all attempts
- Log timing for each attempt

## Impact Assessment

### Positive Impacts
1. **Reliability:** Zero-human workflows no longer blocked by single API outage
2. **Transparency:** Clear logging of which model used, fallback chain state
3. **Flexibility:** Configurable threshold (minimum_required) and behavior (warn/block)

### No Impact (Unchanged)
1. CLI-based reviews (Codex CLI, Gemini CLI) - no fallback needed
2. Successful primary API calls - no change in behavior
3. Existing configuration - backward compatible

### Potential Negative Impacts (Mitigated)
1. Slightly slower failure case (sequential fallback attempts)
2. More complex error messages (aggregated from multiple attempts)

## Rollback Plan

If issues arise:
1. Set `reviews.fallbacks: {}` in workflow.yaml (empty fallbacks = current behavior)
2. Set `reviews.minimum_required: 1` (accept any single review)
3. No code rollback needed - settings control behavior

## Security Considerations

### API Key Exposure
- Fallback chain logged without sensitive data
- API keys never logged
- Error messages sanitized

### Model Trust
- Fallback models are same trusted providers (OpenAI, Anthropic, Google)
- No introduction of untrusted third-party models
- OpenRouter is the established API aggregator

## Conclusion

**Recommendation: PROCEED**

- Risk is low due to additive, backward-compatible design
- Benefits (reliability, graceful degradation) outweigh costs
- Easy rollback via configuration if issues arise
