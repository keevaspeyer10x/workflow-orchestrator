# CORE-026: Review Failure Resilience & API Key Recovery

## Problem Statement
Reviews fail silently after context compaction loses API keys. During CORE-023, only 1 of 4 required reviews ran, and the workflow completed with incomplete coverage. Reviews must fail loudly, guide recovery, and block completion without all required reviews.

## Design Decisions (from 5-model consensus)
1. **Proactive key validation** before running reviews (not just reactive)
2. **Typed error classification** to distinguish auth errors from rate limits/network issues
3. **Required reviews in workflow.yaml** (not hardcoded) - "workflows in yaml not code"
4. **Idempotent retry mechanism** with exponential backoff
5. **Clear recovery guidance** with specific reload instructions

## Implementation Plan

### Phase 1: Workflow-Defined Required Reviews
**Files:** `src/workflow_schema.py`, `src/engine.py`, `workflow.yaml`, `orchestrator-meta.yaml`

- Add `required_reviews` field to workflow schema (list of review type names)
- Update `WorkflowEngine.validate_reviews_completed()` to read from workflow definition
- Remove hardcoded `{"security", "quality"}` from engine.py:1549
- Add `required_reviews` to default_workflow.yaml and orchestrator-meta.yaml

```yaml
# In workflow.yaml REVIEW phase
phases:
  - id: REVIEW
    required_reviews:  # NEW FIELD
      - security
      - quality
      - consistency
      - holistic
      - vibe_coding
```

### Phase 2: Error Classification
**Files:** `src/review/result.py`, `src/review/api_executor.py`, `src/review/cli_executor.py`

- Create `ReviewErrorType` enum:
  ```python
  class ReviewErrorType(Enum):
      NONE = "none"              # No error
      KEY_MISSING = "key_missing"        # API key not found
      KEY_INVALID = "key_invalid"        # API returned 401/403
      RATE_LIMITED = "rate_limited"      # API returned 429
      NETWORK_ERROR = "network_error"    # Connection failed
      TIMEOUT = "timeout"                # Review exceeded timeout
      PARSE_ERROR = "parse_error"        # Output couldn't be parsed
      REVIEW_FAILED = "review_failed"    # Review ran but found blocking issues
  ```

- Add `error_type: ReviewErrorType` field to `ReviewResult`
- Update `APIExecutor.execute()` to classify HTTP errors (401→KEY_INVALID, 429→RATE_LIMITED)
- Update `CLIExecutor.execute()` to classify subprocess errors (FileNotFound→KEY_MISSING for missing CLI)

### Phase 3: Proactive Key Validation
**Files:** `src/review/router.py`, `src/cli.py`

- Add `validate_api_keys()` function:
  ```python
  def validate_api_keys(required_models: list[str]) -> tuple[bool, dict[str, str]]:
      """Validate API keys are available and valid.

      Returns:
          (all_valid, {model: error_message})
      """
      errors = {}
      for model in required_models:
          key_name = MODEL_TO_KEY[model]  # e.g., "gemini" -> "GEMINI_API_KEY"
          key = os.environ.get(key_name)
          if not key:
              errors[model] = f"{key_name} not set"
              continue
          # Lightweight ping (e.g., list models endpoint)
          if not ping_api(model, key):
              errors[model] = f"{key_name} invalid or expired"
      return len(errors) == 0, errors
  ```

- In `cmd_complete()`, before running review:
  ```python
  # Validate key for this review type
  model = get_model_for_review(review_type)
  valid, errors = validate_api_keys([model])
  if not valid:
      print(f"ERROR: API key validation failed for {review_type}")
      print(f"  {errors[model]}")
      print(RECOVERY_INSTRUCTIONS[model])
      sys.exit(1)
  ```

### Phase 4: Recovery Guidance
**Files:** `src/review/recovery.py` (new), `src/cli.py`

- Create recovery instruction templates:
  ```python
  RECOVERY_INSTRUCTIONS = {
      "gemini": """
  To reload Gemini API key:
    1. Using SOPS: eval "$(sops -d secrets.enc.yaml | sed 's/: /=/' | sed 's/^/export /')"
    2. Or set directly: export GEMINI_API_KEY="your-key"
    3. Then retry: orchestrator review retry
  """,
      "openai": "...",
      "grok": "...",
  }
  ```

- Include recovery instructions in error output
- Add `orchestrator review retry` hint in all key-related errors

### Phase 5: Retry Command
**Files:** `src/cli.py`

- Add `orchestrator review retry` command:
  ```python
  def cmd_review_retry(args):
      """Retry failed reviews after key recovery."""
      engine = get_engine()
      failed_reviews = engine.get_failed_reviews()  # From workflow events

      if not failed_reviews:
          print("No failed reviews to retry")
          return

      for review_type in failed_reviews:
          print(f"Retrying {review_type}...")
          # Validate key first
          valid, errors = validate_api_keys([get_model_for_review(review_type)])
          if not valid:
              print(f"  Still failing: {errors}")
              continue
          # Re-run review
          success = run_auto_review(review_type, working_dir)
          if success:
              engine.log_event(REVIEW_COMPLETED, review_type)
          else:
              print(f"  Review still failed")
  ```

- Track retry count per review (max 3 attempts)
- Exponential backoff: 1s, 5s, 30s between retries

### Phase 6: Finish Verification
**Files:** `src/cli.py`, `src/engine.py`

- Update `cmd_finish()`:
  ```python
  # Get required reviews from workflow definition
  required = engine.get_required_reviews()  # From workflow.yaml
  completed = engine.get_completed_reviews()
  missing = required - completed

  if missing:
      print("ERROR: Required reviews not completed:")
      for r in missing:
          print(f"  - {r}")
      print("\nOptions:")
      print("  1. Run missing reviews: orchestrator complete {review}_review")
      print("  2. Retry failed reviews: orchestrator review retry")
      print("  3. Skip (with reason): orchestrator finish --skip-review-check --reason '...'")
      sys.exit(1)
  ```

- Add review completion summary to finish output

## Files Modified

| File | Changes |
|------|---------|
| `src/workflow_schema.py` | Add `required_reviews` field |
| `src/engine.py` | `get_required_reviews()`, update `validate_reviews_completed()` |
| `src/review/result.py` | Add `ReviewErrorType` enum, `error_type` field |
| `src/review/router.py` | Add `validate_api_keys()` |
| `src/review/api_executor.py` | Classify HTTP errors by type |
| `src/review/cli_executor.py` | Classify subprocess errors by type |
| `src/review/recovery.py` | NEW - Recovery instruction templates |
| `src/cli.py` | Update `cmd_complete`, `cmd_finish`, add `cmd_review_retry` |
| `workflow.yaml` | Add `required_reviews` to REVIEW phase |
| `orchestrator-meta.yaml` | Add `required_reviews` to REVIEW phase |
| `src/default_workflow.yaml` | Add `required_reviews` to REVIEW phase |

## Test Cases

1. **Key validation fails** - `validate_api_keys()` returns errors for missing keys
2. **Error classification** - HTTP 401 → KEY_INVALID, 429 → RATE_LIMITED, etc.
3. **Proactive check blocks review** - Missing key prevents review from starting
4. **Recovery instructions shown** - Error output includes reload instructions
5. **Retry command works** - Failed reviews can be retried after key reload
6. **Finish validates required** - Missing required reviews block finish
7. **Workflow.yaml required_reviews** - Engine reads required reviews from definition
8. **Skip escape hatch** - `--skip-review-check --reason` still works

## Risks

| Risk | Mitigation |
|------|------------|
| API ping adds latency | Use lightweight endpoint (list models), timeout 5s |
| False positives on validation | Only check key presence + format, not full auth |
| Breaking existing workflows | `required_reviews` defaults to empty (backward compat) |
| Over-blocking users | Keep `--skip-review-check` escape hatch |

## Success Criteria
- [ ] Reviews that fail due to missing keys show specific error + recovery instructions
- [ ] `orchestrator finish` blocks if required reviews (from workflow.yaml) not completed
- [ ] `orchestrator review retry` command exists and works
- [ ] Proactive key validation catches missing keys before review attempt
- [ ] Error types are classified (not just generic "failed")
