# Risk Analysis: Intelligent Pattern Filtering

## Risk 1: Cross-Project Information Leakage (Medium)
- **Risk**: Error patterns from private repos could leak sensitive information
- **Mitigation**:
  - SecurityScrubber already strips secrets/PII before storage
  - Opt-out flag added per user request
  - Patterns are fingerprints, not full error text

## Risk 2: False Positive Cross-Project Matches (Low)
- **Risk**: Patterns that work in one context might fail in another
- **Mitigation**:
  - Higher threshold for cross-project (0.75 vs 0.6)
  - Must pass guardrails (3+ projects, 5+ successes, 0.7+ Wilson)
  - Context overlap scoring penalizes language/category mismatches

## Risk 3: Database Migration Side Effects (Low)
- **Risk**: New columns/tables could break existing queries
- **Mitigation**: Migration already applied, all columns have defaults

## Risk 4: Performance Degradation (Low)
- **Risk**: Scored lookup is more complex than simple fingerprint match
- **Mitigation**:
  - RPC functions run in Supabase (server-side)
  - Cache still works for tier 1 exact matches
  - Context extraction is lightweight (regex patterns)

## Risk 5: Backward Compatibility (Very Low)
- **Risk**: Existing code might break
- **Mitigation**:
  - ErrorEvent.context already exists (Optional[PatternContext])
  - All new parameters optional with defaults
  - Existing lookup still works, just enhanced

## Summary
All identified risks have appropriate mitigations in place. The implementation approach is conservative with backward compatibility as a priority.
