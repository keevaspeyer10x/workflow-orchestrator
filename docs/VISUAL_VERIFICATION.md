# Visual Verification Integration

The workflow orchestrator integrates with the visual-verification-service to provide AI-powered UAT (User Acceptance Testing) during the VERIFY phase.

## Overview

Visual verification uses Claude's vision capabilities to evaluate your UI against:
- **Specific checks**: Explicit requirements (element visible, button works, etc.)
- **Open-ended evaluation**: Qualitative assessment (design consistency, user journey, edge cases)
- **Style guide compliance**: Automatic comparison against your design system

## Setup

### 1. Deploy the Visual Verification Service

Deploy the [visual-verification-service](https://github.com/your-org/visual-verification-service) to a hosting provider (e.g., Render, Railway, AWS).

### 2. Set Environment Variables

```bash
export VISUAL_VERIFICATION_URL="https://your-service.onrender.com"
export VISUAL_VERIFICATION_API_KEY="your-api-key"
```

### 3. Configure the Workflow

In your `workflow.yaml`, configure the visual verification settings:

```yaml
settings:
  # Visual verification settings
  visual_verification_url: "${VISUAL_VERIFICATION_URL}"
  visual_verification_api_key: "${VISUAL_VERIFICATION_API_KEY}"
  
  # Path to your style guide (relative to project root)
  style_guide_path: "docs/UI_DESIGN_BRIEF.md"
  
  # Enable mobile testing (default: true)
  mobile_check_enabled: true
  
  # Test mode: "quick" or "full"
  visual_test_mode: "quick"
```

## Usage

### CLI Commands

#### Run Visual Verification

```bash
# Verify a URL with inline specification
./orchestrator visual-verify --url "https://your-app.com/feature" \
  --spec "Verify the login form has email and password fields and a submit button"

# Verify with a specification file
./orchestrator visual-verify --url "https://your-app.com/feature" \
  --spec tests/visual/login_flow.md

# Include style guide
./orchestrator visual-verify --url "https://your-app.com/feature" \
  --spec tests/visual/login_flow.md \
  --style-guide docs/UI_DESIGN_BRIEF.md

# Desktop only (skip mobile)
./orchestrator visual-verify --url "https://your-app.com/feature" \
  --spec "Verify the dashboard loads" \
  --no-mobile
```

#### Generate Test Template

```bash
./orchestrator visual-template "User Login Flow"
```

This outputs a template you can save to `tests/visual/user_login_flow.md`.

### During Workflow

Visual verification runs automatically during the `visual_regression_test` step in the VERIFY phase. It will:

1. Find all test files in `tests/visual/`
2. For each test file:
   - Parse the URL and specification
   - Run desktop verification (1280x720)
   - Run mobile verification (375x812) if enabled
   - Include style guide in evaluation if configured
3. Report pass/fail with detailed reasoning

## Test File Format

Create test files in `tests/visual/` with this format:

```markdown
# Visual UAT Test: Feature Name

## Test URL
https://your-app.com/feature

## Pre-conditions
- User is logged in
- [Other setup requirements]

## Specific Checks
- [ ] Login button is visible
- [ ] Form validates email format
- [ ] Error message appears for invalid credentials

## Open-Ended Evaluation (Mandatory)
1. Does this feature work as specified?
2. Is the design consistent with our style guide?
3. Is the user journey intuitive?
4. How does it handle edge cases?
5. Does it work well on mobile?
```

## Viewports

| Viewport | Dimensions | Use Case |
|----------|------------|----------|
| Desktop | 1280x720 | Standard desktop browser |
| Mobile | 375x812 | iPhone 14 Pro (portrait) |

## Pass/Fail Criteria

- **Pass**: No issues identified
- **Fail**: Any issues identified (must be fixed before proceeding)

There is no "pass with notes" - all issues must be addressed. This ensures quality is maintained.

## Best Practices

1. **Write specific checks for critical functionality** - These are fast and cheap to verify
2. **Use open-ended questions for qualitative assessment** - Let the AI catch issues you might miss
3. **Always include mobile testing** - Mobile is often where UI issues appear
4. **Reference your style guide** - Ensures consistency across features
5. **Test edge cases explicitly** - Empty states, errors, loading states
6. **Keep test files focused** - One file per feature or user flow

## Troubleshooting

### Service Not Responding

```bash
# Check service health
curl -X GET "https://your-service.onrender.com/health" \
  -H "X-API-Key: your-api-key"
```

### Verification Timeout

The service has a default timeout of 60 seconds. For complex pages:
- Ensure the page loads quickly
- Consider breaking into smaller test cases
- Check if the service needs more resources

### Mobile Test Failing

Common mobile issues:
- Touch targets too small (< 44px)
- Text too small to read
- Horizontal overflow causing scroll
- Fixed elements covering content
- Forms not optimized for mobile keyboards
