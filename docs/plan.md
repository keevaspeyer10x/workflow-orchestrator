# V4.2 Phase 4: Chat Mode Implementation Plan

## Overview

Implement the Chat Mode system for interactive LLM-driven workflow execution with:
- Safe context management (summarization with validation)
- Session persistence via EventStore
- Crash recovery through event replay
- Meta-commands for session control

## Design Decisions (User-Approved)

1. **Summarization LLM**: Use same LLM configured for session via LLMCallWrapper
2. **Entity Extraction**: Regex-based patterns (deterministic, no LLM calls)
3. **Meta-commands**: /status, /checkpoint, /restore, /pin, /history
4. **Auto-checkpoint**: Every 20 messages or 10 minutes

## Module Structure

```
src/v4/chat/
├── __init__.py           # Module exports
├── models.py             # Message, MessageRole, ChatEvent, SessionConfig
├── validator.py          # SummaryValidator (regex-based entity extraction)
├── context.py            # SafeContextManager (summarization + validation)
├── commands.py           # MetaCommandHandler (parse and execute commands)
└── session.py            # ChatSession (persistence, checkpoint, recovery)

tests/v4/chat/
├── __init__.py
├── test_models.py
├── test_validator.py
├── test_context.py
├── test_commands.py
└── test_session.py
```

## Implementation Order (TDD)

### Phase 1: Models (Foundation)
1. `Message` dataclass - id, role, content, metadata, timestamp
2. `MessageRole` enum - USER, ASSISTANT, SYSTEM
3. `ChatEvent` types - MESSAGE_ADDED, CHECKPOINT_CREATED, SESSION_RESTORED
4. `SessionConfig` - max_tokens, summarization_threshold, checkpoint_interval

### Phase 2: Validator (Deterministic)
1. Entity extraction patterns:
   - File paths: `/path/to/file`, `./relative/path`
   - Function/method names: `function_name()`, `Class.method()`
   - Variable names: camelCase, snake_case identifiers
   - URLs: `http://`, `https://`
   - Decision keywords: "decided", "chose", "approved", "rejected"
2. `ValidationResult` with is_valid, missing_entities, missing_decisions
3. No LLM calls - pure regex matching

### Phase 3: Context Manager
1. Token counting via TokenCounter (Phase 2)
2. Summarization threshold (70% of max_tokens)
3. Pinned message preservation
4. Recent message preservation (last 20)
5. Fallback to truncation on validation failure
6. Uses LLMCallWrapper for summarization

### Phase 4: Commands
1. Parse meta-commands from user input
2. `/status` - Show session state, message count, budget
3. `/checkpoint` - Manual checkpoint creation
4. `/restore <id>` - Restore from checkpoint
5. `/pin <msg_id>` - Pin message (never summarized)
6. `/history [n]` - Show last n messages

### Phase 5: Session
1. Event persistence via SQLiteAsyncEventStore
2. Checkpoint management via CheckpointStore
3. Auto-checkpoint on interval
4. Crash recovery via event replay
5. Budget enforcement via AtomicBudgetTracker
6. LLM calls via LLMCallWrapper

## Integration Points

| Component | From Phase | Usage |
|-----------|------------|-------|
| SQLiteAsyncEventStore | Phase 1 | Chat event persistence |
| CheckpointStore | Phase 1 | Session checkpoints |
| TokenCounter | Phase 2 | Context window tracking |
| AtomicBudgetTracker | Phase 2 | Budget enforcement |
| LLMCallWrapper | Phase 3 | LLM calls with budget |
| LLMRequest/LLMResponse | Phase 3 | Request/response models |

## Execution Strategy

**Sequential execution** because:
- Components have linear dependencies (models → validator → context → commands → session)
- Each component builds on previous one
- TDD requires tests to pass before moving to next component
- Integration testing requires all components to exist

## Acceptance Criteria

- [ ] Chat sessions persist and restore correctly
- [ ] Meta-commands work (/status, /checkpoint, /restore, /pin, /history)
- [ ] Context summarization validated before use
- [ ] Checkpoint/restore tested with complex sessions
- [ ] Crash recovery works mid-conversation
- [ ] Pinned messages never lost during summarization
- [ ] Token budget enforced during chat
