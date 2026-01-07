# Test Cases: Aider Review Provider Integration

## Unit Tests

### AiderExecutor Tests

#### TC-AID-001: Execute Review Success
**Component:** `src/review/aider_executor.py`
**Description:** Execute review with Aider returns successful ReviewResult
**Setup:** Mock subprocess to return review output
**Input:** `review_type="security"`
**Expected:** ReviewResult with success=True, model contains "gemini"
**Assertions:**
- result.success is True
- result.method_used == "aider"
- "gemini" in result.model_used.lower()
- result.raw_output is not empty

#### TC-AID-002: Execute Review Timeout
**Component:** `src/review/aider_executor.py`
**Description:** Handle timeout when Aider takes too long
**Setup:** Mock subprocess to raise TimeoutExpired
**Input:** `review_type="holistic"`
**Expected:** ReviewResult with success=False, error mentions timeout
**Assertions:**
- result.success is False
- "timeout" in result.error.lower()

#### TC-AID-003: Execute Review Command Not Found
**Component:** `src/review/aider_executor.py`
**Description:** Handle missing aider command gracefully
**Setup:** Mock subprocess to raise FileNotFoundError
**Input:** `review_type="quality"`
**Expected:** ReviewResult with success=False, helpful error message
**Assertions:**
- result.success is False
- "aider" in result.error.lower() or "install" in result.error.lower()

#### TC-AID-004: Execute Review Parse Output
**Component:** `src/review/aider_executor.py`
**Description:** Parse Aider output into findings
**Setup:** Mock subprocess with structured review output
**Input:** `review_type="consistency"`
**Expected:** ReviewResult with parsed findings
**Assertions:**
- result.findings is not None
- len(result.findings) > 0 or result.raw_output is not empty

### ReviewSetup Tests

#### TC-AID-005: Check Aider Available
**Component:** `src/review/setup.py`
**Description:** Detect when aider is installed
**Setup:** Mock shutil.which to return path
**Expected:** ReviewSetup.aider_cli is True
**Assertions:**
- setup.aider_cli is True

#### TC-AID-006: Check Aider Not Available
**Component:** `src/review/setup.py`
**Description:** Detect when aider is not installed
**Setup:** Mock shutil.which to return None
**Expected:** ReviewSetup.aider_cli is False
**Assertions:**
- setup.aider_cli is False

### ReviewRouter Tests

#### TC-AID-007: Route to Aider When Available
**Component:** `src/review/router.py`
**Description:** Router selects aider method when available
**Setup:** ReviewSetup with aider_cli=True, openrouter_key=True
**Input:** `method="aider"`
**Expected:** Router uses AIDER method
**Assertions:**
- router.method == ReviewMethod.AIDER

#### TC-AID-008: Fallback When Aider Unavailable
**Component:** `src/review/router.py`
**Description:** Router falls back to API when aider unavailable
**Setup:** ReviewSetup with aider_cli=False, openrouter_key=True
**Input:** `method="auto"`
**Expected:** Router uses API method
**Assertions:**
- router.method == ReviewMethod.API

#### TC-AID-009: Status Message Shows Aider
**Component:** `src/review/router.py`
**Description:** Status message includes aider availability
**Setup:** ReviewSetup with aider_cli=True
**Expected:** Status message contains "aider"
**Assertions:**
- "aider" in router.get_status_message().lower()

## Integration Tests

#### TC-AID-010: End-to-End Review with Aider
**Component:** Full review pipeline
**Description:** Complete review flow using Aider
**Setup:** Real aider installation, OPENROUTER_API_KEY set
**Input:** Run `orchestrator review --method aider`
**Expected:** Review completes with Gemini output
**Assertions:**
- Exit code 0
- Output contains review findings
- Model mentions gemini

## Test Implementation Priority

1. TC-AID-001, TC-AID-002, TC-AID-003 - Core executor tests
2. TC-AID-005, TC-AID-006 - Setup detection
3. TC-AID-007, TC-AID-008 - Router integration
4. TC-AID-009 - Status display
5. TC-AID-010 - End-to-end (manual/CI)
