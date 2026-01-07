# Test Cases: CORE-006, SEC-004, CORE-017, CORE-018

## CORE-006: Automatic Connector Detection

### Unit Tests

1. **test_detect_manus_connector_with_env_var**
   - Set MANUS_API_URL env var
   - Call `detect_manus_connector()`
   - Assert returns True

2. **test_detect_manus_connector_without_env**
   - Clear MANUS_* env vars
   - Call `detect_manus_connector()`
   - Assert returns False

3. **test_get_available_providers_all_available**
   - Mock: claude CLI exists, OpenRouter key set
   - Call `get_available_providers()`
   - Assert returns ['claude_code', 'openrouter', 'manual']

4. **test_get_available_providers_only_manual**
   - Mock: no claude CLI, no API key
   - Call `get_available_providers()`
   - Assert returns ['manual']

5. **test_prompt_user_for_provider_returns_selection**
   - Mock user input selecting 'openrouter'
   - Call `prompt_user_for_provider(['openrouter', 'manual'])`
   - Assert returns 'openrouter'

### Integration Tests

6. **test_handoff_interactive_shows_options**
   - Run `orchestrator handoff --interactive`
   - Assert output shows available provider options

---

## SEC-004: Cross-Repo Secrets Copy

### Unit Tests

1. **test_secrets_copy_success**
   - Create source dir with .secrets.enc
   - Call `secrets copy /source /dest`
   - Assert file copied to dest

2. **test_secrets_copy_creates_dest_dir**
   - Source exists, dest dir doesn't exist
   - Call `secrets copy`
   - Assert dest dir created and file copied

3. **test_secrets_copy_source_not_found**
   - Source dir has no secrets file
   - Call `secrets copy`
   - Assert error message and exit code 1

4. **test_secrets_copy_dest_exists_no_force**
   - Both source and dest have secrets file
   - Call `secrets copy` without --force
   - Assert prompts for confirmation or fails

5. **test_secrets_copy_dest_exists_with_force**
   - Both files exist
   - Call `secrets copy --force`
   - Assert file overwritten

### CLI Tests

6. **test_secrets_copy_from_flag**
   - Run `orchestrator secrets copy --from /other/repo`
   - Assert copies from specified source

7. **test_secrets_copy_to_flag**
   - Run `orchestrator secrets copy --to /other/repo`
   - Assert copies to specified destination

---

## CORE-017: Auto-Update Review Models

### Unit Tests

1. **test_model_registry_create**
   - Call `ModelRegistry()`
   - Assert creates .model_registry.json if not exists

2. **test_is_registry_stale_fresh**
   - Set last_updated to today
   - Call `is_registry_stale()`
   - Assert returns False

3. **test_is_registry_stale_old**
   - Set last_updated to 31 days ago
   - Call `is_registry_stale()`
   - Assert returns True

4. **test_get_latest_models_api_success**
   - Mock OpenRouter API response with model list
   - Call `get_latest_models()`
   - Assert returns parsed model list

5. **test_get_latest_models_api_failure**
   - Mock API timeout
   - Call `get_latest_models()`
   - Assert returns None or cached values

6. **test_update_registry_saves_timestamp**
   - Call `update_registry()`
   - Assert last_updated is now

### CLI Tests

7. **test_update_models_command**
   - Run `orchestrator update-models`
   - Assert queries API and updates registry

8. **test_update_models_no_auto_update_flag**
   - Run `orchestrator update-models --no-auto-update`
   - Assert doesn't auto-update in background

---

## CORE-018: Dynamic Function Calling Detection

### Unit Tests

1. **test_get_model_capabilities_from_api**
   - Mock API response with capabilities
   - Call `get_model_capabilities('openai/gpt-4')`
   - Assert returns correct capabilities dict

2. **test_get_model_capabilities_cached**
   - Pre-populate cache
   - Call `get_model_capabilities()`
   - Assert returns cached value without API call

3. **test_supports_function_calling_true**
   - Model with function calling support
   - Call `supports_function_calling('openai/gpt-4')`
   - Assert returns True

4. **test_supports_function_calling_false**
   - Model without support
   - Call `supports_function_calling('some/basic-model')`
   - Assert returns False

5. **test_supports_function_calling_fallback_to_static**
   - API unavailable, model in static list
   - Call `supports_function_calling('openai/gpt-4')`
   - Assert returns True (from static list)

### Integration Tests

6. **test_openrouter_uses_dynamic_detection**
   - Mock registry with capabilities
   - Create OpenRouterProvider
   - Assert `_supports_function_calling()` uses registry

---

## Test File Organization

```
tests/
  test_model_registry.py     # CORE-017, CORE-018 unit tests
  test_provider_detection.py # CORE-006 unit tests
  test_secrets_copy.py       # SEC-004 unit tests
  test_cli_new_commands.py   # CLI integration tests
```
