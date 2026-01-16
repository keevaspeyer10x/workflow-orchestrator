# Implementation Plan: Intelligent Pattern Filtering

**Task**: Complete intelligent pattern filtering implementation per docs/handoffs/intelligent-pattern-filtering-implementation.md

## Overview
Implement Phase 6: Cross-Project Pattern Relevance - enable patterns learned in one repo to help another while respecting context relevance.

**Key Decision**: Cross-project lookup enabled by default with guardrails (3+ projects, 5+ successes, 0.7+ Wilson score).

**Added Requirement**: Allow repos to opt-out of sharing their learnings with other projects.

## Pre-existing Components (Already Implemented)
- **SQL Migration**: `migrations/002_intelligent_pattern_filtering.sql` already run
- **RPC Functions**: `lookup_patterns_scored()`, `record_pattern_application()`, `is_eligible_for_cross_project()` in migration
- **PatternContext**: Dataclass in `src/healing/models.py`
- **Context Extraction**: Full module at `src/healing/context_extraction.py`

## Multi-Model Review Feedback (Addressed)
1. **Opt-out semantics clarified**: `share_patterns: false` means "don't share MY patterns with others" (provider opt-out). Consumers always receive cross-project patterns unless they opt out separately.
2. **Error handling**: Added graceful fallback to same-project-only on RPC failures
3. **Observability**: Added logging for cross-project matches, guardrail rejections

## Implementation Tasks

### 1. Update Supabase Client (`src/healing/supabase_client.py`)
- Add `lookup_patterns_scored()` method - calls RPC function to get scored patterns
- Add `record_pattern_application()` method - calls RPC to track per-project usage
- Add `get_pattern_project_ids()` method - returns list of projects using a pattern
- Add `get_project_share_setting()` method - check if project opted out
- **Error handling**: Return empty results on RPC failures, log warnings

### 2. Update HealingClient (`src/healing/client.py`)
- Add thresholds: `SAME_PROJECT_THRESHOLD = 0.6`, `CROSS_PROJECT_THRESHOLD = 0.75`
- Modify `lookup()` to use scored results with tiered matching:
  - Tier 1a: Same project exact match (score >= 0.6)
  - Tier 1b: Cross-project exact match (score >= 0.75, passes guardrails)
  - Tier 2: RAG with language filtering
  - Tier 3: Causality
- Add `_lookup_scored()` helper method
- **Add support for opt-out projects** - filter out patterns from opted-out repos
- **Observability**: Log cross-project matches, guardrail rejections, score thresholds
- **Fallback**: On RPC failure, fall back to existing same-project lookup

### 3. Update Detectors (all 4 detectors)
- `workflow_log.py`: Add context extraction in `_parse_event()`
- `subprocess.py`: Add context extraction in `_parse_output()`
- `transcript.py`: Add context extraction in `_parse_content()`
- `hook.py`: Add context extraction in `_parse_hook_output()`

### 4. Update Backfill (`src/healing/backfill.py`)
- Add context extraction in `_extract_error()` method

### 5. Update record_fix_result (`src/healing/supabase_client.py`)
- Modify to call `record_pattern_application()` RPC
- Accept optional `PatternContext` parameter

### 6. Add Opt-Out Configuration
- Add `share_patterns: bool = True` to HealingConfig
- Store opt-out preference in Supabase `healing_config` table
- Filter opted-out patterns in cross-project lookups
- **Schema**: Add `share_patterns BOOLEAN DEFAULT TRUE` to `healing_config`

### 7. Update `__init__.py` exports
- Export `PatternContext`, `extract_context`, and scoring functions

### 8. Write Tests
- `test_context_extraction.py`: Language detection, category detection, Wilson score, overlap
- `test_scored_lookup.py`: Same-project priority, cross-project guardrails, language filtering
- `test_opt_out.py`: Opt-out config respected, opted-out patterns not shared

## Execution Decision

**Sequential execution** - dependencies between steps require ordered implementation:
1. Supabase client methods must exist before HealingClient can use them
2. Context extraction must be imported before detectors can use it
3. Tests depend on all functionality being in place

### Parallel Opportunity Analysis
- **Could parallelize**: 4 detector updates are independent of each other
- **Estimated total work**: 4-6 hours
- **Decision**: Sequential execution because:
  - Dependencies between major components (Supabase → HealingClient)
  - Moderate scope doesn't justify coordination overhead
  - Single session can catch issues early and adjust
  - Tests should follow implementation to verify correctness

## Risk Mitigation
- All changes backward compatible (new columns have defaults)
- Opt-out defaults to sharing (current behavior)
- Cross-project requires passing guardrails
