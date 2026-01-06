# Plan: Multi-Model Review Routing for REVIEW Phase

## Summary

Implement automatic AI code reviews optimized for **vibe coding** (AI-generated code with minimal human review). Reviews catch what coding agents miss: security issues, codebase inconsistencies, quality problems, and holistic concerns.

**Four Reviews:**
1. **Security Review** (Codex) - OWASP, vulnerabilities, auth issues
2. **Consistency Review** (Gemini) - Pattern compliance, existing utilities, codebase fit
3. **Quality Review** (Codex) - Edge cases, complexity, test coverage
4. **Holistic Review** (Gemini) - Open-ended "what did the AI miss?"

**Three Execution Modes:**
- **CLI Mode** (local): Codex CLI + Gemini CLI with full repo access
- **API Mode** (Claude Code Web): OpenRouter with context injection
- **GitHub Actions** (PR gate): Full repo access, blocks merge

## Problem Statement

AI coding agents have systematic blind spots:
- **Tunnel vision**: Solve problems in isolation, miss existing utilities
- **Pattern ignorance**: Don't follow established codebase conventions
- **Security naivety**: Introduce vulnerabilities without realizing
- **Happy path focus**: Miss edge cases and error handling

For vibe coding, these reviews are the **only safety net** before code ships.

## Architecture

### Review Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    Multi-Stage Review Pipeline                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  DURING DEVELOPMENT                                              │
│  ├── Local (Claude Code CLI)                                     │
│  │   └── Codex CLI + Gemini CLI (full repo access)              │
│  │                                                               │
│  └── Web (Claude Code Web)                                       │
│      └── OpenRouter API (context injection)                      │
│                                                                  │
│  ON PR CREATION (GitHub Actions)                                 │
│  ├── Security Review (Codex Action)                              │
│  ├── Consistency Review (Gemini Code Assist)                     │
│  ├── Quality Review (Codex Action)                               │
│  └── Holistic Review (Gemini Code Assist)                        │
│      └── BLOCKS MERGE until all pass                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Environment Auto-Detection

```python
def detect_review_method() -> str:
    """Detect best review method for current environment."""

    # Check for CLI tools (best experience)
    has_codex = shutil.which("codex")
    has_gemini = shutil.which("gemini")

    if has_codex and has_gemini:
        return "cli"

    # Check for API key (fallback)
    if os.environ.get("OPENROUTER_API_KEY"):
        return "api"

    raise ReviewConfigError(
        "No review method available. Either:\n"
        "  1. Install CLIs: npm install -g @openai/codex @google/gemini-cli\n"
        "  2. Set OPENROUTER_API_KEY for API mode"
    )
```

## The Four Reviews

### 1. Security Review (Codex)

```yaml
security_review:
  tool: codex  # or openrouter/openai-gpt-5.2-codex
  prompt: |
    Review this AI-generated code for security vulnerabilities.
    AI agents often introduce these issues without realizing:

    - Injection (SQL, command, XSS, template)
    - Authentication/authorization bypasses
    - Hardcoded secrets or credentials
    - SSRF, CSRF, path traversal
    - Insecure deserialization
    - Missing input validation

    This code has had ZERO human review. Be thorough.

    For each finding:
    ### [CRITICAL|HIGH|MEDIUM|LOW]
    **Issue:** <description>
    **Location:** <file:line>
    **Fix:** <recommendation>
```

### 2. Consistency Review (Gemini - 1M context)

```yaml
consistency_review:
  tool: gemini  # 1M token context = entire codebase
  prompt: |
    You have access to the ENTIRE codebase. Review if this new code:

    1. DUPLICATES existing utilities/helpers
       - List any existing code that does the same thing
       - "There's already src/utils/dates.ts for date formatting"

    2. FOLLOWS established patterns
       - Show examples of how similar problems are solved elsewhere
       - "Other API handlers use the errorHandler middleware"

    3. USES existing abstractions
       - Don't reinvent what already exists
       - "The BaseRepository class already handles this"

    4. MATCHES naming, structure, error handling conventions
       - "Other services use camelCase, this uses snake_case"

    AI agents solve problems in isolation. Find what they missed.
```

### 3. Quality Review (Codex)

```yaml
quality_review:
  tool: codex
  prompt: |
    Review this AI-generated code for production readiness:

    - Edge cases: What inputs weren't considered?
    - Error handling: What can fail? Is it handled?
    - Resource cleanup: File handles, connections closed?
    - Input validation: At system boundaries?
    - Complexity: Is there a simpler solution?
    - Tests: Are they meaningful? What's missing?

    AI agents often take the happy path. Find the unhappy paths.

    ### Quality Score: [1-10]
    **Issues:** (list with severity and location)
    **Missing Tests:** (what scenarios aren't covered)
```

### 4. Holistic Review (Gemini)

```yaml
holistic_review:
  tool: gemini
  prompt: |
    Review this AI-generated code with fresh eyes.

    The security, consistency, and quality reviews have run.
    What else concerns you?

    Consider:
    - Would a senior engineer approve this PR?
    - What questions would come up in code review?
    - What feels "off" even if you can't pinpoint why?
    - What would YOU do differently?
    - Any red flags the other reviews might have missed?

    Be the skeptical human reviewer this code hasn't had.
```

## Setup Command: `setup-reviews`

Bootstrap GitHub Actions in any repo:

```bash
# Set up review infrastructure in current repo
./orchestrator setup-reviews

# Options
./orchestrator setup-reviews --dry-run        # Preview changes
./orchestrator setup-reviews --provider all   # Default: all providers
./orchestrator setup-reviews --skip-actions   # Only config files, no Actions
```

### Generated Files

```
your-repo/
├── .github/
│   └── workflows/
│       └── ai-reviews.yml      ← Generated GitHub Actions workflow
├── .gemini/
│   └── styleguide.md           ← Gemini review instructions
├── AGENTS.md                    ← Codex review instructions
└── .coderabbit.yaml            ← CodeRabbit config (optional)
```

### Generated GitHub Actions Workflow

```yaml
# .github/workflows/ai-reviews.yml
name: AI Code Reviews

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  security-review:
    name: 🔒 Security Review
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Security Review
        uses: openai/codex-action@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          mode: review
          custom-instructions: |
            Focus on security vulnerabilities in AI-generated code.
            Check for: injection, auth issues, secrets, SSRF, path traversal.
            This code has had zero human review - be thorough.

  consistency-review:
    name: 🔄 Consistency Review
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Consistency Review
        uses: google/gemini-code-assist-action@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          # Uses .gemini/styleguide.md for instructions

  quality-review:
    name: ✨ Quality Review
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Quality Review
        uses: openai/codex-action@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          mode: review
          custom-instructions: |
            Focus on code quality and edge cases.
            Check for: error handling, input validation, complexity, test coverage.

  holistic-review:
    name: 🎯 Holistic Review
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Holistic Review
        uses: google/gemini-code-assist-action@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          custom-prompt: |
            Review this code with fresh eyes. What concerns you?
            What would a senior engineer ask about in code review?
```

## Workflow.yaml Settings

```yaml
settings:
  # Review configuration
  reviews:
    enabled: true
    on_by_default: true  # Reviews run automatically

    # Method selection
    method: auto  # auto | cli | api | github-actions

    # GitHub Actions configuration
    github_actions:
      configured: false  # Auto-detected
      required_for_merge: true  # Block merge if reviews fail

    # Fallback when CLI/Actions unavailable
    fallback_to_api: true

    # Prompt to set up if missing
    prompt_setup_if_missing: true

    # Review types to run
    types:
      - security_review
      - consistency_review
      - quality_review
      - holistic_review
```

## CLI Commands

```bash
# Setup reviews in a new repo
./orchestrator setup-reviews
./orchestrator setup-reviews --dry-run

# Check review infrastructure status
./orchestrator review-status
# Output:
#   CLI Tools:    ✓ codex, ✓ gemini
#   API Key:      ✓ OPENROUTER_API_KEY
#   GitHub Actions: ✗ Not configured (run setup-reviews)

# Run reviews manually
./orchestrator review                    # All reviews
./orchestrator review security           # Specific review
./orchestrator review --method cli       # Force CLI mode
./orchestrator review --method api       # Force API mode

# View results
./orchestrator review-results
./orchestrator review-results --json

# Skip reviews (requires justification)
./orchestrator advance --skip-reviews --reason "Emergency hotfix"
```

## Auto-Detection Flow

```python
def on_entering_review_phase():
    """Called when workflow advances to REVIEW phase."""

    # 1. Check what's available
    setup = check_review_setup()

    # 2. Determine method
    if setup.cli_available:
        method = "cli"
    elif setup.api_available:
        method = "api"
        print("⚠️  Using API mode (reduced context). Consider installing CLIs.")
    else:
        raise ReviewConfigError("No review method available")

    # 3. Check GitHub Actions for PR gate
    if not setup.github_actions_configured:
        print("⚠️  GitHub Actions not configured for this repo.")
        print("   Reviews will run locally but won't block PRs.")
        print("   Run: ./orchestrator setup-reviews")

    # 4. Execute reviews
    for review_type in ["security", "consistency", "quality", "holistic"]:
        execute_review(review_type, method)
```

## Implementation Steps

### Phase 1: Core Review Module
1. Create `src/review/` module structure
2. Implement `ReviewContextCollector` for API mode
3. Implement `ReviewRouter` with method detection
4. Create prompt templates for all 4 reviews
5. Implement result parsing

### Phase 2: CLI Integration
6. Add `review` command
7. Add `review-status` command
8. Add `review-results` command
9. Integrate with `advance` command

### Phase 3: Setup Command
10. Implement `setup-reviews` command
11. Generate GitHub Actions workflow file
12. Generate `.gemini/styleguide.md`
13. Generate `AGENTS.md`
14. Auto-detection of existing setup

### Phase 4: Testing
15. Unit tests for each component
16. Integration tests with mock CLIs
17. End-to-end test with real APIs (optional, requires keys)

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `src/review/__init__.py` | Create | Module exports |
| `src/review/context.py` | Create | Context collector for API mode |
| `src/review/router.py` | Create | Method detection and routing |
| `src/review/prompts.py` | Create | All 4 review prompts |
| `src/review/result.py` | Create | Result parsing and storage |
| `src/review/setup.py` | Create | `setup-reviews` implementation |
| `src/review/cli_executor.py` | Create | Execute via Codex/Gemini CLI |
| `src/review/api_executor.py` | Create | Execute via OpenRouter API |
| `src/cli.py` | Modify | Add review commands |
| `src/engine.py` | Modify | Integrate with REVIEW phase |
| `workflow.yaml` | Modify | Add review settings |
| `templates/ai-reviews.yml` | Create | GitHub Actions template |
| `templates/gemini-styleguide.md` | Create | Gemini config template |
| `templates/AGENTS.md` | Create | Codex config template |
| `tests/test_review_*.py` | Create | Test suite |

## Success Criteria

1. ✅ Four reviews run with appropriate tools (Codex/Gemini)
2. ✅ CLI mode works with full repo access
3. ✅ API mode works in Claude Code Web
4. ✅ `setup-reviews` bootstraps GitHub Actions in any repo
5. ✅ GitHub Actions block PR merge until reviews pass
6. ✅ Reviews are on by default, skip requires justification
7. ✅ Auto-detection chooses best available method
8. ✅ Clear status output shows what's configured

## Out of Scope (Future)

- Real-time streaming of review output
- Review result caching (same diff = reuse review)
- Custom prompts per project (beyond styleguide files)
- Review aggregation dashboard
- Automatic fix suggestions/application
