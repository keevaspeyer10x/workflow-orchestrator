# Implementation Plan: Aider Review Provider

## Overview

Integrate Aider as an invisible review provider, enabling Gemini reviews with full repo context. Aider uses a "repo map" that efficiently provides codebase awareness to LLMs.

## Architecture

```
orchestrator review
       │
       ▼
  ReviewRouter
       │
       ├─► CLI Executor (codex, gemini) - Gemini blocked in Claude Code Web
       ├─► API Executor (openrouter) - Limited context
       └─► Aider Executor (NEW) - Full repo context via repo map
```

## Implementation Steps

### 1. Install aider-chat dependency
- Add to requirements.txt or install via pip
- Update session-start.sh to ensure aider is available

### 2. Create Aider Executor (`src/review/aider_executor.py`)
```python
class AiderExecutor:
    def execute(self, review_type: str) -> ReviewResult:
        # Run: aider --model openrouter/google/gemini-2.0-flash-001 --message "review prompt"
        # Aider automatically builds repo map for context
        # Parse output to ReviewResult
```

### 3. Update Review Router
- Add `AIDER = "aider"` to ReviewMethod enum
- Add aider availability check to ReviewSetup
- Route to AiderExecutor when method is "aider"
- Make aider preferred for Gemini reviews when available

### 4. Update setup.py checks
- Add `aider_available: bool` to ReviewSetup dataclass
- Check for `aider` command availability

### 5. Configuration
- Allow specifying aider models in workflow.yaml or config
- Default: `openrouter/google/gemini-2.0-flash-001`
- Alternative: `openrouter/google/gemini-2.5-pro-preview-06-05`

## Files to Modify/Create

| File | Action |
|------|--------|
| `src/review/aider_executor.py` | CREATE - New executor |
| `src/review/router.py` | MODIFY - Add AIDER method |
| `src/review/setup.py` | MODIFY - Add aider check |
| `src/review/__init__.py` | MODIFY - Export AiderExecutor |
| `requirements.txt` | MODIFY - Add aider-chat |
| `install.sh` | MODIFY - Add pip install aider-chat |
| `.claude/hooks/session-start.sh` | MODIFY - Auto-install aider if missing |
| `docs/SETUP_GUIDE.md` | MODIFY - Document Aider as review provider |
| `tests/test_review_aider.py` | CREATE - Tests |

## User Experience

```bash
# User sees this (unchanged)
orchestrator review

# Behind the scenes, if aider available + openrouter key:
# → AiderExecutor runs Gemini with full repo context

# Status shows:
Review Infrastructure Status:
  CLI Tools:      ✓ codex, ✗ gemini (blocked)
  Aider:          ✓ aider (gemini via openrouter)
  API Key:        ✓ OPENROUTER_API_KEY
```

## Aider Command

```bash
aider \
  --model openrouter/google/gemini-2.0-flash-001 \
  --no-auto-commits \
  --no-git \
  --message "Review prompt here" \
  2>&1
```

Key flags:
- `--no-auto-commits` - Don't create commits (review only)
- `--no-git` - Don't interact with git
- `--message` - Non-interactive mode with prompt

## Success Criteria

1. `orchestrator review` works with Gemini via Aider
2. User doesn't know Aider is being used (invisible)
3. Gemini gets full repo context (via repo map)
4. Falls back to OpenRouter API if Aider unavailable
5. Tests pass
