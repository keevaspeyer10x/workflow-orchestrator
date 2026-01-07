# Test Cases: Workflow Improvements WF-005 through WF-009

## WF-008: AI Critique at Phase Gates

### Unit Tests (`tests/test_critique.py`)

| ID | Test Name | Description | Expected Result |
|----|-----------|-------------|-----------------|
| C1 | test_critique_context_collection | Collect context from engine state | Dict with task, constraints, items, skipped |
| C2 | test_critique_context_truncation | Large context truncated to 8k tokens | Context ≤ 8000 chars |
| C3 | test_critique_prompt_plan_execute | Generate PLAN→EXECUTE prompt | Contains requirements focus |
| C4 | test_critique_prompt_execute_review | Generate EXECUTE→REVIEW prompt | Contains completion focus |
| C5 | test_critique_result_parsing | Parse review result into observations | CritiqueResult with observations list |
| C6 | test_critique_critical_detection | Detect critical issues | should_block = True |
| C7 | test_critique_no_critical | All warnings, no criticals | should_block = False |
| C8 | test_critique_api_failure_graceful | API throws exception | Returns None, logs warning |
| C9 | test_critique_timeout | API exceeds 30s timeout | TimeoutError caught, continue |
| C10 | test_critique_disabled | phase_critique: false in settings | Critique not called |

### Integration Tests

| ID | Test Name | Description | Expected Result |
|----|-----------|-------------|-----------------|
| C11 | test_advance_with_critique | Full advance flow with critique | Critique output shown before advance |
| C12 | test_advance_critique_blocking | Critical issue found | User prompted to continue/address |
| C13 | test_advance_no_critique_flag | --no-critique flag | Critique skipped, advance proceeds |
| C14 | test_advance_critique_failure | API failure during advance | Warning shown, advance continues |

---

## WF-005: Summary Before Approval Gates

### Unit Tests (`tests/test_summary.py`)

| ID | Test Name | Description | Expected Result |
|----|-----------|-------------|-----------------|
| S1 | test_summary_completed_items | Summarize completed items | Shows item IDs and notes |
| S2 | test_summary_skipped_items | Include skipped items | Shows skip reasons |
| S3 | test_summary_git_diff_stat | Include git diff stat | Shows files changed count |
| S4 | test_summary_empty_phase | No items completed | Shows "No items completed" |
| S5 | test_summary_format | Output formatting | Correct box drawing chars |
| S6 | test_format_duration | Duration formatting | "2h 15m" format |

### Integration Tests

| ID | Test Name | Description | Expected Result |
|----|-----------|-------------|-----------------|
| S7 | test_advance_shows_summary | Summary before advance | Summary printed before prompt |
| S8 | test_advance_yes_flag | --yes flag skips prompt | No interactive prompt |

---

## WF-009: Document Phase

### Integration Tests (`tests/test_document_phase.py`)

| ID | Test Name | Description | Expected Result |
|----|-----------|-------------|-----------------|
| D1 | test_workflow_has_document_phase | DOCUMENT phase in workflow | Phase exists after VERIFY |
| D2 | test_document_phase_items | Check required items | changelog_entry is required |
| D3 | test_skip_document_phase | Skip entire phase | Phase can be skipped |
| D4 | test_document_phase_optional_items | Optional items skippable | update_readme etc. optional |
| D5 | test_workflow_order | Phase ordering correct | PLAN→EXECUTE→REVIEW→VERIFY→DOCUMENT→LEARN |

---

## WF-006: File Links in Status Output

### Unit Tests (`tests/test_file_links.py`)

| ID | Test Name | Description | Expected Result |
|----|-----------|-------------|-----------------|
| F1 | test_item_state_files_field | ItemState has files_modified | Field exists, Optional[list] |
| F2 | test_complete_item_with_files | Pass files to complete_item | Files stored in state |
| F3 | test_complete_item_auto_detect | Auto-detect from git diff | Changed files captured |
| F4 | test_status_shows_files | Status output includes files | File paths displayed |
| F5 | test_status_no_files | No files tracked | No files section shown |
| F6 | test_files_flag_filter | --files flag controls display | Files shown/hidden |

### Schema Tests

| ID | Test Name | Description | Expected Result |
|----|-----------|-------------|-----------------|
| F7 | test_state_backward_compat | Load state without files_modified | Loads successfully, field = None |
| F8 | test_state_save_with_files | Save state with files | JSON includes files array |

---

## WF-007: Learnings to Roadmap Pipeline

### Unit Tests (`tests/test_learnings_pipeline.py`)

| ID | Test Name | Description | Expected Result |
|----|-----------|-------------|-----------------|
| L1 | test_pattern_should | Detect "should X" pattern | Extracts suggestion |
| L2 | test_pattern_next_time | Detect "next time X" pattern | Extracts suggestion |
| L3 | test_pattern_need_to | Detect "need to X" pattern | Extracts suggestion |
| L4 | test_no_patterns | No actionable patterns | Empty suggestions list |
| L5 | test_categorize_suggestion | Assign prefix (CORE-, WF-, etc) | Correct prefix assigned |
| L6 | test_format_roadmap_entry | Generate markdown entry | Valid roadmap format |
| L7 | test_multiple_learnings | Multiple learnings parsed | All suggestions extracted |
| L8 | test_duplicate_detection | Same suggestion twice | Deduplicated |

---

## Test Execution Commands

```bash
# Run all new tests
pytest tests/test_critique.py tests/test_summary.py tests/test_document_phase.py tests/test_file_links.py tests/test_learnings_pipeline.py -v

# Run with coverage
pytest tests/test_critique.py tests/test_summary.py tests/test_document_phase.py tests/test_file_links.py tests/test_learnings_pipeline.py --cov=src --cov-report=term-missing

# Run only unit tests (fast)
pytest tests/test_critique.py tests/test_summary.py tests/test_file_links.py tests/test_learnings_pipeline.py -v -k "not integration"
```

## Coverage Targets

| Module | Target | Reason |
|--------|--------|--------|
| src/critique.py | 90% | New core feature |
| src/cli.py (new code) | 85% | Critical user interface |
| src/schema.py (changes) | 100% | Must not break existing |
| src/engine.py (changes) | 85% | Core logic |
| src/learnings_pipeline.py | 80% | Pattern matching may have edge cases |

## Acceptance Criteria

1. All 46 tests pass
2. No regressions in existing tests
3. Coverage targets met
4. Manual verification: run full workflow with all features enabled
