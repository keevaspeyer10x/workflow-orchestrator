# Test Cases: OpenRouter Function Calling for Interactive Repo Context

## Unit Tests

### Tool Definition Tests

#### TC-TOOL-001: Read File Tool Schema
**Component:** `src/providers/tools.py`
**Description:** READ_FILE_TOOL has correct OpenAI function schema
**Expected:** Schema has name, description, parameters with required "path"
**Priority:** High

#### TC-TOOL-002: List Files Tool Schema
**Component:** `src/providers/tools.py`
**Description:** LIST_FILES_TOOL has correct schema
**Expected:** Schema has "pattern" parameter for glob matching
**Priority:** High

#### TC-TOOL-003: Search Code Tool Schema
**Component:** `src/providers/tools.py`
**Description:** SEARCH_CODE_TOOL has correct schema
**Expected:** Schema has "pattern" (required) and "path" (optional) parameters
**Priority:** High

### Tool Execution Tests

#### TC-EXEC-001: Read File - Basic
**Component:** `src/providers/tools.py`
**Description:** Read a normal file successfully
**Setup:** Create temp file with known content
**Input:** `execute_read_file("test.txt", working_dir)`
**Expected:** Returns {"content": "<file content>", "size": <bytes>}
**Priority:** High

#### TC-EXEC-002: Read File - Path Traversal Blocked
**Component:** `src/providers/tools.py`
**Description:** Blocks attempts to read outside working_dir
**Input:** `execute_read_file("../../etc/passwd", working_dir)`
**Expected:** Returns {"error": "Path outside working directory"}
**Priority:** High

#### TC-EXEC-003: Read File - Nonexistent
**Component:** `src/providers/tools.py`
**Description:** Handles missing file gracefully
**Input:** `execute_read_file("nonexistent.txt", working_dir)`
**Expected:** Returns {"error": "File not found", "path": "nonexistent.txt"}
**Priority:** High

#### TC-EXEC-004: Read File - Large File Warning
**Component:** `src/providers/tools.py`
**Description:** Logs warning for files >2MB
**Setup:** Create 3MB temp file
**Input:** `execute_read_file("large.bin", working_dir)`
**Expected:** Returns content, logs warning about large file
**Priority:** Medium

#### TC-EXEC-005: Read File - Very Large File Truncated
**Component:** `src/providers/tools.py`
**Description:** Truncates files >50MB with message
**Setup:** Create 60MB temp file (or mock)
**Input:** `execute_read_file("huge.bin", working_dir)`
**Expected:** Returns {"content": "(file too large...)", "truncated": true}
**Priority:** Medium

#### TC-EXEC-006: Read File - Binary Detection
**Component:** `src/providers/tools.py`
**Description:** Handles binary files appropriately
**Setup:** Create file with binary content
**Input:** `execute_read_file("image.png", working_dir)`
**Expected:** Returns {"error": "Binary file"} or base64 encoded
**Priority:** Medium

#### TC-EXEC-007: List Files - Basic Glob
**Component:** `src/providers/tools.py`
**Description:** Lists files matching glob pattern
**Setup:** Create files: a.py, b.py, c.txt
**Input:** `execute_list_files("*.py", working_dir)`
**Expected:** Returns {"files": ["a.py", "b.py"]}
**Priority:** High

#### TC-EXEC-008: List Files - Recursive Glob
**Component:** `src/providers/tools.py`
**Description:** Supports ** for recursive matching
**Setup:** Create nested directory with files
**Input:** `execute_list_files("**/*.py", working_dir)`
**Expected:** Returns all .py files in all subdirectories
**Priority:** High

#### TC-EXEC-009: List Files - No Matches
**Component:** `src/providers/tools.py`
**Description:** Returns empty list when no matches
**Input:** `execute_list_files("*.xyz", working_dir)`
**Expected:** Returns {"files": []}
**Priority:** Medium

#### TC-EXEC-010: Search Code - Basic Pattern
**Component:** `src/providers/tools.py`
**Description:** Finds lines matching regex pattern
**Setup:** Create file with "def foo():" and "def bar():"
**Input:** `execute_search_code("def \\w+", working_dir)`
**Expected:** Returns matches with file paths and line numbers
**Priority:** High

#### TC-EXEC-011: Search Code - Path Filter
**Component:** `src/providers/tools.py`
**Description:** Limits search to specific path
**Setup:** Create test.py and other.py with same content
**Input:** `execute_search_code("pattern", working_dir, path="test.py")`
**Expected:** Only returns matches from test.py
**Priority:** High

#### TC-EXEC-012: Search Code - No Matches
**Component:** `src/providers/tools.py`
**Description:** Returns empty when no matches
**Input:** `execute_search_code("nonexistent_xyz_123", working_dir)`
**Expected:** Returns {"matches": []}
**Priority:** Medium

### Model Detection Tests

#### TC-MODEL-001: GPT-4 Supports Function Calling
**Component:** `src/providers/openrouter.py`
**Description:** Correctly identifies GPT-4+ as function-calling capable
**Input:** `_supports_function_calling("openai/gpt-4")`
**Expected:** Returns True
**Priority:** High

#### TC-MODEL-002: Claude Supports Function Calling
**Component:** `src/providers/openrouter.py`
**Description:** Correctly identifies Claude 3+ as function-calling capable
**Input:** `_supports_function_calling("anthropic/claude-3-opus")`
**Expected:** Returns True
**Priority:** High

#### TC-MODEL-003: Gemini Supports Function Calling
**Component:** `src/providers/openrouter.py`
**Description:** Correctly identifies Gemini Pro as function-calling capable
**Input:** `_supports_function_calling("google/gemini-pro")`
**Expected:** Returns True
**Priority:** High

#### TC-MODEL-004: Unknown Model Defaults Safe
**Component:** `src/providers/openrouter.py`
**Description:** Unknown models fall back gracefully
**Input:** `_supports_function_calling("some/unknown-model")`
**Expected:** Returns False (conservative default)
**Priority:** Medium

### Execute With Tools Tests

#### TC-EWT-001: Basic Tool Loop
**Component:** `src/providers/openrouter.py`
**Description:** Executes tools and returns final response
**Setup:** Mock API to return tool call then final response
**Input:** `execute_with_tools("Read file.txt and summarize", model)`
**Expected:** Tool executed, final response returned
**Priority:** High

#### TC-EWT-002: Multiple Tool Calls
**Component:** `src/providers/openrouter.py`
**Description:** Handles multiple sequential tool calls
**Setup:** Mock API to return 3 tool calls then final response
**Input:** `execute_with_tools("complex task", model)`
**Expected:** All 3 tools executed, final response returned
**Priority:** High

#### TC-EWT-003: Tool Call Warning at 50
**Component:** `src/providers/openrouter.py`
**Description:** Logs warning after 50 tool calls
**Setup:** Mock API to return 51 tool calls
**Input:** `execute_with_tools("intensive task", model)`
**Expected:** Warning logged, execution continues
**Priority:** Medium

#### TC-EWT-004: Hard Limit at 200 Calls
**Component:** `src/providers/openrouter.py`
**Description:** Stops execution at 200 tool calls
**Setup:** Mock API to return infinite tool calls
**Input:** `execute_with_tools("runaway task", model)`
**Expected:** Returns error after 200 calls
**Priority:** High

#### TC-EWT-005: Tool Error Handling
**Component:** `src/providers/openrouter.py`
**Description:** Handles tool execution errors gracefully
**Setup:** Mock tool to raise exception
**Input:** `execute_with_tools("task with error", model)`
**Expected:** Error returned to model, execution continues
**Priority:** High

### Auto-Detection Tests

#### TC-AUTO-001: Execute Uses Tools When Supported
**Component:** `src/providers/openrouter.py`
**Description:** execute() auto-detects and uses tools
**Setup:** Mock GPT-4 model
**Input:** `execute("task", "openai/gpt-4")`
**Expected:** Internally calls execute_with_tools()
**Priority:** High

#### TC-AUTO-002: Execute Falls Back When Not Supported
**Component:** `src/providers/openrouter.py`
**Description:** execute() falls back for non-tool models
**Setup:** Mock basic model
**Input:** `execute("task", "basic/model")`
**Expected:** Uses basic execution path
**Priority:** High

#### TC-AUTO-003: Execute Falls Back on Tool Error
**Component:** `src/providers/openrouter.py`
**Description:** Falls back if tool setup fails
**Setup:** Mock tool initialization to fail
**Input:** `execute("task", "openai/gpt-4")`
**Expected:** Graceful fallback to basic execution
**Priority:** Medium

## Integration Tests

### TC-INT-001: Real API - Read File
**Description:** End-to-end test with real OpenRouter API
**Setup:** Set OPENROUTER_API_KEY, create test file
**Input:** Execute task that requires reading a file
**Expected:** Model reads file via tool, provides correct response
**Priority:** High
**Note:** Mark as `@pytest.mark.integration`

### TC-INT-002: Real API - Search and Read
**Description:** Model searches then reads files
**Setup:** Create codebase with known patterns
**Input:** "Find all functions that return int and explain them"
**Expected:** Model uses search_code, then read_file, provides summary
**Priority:** Medium
**Note:** Mark as `@pytest.mark.integration`

### TC-INT-003: Fallback Path Works
**Description:** Basic model works without tools
**Setup:** Use model known to not support tools
**Input:** Execute simple task
**Expected:** Completes using context injection fallback
**Priority:** High

## Backwards Compatibility Tests

### TC-BC-001: Existing Execute Signature Unchanged
**Component:** `src/providers/openrouter.py`
**Description:** execute(prompt, model) still works
**Input:** `provider.execute("task", "model")`
**Expected:** No signature change errors
**Priority:** High

### TC-BC-002: ExecutionResult Format Unchanged
**Component:** `src/providers/base.py`
**Description:** ExecutionResult has same fields
**Input:** Check result from execute()
**Expected:** Has success, output, error, model_used, etc.
**Priority:** High

### TC-BC-003: Provider Interface Unchanged
**Component:** `src/providers/base.py`
**Description:** AgentProvider interface not broken
**Input:** Check ManualProvider still works
**Expected:** No changes required to other providers
**Priority:** High

## Error Handling Tests

### TC-ERR-001: API Timeout
**Component:** `src/providers/openrouter.py`
**Description:** Handles API timeout during tool loop
**Setup:** Mock API to timeout
**Expected:** Returns error, no crash
**Priority:** Medium

### TC-ERR-002: Invalid Tool Call Format
**Component:** `src/providers/openrouter.py`
**Description:** Handles malformed tool call from API
**Setup:** Mock API to return invalid tool call structure
**Expected:** Logs error, continues or falls back gracefully
**Priority:** Medium

### TC-ERR-003: Rate Limiting
**Component:** `src/providers/openrouter.py`
**Description:** Handles 429 during tool loop
**Setup:** Mock API to return 429
**Expected:** Retries with backoff or returns error
**Priority:** Medium

## Coverage Requirements

- Minimum 90% coverage for `src/providers/tools.py`
- Minimum 85% coverage for new code in `src/providers/openrouter.py`
- All path traversal cases must be tested
- All error paths must have tests
- Integration tests marked with `@pytest.mark.integration`
