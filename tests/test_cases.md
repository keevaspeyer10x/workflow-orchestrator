# V4.2 Phase 4: Chat Mode Test Cases

## Test Structure

```
tests/v4/chat/
├── __init__.py
├── test_models.py       # 6 tests
├── test_validator.py    # 7 tests
├── test_context.py      # 8 tests
├── test_commands.py     # 6 tests
└── test_session.py      # 8 tests
```

**Total: 35 test cases**

---

## test_models.py (6 tests)

### TestMessage
1. **test_message_creation** - Create Message with all fields
2. **test_message_role_enum** - MessageRole.USER, ASSISTANT, SYSTEM
3. **test_message_to_dict** - Serialize message to dict for LLM

### TestChatEvent
4. **test_message_added_event** - Create MESSAGE_ADDED event
5. **test_checkpoint_created_event** - Create CHECKPOINT_CREATED event
6. **test_session_restored_event** - Create SESSION_RESTORED event

---

## test_validator.py (7 tests)

### TestEntityExtraction
1. **test_extract_file_paths** - `/path/to/file.py`, `./relative/path`
2. **test_extract_function_names** - `function_name()`, `Class.method()`
3. **test_extract_urls** - `https://example.com`, `http://api.test`
4. **test_extract_decision_keywords** - "decided", "chose", "approved"

### TestValidation
5. **test_validate_summary_success** - Summary contains all entities
6. **test_validate_summary_missing_entity** - Summary missing file path
7. **test_validate_summary_missing_decision** - Summary missing decision

---

## test_context.py (8 tests)

### TestSafeContextManager
1. **test_no_summarization_below_threshold** - Under 70% returns as-is
2. **test_summarization_triggered_above_threshold** - Over 70% triggers summarization
3. **test_pinned_messages_preserved** - Pinned IDs never summarized
4. **test_recent_messages_preserved** - Last 20 always kept
5. **test_validation_failure_fallback** - Invalid summary → truncation
6. **test_summary_message_created** - Summary becomes SYSTEM message
7. **test_token_count_after_summarization** - Context reduced below threshold
8. **test_empty_message_list** - Empty list returns empty list

---

## test_commands.py (6 tests)

### TestMetaCommandParser
1. **test_parse_status_command** - `/status` → StatusCommand
2. **test_parse_checkpoint_command** - `/checkpoint` → CheckpointCommand
3. **test_parse_restore_command** - `/restore cp_123` → RestoreCommand
4. **test_parse_pin_command** - `/pin msg_456` → PinCommand
5. **test_parse_history_command** - `/history 10` → HistoryCommand
6. **test_non_command_returns_none** - `Hello` → None (not a command)

---

## test_session.py (8 tests)

### TestChatSession
1. **test_send_message** - Send and receive response
2. **test_message_persistence** - Messages saved to EventStore
3. **test_auto_checkpoint** - Checkpoint created after 20 messages
4. **test_restore_checkpoint** - Restore session from checkpoint
5. **test_crash_recovery** - Restart and replay events
6. **test_budget_enforcement** - Budget exhausted → graceful error
7. **test_meta_command_execution** - `/status` returns session info
8. **test_pinned_message_survives_summarization** - Pin → summarize → still present

---

## Integration Tests (in test_session.py)

### TestIntegration
9. **test_full_session_lifecycle** - Create → chat → checkpoint → restore → verify

---

## Test Fixtures

```python
@pytest.fixture
def event_store():
    """In-memory event store for testing."""
    return SQLiteAsyncEventStore(":memory:")

@pytest.fixture
def checkpoint_store(event_store):
    """Checkpoint store using same adapter."""
    return CheckpointStore(event_store._adapter)

@pytest.fixture
def token_counter():
    """Estimation-based token counter."""
    return EstimationTokenCounter()

@pytest.fixture
def budget_tracker():
    """Budget tracker with 100k token limit."""
    tracker = AtomicBudgetTracker(":memory:")
    return tracker

@pytest.fixture
def mock_llm_wrapper():
    """Mock LLM wrapper for testing."""
    wrapper = MagicMock(spec=LLMCallWrapper)
    wrapper.call = AsyncMock(return_value=LLMResponse(
        content="Mock response",
        usage=TokenUsage(input_tokens=100, output_tokens=50),
        model="test-model",
        finish_reason="stop",
    ))
    return wrapper
```

## Test Tags

- `@pytest.mark.unit` - Unit tests (fast, no I/O)
- `@pytest.mark.integration` - Integration tests (with EventStore)
- `@pytest.mark.slow` - Slow tests (>1s)
