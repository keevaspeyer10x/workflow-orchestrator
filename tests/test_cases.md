# Test Cases: Multi-Model Review Routing

## Unit Tests

### Context Collector Tests

#### TC-RC-001: Git Diff Extraction
**Component:** `src/review/context.py`
**Description:** Extracts git diff between main branch and HEAD
**Input:** Repository with uncommitted changes
**Expected:** Returns diff string with added/removed lines
**Priority:** High

#### TC-RC-002: Changed File Content Loading
**Component:** `src/review/context.py`
**Description:** Loads full content of files in git diff
**Input:** Diff showing 3 changed files
**Expected:** Dict with 3 entries, each containing file content
**Priority:** High

#### TC-RC-003: Related Files Detection (Python)
**Component:** `src/review/context.py`
**Description:** Parses Python imports to find related files
**Input:** File with `from src.engine import WorkflowEngine`
**Expected:** Includes `src/engine.py` in related_files
**Priority:** Medium

#### TC-RC-004: Architecture Doc Loading
**Component:** `src/review/context.py`
**Description:** Loads ARCHITECTURE.md when present
**Input:** Repository with docs/ARCHITECTURE.md
**Expected:** Returns architecture doc content
**Priority:** Medium

#### TC-RC-005: Context Size Limiting
**Component:** `src/review/context.py`
**Description:** Truncates context when exceeding limit
**Input:** Large codebase with 200KB of changes
**Expected:** Context truncated to configured limit with warning
**Priority:** High

#### TC-RC-006: No Git Repository Handling
**Component:** `src/review/context.py`
**Description:** Graceful error when not in git repo
**Input:** Directory without .git
**Expected:** Raises ReviewContextError with clear message
**Priority:** High

### Router Tests

#### TC-RR-001: Model Selection - Security Review
**Component:** `src/review/router.py`
**Description:** Routes security_review to Codex
**Input:** `item_id="security_review"`
**Expected:** Returns `"openai/gpt-5.2-codex"`
**Priority:** High

#### TC-RR-002: Model Selection - Architecture Review
**Component:** `src/review/router.py`
**Description:** Routes architecture_review to Gemini
**Input:** `item_id="architecture_review"`
**Expected:** Returns `"google/gemini-3-pro"`
**Priority:** High

#### TC-RR-003: Model Selection - Quality Review
**Component:** `src/review/router.py`
**Description:** Routes quality_review to Codex
**Input:** `item_id="quality_review"`
**Expected:** Returns `"openai/gpt-5.2-codex"`
**Priority:** High

#### TC-RR-004: Fallback Model Selection
**Component:** `src/review/router.py`
**Description:** Uses fallback for unknown items
**Input:** `item_id="unknown_review"`
**Expected:** Returns configured fallback model
**Priority:** High

#### TC-RR-005: Missing Settings Handling
**Component:** `src/review/router.py`
**Description:** Works with empty review_models config
**Input:** Settings without review_models key
**Expected:** Uses fallback for all items
**Priority:** Medium

### Prompt Builder Tests

#### TC-RP-001: Security Review Prompt
**Component:** `src/review/prompts.py`
**Description:** Builds security review prompt with context
**Input:** ReviewContext with diff and changed files
**Expected:** Prompt contains OWASP checklist and code
**Priority:** High

#### TC-RP-002: Architecture Review Prompt
**Component:** `src/review/prompts.py`
**Description:** Builds architecture prompt with related files
**Input:** ReviewContext with architecture docs
**Expected:** Prompt includes arch docs and related files
**Priority:** High

#### TC-RP-003: Context Injection
**Component:** `src/review/prompts.py`
**Description:** Injects all context sections
**Input:** Full ReviewContext
**Expected:** Prompt has git_diff, changed_files, related_files sections
**Priority:** High

### Result Parser Tests

#### TC-RP-101: Parse Security Findings
**Component:** `src/review/result.py`
**Description:** Extracts findings from security review output
**Input:** Model output with CRITICAL and MEDIUM findings
**Expected:** List of Finding objects with severity, description, location
**Priority:** High

#### TC-RP-102: Parse Architecture Assessment
**Component:** `src/review/result.py`
**Description:** Extracts assessment from architecture review
**Input:** Model output with "APPROVED_WITH_NOTES"
**Expected:** ReviewResult with status and findings list
**Priority:** High

#### TC-RP-103: Handle Malformed Output
**Component:** `src/review/result.py`
**Description:** Handles unexpected model output format
**Input:** Output that doesn't match expected format
**Expected:** Returns result with raw_output, success=True, findings=[]
**Priority:** Medium

#### TC-RP-104: Blocking Finding Detection
**Component:** `src/review/result.py`
**Description:** Identifies blocking vs advisory findings
**Input:** Mix of CRITICAL and INFO findings
**Expected:** `has_blocking_findings()` returns True
**Priority:** High

## Integration Tests

### TC-RI-001: OpenRouter Model Execution
**Component:** `src/review/router.py` + `src/providers/openrouter.py`
**Description:** Successfully calls OpenRouter with specified model
**Setup:** Valid OPENROUTER_API_KEY
**Input:** Simple prompt, model="openai/gpt-5.2-codex"
**Expected:** Returns ExecutionResult with model_used set
**Priority:** High

### TC-RI-002: Model Unavailable Fallback
**Component:** `src/review/router.py`
**Description:** Falls back when requested model unavailable
**Setup:** Invalid model ID
**Input:** model="nonexistent/model"
**Expected:** Falls back to configured fallback, logs warning
**Priority:** High

### TC-RI-003: Full Review Execution
**Component:** `src/review/*`
**Description:** End-to-end review with context collection
**Setup:** Git repo with changes
**Input:** `execute_review("security_review")`
**Expected:** Returns ReviewResult with findings
**Priority:** High

### TC-RI-004: Engine Integration
**Component:** `src/engine.py`
**Description:** Engine executes review via router
**Setup:** Workflow in REVIEW phase
**Input:** `complete_item("security_review")`
**Expected:** Review executed, result stored in item_state
**Priority:** High

## CLI Tests

### TC-CLI-001: Review Command - Single Item
**Component:** `src/cli.py`
**Description:** Run specific review via CLI
**Input:** `./orchestrator review security_review`
**Expected:** Executes security review, displays results
**Priority:** High

### TC-CLI-002: Review Command - All Items
**Component:** `src/cli.py`
**Description:** Run all pending reviews
**Input:** `./orchestrator review --all`
**Expected:** Executes all REVIEW phase items
**Priority:** High

### TC-CLI-003: Review Results Display
**Component:** `src/cli.py`
**Description:** Display stored review results
**Input:** `./orchestrator review-results`
**Expected:** Shows findings from completed reviews
**Priority:** Medium

### TC-CLI-004: Auto-Review Flag
**Component:** `src/cli.py`
**Description:** Handoff with auto-review
**Input:** `./orchestrator handoff --auto-review`
**Expected:** Generates handoff then executes reviews
**Priority:** High

### TC-CLI-005: Missing API Key Error
**Component:** `src/cli.py`
**Description:** Clear error when OpenRouter key missing
**Input:** Run review without OPENROUTER_API_KEY
**Expected:** Error with setup instructions
**Priority:** High

## Configuration Tests

### TC-CFG-001: Review Models Setting
**Component:** `workflow.yaml` + `src/schema.py`
**Description:** Load review_models from settings
**Input:** workflow.yaml with review_models dict
**Expected:** Settings accessible, models mapped correctly
**Priority:** High

### TC-CFG-002: Default Fallback Model
**Component:** `src/schema.py`
**Description:** Default fallback when not configured
**Input:** workflow.yaml without review_model_fallback
**Expected:** Uses `anthropic/claude-sonnet-4` as default
**Priority:** Medium

### TC-CFG-003: Context Limit Setting
**Component:** `src/review/context.py`
**Description:** Respects review_context_limit setting
**Input:** `review_context_limit: 50000`
**Expected:** Context truncated at 50K tokens
**Priority:** Medium

## Mock Definitions

### Mock: OpenRouter API

```python
class MockOpenRouterAPI:
    def __init__(self):
        self.calls = []

    def chat_completions(self, model: str, messages: list) -> dict:
        self.calls.append({"model": model, "messages": messages})

        if model == "openai/gpt-5.2-codex":
            return self._codex_response()
        elif model == "google/gemini-3-pro":
            return self._gemini_response()
        else:
            return self._fallback_response()

    def _codex_response(self):
        return {
            "choices": [{
                "message": {
                    "content": """### [SEVERITY: MEDIUM]
**Finding:** SQL query uses string concatenation
**Location:** src/db.py:45
**Evidence:** `query = "SELECT * FROM users WHERE id=" + user_id`
**Recommendation:** Use parameterized queries

No other security issues identified."""
                }
            }],
            "model": "openai/gpt-5.2-codex",
            "usage": {"total_tokens": 500}
        }

    def _gemini_response(self):
        return {
            "choices": [{
                "message": {
                    "content": """### Overall Assessment: APPROVED_WITH_NOTES

**Summary:** Changes follow existing patterns with minor suggestions.

**Findings:**
1. Consider extracting common logic into utility function

**Suggestions:**
- Add docstrings to new public methods"""
                }
            }],
            "model": "google/gemini-3-pro",
            "usage": {"total_tokens": 300}
        }
```

### Mock: Git Repository

```python
class MockGitRepo:
    def __init__(self, changed_files: dict[str, str]):
        self.changed_files = changed_files

    def diff(self, base="main") -> str:
        lines = []
        for path, content in self.changed_files.items():
            lines.append(f"diff --git a/{path} b/{path}")
            lines.append(f"+++ b/{path}")
            for line in content.split("\n"):
                lines.append(f"+{line}")
        return "\n".join(lines)

    def show(self, path: str) -> str:
        return self.changed_files.get(path, "")
```

## Coverage Requirements

- Minimum 80% code coverage for `src/review/` module
- 100% coverage for error handling paths
- All CLI commands must have tests
- Integration tests require OPENROUTER_API_KEY (skip in CI without key)
