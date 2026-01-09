# CORE-023-P3: Conflict Resolution Learning & Config

## Source of Truth

**Primary document:** `docs/archive/2026-01-09_core-023-full-plan-all-parts.md`

This implementation follows the source document exactly. Any deviations will be explicitly noted with justification.

---

## Part 3 Scope (source lines 971-975)

> ### Part 3: Learning & Config - THIRD
> - LEARN phase integration
> - ROADMAP auto-suggestions
> - Config file system

---

## 1. Learning Integration (source lines 67-101)

### Logging (lines 70-77)

Source specifies:
```python
log_event(EventType.CONFLICT_RESOLVED, {
    "file": "src/cli.py",
    "strategy": "sequential_merge",
    "confidence": 0.85,
    "resolution_time_ms": 1250,
})
```

**Implementation:** Add `CONFLICT_RESOLVED` to `EventType` enum in `src/schema.py`, create logging utility that produces exactly this format.

### LEARN Phase → ROADMAP (lines 80-101)

Source specifies the flow:
```
LEARN phase detects:
  "src/cli.py conflicts in 4 of last 10 sessions"
       ↓
Automatically adds to ROADMAP.md:
       ↓
  #### AI-SUGGESTED: Reduce cli.py conflicts
  **Status:** Suggested
  **Source:** AI analysis (LEARN phase, 2026-01-09)
  **Evidence:** cli.py conflicted in 4/10 sessions

  **Recommendation:** Extract argument parsing to separate module
  to reduce merge conflict surface area.
       ↓
User is INFORMED (not asked):
  "ℹ️  Added AI suggestion to ROADMAP: Reduce cli.py conflicts"
```

**Implementation:** Extend `src/learning_engine.py` to:
1. Detect conflict patterns from `.workflow_log.jsonl`
2. Auto-add suggestions to ROADMAP.md in the exact format above
3. Print info message to user (don't prompt)

---

## 2. Config File System (source lines 167-178)

Source specifies (from Grok review):
```
- Add `~/.orchestrator/config.yaml` for:
  - Sensitive globs: `['secrets/*', '*.pem', '.env*']`
  - Generated file policy: `delete | ours | theirs | regenerate`
  - LLM toggle: `disable_llm: true` for air-gapped environments
- Default skip LLM for >10MB files or >50 conflicts (cost/timeout protection)
```

**Implementation:** Create `src/user_config.py` with exactly these capabilities.

---

## 3. Success Criteria (source lines 939-950)

### Configuration
- [x] `~/.orchestrator/config.yaml` for policies
- [x] Sensitive globs configurable
- [x] LLM disable option for air-gapped environments
- [x] Skip LLM for >10MB files or >50 conflicts

### Integration
- [x] Resolutions logged with full telemetry
- [x] Patterns auto-generate ROADMAP suggestions

*(Note: Status conflict warning, exit codes, and --json output were completed in P1)*

---

## 6. Implementation Complete

**All success criteria met.** CORE-023-P3 implemented exactly per source plan.

### Files Created/Modified
- `src/schema.py` - Added CONFLICT_RESOLVED, CONFLICT_ESCALATED EventTypes
- `src/resolution/logger.py` - NEW: Resolution logging utility
- `src/user_config.py` - NEW: User config system (~/.orchestrator/config.yaml)
- `src/learning_engine.py` - Extended with pattern detection + ROADMAP suggestions
- `src/git_conflict_resolver.py` - Integrated logging
- `src/resolution/llm_resolver.py` - Integrated config + logging

### Tests Created
- `tests/test_resolution_logger.py` - 9 tests
- `tests/test_user_config.py` - 21 tests
- `tests/test_conflict_patterns.py` - 12 tests

**Total: 42 new tests, all passing.**

---

## 4. Implementation

| Task | Source Reference | File(s) |
|------|------------------|---------|
| Add CONFLICT_RESOLVED EventType | lines 72 | `src/schema.py` |
| Resolution logging | lines 70-77 | `src/resolution/logger.py` |
| Config file system | lines 167-172 | `src/user_config.py` |
| Conflict pattern detection | lines 84-87 | `src/learning_engine.py` |
| ROADMAP auto-suggestions | lines 89-100 | `src/learning_engine.py` |
| Integrate logging into resolvers | lines 70-77 | `src/git_conflict_resolver.py`, `src/resolution/llm_resolver.py` |

---

## 5. Deviations from Source

**None planned.** Implementation will follow the source document. If any deviation becomes necessary during implementation, it will be documented here with justification before proceeding.
