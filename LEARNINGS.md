# Learnings: Visual Verification Integration

## Task Summary
Added visual verification integration to the workflow orchestrator, connecting to the visual-verification-service for AI-powered UAT testing with hybrid specific checks and open-ended evaluation.

## Root Cause Analysis

### Why This Feature Was Needed
1. **Manual testing bottleneck** - Human review of UI changes is time-consuming and inconsistent
2. **Missing automated UAT** - Unit tests don't catch visual/UX issues
3. **Mobile responsiveness gaps** - Desktop-focused development often misses mobile issues
4. **Style guide drift** - No automated way to verify design consistency

### Why It Wasn't Built Earlier
1. **AI vision capabilities** - Required Claude's vision API which is relatively new
2. **Infrastructure dependency** - Needed the visual-verification-service deployed first
3. **Workflow integration complexity** - Required careful design of test case format and evaluation criteria

## What Was Built

### Components
1. **Visual Verification Client** (`src/visual_verification.py`)
   - HTTP client with retry logic and exponential backoff
   - Support for desktop (1280x720) and mobile (375x812) viewports
   - Style guide integration for design consistency checks

2. **CLI Commands**
   - `visual-verify` - Run verification against a URL
   - `visual-template` - Generate test case template

3. **Workflow Integration**
   - Settings for service URL, API key, style guide path
   - Mobile check toggle (default: enabled)
   - Quick vs full evaluation modes

4. **Documentation**
   - `docs/VISUAL_VERIFICATION.md` - Setup and usage guide
   - `templates/visual_test_template.md` - Test case template

### Test Coverage
- 19 unit tests covering all major functionality
- Integration tested against live service

## Code Review Findings

### Security Review (Score: 7/10)
- **Issues Found:**
  - No HTTPS enforcement on service URL
  - Missing input validation on URLs and parameters
  - Potential exception info leakage
- **Recommendations:**
  - Add URL validation and HTTPS check
  - Sanitize exception messages in production

### Architecture Review (Score: 7/10)
- **Strengths:**
  - Good separation of concerns
  - Clean API design with sensible defaults
  - Robust retry logic
- **Recommendations:**
  - Extract retry logic into reusable utility
  - Add dependency injection for HTTP client (testability)
  - Consider unifying verify and verify_with_style_guide methods

## Deployment Learnings

### Visual Verification Service Deployment Issues
We encountered several issues deploying to Render:

1. **Playwright system dependencies** - Render's Node environment lacks Chromium deps
   - **Solution:** Use Docker deployment with Playwright base image

2. **Docker COPY glob pattern** - BuildKit had issues with `package*.json`
   - **Solution:** Use explicit file names in COPY commands

3. **p-queue ESM/CommonJS incompatibility** - p-queue v7+ is ESM-only
   - **Solution:** Removed p-queue, implemented simple custom queue

4. **Playwright version mismatch** - npm installed newer version than Docker image
   - **Solution:** Pin Playwright to exact version matching Docker image

### Key Deployment Principle
> **Pin all dependencies to exact versions when using Docker with pre-built browser images.**

## Workflow Improvements Identified

### Already Implemented
1. ✅ Visual verification settings in workflow.yaml
2. ✅ CLI commands for visual testing
3. ✅ Test case template with mandatory open-ended questions
4. ✅ Mobile viewport testing by default

### Future Improvements
1. **Automatic test discovery** - Scan `tests/visual/` and run all tests
2. **Baseline management** - Store and compare against baseline screenshots
3. **CI/CD integration** - Run visual tests in GitHub Actions
4. **Cost tracking** - Monitor Claude API usage for visual tests

## Best Practices Established

### Visual Test Case Design
1. **Hybrid approach** - Combine specific checks with open-ended evaluation
2. **Mandatory questions** - Always evaluate: functional, design, UX, edge cases, mobile
3. **Style guide reference** - Always include design system in evaluation context
4. **Both viewports** - Test desktop AND mobile unless explicitly desktop-only

### Pass/Fail Criteria
- **No "pass with notes"** - All issues must be fixed
- **Fail fast** - Stop workflow on visual test failure
- **Clear reasoning** - AI must explain its evaluation

## Files Changed

### New Files
- `src/visual_verification.py` - Visual verification client
- `tests/test_visual_verification.py` - Unit tests
- `docs/VISUAL_VERIFICATION.md` - Documentation
- `templates/visual_test_template.md` - Test template

### Modified Files
- `src/cli.py` - Added visual-verify and visual-template commands
- `examples/development_workflow.yaml` - Added visual verification settings

## Recommendations for Future Tasks

1. **Always test Docker builds locally** before pushing to cloud providers
2. **Pin exact versions** for dependencies in containerized deployments
3. **Use ESM-compatible packages** or implement simple alternatives
4. **Include mobile testing** by default for any UI work
5. **Reference style guides** in all visual evaluations
