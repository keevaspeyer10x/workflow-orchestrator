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
