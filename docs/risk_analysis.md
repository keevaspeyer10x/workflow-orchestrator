# V3 Pre-Rollout Fixes - Risk Analysis

## Overview
Fix 5 issues before V3 rollout: #71, #79, #74, #87, #82

## Risk Assessment

### Issue #71: hmac.compare_digest for timing attack prevention
| Aspect | Assessment |
|--------|------------|
| **Risk Level** | Low |
| **Change Scope** | Single line change in audit.py |
| **Breaking Changes** | None - API unchanged |
| **Rollback Plan** | Revert commit |

**Mitigation:** Standard library function with well-understood behavior.

---

### Issue #79: Audit log DoS fix
| Aspect | Assessment |
|--------|------------|
| **Risk Level** | Medium |
| **Change Scope** | Replace `_load_last_hash()` method |
| **Breaking Changes** | None - internal implementation change |
| **Rollback Plan** | Revert commit |

**Risks:**
1. Edge case: File smaller than 4KB chunk - handled by min() check
2. Edge case: No complete line in chunk - handled by loop through lines
3. Binary vs text mode change - JSON parsing handles UTF-8

**Mitigation:** Comprehensive test coverage for edge cases.

---

### Issue #74: Audit integrity check in health.py
| Aspect | Assessment |
|--------|------------|
| **Risk Level** | Low |
| **Change Scope** | New method, addition to full_check() |
| **Breaking Changes** | None - additive change |
| **Rollback Plan** | Revert commit |

**Mitigation:** New functionality only, existing behavior unchanged.

---

### Issue #87: Optimize _auto_detect_important_files
| Aspect | Assessment |
|--------|------------|
| **Risk Level** | Low |
| **Change Scope** | Performance optimization |
| **Breaking Changes** | None - same output, faster |
| **Rollback Plan** | Revert commit |

**Risks:**
1. git command not available - handled by try/except fallback
2. subprocess timeout - 5 second timeout prevents hangs

**Mitigation:** Graceful fallback to existing rglob approach.

---

### Issue #82: Design Validation Review
| Aspect | Assessment |
|--------|------------|
| **Risk Level** | Low |
| **Change Scope** | New workflow item |
| **Breaking Changes** | None - additive, skippable |
| **Rollback Plan** | Revert commit |

**Mitigation:** Skippable when plan.md doesn't exist.

---

## Overall Risk Summary

| Priority | Issue | Risk | Impact |
|----------|-------|------|--------|
| P0 | #71 Security | Low | Security improvement |
| P1 | #79 Performance | Medium | Performance/security improvement |
| P2 | #74 Defense | Low | Enhanced monitoring |
| Low | #87 Performance | Low | Performance improvement |
| Feature | #82 | Low | Workflow enhancement |

**Conclusion:** All changes are low-to-medium risk with clear rollback paths. Sequential execution minimizes risk of conflicts.
