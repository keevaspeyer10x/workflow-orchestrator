# Test Cases: Visual Verification Integration

## Unit Tests

### TC-VV-001: VisualVerificationClient Initialization
**Component:** `visual_verification.py`
**Description:** Client initializes with service URL and API key
**Input:** `service_url="https://example.com"`, `api_key="test-key"`
**Expected:** Client object created with correct attributes
**Priority:** High

### TC-VV-002: Verify Request Formation
**Component:** `visual_verification.py`
**Description:** Verify method forms correct API request
**Input:** URL, specification, actions list
**Expected:** POST request to `/verify` with correct payload structure
**Priority:** High

### TC-VV-003: Desktop Viewport Configuration
**Component:** `visual_verification.py`
**Description:** Desktop viewport settings applied correctly
**Input:** `viewport={width: 1280, height: 720}`
**Expected:** Request includes correct viewport dimensions
**Priority:** Medium

### TC-VV-004: Mobile Viewport Configuration
**Component:** `visual_verification.py`
**Description:** Mobile viewport settings applied correctly
**Input:** `viewport={width: 375, height: 812}`
**Expected:** Request includes correct viewport dimensions
**Priority:** Medium

### TC-VV-005: Style Guide Inclusion
**Component:** `visual_verification.py`
**Description:** Style guide content appended to specification
**Input:** Specification + style guide content
**Expected:** Combined specification includes both
**Priority:** High

### TC-VV-006: API Error Handling
**Component:** `visual_verification.py`
**Description:** Handles API errors gracefully
**Input:** Service returns 500 error
**Expected:** Raises VisualVerificationError with details
**Priority:** High

### TC-VV-007: Retry Logic
**Component:** `visual_verification.py`
**Description:** Retries on transient failures
**Input:** Service fails twice, succeeds third time
**Expected:** Returns successful result after retries
**Priority:** Medium

### TC-VV-008: Timeout Handling
**Component:** `visual_verification.py`
**Description:** Handles request timeout
**Input:** Service doesn't respond within timeout
**Expected:** Raises TimeoutError with clear message
**Priority:** Medium

## Integration Tests

### TC-VV-101: Workflow Settings Loading
**Component:** `engine.py`
**Description:** Visual verification settings loaded from workflow.yaml
**Input:** workflow.yaml with visual_verification_url set
**Expected:** Settings accessible in engine
**Priority:** High

### TC-VV-102: Environment Variable Substitution
**Component:** `engine.py`
**Description:** ${VAR} syntax replaced with environment values
**Input:** `visual_verification_url: "${VISUAL_VERIFICATION_URL}"`
**Expected:** Actual URL from environment used
**Priority:** High

### TC-VV-103: Visual Test File Discovery
**Component:** `engine.py`
**Description:** Finds all .md files in tests/visual/
**Input:** Directory with 3 test files
**Expected:** All 3 files discovered and loaded
**Priority:** High

### TC-VV-104: Test Specification Parsing
**Component:** `engine.py`
**Description:** Parses test file into structured specification
**Input:** Test file with URL, actions, checks
**Expected:** Structured object with all fields
**Priority:** High

### TC-VV-105: Dual Viewport Execution
**Component:** `engine.py`
**Description:** Runs verification for both desktop and mobile
**Input:** Test with mobile_check_enabled: true
**Expected:** Two verification calls made
**Priority:** High

### TC-VV-106: Mobile Check Disabled
**Component:** `engine.py`
**Description:** Skips mobile when disabled
**Input:** Test with mobile_check_enabled: false
**Expected:** Only desktop verification called
**Priority:** Medium

### TC-VV-107: Result Aggregation
**Component:** `engine.py`
**Description:** Combines desktop and mobile results
**Input:** Desktop pass, mobile fail
**Expected:** Overall fail with both results detailed
**Priority:** High

## CLI Tests

### TC-VV-201: visual-verify Command
**Component:** `cli.py`
**Description:** Manual verification via CLI
**Input:** `./orchestrator visual-verify --url "..." --spec "..."`
**Expected:** Runs verification, outputs result
**Priority:** High

### TC-VV-202: visual-template Command
**Component:** `cli.py`
**Description:** Generate test template
**Input:** `./orchestrator visual-template "Login Flow"`
**Expected:** Outputs template with feature name filled in
**Priority:** Medium

### TC-VV-203: visual-verify-all Command
**Component:** `cli.py`
**Description:** Run all visual tests
**Input:** `./orchestrator visual-verify-all`
**Expected:** Discovers and runs all tests in tests/visual/
**Priority:** High

### TC-VV-204: Missing Service URL Error
**Component:** `cli.py`
**Description:** Clear error when service not configured
**Input:** Run without VISUAL_VERIFICATION_URL set
**Expected:** Error message with setup instructions
**Priority:** High

## End-to-End Tests

### TC-VV-301: Full Workflow with Visual Verification
**Component:** Full system
**Description:** Complete workflow including visual_regression_test step
**Setup:** 
- visual-verification-service running
- Test app deployed
- Visual test file created
**Steps:**
1. Start workflow
2. Complete PLAN, EXECUTE, REVIEW phases
3. Reach VERIFY phase
4. visual_regression_test step runs automatically
**Expected:** Visual verification executes, results displayed
**Priority:** High

### TC-VV-302: Skip Visual Verification
**Component:** Full system
**Description:** Can skip visual verification with reason
**Input:** `./orchestrator skip visual_regression_test --reason "Backend only change"`
**Expected:** Step skipped, reason logged
**Priority:** Medium

### TC-VV-303: Visual Test Failure Blocks Workflow
**Component:** Full system
**Description:** Failed visual test prevents advancement
**Setup:** Test that will fail (e.g., broken UI)
**Expected:** Workflow blocked at visual_regression_test, failure details shown
**Priority:** High

## Mock Definitions

### Mock: Visual Verification Service

```python
class MockVisualVerificationService:
    def __init__(self):
        self.calls = []
    
    def verify(self, request):
        self.calls.append(request)
        return {
            "success": True,
            "passed": True,
            "evaluation": {
                "functional": {"passed": True, "feedback": "Feature works as expected"},
                "design": {"passed": True, "feedback": "Consistent with style guide"},
                "ux": {"passed": True, "feedback": "Intuitive user journey"},
                "edge_cases": {"passed": True, "feedback": "Handles errors gracefully"},
                "mobile": {"passed": True, "feedback": "Responsive design works well"}
            },
            "screenshots": ["desktop.png", "mobile.png"]
        }
    
    def verify_failure(self, request):
        return {
            "success": True,
            "passed": False,
            "evaluation": {
                "functional": {"passed": False, "feedback": "Submit button not clickable"},
                "design": {"passed": True, "feedback": "Consistent with style guide"},
                "ux": {"passed": True, "feedback": "Intuitive user journey"},
                "edge_cases": {"passed": False, "feedback": "No error message on invalid input"},
                "mobile": {"passed": False, "feedback": "Form overflows on mobile"}
            },
            "screenshots": ["desktop.png", "mobile.png"]
        }
```

## Coverage Requirements

- Minimum 80% code coverage for new modules
- 100% coverage for error handling paths
- All CLI commands must have tests
