# Risk Analysis: CORE-006, SEC-004, CORE-017, CORE-018

## Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| API rate limiting (CORE-017/018) | Medium | Low | Cache results, exponential backoff |
| Network failures during model fetch | Medium | Low | Fall back to static list |
| User confusion with interactive prompts | Low | Low | Clear messaging, default options |
| Breaking existing provider auto-detection | Medium | Medium | Comprehensive tests, backward compat |
| Secrets file corruption during copy | Low | High | Validate before overwrite |

---

## CORE-006 Risks

### Risk 1: Breaking Auto-Detection
- **Description**: Changes to provider detection could break existing workflows
- **Likelihood**: Medium
- **Impact**: Medium
- **Mitigation**:
  - Keep existing `_auto_detect_provider()` logic as baseline
  - Only add interactive selection when explicitly requested (`--interactive`)
  - Comprehensive test coverage for all detection paths

### Risk 2: Manus Connector Detection False Positives
- **Description**: May incorrectly detect Manus environment
- **Likelihood**: Low
- **Impact**: Low
- **Mitigation**:
  - Use multiple indicators (env vars, file paths, API availability)
  - Conservative detection (require multiple signals)

---

## SEC-004 Risks

### Risk 1: Accidental File Overwrite
- **Description**: User might accidentally overwrite existing secrets
- **Likelihood**: Medium
- **Impact**: High
- **Mitigation**:
  - Check if destination exists and warn
  - Require `--force` flag to overwrite
  - Never modify source file

### Risk 2: Path Traversal
- **Description**: Malicious paths could access unintended files
- **Likelihood**: Low
- **Impact**: Medium
- **Mitigation**:
  - Validate paths are within expected directories
  - Use `Path.resolve()` to normalize paths
  - Only copy the specific secrets file, not arbitrary files

---

## CORE-017 Risks

### Risk 1: API Unavailability
- **Description**: OpenRouter API may be down or rate-limited
- **Likelihood**: Medium
- **Impact**: Low
- **Mitigation**:
  - Cache model list locally
  - Fall back to hardcoded defaults
  - Retry with exponential backoff

### Risk 2: Model List Changes
- **Description**: API response format might change
- **Likelihood**: Low
- **Impact**: Medium
- **Mitigation**:
  - Validate API response structure
  - Graceful degradation to static list
  - Version-check API responses

---

## CORE-018 Risks

### Risk 1: Incorrect Capability Detection
- **Description**: API might report incorrect capabilities
- **Likelihood**: Low
- **Impact**: Medium
- **Mitigation**:
  - Cross-reference with known static list
  - Conservative default (assume no function calling if unknown)
  - Allow manual override via config

### Risk 2: Cache Staleness
- **Description**: Cached capabilities become outdated
- **Likelihood**: Medium
- **Impact**: Low
- **Mitigation**:
  - Auto-refresh after 30 days
  - Manual refresh via `update-models` command
  - Warning when cache is old

---

## Overall Assessment

**Risk Level: LOW**

All changes are additive and backward-compatible. Existing functionality is preserved with new features layered on top. Main risks are around API availability, which is mitigated by caching and fallbacks.
