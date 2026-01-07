# Risk Analysis: Multi-Source Secrets Manager

## Executive Summary

This feature adds a unified secrets manager that fetches secrets from env vars, SOPS, or GitHub private repos. Overall risk is **LOW to MEDIUM** due to read-only operations, no disk persistence of decrypted secrets, and additive design that preserves existing behavior.

---

## Risk Matrix

| Risk | Likelihood | Impact | Severity | Mitigation |
|------|------------|--------|----------|------------|
| R1: Secret exposure in logs | Medium | High | **Medium** | Never log secret values, redact in errors |
| R2: GitHub repo misconfiguration | Medium | Medium | **Medium** | Validate repo access, clear error messages |
| R3: SOPS decryption failures | Low | Low | **Low** | Graceful fallthrough, clear diagnostics |
| R4: Cache persistence risks | Low | High | **Medium** | Memory-only cache, no disk writes |
| R5: Breaking existing behavior | Low | High | **Medium** | Env vars checked first, additive design |
| R6: GitHub API rate limits | Low | Low | **Low** | Cache results, minimal API calls |

---

## Detailed Risk Analysis

### R1: Secret Exposure in Logs

**Description:** Secrets could accidentally be logged, exposed in error messages, or included in exception traces.

**Likelihood:** Medium - Easy to accidentally log a secret value.

**Impact:** High - Secret compromise requires rotation.

**Mitigation:**
1. Never log secret values, only names
2. Redact any potential secret values in error messages
3. Use `[REDACTED]` placeholder consistently
4. Review all logging statements for secret exposure

**Implementation:**
```python
def get_secret(self, name: str) -> Optional[str]:
    logger.debug(f"Fetching secret: {name}")  # Never log value
    if value := self._try_sops(name):
        logger.debug(f"Found {name} in SOPS")  # Don't log value
        return value
    # ...
```

---

### R2: GitHub Repo Misconfiguration

**Description:** User configures wrong repo, public repo, or repo they don't have access to.

**Likelihood:** Medium - Configuration errors are common.

**Impact:** Medium - Secrets not found, confusing errors.

**Mitigation:**
1. Validate repo format (owner/name)
2. Check repo accessibility before attempting fetch
3. Clear error messages explaining what's wrong
4. Document expected repo structure

**Implementation:**
```python
def _try_github_repo(self, name: str) -> Optional[str]:
    repo = self._config.get("secrets_repo")
    if not repo or "/" not in repo:
        logger.debug("No valid secrets_repo configured")
        return None
    # ... validate repo access
```

---

### R3: SOPS Decryption Failures

**Description:** SOPS not installed, wrong key, corrupted file, or other decryption issues.

**Likelihood:** Low - SOPS is well-tested; users typically test setup.

**Impact:** Low - Falls through to next source gracefully.

**Mitigation:**
1. Check if SOPS is installed before attempting
2. Verify SOPS_AGE_KEY is set before attempting
3. Catch all SOPS errors and fall through
4. Log diagnostic info for debugging

**Implementation:**
```python
def _try_sops(self, name: str) -> Optional[str]:
    if not shutil.which("sops"):
        logger.debug("SOPS not installed, skipping")
        return None
    if not os.environ.get("SOPS_AGE_KEY"):
        logger.debug("SOPS_AGE_KEY not set, skipping")
        return None
    # ... attempt decryption
```

---

### R4: Cache Persistence Risks

**Description:** Decrypted secrets persisted to disk could be exposed.

**Likelihood:** Low - Design explicitly avoids disk writes.

**Impact:** High - Persistent secret exposure.

**Mitigation:**
1. Cache in memory only (Python dict)
2. Never write decrypted secrets to files
3. Clear cache on manager destruction
4. Document that secrets are never persisted

**Implementation:**
```python
class SecretsManager:
    def __init__(self):
        self._cache = {}  # Memory only
        # Never: self._cache_file.write(...)
```

---

### R5: Breaking Existing Behavior

**Description:** Changes could break existing env var-based secret access.

**Likelihood:** Low - Env vars are checked first, no changes to that path.

**Impact:** High - User workflows fail unexpectedly.

**Mitigation:**
1. Env vars always checked first (highest priority)
2. Existing code paths unchanged
3. New sources are additive fallbacks
4. Extensive testing of existing behavior

**Implementation:**
```python
def get_secret(self, name: str) -> Optional[str]:
    # ALWAYS check env first - preserves existing behavior
    if value := os.environ.get(name):
        return value
    # New sources are fallbacks only
    # ...
```

---

### R6: GitHub API Rate Limits

**Description:** Excessive API calls could hit GitHub rate limits.

**Likelihood:** Low - Secrets fetched once and cached.

**Impact:** Low - Temporary inability to fetch, falls through.

**Mitigation:**
1. Cache all fetched secrets
2. Minimize API calls (one per secret, once per session)
3. Handle rate limit errors gracefully
4. Document caching behavior

---

## Security Considerations

### What We're NOT Doing (Intentionally)

| Capability | Status | Reason |
|------------|--------|--------|
| Disk persistence of secrets | **Excluded** | High exposure risk |
| Logging secret values | **Excluded** | Log exposure risk |
| Caching SOPS_AGE_KEY | **Excluded** | Key should only come from env |
| Fetching from arbitrary URLs | **Excluded** | Only configured GitHub repo |

### Defense in Depth

1. **Priority ordering**: Env vars first (fastest, most secure)
2. **Memory-only cache**: No disk persistence
3. **Redaction**: All secret values redacted in logs/errors
4. **Validation**: Repo format and access validated
5. **Graceful degradation**: Each source fails independently

---

## Rollback Plan

If issues discovered post-deployment:

1. **Immediate**: Set secrets directly via env vars (bypass new system)
2. **Quick fix**: Remove `secrets_repo` config to disable GitHub source
3. **Full rollback**: Revert to previous version (git revert)

---

## Monitoring & Observability

Add logging for:
- Which source each secret came from
- SOPS/GitHub failures (not values, just status)
- Cache hits vs fetches
- Configuration diagnostics

---

## Conclusion

The feature is **LOW to MEDIUM risk** overall:
- Env var priority preserves existing behavior
- Memory-only caching prevents persistence exposure
- Graceful fallthrough on any source failure
- Read-only operations limit blast radius

**Recommendation:** Proceed with implementation, with emphasis on:
1. Never logging secret values (R1)
2. Clear error messages for configuration (R2)
3. Preserving env var priority (R5)
