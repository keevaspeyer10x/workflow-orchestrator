# Risk Analysis: Workflow Improvements WF-005 through WF-009

## Risk Matrix

| Risk ID | Description | Likelihood | Impact | Score | Mitigation |
|---------|-------------|------------|--------|-------|------------|
| R1 | Critique API failures halt workflow | Medium | Medium | 6 | Graceful fallback - continue without critique |
| R2 | Critique too slow (>30s) | Low | Medium | 4 | Use fast model, 30s timeout, async option |
| R3 | Over-blocking causes frustration | Medium | High | 9 | Advisory mode default, `--no-critique` flag |
| R4 | Context exceeds model limits | Medium | Medium | 6 | Truncate to 8k tokens, prioritize recent items |
| R5 | Critique finds false positives | Medium | Low | 4 | Human confirmation before blocking |
| R6 | File tracking misses files | Low | Low | 2 | Manual `--files` flag as override |
| R7 | Learnings parser misidentifies patterns | Medium | Low | 4 | Human confirmation before adding to roadmap |
| R8 | Breaking change to workflow state schema | Low | High | 6 | Version state file, migration path |

## Detailed Risk Analysis

### R1: Critique API Failures
**Scenario:** OpenRouter/Gemini API is down or returns errors.
**Impact:** Workflow cannot advance, blocking development.
**Mitigation:**
- Wrap critique call in try/except
- On failure, log warning and continue without critique
- Add `--force` flag to bypass critique entirely
```python
try:
    result = critique.run(context)
except CritiqueError as e:
    logger.warning(f"Critique failed: {e}. Continuing without critique.")
    result = None
```

### R2: Critique Latency
**Scenario:** Critique takes >30 seconds, slowing workflow.
**Impact:** Developer frustration, reduced productivity.
**Mitigation:**
- Use gemini-2.0-flash (fastest available)
- Set 30-second timeout
- Show progress indicator
- Consider async critique (continue in background)

### R3: Over-Blocking (HIGHEST RISK)
**Scenario:** Critique flags too many issues, blocking legitimate advances.
**Impact:** Developers bypass system entirely, defeating purpose.
**Mitigation:**
- Default to advisory mode (show issues but don't block)
- Only block on "critical" severity
- `--no-critique` flag for edge cases
- Track blocking rate - if >20% workflows blocked, tune prompts

### R4: Context Size
**Scenario:** Large diffs/many items exceed model context window.
**Impact:** Truncated context leads to poor critique.
**Mitigation:**
- Limit to 8k tokens total
- Prioritize: task description > constraints > recent items > diff
- Summarize diff (stat only, not full content)
- Truncate with "... (truncated)" marker

### R5: False Positives
**Scenario:** Critique warns about non-issues.
**Impact:** Alert fatigue, users ignore critique.
**Mitigation:**
- Tune prompts to be conservative
- Focus on gaps/missing items, not style
- Allow user to mark false positives (future: feedback loop)

### R8: Schema Changes
**Scenario:** Adding `files_modified` to ItemState breaks existing workflows.
**Impact:** In-progress workflows fail to load.
**Mitigation:**
- Add field as Optional with default None
- Parse existing state gracefully (missing field = None)
- Version state file format if major changes needed

## Impact Assessment

### Files Modified
| File | Risk Level | Reason |
|------|------------|--------|
| `src/cli.py` | Medium | Core user interface, must not break |
| `src/critique.py` | Low | New file, no existing dependencies |
| `src/schema.py` | Medium | State schema, backward compatibility |
| `src/engine.py` | Medium | Core logic, existing tests cover |
| `workflow.yaml` | Low | Additive changes only |

### Test Coverage Requirements
- All new code must have >80% coverage
- Existing tests must pass unchanged
- Integration test: full workflow with critique enabled

## Rollback Plan

If issues arise post-implementation:

1. **Disable critique:** Set `phase_critique: false` in workflow.yaml
2. **Remove DOCUMENT phase:** Delete from workflow.yaml, existing workflows continue
3. **Ignore file links:** Field is optional, no impact if removed
4. **Disable learnings pipeline:** Don't call the function

All features designed to be independently disableable with no cascading failures.

## Security Considerations

| Concern | Assessment | Mitigation |
|---------|------------|------------|
| API key exposure | Low | Uses existing OPENROUTER_API_KEY handling |
| Prompt injection | Low | Context is internal data, not user input |
| Information leakage | Low | Critique stays local, no external logging |

## Decision Points

1. **If critique blocks >20% of advances:** Reduce prompt strictness
2. **If critique latency >30s avg:** Consider removing or making async
3. **If false positive rate >30%:** Tune prompts or disable feature

## Approval Checklist

- [ ] Risks R1-R8 mitigations acceptable
- [ ] Schema changes backward compatible
- [ ] Rollback plan sufficient
- [ ] Security considerations addressed
