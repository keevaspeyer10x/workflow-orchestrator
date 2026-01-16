# Phase 2 Test Cases

## Test Files

```
tests/healing/
├── test_security.py
├── test_supabase_client.py
├── test_preseeded.py
├── test_pattern_generator.py
├── test_embeddings.py
├── test_healing_client.py
└── test_lookup_tiers.py
```

## 1. Security Scrubber Tests (`test_security.py`)

### Unit Tests

| Test Case | Input | Expected Output |
|-----------|-------|-----------------|
| `test_scrub_api_key` | `"api_key=sk-abc123def456"` | `"api_key=<REDACTED>"` |
| `test_scrub_bearer_token` | `"Authorization: Bearer xyz"` | `"Authorization: Bearer <REDACTED>"` |
| `test_scrub_password` | `"password=secret123"` | `"password=<REDACTED>"` |
| `test_scrub_aws_key` | `"AKIAIOSFODNN7EXAMPLE"` | `"<AWS_KEY>"` |
| `test_scrub_private_key` | PEM format key | `"<PRIVATE_KEY>"` |
| `test_scrub_connection_string` | `"postgres://user:pass@host"` | `"postgres://<REDACTED>"` |
| `test_scrub_email` | `"user@example.com"` | `"<EMAIL>"` |
| `test_scrub_multiple` | Text with multiple secrets | All secrets redacted |
| `test_scrub_no_secrets` | `"Hello world"` | `"Hello world"` (unchanged) |
| `test_scrub_error_event` | ErrorEvent with secrets | ErrorEvent with scrubbed fields |

## 2. Supabase Client Tests (`test_supabase_client.py`)

### Unit Tests (mocked Supabase)

| Test Case | Description |
|-----------|-------------|
| `test_lookup_pattern_found` | Returns pattern when fingerprint exists |
| `test_lookup_pattern_not_found` | Returns None when fingerprint missing |
| `test_lookup_pattern_quarantined` | Returns None for quarantined patterns |
| `test_lookup_similar_above_threshold` | Returns similar patterns above 0.7 |
| `test_lookup_similar_below_threshold` | Returns empty when all below 0.7 |
| `test_get_causes` | Returns causality edges for fingerprint |
| `test_get_causes_with_depth` | Limits causality depth |
| `test_record_pattern_new` | Inserts new pattern |
| `test_record_pattern_existing` | Upserts existing pattern |
| `test_record_pattern_scrubs` | Scrubs description before insert |
| `test_record_fix_result_success` | Increments success_count |
| `test_record_fix_result_failure` | Increments failure_count |
| `test_audit_log` | Inserts audit entry |

## 3. Pre-seeded Patterns Tests (`test_preseeded.py`)

### Unit Tests

| Test Case | Description |
|-----------|-------------|
| `test_patterns_count` | At least 25 patterns defined |
| `test_patterns_have_required_fields` | All have fingerprint_pattern, safety_category, action |
| `test_patterns_valid_safety_category` | All are 'safe', 'moderate', or 'risky' |
| `test_patterns_valid_action_type` | All actions have valid action_type |
| `test_python_module_not_found` | Pattern matches ModuleNotFoundError |
| `test_node_module_not_found` | Pattern matches Cannot find module |
| `test_go_package_not_found` | Pattern matches cannot find package |
| `test_pytest_fixture_not_found` | Pattern matches fixture not found |
| `test_seed_patterns_inserts` | seed_patterns() inserts all patterns |
| `test_seed_patterns_idempotent` | Running twice doesn't duplicate |

## 4. Pattern Generator Tests (`test_pattern_generator.py`)

### Unit Tests (mocked Claude)

| Test Case | Description |
|-----------|-------------|
| `test_generate_from_diff_valid` | Generates pattern from error+diff |
| `test_generate_from_diff_with_context` | Uses context in prompt |
| `test_generate_from_diff_invalid_json` | Handles malformed LLM response |
| `test_generate_from_diff_api_error` | Handles API timeout/error |
| `test_extract_from_transcript_finds_fixes` | Finds error→fix sequences |
| `test_extract_from_transcript_empty` | Returns empty for no fixes |
| `test_extract_from_transcript_multiple` | Finds multiple fixes |

## 5. Embedding Service Tests (`test_embeddings.py`)

### Unit Tests (mocked OpenAI)

| Test Case | Description |
|-----------|-------------|
| `test_embed_text` | Returns 1536-dim vector |
| `test_embed_error` | Combines error fields for embedding |
| `test_embed_error_with_file_path` | Includes file path in text |
| `test_embed_no_api_key` | Returns None gracefully |
| `test_embed_api_error` | Returns None on API error |
| `test_embed_rate_limit` | Handles rate limit gracefully |

## 6. Healing Client Tests (`test_healing_client.py`)

### Integration Tests (mocked adapters)

| Test Case | Description |
|-----------|-------------|
| `test_lookup_tier1_cache_hit` | Returns from cache |
| `test_lookup_tier1_supabase_hit` | Returns from Supabase, caches |
| `test_lookup_tier2_similar_found` | Falls back to RAG search |
| `test_lookup_tier3_causality` | Returns causality edges |
| `test_lookup_no_match` | Returns empty LookupResult |
| `test_lookup_no_embedding_service` | Skips Tier 2 |
| `test_lookup_concurrent` | Handles concurrent lookups |

## 7. Three-Tier Lookup Tests (`test_lookup_tiers.py`)

### End-to-End Tests (full mock stack)

| Test Case | Description |
|-----------|-------------|
| `test_tier1_exact_match` | Fingerprint found in Supabase |
| `test_tier2_semantic_match` | No exact match, RAG finds similar |
| `test_tier3_causality_only` | No pattern, returns causality |
| `test_all_tiers_miss` | No match at any tier |
| `test_tier_priority` | Tier 1 > Tier 2 > Tier 3 |
| `test_cache_invalidation` | Cache respects TTL |

## Test Fixtures

### Common Fixtures (`conftest.py`)

```python
@pytest.fixture
def sample_error_event() -> ErrorEvent:
    """Sample error for testing."""

@pytest.fixture
def sample_pattern() -> dict:
    """Sample Supabase pattern."""

@pytest.fixture
def mock_supabase() -> AsyncMock:
    """Mocked Supabase client."""

@pytest.fixture
def mock_openai() -> AsyncMock:
    """Mocked OpenAI client."""

@pytest.fixture
def mock_anthropic() -> AsyncMock:
    """Mocked Anthropic client."""
```

## Coverage Target

- Line coverage: 90%+
- Branch coverage: 85%+
- All edge cases covered
- All error paths tested

---

# Phase 3 Test Cases

## Test Files

```
tests/healing/
├── test_safety.py          # 15 tests
├── test_costs.py           # 15 tests
├── test_cascade.py         # 13 tests
├── test_judges.py          # 17 tests
├── test_validation.py      # 12 tests
├── test_context.py         # 12 tests
└── test_applicator.py      # 15 tests
```

**Total: 99 new Phase 3 tests**

## 8. Safety Categorizer Tests (`test_safety.py`)

| Test Case | Description |
|-----------|-------------|
| `test_protected_path_is_risky` | Files in protected paths → RISKY |
| `test_migration_is_risky` | Migration files → RISKY |
| `test_env_file_is_risky` | .env files → RISKY |
| `test_empty_diff_is_safe` | Empty diffs → SAFE |
| `test_formatting_only_is_safe` | Whitespace changes → SAFE |
| `test_import_only_is_safe` | Import additions → SAFE |
| `test_comment_only_is_safe` | Comment changes → SAFE |
| `test_function_signature_change_is_risky` | Function sig changes → RISKY |
| `test_database_operation_is_risky` | SQL operations → RISKY |
| `test_security_sensitive_is_risky` | Password/auth → RISKY |
| `test_error_handling_is_moderate` | Try/except → MODERATE |
| `test_conditional_change_is_moderate` | If/else → MODERATE |
| `test_loop_change_is_moderate` | For/while → MODERATE |

## 9. Cost Tracker Tests (`test_costs.py`)

| Test Case | Description |
|-----------|-------------|
| `test_initial_status` | Zero usage on init |
| `test_record_embedding_cost` | Embeddings tracked |
| `test_record_judge_cost` | Judge calls tracked |
| `test_can_validate_safe` | SAFE allowed under limit |
| `test_can_validate_moderate` | MODERATE allowed under limit |
| `test_can_validate_risky` | RISKY allowed under limit |
| `test_estimate_cost_safe` | 1 judge cost |
| `test_estimate_cost_moderate` | 2 judge cost |
| `test_estimate_cost_risky` | 3 judge cost |
| `test_is_over_budget` | Budget exceeded detection |
| `test_is_over_validation_limit` | Limit exceeded detection |

## 10. Cascade Detector Tests (`test_cascade.py`)

| Test Case | Description |
|-----------|-------------|
| `test_new_file_not_hot` | New files not hot |
| `test_file_becomes_hot` | 3+ mods → hot |
| `test_file_not_hot_below_threshold` | <3 mods not hot |
| `test_record_fix` | Fix recording works |
| `test_check_cascade_detects_recent_fix` | Recent fix cascade detected |
| `test_check_cascade_ignores_old_fix` | Old fixes ignored |
| `test_check_cascade_ignores_different_file` | Unrelated files ignored |
| `test_get_hot_files` | Hot file listing |
| `test_get_recent_fixes` | Recent fix listing |

## 11. Multi-Model Judge Tests (`test_judges.py`)

| Test Case | Description |
|-----------|-------------|
| `test_vote_with_approval` | Approval vote creation |
| `test_vote_with_rejection` | Rejection vote creation |
| `test_vote_with_error` | Error vote handling |
| `test_approval_count` | Approval counting |
| `test_get_judge_count_safe` | 1 judge for SAFE |
| `test_get_judge_count_moderate` | 2 judges for MODERATE |
| `test_get_judge_count_risky` | 3 judges for RISKY |
| `test_build_judge_prompt` | Prompt construction |
| `test_parse_vote_valid_json` | Valid JSON parsing |
| `test_parse_vote_json_in_markdown` | Markdown JSON parsing |
| `test_parse_vote_invalid_json` | Invalid JSON handling |
| `test_get_api_key_from_env` | Env key retrieval |
| `test_get_api_key_explicit` | Explicit key usage |
| `test_judge_without_api_keys` | Missing key handling |
| `test_judge_with_mocked_api` | Mocked approval flow |

## 12. Validation Pipeline Tests (`test_validation.py`)

| Test Case | Description |
|-----------|-------------|
| `test_passed_preflight` | Preflight pass detection |
| `test_failed_preflight` | Preflight fail detection |
| `test_passed_verification` | Verification pass detection |
| `test_passed_approval` | Approval pass detection |
| `test_kill_switch_blocks` | Kill switch blocks all |
| `test_hard_constraints_too_many_files` | >2 files blocked |
| `test_hard_constraints_too_many_lines` | >30 lines blocked |
| `test_no_precedent_blocks` | No pattern blocked |
| `test_preseeded_has_precedent` | Preseeded patterns pass |
| `test_cascade_detection_blocks` | Hot files blocked |
| `test_risky_never_auto_approved` | RISKY requires human |

## 13. Context Retriever Tests (`test_context.py`)

| Test Case | Description |
|-----------|-------------|
| `test_file_context_exists` | Existing file context |
| `test_file_context_not_exists` | Missing file handling |
| `test_file_context_with_error` | Error tracking |
| `test_all_files` | All files collection |
| `test_to_prompt_context` | Prompt formatting |
| `test_to_prompt_context_excludes_missing` | Missing excluded |
| `test_get_context_error_file` | Error file retrieval |
| `test_get_context_with_fix_action` | Fix action files |
| `test_get_context_missing_file` | Missing file handling |
| `test_get_related_files_python` | Python related files |
| `test_get_related_files_javascript` | JS related files |
| `test_get_related_files_go` | Go related files |

## 14. Fix Applicator Tests (`test_applicator.py`)

| Test Case | Description |
|-----------|-------------|
| `test_apply_result_success` | Success result |
| `test_apply_result_with_pr` | PR result |
| `test_apply_result_failure` | Failure result |
| `test_verify_result_passed` | Verify pass |
| `test_verify_result_failed` | Verify fail |
| `test_apply_not_approved` | Unapproved rejected |
| `test_apply_diff_success` | Diff application |
| `test_apply_command` | Command execution |
| `test_apply_file_edit` | File editing |
| `test_apply_verification_failure` | Rollback on failure |
| `test_apply_creates_pr_in_cloud` | Cloud → PR |
| `test_apply_creates_pr_for_moderate` | MODERATE → PR |
| `test_apply_direct_merge_for_safe_local` | SAFE+local → merge |
| `test_apply_records_cascade` | Cascade tracking |
| `test_build_pr_body` | PR body generation |

---

# Phase 4 Test Cases

## Test Files

```
tests/healing/
├── test_cli_heal.py        # 18 tests
├── test_cli_issues.py      # 10 tests
└── test_hooks_integration.py  # 12 tests
```

**Total: 40 new Phase 4 tests**

## 15. CLI Heal Commands (`test_cli_heal.py`)

| Test Case | Description |
|-----------|-------------|
| `test_heal_status_basic` | Shows environment, enabled, pattern count |
| `test_heal_status_kill_switch` | Shows ACTIVE warning when kill switch on |
| `test_heal_status_no_supabase` | Graceful offline mode |
| `test_heal_apply_valid` | Applies fix, returns PR/commit |
| `test_heal_apply_dry_run` | Shows preview, no changes |
| `test_heal_apply_not_found` | Error for invalid fix ID |
| `test_heal_apply_force` | Bypasses safety, shows warning |
| `test_heal_ignore_valid` | Ignores pattern with reason |
| `test_heal_ignore_missing_reason` | Error without reason |
| `test_heal_unquarantine_valid` | Resets quarantined pattern |
| `test_heal_explain_valid` | Shows reasons for non-auto-apply |
| `test_heal_explain_not_found` | Error for unknown pattern |
| `test_heal_export_yaml` | Exports YAML to stdout |
| `test_heal_export_json` | Exports JSON to stdout |
| `test_heal_export_file` | Exports to file |
| `test_heal_backfill_explicit` | Processes logs with cost limit |
| `test_heal_backfill_empty` | Returns 0 for empty directory |
| `test_heal_backfill_invalid_logs` | Skips invalid lines |

## 16. CLI Issues Commands (`test_cli_issues.py`)

| Test Case | Description |
|-----------|-------------|
| `test_issues_list_all` | Lists all issues in table |
| `test_issues_list_by_status` | Filters by status |
| `test_issues_list_by_severity` | Filters by severity |
| `test_issues_list_limit` | Respects limit |
| `test_issues_list_empty` | Shows message for no issues |
| `test_issues_review_with_fixes` | Applies selected fixes |
| `test_issues_review_skip_all` | No changes when all skipped |
| `test_issues_review_empty` | Shows message for empty queue |
| `test_issues_review_partial` | Applies some, skips others |
| `test_issues_review_apply_error` | Handles apply failure |

## 17. Workflow Hooks Integration (`test_hooks_integration.py`)

| Test Case | Description |
|-----------|-------------|
| `test_on_phase_complete_detects_errors` | Errors accumulated from phase |
| `test_on_phase_complete_no_errors` | No errors when clean |
| `test_on_subprocess_complete_failure` | Captures subprocess errors |
| `test_on_subprocess_complete_success` | Ignores successful commands |
| `test_on_workflow_complete_summary` | Displays summary with suggestions |
| `test_on_workflow_complete_no_errors` | No summary when clean |
| `test_on_learn_phase_patterns` | Extracts patterns from learnings |
| `test_hooks_disabled` | No-op when hooks disabled |
| `test_hooks_exception_handling` | Failures don't stop workflow |
| `test_hooks_concurrent` | Handles concurrent hook calls |
| `test_hooks_accumulator_dedup` | Deduplicates across hooks |
| `test_hooks_workflow_id_context` | Workflow ID passed to all hooks |

---

# Phase 5 Test Cases

## Test Files

```
tests/healing/
├── test_metrics.py           # 10 tests
├── test_circuit_breaker.py   # 15 tests
├── test_flakiness.py         # 10 tests
├── test_backfill.py          # 10 tests
└── test_cache_optimizer.py   # 8 tests
```

**Total: 53 new Phase 5 tests**

## 18. Metrics Collection (`test_metrics.py`)

| Test Case | Description |
|-----------|-------------|
| `test_get_dashboard_data` | Returns all metrics |
| `test_get_dashboard_empty_history` | Zero values, no errors |
| `test_calc_detection_rate` | Errors detected / total failures |
| `test_calc_auto_fix_rate` | Auto-applied / detected |
| `test_calc_success_rate` | Successful / applied |
| `test_get_cost_history` | Daily cost over time |
| `test_get_pattern_growth` | New patterns over time |
| `test_get_top_errors` | Most frequent patterns |
| `test_metrics_date_range` | Respects days parameter |
| `test_metrics_project_filter` | Filters by project_id |

## 19. Circuit Breaker (`test_circuit_breaker.py`)

| Test Case | Description |
|-----------|-------------|
| `test_initial_state_closed` | Starts in closed state |
| `test_should_allow_fix_closed` | Allows fixes when closed |
| `test_record_revert` | Records revert event |
| `test_trip_on_threshold` | Trips after 2 reverts/hour |
| `test_no_trip_below_threshold` | No trip for 1 revert |
| `test_should_not_allow_fix_open` | Blocks fixes when open |
| `test_cooldown_period` | Remains open during cooldown |
| `test_half_open_after_cooldown` | Allows test fix after cooldown |
| `test_close_on_success` | Closes on successful test fix |
| `test_reopen_on_failure` | Reopens on failed test fix |
| `test_state_persistence_save` | Saves state to Supabase |
| `test_state_persistence_load` | Loads state from Supabase |
| `test_state_persistence_resume` | State survives restart |
| `test_old_reverts_expire` | Reverts older than 1 hour don't count |
| `test_manual_reset` | Manual reset to closed |

## 20. Flakiness Detection (`test_flakiness.py`)

| Test Case | Description |
|-----------|-------------|
| `test_is_flaky_deterministic` | Consistent timing → False |
| `test_is_flaky_intermittent` | High variance timing → True |
| `test_is_flaky_insufficient_data` | <3 occurrences → False |
| `test_determinism_score_high` | Low variance → high score |
| `test_determinism_score_low` | High variance → low score |
| `test_determinism_score_no_data` | Returns 1.0 (assume deterministic) |
| `test_get_occurrences` | Retrieves occurrence timestamps |
| `test_get_occurrences_window` | Respects window parameter |
| `test_variance_calculation` | Correct variance formula |
| `test_flaky_pattern_flagged` | Flaky patterns marked |

## 21. Historical Backfill (`test_backfill.py`)

| Test Case | Description |
|-----------|-------------|
| `test_backfill_workflow_logs` | Processes .workflow_log.jsonl |
| `test_backfill_empty_directory` | Returns 0 for empty dir |
| `test_backfill_invalid_format` | Skips invalid lines |
| `test_backfill_respects_cost_limit` | Stops at daily limit |
| `test_backfill_returns_count` | Returns processed count |
| `test_backfill_deduplicates` | No duplicate patterns |
| `test_backfill_records_historical` | Marks as historical |
| `test_backfill_multiple_logs` | Processes multiple files |
| `test_backfill_glob_pattern` | Respects glob pattern |
| `test_backfill_dry_run` | Shows count without processing |

## 22. Cache Optimizer (`test_cache_optimizer.py`)

| Test Case | Description |
|-----------|-------------|
| `test_warm_cache_local` | Loads top 100 patterns |
| `test_warm_cache_cloud` | Returns 0 in cloud |
| `test_cache_hit_after_warm` | Lookup returns from cache |
| `test_warm_cache_empty` | Handles no patterns |
| `test_warm_cache_respects_limit` | Only top 100 |
| `test_warm_cache_ttl` | Sets 24-hour TTL |
| `test_cache_invalidation` | Respects TTL expiry |
| `test_warm_cache_error_handling` | Continues on errors |

---

## Integration Test Summary

| Phase | Test Files | Test Count |
|-------|------------|------------|
| Phase 2 | 7 files | ~50 tests |
| Phase 3 | 7 files | 99 tests |
| Phase 4 | 3 files | 40 tests |
| Phase 5 | 5 files | 53 tests |
| **Total** | **22 files** | **~242 tests** |

## Coverage Target

- Line coverage: 90%+
- Branch coverage: 85%+
- All edge cases covered
- All error paths tested
