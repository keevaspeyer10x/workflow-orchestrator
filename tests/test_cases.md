# Test Cases: Intelligent Pattern Filtering

## 1. Context Extraction Tests (`tests/healing/test_context_extraction.py`)

### Language Detection
- `test_detect_language_python` - Python error patterns detected (ModuleNotFoundError, ImportError, .py files)
- `test_detect_language_javascript` - JavaScript patterns (ReferenceError, npm ERR, .js/.ts files)
- `test_detect_language_go` - Go patterns (panic:, .go files, goroutine)
- `test_detect_language_rust` - Rust patterns (error[E], cargo, .rs files)
- `test_detect_language_file_extension_priority` - File extension takes precedence over pattern matching
- `test_detect_language_unknown` - Returns None with 0.0 confidence for unknown patterns

### Error Category Detection
- `test_detect_category_dependency` - ModuleNotFoundError, npm ERR 404
- `test_detect_category_syntax` - SyntaxError, IndentationError
- `test_detect_category_runtime` - RuntimeError, panic
- `test_detect_category_network` - ConnectionError, ECONNREFUSED
- `test_detect_category_permission` - PermissionError, EACCES

### Scoring Functions
- `test_wilson_score_sample_size` - 1/1 (100%) should score lower than 95/100 (95%)
- `test_wilson_score_zero_total` - Returns 0.5 (neutral) for no data
- `test_wilson_score_high_confidence` - 100/100 scores near 0.95
- `test_recency_score_recent` - Recent success scores ~1.0
- `test_recency_score_30_days` - 30-day old success scores ~0.5 (half-life)
- `test_recency_score_none` - Returns 0.5 for unknown last_success

### Context Overlap
- `test_context_overlap_full_match` - Same context returns ~1.0
- `test_context_overlap_language_match_only` - Language match scores higher than category
- `test_context_overlap_no_match` - Different contexts score low
- `test_context_overlap_partial` - Partial match (e.g., same language, different framework)

### Cross-Project Eligibility
- `test_eligible_meets_all_criteria` - 3+ projects, 5+ successes, 0.7+ Wilson → True
- `test_ineligible_few_projects` - 2 projects → False
- `test_ineligible_few_successes` - 4 successes → False
- `test_ineligible_low_wilson` - 50% success rate → False

## 2. Scored Lookup Tests (`tests/healing/test_scored_lookup.py`)

### Same-Project Lookup
- `test_same_project_found` - Pattern from same project returns with tier=1
- `test_same_project_threshold` - Score >= 0.6 required
- `test_same_project_below_threshold` - Score < 0.6 falls through to cross-project

### Cross-Project Lookup
- `test_cross_project_found` - Pattern meeting guardrails returns with tier=1
- `test_cross_project_threshold` - Score >= 0.75 required
- `test_cross_project_guardrails_enforced` - Pattern not meeting guardrails skipped
- `test_cross_project_opt_out_respected` - Patterns from opted-out projects filtered

### Fallback Behavior
- `test_rpc_failure_fallback` - Falls back to existing lookup on RPC error
- `test_language_mismatch_penalty` - Cross-project with different language scores lower

## 3. Supabase Client Tests (`tests/healing/test_supabase_scoring.py`)

- `test_lookup_patterns_scored_returns_list` - RPC returns scored patterns
- `test_record_pattern_application_success` - Records success with context
- `test_record_pattern_application_failure` - Records failure
- `test_get_pattern_project_ids` - Returns project list
- `test_get_project_share_setting_true` - Default is sharing enabled
- `test_get_project_share_setting_false` - Respects opt-out

## 4. Detector Integration Tests

- `test_workflow_log_detector_context` - Context populated in ErrorEvent
- `test_subprocess_detector_context` - Context populated in ErrorEvent
- `test_backfill_context_extraction` - Historical errors get context

## 5. Opt-Out Tests (`tests/healing/test_opt_out.py`)

- `test_opt_out_config_default_true` - share_patterns defaults to True
- `test_opt_out_config_false` - Can set share_patterns to False
- `test_opted_out_patterns_not_returned` - Cross-project lookup excludes opted-out patterns
- `test_same_project_ignores_opt_out` - Same-project lookup still works when opted-out
