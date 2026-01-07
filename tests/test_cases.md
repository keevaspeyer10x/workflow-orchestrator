# Test Cases: Roadmap Items Implementation

## CORE-012: OpenRouter Streaming Support

### Unit Tests (`tests/test_openrouter_streaming.py`)

1. **test_execute_streaming_yields_chunks**
   - Mock streaming response with multiple chunks
   - Verify each chunk is yielded in order
   - Verify final ExecutionResult contains complete text

2. **test_execute_streaming_handles_interruption**
   - Mock connection interruption mid-stream
   - Verify partial content is returned
   - Verify error is logged

3. **test_streaming_disabled_with_tools**
   - Request streaming with tools enabled
   - Verify falls back to non-streaming execution
   - Verify warning is logged

4. **test_stream_flag_in_cli**
   - Call handoff with --stream flag
   - Verify streaming execution is triggered

## VV-001: Auto-load Style Guide

### Unit Tests (`tests/test_visual_verification.py`)

1. **test_auto_load_style_guide_on_init**
   - Create client with style_guide_path
   - Verify style guide content is loaded

2. **test_verify_includes_style_guide_automatically**
   - Mock verify endpoint
   - Verify specification includes style guide content

3. **test_verify_without_style_guide_when_disabled**
   - Set include_style_guide=False
   - Verify specification does NOT include style guide

4. **test_missing_style_guide_logs_warning**
   - Provide non-existent path
   - Verify warning logged, no error raised

## VV-002: Workflow Step Integration

### Integration Tests

1. **test_run_all_visual_tests_finds_test_files**
   - Create test files in tests/visual/
   - Call run_all_visual_tests()
   - Verify all files are discovered

2. **test_visual_tests_respect_app_url_setting**
   - Configure app_url in workflow settings
   - Verify tests use configured URL

## VV-003: Visual Test Discovery

### Unit Tests

1. **test_discover_visual_tests_finds_markdown_files**
   - Create test files with YAML frontmatter
   - Verify all are discovered

2. **test_parse_test_file_extracts_metadata**
   - Parse file with url, viewport, tags
   - Verify all fields extracted correctly

3. **test_filter_tests_by_tag**
   - Create tests with different tags
   - Filter by specific tag
   - Verify only matching tests returned

### CLI Tests

4. **test_visual_verify_all_command**
   - Run `orchestrator visual-verify-all`
   - Verify all tests executed
   - Verify summary output

## VV-004: Baseline Screenshot Management

### Unit Tests

1. **test_save_baseline_creates_file**
   - Run verification with --save-baseline
   - Verify baseline saved to correct path

2. **test_compare_with_baseline_detects_differences**
   - Save baseline, modify page, run comparison
   - Verify difference detected

3. **test_baseline_directory_created_if_missing**
   - Delete baselines directory
   - Save baseline
   - Verify directory created

## VV-006: Cost Tracking

### Unit Tests

1. **test_cost_tracker_accumulates_costs**
   - Log multiple verification costs
   - Verify total is correct

2. **test_show_cost_flag_displays_costs**
   - Run verification with --show-cost
   - Verify cost information displayed

3. **test_costs_logged_to_file**
   - Run verifications
   - Verify costs written to .visual_verification_costs.json

## WF-003: Model Selection Guidance

### Unit Tests (`tests/test_model_registry.py` additions)

1. **test_get_latest_model_codex_category**
   - Call get_latest_model('codex')
   - Verify returns latest OpenAI model

2. **test_get_latest_model_gemini_category**
   - Call get_latest_model('gemini')
   - Verify returns latest Gemini model

3. **test_get_latest_model_fallback_on_error**
   - Mock registry unavailable
   - Verify returns hardcoded fallback

## Changelog Automation

### Unit Tests (`tests/test_changelog_automation.py`)

1. **test_parse_completed_roadmap_items**
   - Parse ROADMAP.md with completed items
   - Verify correct items extracted

2. **test_append_to_changelog**
   - Append completed items
   - Verify correct format in CHANGELOG.md

3. **test_remove_completed_from_roadmap**
   - Remove completed items
   - Verify ROADMAP.md updated correctly
   - Verify backup created

4. **test_workflow_item_prompts_for_changelog**
   - Run LEARN phase update_changelog_roadmap item
   - Verify user prompted to update changelog
