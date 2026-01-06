# Implementation Plan: Visual Verification Integration

## Overview

Add AI-powered UAT testing to the workflow-orchestrator by integrating with the visual-verification-service. This enables automated functional and design review of UI changes using Claude's vision capabilities.

## Scope

### In Scope
1. Visual verification client module for orchestrator
2. Workflow settings for visual verification configuration
3. Test case template for visual UAT tests
4. Integration with `visual_regression_test` workflow step
5. Desktop + mobile screenshot capture
6. Hybrid evaluation (specific checks + open-ended questions)

### Out of Scope
- Deployment of visual-verification-service (user handles via Render)
- Pixel-perfect comparison testing
- Video recording of test sessions

## Implementation Components

### 1. Visual Verification Client (`src/visual_verification.py`)

New module to communicate with the visual-verification-service API:

```python
class VisualVerificationClient:
    def __init__(self, service_url: str, api_key: str):
        self.service_url = service_url
        self.api_key = api_key
    
    def verify(self, url: str, specification: str, 
               actions: list = None, viewports: list = None) -> VerificationResult:
        """Run visual verification against a URL."""
        pass
    
    def verify_with_style_guide(self, url: str, specification: str,
                                 style_guide_content: str) -> VerificationResult:
        """Run verification with style guide context included."""
        pass
```

### 2. Workflow Settings Updates (`workflow.yaml`)

Add new configurable settings:

```yaml
settings:
  # Visual verification settings
  visual_verification_url: "${VISUAL_VERIFICATION_URL}"
  visual_verification_api_key: "${VISUAL_VERIFICATION_API_KEY}"
  style_guide_path: "docs/UI_DESIGN_BRIEF.md"
  mobile_check_enabled: true
  visual_test_mode: "quick"  # "quick" or "full"
  
  # Viewport configurations
  desktop_viewport: { width: 1280, height: 720 }
  mobile_viewport: { width: 375, height: 812 }
```

### 3. Test Case Template (`templates/visual_test_template.md`)

Standard template for visual UAT tests:

```markdown
# Visual UAT Test: [Feature Name]

## Test URL
{{base_url}}/path/to/feature

## Pre-conditions
- User is logged in
- [Other setup requirements]

## Actions to Perform
1. Navigate to the page
2. [Action 2]
3. [Action 3]

## Specific Checks
- [ ] [Specific element] is visible
- [ ] [Specific functionality] works
- [ ] [Expected state] is achieved

## Open-Ended Evaluation (Mandatory)
1. Does this feature work as specified? Can the user complete the intended action?
2. Is the design consistent with our style guide?
3. Is the user journey intuitive? Would a first-time user understand what to do?
4. How does it handle edge cases (errors, empty states, unexpected input)?
5. Does it work well on mobile? Are there any responsive design issues?

## Open-Ended Evaluation (Optional)
- [ ] Accessibility: Are there any obvious accessibility concerns?
- [ ] Visual hierarchy: Does the layout guide the user appropriately?
- [ ] Performance: Do loading states feel responsive?
```

### 4. CLI Integration (`src/cli.py`)

Add commands for visual verification:

```bash
# Run visual verification manually
./orchestrator visual-verify --url "https://app.example.com/feature" --spec "tests/visual/feature.md"

# Run all visual tests
./orchestrator visual-verify-all

# Generate visual test template
./orchestrator visual-template "Feature Name" > tests/visual/feature.md
```

### 5. Engine Integration (`src/engine.py`)

Update the `visual_regression_test` step handler:

```python
def handle_visual_regression_test(self, item):
    # Load visual test files from tests/visual/
    # For each test:
    #   1. Load specification
    #   2. Include style guide if configured
    #   3. Run verification for desktop viewport
    #   4. Run verification for mobile viewport (if enabled)
    #   5. Aggregate results
    # Return pass/fail with detailed feedback
```

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `src/visual_verification.py` | Create | Visual verification client |
| `src/cli.py` | Modify | Add visual-verify commands |
| `src/engine.py` | Modify | Integrate visual verification into workflow |
| `examples/development_workflow.yaml` | Modify | Add visual verification settings |
| `templates/visual_test_template.md` | Create | Standard test template |
| `docs/VISUAL_VERIFICATION.md` | Create | Setup and usage documentation |

## Implementation Order

1. **Phase 1: Client Module**
   - Create `visual_verification.py` with API client
   - Add error handling and retry logic
   - Support both desktop and mobile viewports

2. **Phase 2: Workflow Integration**
   - Add settings to workflow.yaml schema
   - Update engine to handle visual_regression_test
   - Load and parse visual test files

3. **Phase 3: CLI Commands**
   - Add `visual-verify` command
   - Add `visual-template` command
   - Add `visual-verify-all` command

4. **Phase 4: Templates & Documentation**
   - Create test template
   - Write setup documentation
   - Add examples

## Claude Code Handoff Decision

**Decision: Use Claude Code for implementation**

Rationale:
- Multiple files need to be created/modified
- Integration with existing codebase requires understanding of patterns
- Testing requires running the actual code
- Not a trivial single-line change

## Dependencies

- `requests` library (already available)
- visual-verification-service deployed and accessible
- Environment variables: `VISUAL_VERIFICATION_URL`, `VISUAL_VERIFICATION_API_KEY`

## Success Criteria

1. ✅ Can run visual verification from CLI
2. ✅ Workflow automatically runs visual tests at `visual_regression_test` step
3. ✅ Both desktop and mobile viewports tested
4. ✅ Style guide content included in evaluation
5. ✅ Clear pass/fail output with detailed feedback
6. ✅ Test template is easy to use
7. ✅ Documentation is complete
