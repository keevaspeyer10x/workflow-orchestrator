# Risk Analysis: Aider Review Provider Integration

## Executive Summary

This feature adds Aider as a review provider to enable Gemini reviews with full repo context. Overall risk is **LOW** due to read-only operation, existing patterns, and graceful fallback.

---

## Risk Matrix

| Risk | Likelihood | Impact | Severity | Mitigation |
|------|------------|--------|----------|------------|
| Aider not installed | Medium | Low | Low | Graceful fallback to OpenRouter API |
| Aider command fails | Low | Low | Low | Error handling, return ReviewResult with error |
| OpenRouter key missing | Low | Medium | Low | Check in setup, clear error message |
| Aider output parsing fails | Medium | Low | Low | Return raw output if parsing fails |
| Slow review (repo map build) | Medium | Low | Low | Timeout handling, progress indication |
| Dependency bloat | Low | Low | Low | aider-chat is well-maintained, pinned version |

---

## Detailed Risk Analysis

### R1: Aider Not Installed
**Risk:** Aider is not installed when user runs `orchestrator review`
**Likelihood:** Medium (new dependency)
**Impact:** Low (fallback available)
**Mitigation:**
- Check for `aider` command in ReviewSetup
- Fall back to OpenRouter API if unavailable
- Session-start hook installs aider automatically

### R2: Aider Command Failure
**Risk:** Aider subprocess fails or hangs
**Likelihood:** Low
**Impact:** Low
**Mitigation:**
- Timeout handling (5 minute default)
- Capture stderr for debugging
- Return ReviewResult with error message

### R3: Output Parsing Failure
**Risk:** Aider output format changes or is unexpected
**Likelihood:** Medium (external dependency)
**Impact:** Low
**Mitigation:**
- Graceful parsing with fallback to raw output
- Log warnings for debugging
- ReviewResult still contains raw_output field

### R4: Performance Overhead
**Risk:** Aider's repo map takes time to build
**Likelihood:** Medium (large repos)
**Impact:** Low (one-time per review)
**Mitigation:**
- Aider caches repo map
- Progress indication in output
- User already expects reviews to take time

---

## Security Considerations

| Concern | Assessment | Mitigation |
|---------|------------|------------|
| API key exposure | Low | Uses existing OPENROUTER_API_KEY, passed via env |
| Code sent to LLM | Accepted | Same as existing review providers |
| Aider auto-commits | None | `--no-auto-commits` flag |
| Aider git operations | None | `--no-git` flag |

---

## Rollback Plan

1. Remove `aider` from ReviewMethod enum
2. Remove AiderExecutor import
3. Router falls back to existing methods
4. No data migration needed (stateless)

---

## Approval

- [ ] Risks acceptable for implementation
- [ ] Mitigations adequate
- [ ] Rollback plan reviewed
